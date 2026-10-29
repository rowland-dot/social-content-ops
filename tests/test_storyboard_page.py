"""storyboard_page.py build: the storyboard approval page, built from a video plan (issue 51).

Seam: the `build` command line of skills/shared/scripts/storyboard_page.py, run on example plans written for these
tests (video 01 is not in git, and its plan has the old six-column table, so it is not used here). The page is read
back with an HTML parser through the classes the script documents: each shot is an element of class `shot` holding
the fields `no`, `time`, `voice`, `scene`, `source`, `note` and an image of class `still`; each open ending is a
`section.option` holding its shots, switched by a `button.switch`.

Expected values are the literals written in the example plans below, never read back from the script. The "word
for word" tests also read the plan a second way: the voice lines of the page, joined, must equal the plan's own full
script block.

The plan layout under test is the one skills/builtin/video-script/SKILL.md defines (The owner, 2026-10-16: a fixed shot
list inside the plan, notes in their own column, one table per still-open ending).
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "shared" / "scripts" / "storyboard_page.py"
PNG = base64.b64decode(  # a real 1x1 picture, so a browser test can tell a still that loaded from one that did not
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

HEADER = "| 镜 | 时间 | 口播 | 画面 | 来源 | 分镜图 | 备注 |\n|---|---|---|---|---|---|---|\n"

PLAN_NO_ENDINGS = f"""# 视频99｜测试用分镜

## 当前状态
这是测试写的计划，不是真实视频。

## 完整口播稿
```
你好，世界。
A&B 比 <C> 好。
再见。
```

## 分镜表
{HEADER}| 01 | 0.00–3.00s | 你好，世界。 | 一杯清水放在台面中央 | 图卡 | shot01.png | |
| 02 | 3.00–6.50s | A&B 比 <C> 好。 | 手拿量勺倒粉末（"特写"） | Kling 3.0 Turbo | shot02.png | 10-15 负责人定：和镜 03 对调 |
| 03 | 6.50–9.00s | 再见。 | 空镜 | 图卡 | 方案 B-shot03#2.png | |

## 变更记录
- 10-15 测试用
"""

SHOTS_NO_ENDINGS = [
    dict(no="01", time="0.00–3.00s", voice="你好，世界。", scene="一杯清水放在台面中央", source="图卡", note=None,
         still="shot01.png"),
    dict(no="02", time="3.00–6.50s", voice="A&B 比 <C> 好。", scene='手拿量勺倒粉末（"特写"）',
         source="Kling 3.0 Turbo", note="10-15 负责人定：和镜 03 对调", still="shot02.png"),
    dict(no="03", time="6.50–9.00s", voice="再见。", scene="空镜", source="图卡", note=None,
         still="方案 B-shot03#2.png"),
]


class Page(HTMLParser):
    """What the page says, by the classes the script documents."""

    FIELDS = ("no", "time", "voice", "scene", "source", "note")

    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.shots: list[dict] = []
        self.switches: list[str] = []
        self.options: list[str] = []
        self._option: str | None = None
        self._field: tuple[str, str] | None = None  # (field name or "switch", the tag that closes it)
        self._buffer: list[str] = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "section" and "option" in classes:
            self._option = a.get("data-option")
            self.options.append(self._option)
        elif "shot" in classes:
            self.shots.append({"option": self._option, "still": None, "src": None,
                               **dict.fromkeys(self.FIELDS)})
        elif tag == "img" and "still" in classes and self.shots:
            self.shots[-1]["src"] = a.get("src")
        elif tag == "button" and "switch" in classes:
            self._field, self._buffer = ("switch", tag), []
        else:
            for name in self.FIELDS:
                if name in classes and self.shots:
                    self._field, self._buffer = (name, tag), []

    def handle_data(self, data):
        if self._field:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "section":
            self._option = None
        if self._field and tag == self._field[1]:
            text = "".join(self._buffer)
            if self._field[0] == "switch":
                self.switches.append(text)
            else:
                self.shots[-1][self._field[0]] = text
            self._field = None


def build(tmp: Path, plan_text: str, *, stills=("shot01.png", "shot02.png", "方案 B-shot03#2.png"), extra=()):
    """Write a video folder (plan.md and storyboard/<stills>) and run the builder on it."""
    folder = tmp / "视频99"
    (folder / "storyboard").mkdir(parents=True)
    for name in stills:
        (folder / "storyboard" / name).write_bytes(PNG)
    (folder / "shot01.png").write_bytes(PNG)  # one level up, so a still named as a path out of the folder really exists
    (folder / "plan.md").write_text(plan_text, encoding="utf-8")
    page = folder / "审批稿.html"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "build", "--plan", str(folder / "plan.md"),
         "--storyboard", str(folder / "storyboard"), "-o", str(page), *extra],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    return result, page


def read_page(page: Path) -> Page:
    return Page(page.read_text(encoding="utf-8"))


# --- the page repeats the plan, word for word ------------------------------------------------------------

def test_every_shot_row_carries_the_plans_own_words_in_plan_order(tmp_path):
    result, page = build(tmp_path, PLAN_NO_ENDINGS)
    assert result.returncode == 0, result.stdout + result.stderr
    shots = read_page(page).shots
    assert [{k: s[k] for k in ("no", "time", "voice", "scene", "source", "note")} for s in shots] == \
           [{k: e[k] for k in ("no", "time", "voice", "scene", "source", "note")} for e in SHOTS_NO_ENDINGS]


def test_the_voice_lines_joined_equal_the_plans_own_full_script_block(tmp_path):
    result, page = build(tmp_path, PLAN_NO_ENDINGS)
    assert result.returncode == 0, result.stdout + result.stderr
    script_block = re.search(r"## 完整口播稿\n```\n(.*?)\n```", PLAN_NO_ENDINGS, re.S).group(1)  # read from the plan itself
    assert "\n".join(s["voice"] for s in read_page(page).shots) == script_block


def test_a_note_is_its_own_line_and_never_part_of_the_voice_line(tmp_path):
    result, page = build(tmp_path, PLAN_NO_ENDINGS)
    assert result.returncode == 0, result.stdout + result.stderr
    second = read_page(page).shots[1]
    assert second["note"] == "10-15 负责人定：和镜 03 对调"
    assert "负责人定" not in second["voice"] and "负责人定" not in second["scene"]


# --- the stills sit beside their rows, by relative path -------------------------------------------------

def test_each_shot_shows_its_still_by_a_path_relative_to_the_page(tmp_path):
    result, page = build(tmp_path, PLAN_NO_ENDINGS)
    assert result.returncode == 0, result.stdout + result.stderr
    shots = read_page(page).shots
    assert shots[0]["src"] == "storyboard/shot01.png"
    for shot, expected in zip(shots, SHOTS_NO_ENDINGS):
        assert not re.match(r"^([a-zA-Z]:|/|file:)", shot["src"]), shot["src"]
        assert "#" not in shot["src"] and " " not in shot["src"], shot["src"]  # a browser would cut the name at the #
        assert (page.parent / unquote(shot["src"])).resolve() == \
               (page.parent / "storyboard" / expected["still"]).resolve()  # a name with a space and Chinese still opens


# --- one switch for each ending still open ---------------------------------------------------------------

PLAN_WITH_ENDINGS = f"""# 视频98｜测试用分镜（结尾未定）

## 分镜表
{HEADER}| 01 | 0.00–3.00s | 开头一句。 | 开头画面 | 图卡 | shot01.png | |
| 02 | 3.00–6.00s | 中间一句。 | 中间画面 | 图卡 | shot02.png | |

## 待定结尾：方案 A（留评论问题）
{HEADER}| 03 | 6.00–9.00s | 结尾甲一。 | 甲画面一 | 图卡 | A-shot03.png | |
| 04 | 9.00–12.00s | 结尾甲二。 | 甲画面二 | 图卡 | A-shot04.png | 甲备注 |
| 05 | 12.00–15.00s | 结尾甲三。 | 甲画面三 | 图卡 | A-shot05.png | |

## 待定结尾：方案 B（收藏引导）
{HEADER}| 03 | 6.00–9.50s | 结尾乙一。 | 乙画面一 | 图卡 | B-shot03.png | |
| 04 | 9.50–13.00s | 结尾乙二。 | 乙画面二 | 图卡 | B-shot04.png | |
"""
ENDING_STILLS = ("shot01.png", "shot02.png", "A-shot03.png", "A-shot04.png", "A-shot05.png", "B-shot03.png",
                 "B-shot04.png")


def test_each_open_ending_gets_one_switch_named_as_the_plan_names_it(tmp_path):
    result, page = build(tmp_path, PLAN_WITH_ENDINGS, stills=ENDING_STILLS)
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = read_page(page)
    assert parsed.switches == ["方案 A（留评论问题）", "方案 B（收藏引导）"]
    assert parsed.options == ["方案 A（留评论问题）", "方案 B（收藏引导）"]


def test_each_ending_shows_its_own_shots_even_when_the_endings_differ_in_length(tmp_path):
    result, page = build(tmp_path, PLAN_WITH_ENDINGS, stills=ENDING_STILLS)
    assert result.returncode == 0, result.stdout + result.stderr
    shots = read_page(page).shots

    def of(option):
        return [(s["no"], s["voice"], s["note"]) for s in shots if s["option"] == option]

    assert of(None) == [("01", "开头一句。", None), ("02", "中间一句。", None)]  # what every ending shares
    assert of("方案 A（留评论问题）") == [("03", "结尾甲一。", None), ("04", "结尾甲二。", "甲备注"),
                                      ("05", "结尾甲三。", None)]
    assert of("方案 B（收藏引导）") == [("03", "结尾乙一。", None), ("04", "结尾乙二。", None)]


def test_an_ending_shot_shows_the_still_named_in_its_own_table(tmp_path):
    result, page = build(tmp_path, PLAN_WITH_ENDINGS, stills=ENDING_STILLS)
    assert result.returncode == 0, result.stdout + result.stderr
    third = [s for s in read_page(page).shots if s["no"] == "03"]
    assert [s["src"] for s in third] == ["storyboard/A-shot03.png", "storyboard/B-shot03.png"]


# --- the builder refuses what it cannot read, and never guesses -----------------------------------------------

SIX_COLUMN_ROWS = "| 镜 | 时间 | 口播 | 画面 | 来源 | 分镜图 |\n|---|---|---|---|---|---|\n| 01 | 0.00–3.00s | 你好，世界。 | 一杯水 | 图卡 | shot01.png |\n"
ALL_STILLS = ("shot01.png", "shot02.png", "方案 B-shot03#2.png")

REFUSALS = {
    "no shot table at all": (
        PLAN_NO_ENDINGS.replace("## 分镜表", "## 镜头"), ALL_STILLS, ["分镜表"]),
    "the old six-column table without a notes column": (
        PLAN_NO_ENDINGS.replace(PLAN_NO_ENDINGS[PLAN_NO_ENDINGS.index("| 镜 |"):PLAN_NO_ENDINGS.index("## 变更记录")],
                                SIX_COLUMN_ROWS + "\n"), ALL_STILLS, ["分镜表", "备注"]),
    "a row with a cell too few": (
        PLAN_NO_ENDINGS.replace("| 图卡 | shot01.png | |", "| 图卡 | shot01.png |"), ALL_STILLS, ["镜 01"]),
    "a row with no still": (
        PLAN_NO_ENDINGS.replace("| 图卡 | 方案 B-shot03#2.png | |", "| 图卡 |  | |"), ALL_STILLS, ["镜 03", "空的"]),
    "a table whose columns are the right ones in the wrong order": (
        PLAN_NO_ENDINGS.replace("| 分镜图 | 备注 |\n|---", "| 备注 | 分镜图 |\n|---"), ALL_STILLS, ["表头"]),
    "a still cell that is prose, not a file name": (
        PLAN_NO_ENDINGS.replace("| shot02.png |", "| 首帧 shot02.png（Codex），片段 `assets/clip02.mp4` |"), ALL_STILLS,
        ["镜 02", "首帧 shot02.png（Codex）"]),
    "a still cell that is a path out of the folder": (
        PLAN_NO_ENDINGS.replace("| shot01.png |", "| ../shot01.png |"), ALL_STILLS, ["镜 01", "../shot01.png"]),
    "a still cell that is a Windows path out of the folder": (
        PLAN_NO_ENDINGS.replace("| shot01.png |", "| ..\\shot01.png |"), ALL_STILLS, ["镜 01", "..\\shot01.png"]),
    "a table whose header has no separator line under it": (
        PLAN_NO_ENDINGS.replace("|---|---|---|---|---|---|---|\n", ""), ALL_STILLS, ["分镜表"]),
    "a named still that is not in the storyboard folder": (
        PLAN_NO_ENDINGS, ("shot01.png", "方案 B-shot03#2.png"), ["镜 02", "shot02.png"]),
    "two shot tables": (
        PLAN_NO_ENDINGS + "\n## 分镜表（旧）\n" + HEADER + "| 01 | 0.00–3.00s | 旧。 | 旧 | 图卡 | shot01.png | |\n",
        ALL_STILLS, ["分镜表"]),
    "a shot table with no shots in it": (
        PLAN_NO_ENDINGS.replace(PLAN_NO_ENDINGS[PLAN_NO_ENDINGS.index("| 01 |"):PLAN_NO_ENDINGS.index("## 变更记录")],
                                "\n"), ALL_STILLS, ["分镜表"]),
    "an open ending table with a short row": (
        PLAN_WITH_ENDINGS.replace("| 图卡 | B-shot04.png | |", "| 图卡 | B-shot04.png |"), ENDING_STILLS,
        ["方案 B（收藏引导）", "镜 04"]),
    "an open ending whose still is missing": (
        PLAN_WITH_ENDINGS, tuple(n for n in ENDING_STILLS if n != "A-shot05.png"),
        ["方案 A（留评论问题）", "镜 05", "A-shot05.png"]),
    "two open endings with the same name": (
        PLAN_WITH_ENDINGS.replace("方案 B（收藏引导）", "方案 A（留评论问题）"), ENDING_STILLS, ["方案 A（留评论问题）"]),
    "an open ending table that has no name": (
        PLAN_WITH_ENDINGS.replace("## 待定结尾：方案 B（收藏引导）", "## 待定结尾"), ENDING_STILLS, ["待定结尾"]),
}


@pytest.mark.parametrize("what", REFUSALS)
def test_the_builder_refuses_naming_the_row_and_writes_no_page(what, tmp_path):
    plan_text, stills, must_name = REFUSALS[what]
    result, page = build(tmp_path, plan_text, stills=stills)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    for name in must_name:
        assert name in result.stderr, (name, result.stderr)
    assert not page.exists()


def test_a_plan_that_is_not_there_is_refused(tmp_path):
    page = tmp_path / "page.html"
    result = subprocess.run([sys.executable, str(SCRIPT), "build", "--plan", str(tmp_path / "no-such-plan.md"),
                             "-o", str(page)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 2 and "no-such-plan.md" in result.stderr
    assert not page.exists()


# --- the script goes for approval before any still is made --------------------------------------------------
# The owner approves the topic, then the full script, then a still for every shot (a brand's settings). The script stage has
# no stills yet, so --script-only builds the same page from the same table without them and says so on each row.

NO_STILLS = ("shot01.png", "shot02.png", "方案 B-shot03#2.png")


def without_stills(plan_text: str, names=NO_STILLS) -> str:
    for name in names:
        plan_text = plan_text.replace(f"| {name} |", "|  |")
    return plan_text


def test_script_only_builds_the_page_from_a_plan_whose_stills_are_not_made_yet(tmp_path):
    result, page = build(tmp_path, without_stills(PLAN_NO_ENDINGS), stills=(), extra=("--script-only",))
    assert result.returncode == 0, result.stdout + result.stderr
    shots = read_page(page).shots
    assert [s["voice"] for s in shots] == [e["voice"] for e in SHOTS_NO_ENDINGS]
    assert [s["note"] for s in shots] == [e["note"] for e in SHOTS_NO_ENDINGS]
    assert all(s["src"] is None for s in shots)
    assert page.read_text(encoding="utf-8").count("分镜图还没出") == len(SHOTS_NO_ENDINGS)


def test_script_only_needs_no_storyboard_folder_at_all_and_still_reads_the_endings(tmp_path):
    folder = tmp_path / "视频98"
    folder.mkdir()
    (folder / "plan.md").write_text(without_stills(PLAN_WITH_ENDINGS, ENDING_STILLS), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "build", "--plan", str(folder / "plan.md"), "--script-only"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONUTF8": "1"})
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = read_page(folder / "分镜脚本-审批稿.html")
    assert parsed.switches == ["方案 A（留评论问题）", "方案 B（收藏引导）"]
    assert [s["no"] for s in parsed.shots if s["option"] == "方案 B（收藏引导）"] == ["03", "04"]


def test_without_script_only_the_same_plan_is_refused_for_its_missing_stills(tmp_path):
    result, page = build(tmp_path, without_stills(PLAN_NO_ENDINGS), stills=())
    assert result.returncode == 2 and "镜 01" in result.stderr
    assert not page.exists()


# --- writing the plan the way people do ----------------------------------------------------------------------

def test_an_ending_name_with_quotes_and_an_ampersand_still_groups_its_shots_and_names_its_switch(tmp_path):
    name = '方案 C（"收藏" & 转发）'
    plan = PLAN_WITH_ENDINGS.replace("方案 B（收藏引导）", name)
    result, page = build(tmp_path, plan, stills=ENDING_STILLS)
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = read_page(page)
    assert parsed.switches == ["方案 A（留评论问题）", name]
    assert [s["no"] for s in parsed.shots if s["option"] == name] == ["03", "04"]


def test_an_ending_heading_written_with_an_ascii_colon_is_read_too(tmp_path):
    plan = PLAN_WITH_ENDINGS.replace("## 待定结尾：方案 B（收藏引导）", "## 待定结尾: 方案 B（收藏引导）")
    result, page = build(tmp_path, plan, stills=ENDING_STILLS)
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_page(page).switches == ["方案 A（留评论问题）", "方案 B（收藏引导）"]


def test_a_pipe_written_as_backslash_pipe_stays_inside_its_cell(tmp_path):
    plan = PLAN_NO_ENDINGS.replace("| 你好，世界。 |", "| 你好\\|世界。 |")
    result, page = build(tmp_path, plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_page(page).shots[0]["voice"] == "你好|世界。"


# --- where it reads and where it writes --------------------------------------------------------------------

def test_with_only_a_plan_given_the_stills_come_from_storyboard_beside_it_and_the_page_lands_beside_it(tmp_path):
    folder = tmp_path / "视频99"
    (folder / "storyboard").mkdir(parents=True)
    for name in ("shot01.png", "shot02.png", "方案 B-shot03#2.png"):
        (folder / "storyboard" / name).write_bytes(PNG)
    (folder / "plan.md").write_text(PLAN_NO_ENDINGS, encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "build", "--plan", str(folder / "plan.md")], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    assert result.returncode == 0, result.stdout + result.stderr
    pages = sorted(p.name for p in folder.glob("*.html"))
    assert pages == ["分镜脚本-审批稿.html"]
    assert read_page(folder / pages[0]).shots[0]["src"] == "storyboard/shot01.png"


def test_a_page_saved_in_another_folder_still_reaches_its_stills_by_a_relative_path(tmp_path):
    result, page = build(tmp_path, PLAN_NO_ENDINGS)
    elsewhere = tmp_path / "视频99" / "审批" / "稿" / "page.html"
    again = subprocess.run(
        [sys.executable, str(SCRIPT), "build", "--plan", str(tmp_path / "视频99" / "plan.md"), "--storyboard",
         str(tmp_path / "视频99" / "storyboard"), "-o", str(elsewhere)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    assert result.returncode == 0 and again.returncode == 0, again.stdout + again.stderr
    assert read_page(elsewhere).shots[0]["src"] == "../../storyboard/shot01.png"


def test_the_plans_text_is_escaped_so_the_page_shows_it_instead_of_obeying_it(tmp_path):
    result, page = build(tmp_path, PLAN_NO_ENDINGS)
    assert result.returncode == 0, result.stdout + result.stderr
    raw = page.read_text(encoding="utf-8")
    assert "<C>" not in raw and "A&B" not in raw  # the second shot's voice line, written as markup would be
    assert "A&amp;B 比 &lt;C&gt; 好。" in raw
    assert not re.search(r"[A-Za-z]:\\|file://|https?://", raw)  # nothing absolute: the folder opens anywhere


# --- no open ending, no switch ---------------------------------------------------------------------------

def test_a_plan_with_no_open_ending_gets_no_switches(tmp_path):
    result, page = build(tmp_path, PLAN_NO_ENDINGS)
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = read_page(page)
    assert parsed.switches == [] and parsed.options == []
    assert all(s["option"] is None for s in parsed.shots)


# --- in a real browser: the switches switch and the stills load -----------------------------------------

@pytest.mark.usefixtures("chromium")
def test_in_a_browser_the_first_ending_shows_first_and_each_switch_shows_only_its_own_ending(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    result, page = build(tmp_path, PLAN_WITH_ENDINGS.replace("B-shot04.png", "B shot04#2.png"),
                         stills=tuple(n.replace("B-shot04.png", "B shot04#2.png") for n in ENDING_STILLS))
    assert result.returncode == 0, result.stdout + result.stderr

    def visible_voices(browser_page):
        return [el.inner_text() for el in browser_page.query_selector_all(".shot .voice") if el.is_visible()]

    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        shown = browser.new_page()
        shown.goto(page.as_uri())
        assert visible_voices(shown) == ["开头一句。", "中间一句。", "结尾甲一。", "结尾甲二。", "结尾甲三。"]
        switches = shown.query_selector_all("button.switch")
        assert [b.get_attribute("aria-pressed") for b in switches] == ["true", "false"]
        switches[1].click()
        assert visible_voices(shown) == ["开头一句。", "中间一句。", "结尾乙一。", "结尾乙二。"]
        assert [b.get_attribute("aria-pressed") for b in switches] == ["false", "true"]
        switches[0].click()
        assert visible_voices(shown)[2:] == ["结尾甲一。", "结尾甲二。", "结尾甲三。"]
        unloaded = shown.evaluate(
            "() => [...document.images].filter(i => i.offsetParent !== null && i.naturalWidth === 0).length")
        assert unloaded == 0  # every picture on show loaded: names with a space, Chinese and a # all resolve
        switches[1].click()
        assert shown.evaluate(
            "() => [...document.images].filter(i => i.offsetParent !== null && i.naturalWidth === 0).length") == 0
        browser.close()


# --- a short drama episode: the page is built from shots.json + lines.json (issue 54) ---------------------
# The format is skills/builtin/short-drama/references/shot-prompt-format.md. Expected values are the literals in the
# example episode below, never read back from the script.

import json

DRAMA_SHOTS = {
    "episode": 1, "title": "赘婿觉醒", "style_prefix": "都市港风，9:16竖屏",
    "shots": [
        {"idx": 1, "span": "0-3s", "desc": "开场钩：男主被泼酒", "prompt": "长长的生成指令甲 SECRET-PROMPT-1",
         "refs": ["C01", "S01"], "tail": "尾帧：男主抬眼，眼神变冷", "frame": "episodes/ep01/shots/shot01.png",
         "caption": "「你也配？」 SECRET-CAPTION-1", "status": "planned"},
        {"idx": 2, "span": "3-8s", "desc": "对手拍桌 & 起身 <冲突>", "prompt": "SECRET-PROMPT-2", "refs": ["C02"],
         "tail": "", "frame": "episodes/ep01/shots/镜 02#终.png", "status": "planned"},
        {"idx": 3, "span": "8-10s", "desc": "空镜：雨夜街头", "prompt": "SECRET-PROMPT-3", "refs": ["S02", "P01", "C01"],
         "tail": "尾帧：路灯闪烁", "frame": "episodes/ep01/shots/shot03.png", "status": "planned"},
    ],
}
DRAMA_LINES = [
    {"speaker": "林策", "text": "你终于来了。", "emotion": "冷笑", "shot": 2},
    {"speaker": "旁白", "text": "他等了三年。", "emotion": "平静", "shot": 1},
    {"speaker": "对手", "text": "A&B 比 <C> 好？", "emotion": "愤怒", "shot": 2, "at": 1.5},
]
DRAMA_FRAMES = ("shot01.png", "镜 02#终.png", "shot03.png")
DRAMA_EXPECTED = [
    dict(no="1", time="0-3s", voice="旁白：他等了三年。", scene="开场钩：男主被泼酒", source="C01、S01",
         note="尾帧：男主抬眼，眼神变冷"),
    dict(no="2", time="3-8s", voice="林策：你终于来了。\n对手：A&B 比 <C> 好？", scene="对手拍桌 & 起身 <冲突>",
         source="C02", note=None),
    dict(no="3", time="8-10s", voice="", scene="空镜：雨夜街头", source="S02、P01、C01", note="尾帧：路灯闪烁"),
]


def build_drama(tmp: Path, shots=None, lines=None, *, frames=DRAMA_FRAMES, extra=()):
    """Write an episode folder (shots.json, lines.json, shots/<frames>) and run the builder on it."""
    ep = tmp / "episodes" / "ep01"
    (ep / "shots").mkdir(parents=True)
    for name in frames:
        (ep / "shots" / name).write_bytes(PNG)
    (ep / "shots.json").write_text(json.dumps(DRAMA_SHOTS if shots is None else shots, ensure_ascii=False),
                                   encoding="utf-8")
    (ep / "lines.json").write_text(json.dumps(DRAMA_LINES if lines is None else lines, ensure_ascii=False),
                                   encoding="utf-8")
    page = ep / "审批稿.html"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "build", "--drama-episode", str(ep), "-o", str(page), *extra],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    return result, page


def test_a_drama_episode_page_carries_every_field_of_its_shot_list_word_for_word(tmp_path):
    result, page = build_drama(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    got = [{k: s[k] for k in ("no", "time", "voice", "scene", "source", "note")} for s in read_page(page).shots]
    assert got == DRAMA_EXPECTED


def test_a_drama_script_only_page_says_the_stills_are_not_made_and_needs_no_frame_files(tmp_path):
    shots = json.loads(json.dumps(DRAMA_SHOTS))
    for s in shots["shots"]:
        s["frame"] = None  # the script stage: no first frame exists yet
    result, page = build_drama(tmp_path, shots, frames=(), extra=("--script-only",))
    assert result.returncode == 0, result.stdout + result.stderr
    text = page.read_text(encoding="utf-8")
    assert text.count("分镜图还没出") == 3 and "<img" not in text
    assert [s["voice"] for s in read_page(page).shots] == [e["voice"] for e in DRAMA_EXPECTED]


def test_a_drama_stills_page_shows_each_frame_by_its_file_name_from_the_shots_folder(tmp_path):
    result, page = build_drama(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    srcs = [s["src"] for s in read_page(page).shots]
    assert srcs[0] == "shots/shot01.png"
    assert [(page.parent / unquote(src)).resolve() for src in srcs] == \
           [(page.parent / "shots" / name).resolve() for name in DRAMA_FRAMES]  # the name with a space and # opens


def test_a_drama_page_leaves_out_the_generation_prompt_and_the_caption(tmp_path):
    result, page = build_drama(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    text = page.read_text(encoding="utf-8")
    assert "SECRET-PROMPT" not in text and "SECRET-CAPTION" not in text and "style_prefix" not in text


def test_a_drama_page_has_no_ending_switch(tmp_path):
    result, page = build_drama(tmp_path)
    parsed = read_page(page)
    assert parsed.switches == [] and parsed.options == []


def _drama(edit=None, lines_edit=None):
    shots, lines = json.loads(json.dumps(DRAMA_SHOTS)), json.loads(json.dumps(DRAMA_LINES))
    if edit:
        edit(shots["shots"])
    if lines_edit:
        lines_edit(lines)
    return shots, lines


def _drop(shot_index, key):
    return lambda shots: shots[shot_index].pop(key)


DRAMA_REFUSALS = {
    "a shot with no idx": (_drama(_drop(1, "idx")), DRAMA_FRAMES, ["idx"]),
    "a shot with no span": (_drama(_drop(1, "span")), DRAMA_FRAMES, ["镜 2", "span"]),
    "a shot with no desc": (_drama(_drop(2, "desc")), DRAMA_FRAMES, ["镜 3", "desc"]),
    "a line whose shot matches no shot": (
        _drama(lines_edit=lambda lines: lines.append({"speaker": "路人", "text": "哎？", "shot": 9})), DRAMA_FRAMES,
        ["lines.json", "shot 9"]),
    "a line with no shot": (
        _drama(lines_edit=lambda lines: lines.append({"speaker": "路人", "text": "哎？"})), DRAMA_FRAMES,
        ["lines.json", "路人：哎？", "shot"]),
    "a frame file that is not in the shots folder": (_drama(), ("shot01.png", "shot03.png"), ["镜 2", "镜 02#终.png"]),
    "a shot with no frame at the stills stage": (_drama(lambda shots: shots[0].update(frame=None)), DRAMA_FRAMES,
                                                 ["镜 1", "frame"]),
}


@pytest.mark.parametrize("what", DRAMA_REFUSALS)
def test_a_drama_episode_that_cannot_be_read_stops_the_build_naming_the_shot(what, tmp_path):
    (shots, lines), frames, must_name = DRAMA_REFUSALS[what]
    result, page = build_drama(tmp_path, shots, lines, frames=frames)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    for name in must_name:
        assert name in result.stderr, (name, result.stderr)
    assert "Traceback" not in result.stderr
    assert not page.exists()


def test_a_drama_folder_without_its_shot_list_is_refused(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "build", "--drama-episode", str(tmp_path / "ep77")],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 2 and "shots.json" in result.stderr and "Traceback" not in result.stderr


def test_build_without_a_plan_or_a_drama_episode_is_refused(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "build"], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8")
    assert result.returncode == 2 and "--plan" in result.stderr and "Traceback" not in result.stderr
