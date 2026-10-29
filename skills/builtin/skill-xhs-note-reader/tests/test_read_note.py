"""Tests for read_note.py: the one step that saves the whole content of a Xiaohongshu note.

Everything outside the step is a stand-in (the guarded reader, the downloads, the text-in-image engine, ffmpeg, the
transcriber, the 点点 chat), so no test reaches Xiaohongshu, its file servers or a paid service.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))   # read_note imports diandian_reply from its own folder
spec = importlib.util.spec_from_file_location("read_note", SCRIPTS / "read_note.py")
rn = importlib.util.module_from_spec(spec)
sys.modules["read_note"] = rn   # a dataclass looks its own module up here
spec.loader.exec_module(rn)

NOTE_ID = "6aabad9400000000110328e1"
FULL_ADDRESS = f"https://www.xiaohongshu.com/explore/{NOTE_ID}?xsec_token=tok-secret&xsec_source=pc_search"
GOOD_REPLY = "这篇笔记讲了三个做法：\n- 先把底妆做薄\n- 再用散粉定妆\n- 最后补一层高光"
MB = 1024 * 1024


def image_note(count: int = 5) -> dict:
    return {
        "note_id": NOTE_ID, "type": "normal", "title": "三步底妆", "desc": "正文第一段\n#底妆 #教程",
        "tag_list": [{"id": "1", "name": "底妆", "type": "topic"}],
        "interact_info": {"liked_count": "12", "collected_count": "30"},
        "user": {"user_id": "u1", "nickname": "作者", "xsec_token": "user-secret-token"},
        "image_list": [{"url": f"http://sns-webpic-qc.xhscdn.com/raw{i}", "url_default": f"http://sns-webpic-qc.xhscdn.com/img{i}!nd"}
                       for i in range(1, count + 1)],
        "webUrl": FULL_ADDRESS,
    }


def video_note(video: dict | None) -> dict:
    note = image_note(2)
    note["type"] = "video"
    if video is not None:
        note["video"] = video
    return note


class Calls:
    """What the stand-ins were asked, so a test can see what the step did and in which order."""
    def __init__(self):
        self.downloads: list[tuple[str, str]] = []
        self.ocr: list[str] = []
        self.grabs: list[float] = []
        self.sheets: list[list[str]] = []
        self.transcribe: list[tuple[str, float]] = []
        self.diandian: list[str] = []
        self.clock = 0.0


def make_deps(note: dict | None = None, calls: Calls | None = None, **over):
    calls = calls or Calls()

    def read(link):
        return note if note is not None else image_note()

    def download(url, dest):
        calls.downloads.append((url, Path(dest).name))
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"BYTES:" + url.encode())

    def ocr(path):
        calls.ocr.append(Path(path).name)
        return f"text in {Path(path).name}"

    def grab(video, t, dest):
        calls.grabs.append(t)
        Path(dest).write_bytes(b"F" * over.get("frame_bytes", 1000))
        calls.clock += over.get("seconds_per_grab", 0.0)

    def sheet(frames, dest):
        calls.sheets.append([Path(f).name for f in frames])
        Path(dest).write_bytes(b"SHEET")

    def transcribe(video, max_seconds):
        calls.transcribe.append((Path(video).name, max_seconds))
        return {"text": "视频里说的话", "partial": False, "segments": [{"start": 0.0, "end": 2.0, "text": "视频里说的话"}]}

    def diandian(address, dest):
        calls.diandian.append(address)
        Path(dest).write_text(GOOD_REPLY, encoding="utf-8")
        return 0

    base = rn.Deps(
        read=read, download=download, ocr=ocr,
        video_duration=lambda video: over.get("duration", 22.0),
        grab_frame=grab, scene_times=lambda video: over.get("scenes", []), contact_sheet=sheet,
        transcribe=transcribe, diandian=diandian, clock=lambda: calls.clock,
    )
    fields = {k: v for k, v in over.items() if k in {f.name for f in dataclasses.fields(rn.Deps)}}
    return dataclasses.replace(base, **fields), calls


def run(note=None, tmp_path=None, **over):
    deps, calls = make_deps(note, **over)
    record = rn.read_note(FULL_ADDRESS, tmp_path, deps, **({"want_diandian": over["want_diandian"]} if "want_diandian" in over else {}))
    return record, calls, tmp_path / NOTE_ID


# --- an image note: 5 images, 5 texts in order, one record of every part ---------------------------

def test_image_note_saves_images_their_text_in_order_and_a_record_of_every_part(tmp_path):
    record, calls, folder = run(tmp_path=tmp_path)
    assert sorted(p.name for p in (folder / "images").iterdir()) == [f"0{i}.jpg" for i in range(1, 6)]
    assert [u for u, _ in calls.downloads] == [f"http://sns-webpic-qc.xhscdn.com/img{i}!nd" for i in range(1, 6)]
    texts = json.loads((folder / "image-text.json").read_text(encoding="utf-8"))
    assert [t["image"] for t in texts] == [f"images/0{i}.jpg" for i in range(1, 6)]
    assert [t["text"] for t in texts] == [f"text in 0{i}.jpg" for i in range(1, 6)]
    on_disk = json.loads((folder / "record.json").read_text(encoding="utf-8"))
    assert on_disk == record
    assert set(record["parts"]) == {"read", "caption", "images", "image_text", "video", "frames", "speech", "diandian"}
    assert {k: v["status"] for k, v in record["parts"].items()} == {
        "read": "produced", "caption": "produced", "images": "produced", "image_text": "produced",
        "video": "skipped", "frames": "skipped", "speech": "skipped", "diandian": "produced",
    }
    assert record["parts"]["video"]["reason"] == "not a video note"
    assert record["note_id"] == NOTE_ID


def test_the_caption_is_kept_in_plain_text(tmp_path):
    _, _, folder = run(tmp_path=tmp_path)
    caption = (folder / "caption.md").read_text(encoding="utf-8")
    assert "三步底妆" in caption and "正文第一段" in caption and "底妆" in caption


def test_the_read_is_saved_as_it_came_back(tmp_path):
    _, _, folder = run(tmp_path=tmp_path)
    assert json.loads((folder / "read.json").read_text(encoding="utf-8"))["note_id"] == NOTE_ID


# --- the video address, in each spelling the read can use ------------------------------------------

ORIGIN = "https://sns-video-bd.xhscdn.com/pre_post/abc123"
STREAMS = {"h264": [
    {"size": 100, "master_url": "http://sns-video-bd.xhscdn.com/small.mp4", "backup_urls": ["http://sns-video-qc.xhscdn.com/small-b.mp4"]},
    {"size": 900, "master_url": "http://sns-video-bd.xhscdn.com/big.mp4", "backup_urls": ["http://sns-video-qc.xhscdn.com/big-b.mp4"]},
], "h265": [{"size": 500, "master_url": "http://sns-video-bd.xhscdn.com/mid.mp4"}]}
STREAMS_CAMEL = {"h264": [
    {"size": 100, "masterUrl": "http://sns-video-bd.xhscdn.com/small.mp4"},
    {"size": 900, "masterUrl": "http://sns-video-bd.xhscdn.com/big.mp4"},
]}


@pytest.mark.parametrize("label, note, expected", [
    ("snake-case feed fields, origin key present", {"video": {"consumer": {"origin_video_key": "pre_post/abc123"}, "media": {"stream": STREAMS}}}, ORIGIN),
    ("camel-case page fields, origin key present", {"video": {"consumer": {"originVideoKey": "pre_post/abc123"}}}, ORIGIN),
    ("only stream entries, snake-case: the largest, backup address first", {"video": {"media": {"stream": STREAMS}}}, "http://sns-video-qc.xhscdn.com/big-b.mp4"),
    ("only stream entries, camel-case: the largest, master address", {"video": {"media": {"stream": STREAMS_CAMEL}}}, "http://sns-video-bd.xhscdn.com/big.mp4"),
    ("the note object wrapped one level down", {"note": {"video": {"consumer": {"origin_video_key": "pre_post/abc123"}}}}, ORIGIN),
    ("no video fields", {"type": "video"}, None),
    ("an empty video object", {"video": {}}, None),
    ("an address on a host that is not the platform's file servers", {"video": {"media": {"stream": {"h264": [{"size": 1, "master_url": "https://evil.example/x.mp4"}]}}}}, None),
])
def test_video_address_is_picked_from_whichever_spelling_the_read_uses(label, note, expected):
    assert rn.pick_video_address(note) == expected, label


def test_a_video_note_without_an_address_says_so_and_still_finishes_images_and_text(tmp_path):
    record, calls, folder = run(video_note(None), tmp_path)
    assert record["parts"]["video"] == {"status": "skipped", "reason": "video address not in read"}
    assert record["parts"]["frames"]["status"] == "skipped" and record["parts"]["speech"]["status"] == "skipped"
    assert record["parts"]["images"]["status"] == "produced" and record["parts"]["image_text"]["status"] == "produced"
    assert not any(name.endswith(".mp4") for _, name in calls.downloads)
    assert calls.transcribe == [] and calls.grabs == []


def test_a_video_note_with_an_address_is_downloaded_framed_and_transcribed(tmp_path):
    record, calls, folder = run(video_note({"consumer": {"origin_video_key": "pre_post/abc123"}}), tmp_path)
    assert (ORIGIN, "note.mp4") in calls.downloads
    assert (folder / "video" / "note.mp4").is_file()
    assert record["parts"]["video"]["status"] == "produced"
    assert record["parts"]["frames"]["status"] == "produced" and (folder / "frames" / "contact-sheet.jpg").is_file()
    assert record["parts"]["speech"]["status"] == "produced"
    assert json.loads((folder / "speech.json").read_text(encoding="utf-8"))["text"] == "视频里说的话"


# --- frames: 5 s spacing plus scene changes, stopping at 60 frames, 20 MB or 120 s -------------------

def test_frames_are_taken_every_5_seconds(tmp_path):
    assert rn.sample_times(22.0) == [0.0, 5.0, 10.0, 15.0, 20.0]
    assert rn.sample_times(20.0) == [0.0, 5.0, 10.0, 15.0]
    assert rn.sample_times(3.0) == [0.0]


def test_scene_changes_are_added_unless_a_frame_is_already_within_a_second(tmp_path):
    record, calls, _ = run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path, duration=22.0, scenes=[0.4, 7.3, 7.9, 12.0])
    assert sorted(calls.grabs) == [0.0, 5.0, 7.3, 10.0, 12.0, 15.0, 20.0]
    assert record["parts"]["frames"]["count"] == 7 and record["parts"]["frames"]["stopped_by"] is None


def test_frames_stop_at_60(tmp_path):
    record, calls, folder = run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path, duration=1000.0, scenes=[3.0, 8.0])
    frames = record["parts"]["frames"]
    assert frames["count"] == 60 and frames["stopped_by"] == "frames"
    assert len(list((folder / "frames").glob("frame-*.jpg"))) == 60
    assert all(t % 5 == 0 for t in calls.grabs), "the even 5 s spacing comes before scene changes when the cap is near"
    assert len(calls.sheets) == 1 and len(calls.sheets[0]) == 60


def test_frames_stop_at_20_megabytes(tmp_path):
    record, calls, folder = run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path, duration=1000.0, frame_bytes=MB)
    frames = record["parts"]["frames"]
    assert frames["stopped_by"] == "bytes" and frames["count"] == 20
    assert sum(p.stat().st_size for p in (folder / "frames").glob("frame-*.jpg")) <= 20 * MB


def test_frames_stop_at_120_seconds_of_work(tmp_path):
    record, calls, _ = run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path, duration=1000.0, seconds_per_grab=10.0)
    frames = record["parts"]["frames"]
    assert frames["stopped_by"] == "seconds" and frames["count"] == 12


# --- speech: capped at 600 s a video; running out of time marks the transcript partial ---------------

def test_speech_is_asked_for_at_most_600_seconds(tmp_path):
    _, calls, _ = run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path)
    assert calls.transcribe == [("note.mp4", 600)]


def test_a_transcript_that_ran_out_of_time_is_marked_partial_not_dropped(tmp_path):
    def transcribe(video, max_seconds):
        return {"text": "说到一半", "partial": True, "segments": []}
    record, _, folder = run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path, transcribe=transcribe)
    assert record["parts"]["speech"]["status"] == "partial"
    saved = json.loads((folder / "speech.json").read_text(encoding="utf-8"))
    assert saved["partial"] is True and saved["text"] == "说到一半"


def test_no_speech_found_is_said_not_failed(tmp_path):
    record, _, _ = run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path, transcribe=lambda v, s: {"text": "", "partial": False, "segments": []})
    assert record["parts"]["speech"] == {"status": "produced", "note": "no speech found"}


# --- 点点: only a finished, whole reply is saved; the guard's refusals are final --------------------

def test_a_finished_reply_is_saved_whole_minus_a_recognised_footer(tmp_path):
    def diandian(address, dest):
        Path(dest).write_text(GOOD_REPLY + "\n\n以上内容由 AI 生成，仅供参考。", encoding="utf-8")
        return 0
    record, calls, folder = run(tmp_path=tmp_path, diandian=diandian)
    assert (folder / "diandian.md").read_text(encoding="utf-8").strip() == GOOD_REPLY
    assert record["parts"]["diandian"]["status"] == "produced"


def test_diandian_is_given_the_full_note_address_from_the_read(tmp_path):
    _, calls, _ = run(tmp_path=tmp_path)
    assert calls.diandian == [FULL_ADDRESS]


@pytest.mark.parametrize("reply_text, reason", [
    ("抱歉，我目前无法直接访问小红书链接来读取笔记内容。\n\n你可以把笔记的标题或正文内容直接复制发给我，我来帮你总结！", "refusal"),
    ("记录\n通过自然语言对话，- 快速改成别的做法，再补一些字数让它够长一点点", "incomplete"),
    ("太短了", "too short"),
])
def test_a_refusal_or_damaged_or_short_reply_is_not_saved_as_a_summary(tmp_path, reply_text, reason):
    def diandian(address, dest):
        Path(dest).write_text(reply_text, encoding="utf-8")
        return 0
    record, _, folder = run(tmp_path=tmp_path, diandian=diandian)
    assert not (folder / "diandian.md").exists()
    assert record["parts"]["diandian"] == {"status": "failed", "reason": f"reply not saved: {reason}"}


@pytest.mark.parametrize("code, words", [
    (65, "daily cap"), (66, "tripped"), (70, "login"), (71, "using the account"),
])
def test_when_the_guard_says_no_the_step_reports_it_once_and_never_retries(tmp_path, code, words):
    attempts = []
    def diandian(address, dest):
        attempts.append(address)
        return code
    record, _, folder = run(tmp_path=tmp_path, diandian=diandian)
    assert len(attempts) == 1
    part = record["parts"]["diandian"]
    assert part["status"] == "skipped" and words in part["reason"]
    assert not (folder / "diandian.md").exists()
    assert record["parts"]["images"]["status"] == "produced", "the other parts are not touched"


def test_diandian_can_be_left_out(tmp_path):
    record, calls, _ = run(tmp_path=tmp_path, want_diandian=False)
    assert calls.diandian == []
    assert record["parts"]["diandian"] == {"status": "skipped", "reason": "left out by request"}


def test_no_full_note_address_means_no_diandian_call(tmp_path):
    note = image_note()
    del note["webUrl"]
    deps, calls = make_deps(note)
    record = rn.read_note("http://xhslink.com/o/AbCdEf123", tmp_path, deps)
    assert calls.diandian == []
    assert record["parts"]["diandian"]["status"] == "skipped"
    assert "full note address" in record["parts"]["diandian"]["reason"]


# --- one failed part never deletes or hides the others -----------------------------------------------

def test_a_failed_image_download_is_named_and_the_rest_carry_on(tmp_path):
    base, calls = make_deps()
    def download(url, dest):
        if url.endswith("img3!nd"):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"half a file")   # what a download cut off part-way leaves behind
            raise RuntimeError("HTTP 404")
        base.download(url, dest)
    record, _, folder = run(tmp_path=tmp_path, download=download)
    images = record["parts"]["images"]
    assert images["status"] == "partial" and images["failed"] == [{"image": "03.jpg", "reason": "HTTP 404"}]
    assert (folder / "images" / "01.jpg").exists() and (folder / "images" / "05.jpg").exists()
    assert not (folder / "images" / "03.jpg").exists(), "a half-downloaded file is not left looking like an image"
    texts = json.loads((folder / "image-text.json").read_text(encoding="utf-8"))
    assert [t["image"] for t in texts] == ["images/01.jpg", "images/02.jpg", "images/04.jpg", "images/05.jpg"]
    assert record["parts"]["diandian"]["status"] == "produced"


def test_text_in_images_that_cannot_run_is_skipped_with_the_reason(tmp_path):
    def ocr(path):
        raise rn.PartUnavailable("rapidocr_onnxruntime is not installed (run ops/wsl-setup/setup.sh --only python-packages)")
    record, _, folder = run(tmp_path=tmp_path, ocr=ocr)
    assert record["parts"]["image_text"]["status"] == "skipped"
    assert "rapidocr_onnxruntime is not installed" in record["parts"]["image_text"]["reason"]
    assert record["parts"]["images"]["status"] == "produced" and (folder / "images" / "05.jpg").exists()


def test_one_unreadable_image_leaves_a_gap_in_the_text_not_a_hole_in_the_order(tmp_path):
    def ocr(path):
        if path.name == "02.jpg":
            raise RuntimeError("cannot decode")
        return f"text in {path.name}"
    record, _, folder = run(tmp_path=tmp_path, ocr=ocr)
    texts = json.loads((folder / "image-text.json").read_text(encoding="utf-8"))
    assert [t["image"] for t in texts] == [f"images/0{i}.jpg" for i in range(1, 6)]
    assert texts[1] == {"image": "images/02.jpg", "text": None, "error": "cannot decode"}
    assert record["parts"]["image_text"]["status"] == "partial"


def test_a_failed_frame_step_does_not_stop_speech_or_the_summary(tmp_path):
    def contact_sheet(frames, dest):
        raise RuntimeError("ffmpeg exited 1")
    record, _, folder = run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path, contact_sheet=contact_sheet)
    assert record["parts"]["frames"]["status"] == "failed" and "ffmpeg exited 1" in record["parts"]["frames"]["reason"]
    assert record["parts"]["speech"]["status"] == "produced" and record["parts"]["diandian"]["status"] == "produced"


def test_a_read_that_fails_makes_a_record_with_nothing_else(tmp_path):
    def read(link):
        raise rn.ReadFailed("redbook-guard: tripped. The platform raised a safety signal earlier")
    deps, _ = make_deps(read=read)
    with pytest.raises(rn.ReadFailed, match="tripped"):
        rn.read_note(FULL_ADDRESS, tmp_path, deps)
    assert list(tmp_path.iterdir()) == []


# --- nothing secret is written next to the content ----------------------------------------------------

def test_no_file_but_the_saved_read_holds_an_access_code(tmp_path):
    run(video_note({"consumer": {"origin_video_key": "k"}}), tmp_path)
    folder = tmp_path / NOTE_ID
    holders = []
    for path in folder.rglob("*"):
        if path.is_file() and (b"xsec_token" in path.read_bytes() or b"tok-secret" in path.read_bytes() or b"user-secret-token" in path.read_bytes()):
            holders.append(path.relative_to(folder).as_posix())
    assert holders == ["read.json"]


# --- the real stand-in-free pieces: the adapters over the guarded reader, ffmpeg, the OCR engine -------

FAKE_REDBOOK = textwrap.dedent('''
    import json, shutil, sys
    log = open(sys.argv[1], "a", encoding="utf-8")
    args = sys.argv[2:]
    log.write(" ".join(args) + "\\n")
    if args[0] == "read":
        print(json.dumps({"note_id": "n1", "type": "normal", "title": "t", "image_list": [], "webUrl": "https://www.xiaohongshu.com/explore/n1?xsec_token=x"}))
    elif args[0] == "fetch-file":
        open(args[2], "wb").write(b"FILE")
    elif args[0] == "diandian":
        open(args[2], "w", encoding="utf-8").write("reply")
''')


def fake_redbook(tmp_path):
    script = tmp_path / "fake_redbook.py"
    script.write_text(FAKE_REDBOOK, encoding="utf-8")
    log = tmp_path / "redbook.log"
    return [sys.executable, str(script), str(log)], log


def test_the_default_reader_runs_the_guarded_command_and_parses_its_answer(tmp_path):
    cmd, log = fake_redbook(tmp_path)
    deps = rn.default_deps(redbook=cmd)
    note = deps.read("http://xhslink.com/o/AbCdEf123")
    assert note["note_id"] == "n1"
    assert log.read_text(encoding="utf-8").splitlines() == ["read http://xhslink.com/o/AbCdEf123 --json"]


def test_the_default_reader_reports_the_guards_own_words_when_it_refuses(tmp_path):
    script = tmp_path / "refusing.py"
    script.write_text("import sys\nsys.stderr.write('redbook-guard: tripped: captcha. Tell the owner, do not retry.\\n')\nsys.exit(66)\n", encoding="utf-8")
    deps = rn.default_deps(redbook=[sys.executable, str(script)])
    with pytest.raises(rn.ReadFailed, match="tripped"):
        deps.read("https://www.xiaohongshu.com/explore/n1")


def test_downloads_and_the_summary_go_through_the_guard_never_around_it(tmp_path):
    cmd, log = fake_redbook(tmp_path)
    deps = rn.default_deps(redbook=cmd)
    dest = tmp_path / "images" / "01.jpg"
    deps.download("http://sns-webpic-qc.xhscdn.com/a", dest)
    assert dest.read_bytes() == b"FILE"
    reply = tmp_path / "reply.txt"
    assert deps.diandian(FULL_ADDRESS, reply) == 0
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"fetch-file http://sns-webpic-qc.xhscdn.com/a {dest}", f"diandian {FULL_ADDRESS} {reply}"]


def test_a_refused_download_names_the_guards_reason(tmp_path):
    script = tmp_path / "refusing.py"
    script.write_text("import sys\nsys.stderr.write('redbook-guard: tripped: captcha\\n')\nsys.exit(66)\n", encoding="utf-8")
    deps = rn.default_deps(redbook=[sys.executable, str(script)])
    with pytest.raises(RuntimeError, match="tripped"):
        deps.download("http://sns-webpic-qc.xhscdn.com/a", tmp_path / "x.jpg")


def test_the_default_ocr_joins_the_engine_lines_in_reading_order(tmp_path, monkeypatch):
    class Engine:
        def __call__(self, path):
            return [[[[0, 0]], "第一行", 0.99], [[[0, 9]], "第二行", 0.97]], [0.1]
    fake = type(sys)("rapidocr_onnxruntime")
    fake.RapidOCR = Engine
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", fake)
    assert rn.default_deps(redbook=["x"]).ocr(tmp_path / "a.jpg") == "第一行\n第二行"


def test_the_default_ocr_says_what_to_run_when_the_engine_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
    with pytest.raises(rn.PartUnavailable, match="setup.sh --only python-packages"):
        rn.default_deps(redbook=["x"]).ocr(tmp_path / "a.jpg")


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg is not installed here")
def test_the_default_frame_tools_work_on_a_real_clip(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=12",
                    "-pix_fmt", "yuv420p", str(clip)], check=True, timeout=120, stdin=subprocess.DEVNULL)
    deps = rn.default_deps(redbook=["x"])
    assert 11.5 < deps.video_duration(clip) < 12.5
    frame = tmp_path / "f.jpg"
    deps.grab_frame(clip, 5.0, frame)
    assert frame.stat().st_size > 500
    sheet = tmp_path / "sheet.jpg"
    deps.contact_sheet([frame, frame, frame], sheet)
    assert sheet.stat().st_size > 500
    assert isinstance(deps.scene_times(clip), list)


# --- the command line ----------------------------------------------------------------------------------

def test_the_command_prints_the_record_and_exits_0_when_the_read_worked(tmp_path, capsys):
    deps, _ = make_deps()
    code = rn.main([FULL_ADDRESS, "--out", str(tmp_path)], deps=deps)
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and printed["note_id"] == NOTE_ID and printed["folder"].endswith(NOTE_ID)


def test_the_command_exits_1_and_says_why_when_the_read_fails(tmp_path, capsys):
    def read(link):
        raise rn.ReadFailed("redbook-guard: daily cap reached")
    deps, _ = make_deps(read=read)
    assert rn.main([FULL_ADDRESS, "--out", str(tmp_path)], deps=deps) == 1
    assert "daily cap reached" in capsys.readouterr().err


def test_the_command_refuses_a_link_that_is_not_a_note_link(tmp_path, capsys):
    deps, calls = make_deps()
    assert rn.main(["https://example.com/post/1", "--out", str(tmp_path)], deps=deps) == 2
    assert "note link" in capsys.readouterr().err


def test_skip_diandian_flag(tmp_path, capsys):
    deps, calls = make_deps()
    assert rn.main([FULL_ADDRESS, "--out", str(tmp_path), "--skip-diandian"], deps=deps) == 0
    assert calls.diandian == []


# --- the guard's exit code travels with the error (issue 84: a topic study stops on it) ---------------------------

def _refusing(tmp_path, code):
    script = tmp_path / "refusing.py"
    script.write_text(f"import sys\nsys.stderr.write('redbook-guard: refused\\n')\nsys.exit({code})\n", encoding="utf-8")
    return rn.default_deps(redbook=[sys.executable, str(script)])


@pytest.mark.parametrize("code", [65, 66, 70, 71])
def test_a_refused_read_carries_the_guards_exit_code(tmp_path, code):
    with pytest.raises(rn.ReadFailed) as caught:
        _refusing(tmp_path, code).read("https://www.xiaohongshu.com/explore/n1")
    assert caught.value.code == code


@pytest.mark.parametrize("code", [65, 66, 70, 71])
def test_a_refused_download_carries_the_guards_exit_code(tmp_path, code):
    with pytest.raises(rn.DownloadFailed) as caught:
        _refusing(tmp_path, code).download("http://sns-webpic-qc.xhscdn.com/a", tmp_path / "x.jpg")
    assert caught.value.code == code and isinstance(caught.value, RuntimeError)


def test_an_error_made_without_a_code_has_none():
    assert rn.ReadFailed("no reason").code is None and rn.DownloadFailed("no reason").code is None
