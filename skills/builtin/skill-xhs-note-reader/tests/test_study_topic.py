"""Tests for study_topic.py (issue 84): one topic study that saves whole image sets from the top posts.

Everything outside the step is a stand-in (the guarded search, the guarded reads and file downloads), or the real guard
script wired to stand-in programs, so no test reaches Xiaohongshu or its file servers.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import textwrap
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
GUARD = HERE.parents[1] / "skill-xhs-analyzer" / "scripts" / "redbook-guard.sh"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rn = _load("read_note")
st = _load("study_topic")

KEYWORD = "燕麦怎么选"
DATE = "2026-10-29"
SECRETS = (b"xsec_token", b"tok-secret", b"user-secret-token")

# id: (likes as the search shows them, favourites, type, images in the set)
# By likes alone the top five would include p1 and leave out p5; by likes plus favourites it is the other way round.
POSTS = {
    "p1": ("700", "0", "normal", 3),       # 700
    "p2": ("900", "10", "normal", 4),      # 910
    "p3": ("1.2万", "300", "normal", 2),    # 12000 + 300 = 12300
    "p4": ("40", "20", "normal", 3),       # 60
    "p5": ("300", "700", "normal", 5),     # 1000
    "p6": ("500", "450", "normal", 3),     # 950
    "p7": ("20", "5", "normal", 2),        # 25
    "p8": ("600", "200", "normal", 4),     # 800
}
TOP_FIVE = ["p3", "p5", "p6", "p2", "p8"]   # by likes plus favourites, highest first
SUMS = {"p3": 12300, "p5": 1000, "p6": 950, "p2": 910, "p8": 800}


def address(pid: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{pid}?xsec_token=tok-secret-{pid}&xsec_source=pc_search"


def search_answer(posts: dict | None = None) -> dict:
    items = [{"id": "q0", "query": "燕麦蛋白怎么选"}]   # the search also returns query suggestions
    for pid, (likes, favs, kind, _count) in (posts or POSTS).items():
        items.append({"id": pid, "webUrl": address(pid), "note_card": {
            "type": kind, "display_title": f"标题-{pid}", "user": {"nickname": f"作者-{pid}"},
            "interact_info": {"liked_count": likes, "collected_count": favs}}})
    return {"items": items}


def read_answer(pid: str, posts: dict | None = None) -> dict:
    likes, favs, kind, count = (posts or POSTS)[pid]
    return {
        "note_id": pid, "type": kind, "title": f"标题-{pid}", "desc": "正文",
        "interact_info": {"liked_count": likes, "collected_count": favs},
        "user": {"user_id": "u1", "nickname": f"作者-{pid}", "xsec_token": "user-secret-token"},
        "image_list": [{"url": f"http://sns-webpic-qc.xhscdn.com/{pid}/raw{i}", "url_default": f"http://sns-webpic-qc.xhscdn.com/{pid}/img{i}!nd"}
                       for i in range(1, count + 1)],
        "webUrl": address(pid),
    }


def write_png(dest, shade: int) -> None:
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 60), (shade, 0, 0)).save(dest, "PNG")


def shade_of(url: str) -> int:
    return int(re.search(r"img(\d+)", url).group(1)) * 20 + 10


class Calls:
    def __init__(self):
        self.searches: list = []
        self.reads: list = []        # the note ids asked for, in order
        self.downloads: list = []    # the addresses fetched, in order
        self.ocr: list = []
        self.diandian: list = []


def make_deps(posts=None, *, fail_read_at=None, fail_download=None, fail_search=None):
    """fail_read_at: {n: exception} raised on the n-th read of this run. fail_download: {url fragment: exception}."""
    calls = Calls()
    fail_read_at = fail_read_at or {}
    fail_download = fail_download or {}

    def search(keyword):
        calls.searches.append(keyword)
        if fail_search:
            raise fail_search
        return search_answer(posts)

    def read(link):
        pid = re.search(r"/explore/([A-Za-z0-9_-]+)", link).group(1)
        calls.reads.append(pid)
        if len(calls.reads) in fail_read_at:
            raise fail_read_at[len(calls.reads)]
        return read_answer(pid, posts)

    def download(url, dest):
        calls.downloads.append(url)
        for fragment, error in fail_download.items():
            if fragment in url:
                raise error
        write_png(dest, shade_of(url))

    def ocr(path):
        calls.ocr.append(str(path))
        return "never asked for"

    def diandian(address_, dest):
        calls.diandian.append(address_)
        return 0

    note = rn.Deps(read=read, download=download, ocr=ocr, video_duration=lambda v: 1.0, grab_frame=lambda *a: None,
                   scene_times=lambda v: [], contact_sheet=lambda *a: None,
                   transcribe=lambda v, s: {"text": "", "partial": False, "segments": []}, diandian=diandian)
    return st.StudyDeps(search=search, note=note), calls


def folders(tmp_path):
    return tmp_path / "对标笔记库" / "image-sets", tmp_path / "对标笔记库" / "research" / f"{DATE}-{KEYWORD}"


def study(tmp_path, deps, n=5, keyword=KEYWORD):
    image_sets, study_dir = folders(tmp_path)
    return st.run_study(keyword, n, deps, image_sets=image_sets, study_dir=study_dir, date=DATE)


def set_name(n: int, pid: str) -> str:
    return f"{DATE}-{KEYWORD}-{n}-标题-{pid}"


def write_summary(tmp_path, names) -> Path:
    _, study_dir = folders(tmp_path)
    path = study_dir / "summary.md"
    path.write_text("# 小结\n\n" + "\n".join(f"- {name}：怎么做的" for name in names) + "\n\n共同点：……\n", encoding="utf-8")
    return path


# --- seam 1: the top five by likes plus favourites, every image, in post order --------------------------

def test_a_study_of_eight_posts_with_n_5_saves_the_top_five_by_likes_plus_favourites_every_image_in_post_order(tmp_path):
    deps, calls = make_deps()
    result = study(tmp_path, deps)
    image_sets, _ = folders(tmp_path)

    assert calls.searches == [KEYWORD]                    # one search
    assert calls.reads == TOP_FIVE                        # the five by likes plus favourites, in that order, no other post
    expected = [set_name(i, pid) for i, pid in enumerate(TOP_FIVE, start=1)]
    assert sorted(p.name for p in image_sets.iterdir()) == sorted(expected)   # one folder per set, nothing else there
    for i, pid in enumerate(TOP_FIVE, start=1):
        count = POSTS[pid][3]
        folder = image_sets / set_name(i, pid)
        assert sorted(p.name for p in folder.glob("[0-9][0-9].jpg")) == [f"{k:02d}.jpg" for k in range(1, count + 1)]
        # post order: image k is the k-th image the read listed
        assert [Image.open(folder / f"{k:02d}.jpg").getpixel((0, 0))[0] for k in range(1, count + 1)] == [k * 20 + 10 for k in range(1, count + 1)]
    assert [s["folder"] for s in result["sets"]] == expected
    assert result["reads_used"] == 6                      # one search and five reads


def test_the_set_carries_a_contact_sheet_and_a_record_naming_the_post(tmp_path):
    deps, _ = make_deps()
    study(tmp_path, deps)
    folder = folders(tmp_path)[0] / set_name(2, "p5")
    with Image.open(folder / "contact-sheet.jpg") as sheet:
        assert sheet.width >= 5 * 100                      # one thumbnail per image, side by side
    record = (folder / "record.md").read_text(encoding="utf-8")
    for must in ("标题-p5", "作者-p5", "300", "700", "1000", "5", "https://www.xiaohongshu.com/explore/p5"):
        assert must in record
    assert "xsec_token" not in record


def test_n_is_a_parameter(tmp_path):
    deps, calls = make_deps()
    result = study(tmp_path, deps, n=3)
    assert calls.reads == TOP_FIVE[:3] and len(result["sets"]) == 3


def test_ranking_uses_the_post_scorers_formula_not_a_second_copy(tmp_path, monkeypatch):
    # If the study had its own copy of the formula, changing the scorer's would change nothing.
    monkeypatch.setattr(st.score, "engagement", lambda post: post["favourites"])
    deps, calls = make_deps()
    study(tmp_path, deps, n=2)
    assert calls.reads == ["p5", "p6"]                    # favourites only: 700 then 450


def test_counts_written_with_wan_are_read_as_numbers():
    assert st.parse_count("1.2万") == 12000
    assert st.parse_count("987") == 987
    assert st.parse_count(None) == 0 and st.parse_count("") == 0 and st.parse_count("赞") == 0


def test_text_in_images_and_the_summary_chat_are_not_asked_for(tmp_path):
    deps, calls = make_deps()
    study(tmp_path, deps)
    assert len(calls.reads) == 5                          # the study did read the posts ...
    assert calls.ocr == [] and calls.diandian == []       # ... and asked for nothing beyond the images


# --- seam 1b: every download goes through the guard's file-download step ------------------------------------

def _executable(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("flock") is None, reason="the guard needs bash and flock")
def test_every_download_goes_through_the_guards_file_download_step_and_leaves_one_call_log_line(tmp_path, monkeypatch):
    stand_in = tmp_path / "stand-in"
    (stand_in / "notes").mkdir(parents=True)
    (stand_in / "search.json").write_text(json.dumps(search_answer()), encoding="utf-8")
    for pid in POSTS:
        (stand_in / "notes" / f"{pid}.json").write_text(json.dumps(read_answer(pid)), encoding="utf-8")
    write_png(stand_in / "file.png", 90)
    real = _executable(tmp_path / "real-redbook", textwrap.dedent(f'''\
        #!{sys.executable}
        import os, sys
        d = os.environ["STAND_IN"]
        if sys.argv[1] == "search":
            sys.stdout.write(open(d + "/search.json", encoding="utf-8").read())
        else:
            pid = sys.argv[2].split("/explore/")[1].split("?")[0]
            sys.stdout.write(open(d + "/notes/" + pid + ".json", encoding="utf-8").read())
        '''))
    cookie = _executable(tmp_path / "cookie", "#!/bin/sh\necho 'a1=stand-in'\n")
    download = _executable(tmp_path / "download", '#!/bin/sh\ncp "$STAND_IN/file.png" "$2"\n')
    state = tmp_path / "guard-state"
    for key, value in {"STAND_IN": str(stand_in), "REDBOOK_REAL_BIN": str(real), "REDBOOK_COOKIE_HELPER": str(cookie),
                       "REDBOOK_DOWNLOAD_CMD": str(download), "REDBOOK_GUARD_STATE_DIR": str(state), "REDBOOK_MIN_GAP_SEC": "0"}.items():
        monkeypatch.setenv(key, value)

    deps = st.default_deps(redbook=["bash", str(GUARD)])
    result = study(tmp_path, deps)

    log = (state / "calls.log").read_text(encoding="utf-8").splitlines()
    total_images = sum(POSTS[pid][3] for pid in TOP_FIVE)
    assert sum(1 for line in log if line.endswith(" ok fetch-file")) == total_images
    assert sum(1 for line in log if line.endswith(" ok search")) == 1
    assert sum(1 for line in log if line.endswith(" ok read")) == 5
    assert [s["folder"] for s in result["sets"]] == [set_name(i, pid) for i, pid in enumerate(TOP_FIVE, start=1)]
    assert result["problems"] == []


# --- seam 2: the post-run check ---------------------------------------------------------------------------------

def _damage_missing(path):
    path.unlink()


def _damage_empty(path):
    path.write_bytes(b"")


def _damage_not_an_image(path):
    path.write_bytes(b"this is not a picture")


@pytest.mark.parametrize("damage, word", [(_damage_missing, "missing"), (_damage_empty, "empty"), (_damage_not_an_image, "open")])
def test_the_post_run_check_fails_the_run_naming_the_set_and_the_image(tmp_path, damage, word):
    deps, _ = make_deps()
    assert study(tmp_path, deps)["problems"] == []
    image_sets, study_dir = folders(tmp_path)
    damage(image_sets / set_name(3, "p6") / "02.jpg")

    again_deps, calls = make_deps()
    result = study(tmp_path, again_deps)

    assert result["status"] == "failed"
    assert len(result["problems"]) == 1
    problem = result["problems"][0]
    assert problem["set"] == set_name(3, "p6") and problem["image"] == "02.jpg" and word in problem["problem"]
    index = (study_dir / "index.md").read_text(encoding="utf-8")
    assert set_name(3, "p6") in index and "02.jpg" in index
    assert calls.searches == [] and calls.reads == []     # the check reads files, it does not go back to the platform


def test_a_set_with_fewer_images_than_its_read_listed_fails_the_run(tmp_path):
    deps, _ = make_deps(fail_download={"/p5/img3!": RuntimeError("the download exited 1")})
    result = study(tmp_path, deps)
    assert result["status"] == "failed"
    assert [(p["set"], p["image"]) for p in result["problems"]] == [(set_name(2, "p5"), "03.jpg")]


def test_a_set_that_came_out_short_is_read_again_on_a_rerun_and_no_other_post_is(tmp_path):
    deps, _ = make_deps(fail_download={"/p5/img3!": RuntimeError("the download exited 1")})
    study(tmp_path, deps)
    again, calls = make_deps()
    result = study(tmp_path, again)
    assert calls.searches == [] and calls.reads == ["p5"]
    assert result["problems"] == [] and result["status"] == "incomplete"   # only the summary is still owed
    assert len(list((folders(tmp_path)[0] / set_name(2, "p5")).glob("[0-9][0-9].jpg"))) == 5


# --- seam 3: the index, and the summary the study is not complete without ------------------------------------

def test_the_index_lists_topic_keyword_date_reads_used_and_every_set_with_likes_favourites_and_their_sum(tmp_path):
    deps, _ = make_deps()
    study(tmp_path, deps)
    text = (folders(tmp_path)[1] / "index.md").read_text(encoding="utf-8")
    for must in (KEYWORD, DATE, "6"):
        assert must in text
    for i, pid in enumerate(TOP_FIVE, start=1):
        likes = st.parse_count(POSTS[pid][0])
        favs = st.parse_count(POSTS[pid][1])
        row = next(line for line in text.splitlines() if set_name(i, pid) in line)
        for number in (likes, favs, SUMS[pid], POSTS[pid][3]):
            assert str(number) in row


def test_the_study_is_incomplete_while_the_summary_is_missing(tmp_path):
    deps, _ = make_deps()
    result = study(tmp_path, deps)
    assert len(result["sets"]) == 5                       # five sets saved, and still not finished
    assert result["status"] == "incomplete" and result["summary"]["missing"] is True


def test_the_study_is_incomplete_while_the_summary_leaves_out_a_saved_set(tmp_path):
    deps, _ = make_deps()
    study(tmp_path, deps)
    names = [set_name(i, pid) for i, pid in enumerate(TOP_FIVE, start=1)]
    write_summary(tmp_path, names[:4])
    again, calls = make_deps()
    result = study(tmp_path, again)
    assert result["status"] == "incomplete"
    assert result["summary"]["missing"] is False and result["summary"]["not_named"] == [names[4]]
    assert calls.searches == [] and calls.reads == []


def test_the_study_is_complete_once_the_summary_names_every_saved_set(tmp_path):
    deps, _ = make_deps()
    study(tmp_path, deps)
    write_summary(tmp_path, [set_name(i, pid) for i, pid in enumerate(TOP_FIVE, start=1)])
    again, _ = make_deps()
    result = study(tmp_path, again)
    assert result["status"] == "complete" and result["summary"]["not_named"] == []


# --- seam 4: stops, reruns, video posts -----------------------------------------------------------------------------

@pytest.mark.parametrize("code, words", [
    (65, "daily cap"), (66, "tripped"), (70, "no login"), (71, "using the account"),
])
def test_a_guard_stop_mid_study_stops_at_once_keeps_the_saved_sets_and_says_where_and_why(tmp_path, code, words):
    deps, calls = make_deps(fail_read_at={3: rn.ReadFailed(f"redbook-guard: {words}", code=code)})
    result = study(tmp_path, deps)
    image_sets, study_dir = folders(tmp_path)

    assert result["status"] == "stopped"
    assert calls.reads == TOP_FIVE[:3]                    # no retry, no read after the stop
    assert sorted(p.name for p in image_sets.iterdir()) == [set_name(1, "p3"), set_name(2, "p5")]
    assert result["stopped"]["pick"] == 3 and words in result["stopped"]["reason"]
    index = (study_dir / "index.md").read_text(encoding="utf-8")
    assert "标题-p6" in index and words in index          # where it stopped, and why
    assert result["reads_used"] == 3                      # the search and two reads; the refused read was not spent


def test_a_safety_signal_during_a_file_download_stops_the_study_too(tmp_path):
    deps, calls = make_deps(fail_download={"/p6/img2!": rn.DownloadFailed("redbook-guard: tripped on 'captcha'", code=66)})
    result = study(tmp_path, deps)
    assert result["status"] == "stopped" and result["stopped"]["pick"] == 3
    assert calls.reads == TOP_FIVE[:3]
    assert not any("/p6/img3" in url for url in calls.downloads)   # nothing more is fetched after the stop
    assert [s["folder"] for s in result["sets"]] == [set_name(1, "p3"), set_name(2, "p5")]   # the half-fetched set is not filed


def test_a_search_the_guard_refuses_stops_the_study_before_any_read(tmp_path):
    deps, calls = make_deps(fail_search=rn.ReadFailed("redbook-guard: daily cap reached", code=65))
    result = study(tmp_path, deps)
    assert result["status"] == "stopped" and result["stopped"]["pick"] == 0 and calls.reads == []
    assert "daily cap" in (folders(tmp_path)[1] / "index.md").read_text(encoding="utf-8")


def test_a_rerun_after_a_stop_spends_no_second_search_and_reads_no_saved_post_again(tmp_path):
    deps, _ = make_deps(fail_read_at={3: rn.ReadFailed("redbook-guard: tripped", code=66)})
    study(tmp_path, deps)
    again, calls = make_deps()
    result = study(tmp_path, again)
    assert calls.searches == []
    assert calls.reads == TOP_FIVE[2:]                    # picks 3, 4, 5 only
    assert [s["folder"] for s in result["sets"]] == [set_name(i, pid) for i, pid in enumerate(TOP_FIVE, start=1)]
    assert result["status"] == "incomplete" and result["stopped"] is None
    assert result["reads_used"] == 6                      # 1 search + 2 reads, then 3 more


def test_a_rerun_of_a_finished_study_touches_nothing_on_the_platform(tmp_path):
    deps, _ = make_deps()
    study(tmp_path, deps)
    again, calls = make_deps()
    result = study(tmp_path, again)
    assert calls.searches == [] and calls.reads == [] and calls.downloads == []
    assert result["reads_used"] == 6


def test_a_video_post_in_the_picks_is_skipped_as_a_set_and_the_index_says_so(tmp_path):
    posts = dict(POSTS, p3=("1.2万", "300", "video", 2))
    deps, calls = make_deps(posts)
    result = study(tmp_path, deps)
    assert calls.reads == ["p5", "p6", "p2", "p8"]
    assert [s["folder"] for s in result["sets"]] == [set_name(2, "p5"), set_name(3, "p6"), set_name(4, "p2"), set_name(5, "p8")]
    assert result["skipped"] == [{"pick": 1, "title": "标题-p3", "reason": "video"}]
    index = (folders(tmp_path)[1] / "index.md").read_text(encoding="utf-8")
    row = next(line for line in index.splitlines() if "标题-p3" in line)
    assert "视频" in row
    assert not any("/p3/" in url for url in calls.downloads)


def test_a_read_that_fails_for_another_reason_is_named_and_the_study_goes_on(tmp_path):
    deps, calls = make_deps(fail_read_at={2: rn.ReadFailed("the reader did not return a note")})
    result = study(tmp_path, deps)
    assert result["status"] == "failed"
    assert calls.reads == TOP_FIVE                        # carried on to the rest
    assert result["failed_reads"] == [{"pick": 2, "title": "标题-p5", "reason": "the reader did not return a note"}]
    assert len(result["sets"]) == 4


# --- seam 5: nothing secret outside the raw copies ------------------------------------------------------------------------

def test_no_file_the_step_writes_holds_an_access_code_apart_from_the_raw_copies(tmp_path):
    deps, _ = make_deps()
    study(tmp_path, deps)
    again, _ = make_deps()
    write_summary(tmp_path, [set_name(i, pid) for i, pid in enumerate(TOP_FIVE, start=1)])
    study(tmp_path, again)
    image_sets, study_dir = folders(tmp_path)
    raw = study_dir / "raw"
    holders, raw_holders = [], []
    for root in (image_sets, study_dir):
        for path in root.rglob("*"):
            if path.is_file() and any(secret in path.read_bytes() for secret in SECRETS):
                (raw_holders if raw in path.parents else holders).append(path.relative_to(tmp_path).as_posix())
    assert holders == []
    assert raw_holders                                    # the platform's own answers are kept untouched, in raw/ only


# --- the command line --------------------------------------------------------------------------------------------------------

def test_the_default_folders_follow_the_brands_research_layout():
    image_sets, study_dir = st.default_folders("Northwind", KEYWORD, DATE)
    base = Path("outputs") / "Northwind" / "品牌资料" / "对标笔记库"
    assert image_sets == base / "image-sets" and study_dir == base / "research" / f"{DATE}-{KEYWORD}"


def _argv(tmp_path, *extra):
    image_sets, study_dir = folders(tmp_path)
    return ["--brand", "Northwind", "--keyword", KEYWORD, "--image-sets", str(image_sets), "--study-dir", str(study_dir), "--date", DATE, *extra]


@pytest.mark.parametrize("stage, code", [("first", 4), ("summary", 0)])
def test_the_command_exits_0_only_when_the_study_is_complete(tmp_path, capsys, stage, code):
    deps, _ = make_deps()
    if stage == "summary":
        study(tmp_path, deps)
        write_summary(tmp_path, [set_name(i, pid) for i, pid in enumerate(TOP_FIVE, start=1)])
        deps, _ = make_deps()
    assert st.main(_argv(tmp_path), deps=deps) == code
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == ("complete" if code == 0 else "incomplete")


def test_the_command_exits_3_when_stopped_and_1_when_the_check_fails(tmp_path, capsys):
    deps, _ = make_deps(fail_read_at={2: rn.ReadFailed("redbook-guard: tripped", code=66)})
    assert st.main(_argv(tmp_path), deps=deps) == 3
    assert "tripped" in capsys.readouterr().err
    deps, _ = make_deps(fail_download={"/p5/img3!": RuntimeError("the download exited 1")})
    assert st.main(_argv(tmp_path), deps=deps) == 1


def test_the_command_refuses_a_nonsense_n(tmp_path, capsys):
    deps, calls = make_deps()
    assert st.main(_argv(tmp_path, "-n", "0"), deps=deps) == 2
    assert calls.searches == []
