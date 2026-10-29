"""auto-short-video assembler: how burned-in subtitles break into lines (issue 30).

Every test goes through the assembler's SRT-to-ASS step, the step that decides where each caption
breaks, and reads the Dialogue lines it writes (lines are joined by the ASS soft break `\\N`).
Nothing here recomputes the assembler's own line limit: the font size is the only input, the
expected breaks are literals.

Reference answer: Easel's hand-broken subtitles for video 01 (2026-10-16), the
"断行一览.json" next to the sample renders (96 px and 84 px).

Set ASSEMBLE_UNDER_TEST to another assemble.py to run the same tests against it (the committed
version, or an older copy). Needs jieba (Easel's .venv in WSL has it).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(os.environ.get("ASSEMBLE_UNDER_TEST") or ROOT / "skills/builtin/auto-short-video/scripts/assemble.py")

# Chinese and English punctuation that must never open a subtitle line.
NO_LINE_START = "，。、？！：；）」』”’》…,.?!:;)%"

# The nine sentences of video 01, as the voice-over says them.
VIDEO01 = [
    "燕麦蛋白，到底早上喝，还是晚上喝？",
    "答案比你想的简单：什么时候喝都行。",
    "立冬天冷，早上加进热咖啡、热豆浆，燕麦肽冷热都能冲。",
    "上班装一勺去工位，温水摇一摇也行。",
    "晚上习惯喝杯温牛奶，就顺手放进牛奶里。",
    "比起几点喝，更要紧的是每天都记得喝。",
    "挑一件你天天都会做的事，跟它绑在一起。",
    "你打算把它放进一天里的哪个时间？",
    "评论区说说。",
]


def _load():
    spec = importlib.util.spec_from_file_location("assemble_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def asm():
    return _load()


def _srt(captions: list[str]) -> str:
    return "\n".join(
        f"{i}\n00:00:{i - 1:02d},000 --> 00:00:{i:02d},000\n{c}\n" for i, c in enumerate(captions, 1)
    )


def _wrapped(asm, tmp_path, captions: list[str], size: int, **kwargs) -> list[list[str]]:
    """The lines each caption breaks into at `size` px on a 1080x1920 video."""
    srt = tmp_path / "t.srt"
    ass = tmp_path / "t.ass"
    srt.write_text(_srt(captions), encoding="utf-8")
    asm._srt_to_ass(srt, ass, 1080, 1920, font_size=size, **kwargs)
    rows = [ln for ln in ass.read_text(encoding="utf-8").splitlines() if ln.startswith("Dialogue:")]
    return [ln.split(",", 9)[9].split("\\N") for ln in rows]  # the Text field is the tenth


# Easel's hand-broken lines for video 01 (断行一览.json). Literals from that file, not computed.
REF_96 = [
    ["燕麦蛋白，到底早上喝，", "还是晚上喝？"],
    ["答案比你想的简单：", "什么时候喝都行。"],
    ["立冬天冷，早上加进热咖啡、", "热豆浆，燕麦肽冷热都能冲。"],
    ["上班装一勺去工位，", "温水摇一摇也行。"],
    ["晚上习惯喝杯温牛奶，", "就顺手放进牛奶里。"],
    ["比起几点喝，", "更要紧的是每天都记得喝。"],
    ["挑一件你天天都会做的事，", "跟它绑在一起。"],
    ["你打算把它放进", "一天里的哪个时间？"],
    ["评论区说说。"],
]


# ---- 1. no line starts with punctuation; a caption that fits one line is left alone ----------

@pytest.mark.parametrize("size", [54, 72, 84, 96])
def test_no_subtitle_line_starts_with_punctuation(asm, tmp_path, size):
    captions = VIDEO01 + ["一二三四五六七八九十一二三四五六七八，九"]
    for caption, lines in zip(captions, _wrapped(asm, tmp_path, captions, size)):
        assert "".join(lines) == caption, f"text changed at {size} px: {lines}"
        starts = [ln[0] for ln in lines]
        assert not any(ch in NO_LINE_START for ch in starts), f"{size} px: {lines}"


@pytest.mark.parametrize("size", [54, 96])
def test_a_short_caption_stays_on_one_line(asm, tmp_path, size):
    assert _wrapped(asm, tmp_path, ["你好", "评论区说说。"], size) == [["你好"], ["评论区说说。"]]


# ---- 2. lines are as wide as the glyphs really are, balanced, broken at a pause --------------

def test_96px_breaks_match_the_hand_broken_reference_for_every_sentence(asm, tmp_path):
    assert _wrapped(asm, tmp_path, VIDEO01, 96) == REF_96


def test_84px_breaks_match_the_reference_and_sentence_8_stays_in_two_lines(asm, tmp_path):
    got = _wrapped(asm, tmp_path, VIDEO01, 84)
    # Sentence 8 (index 7) fits one line only with the reference's narrower side margins, so
    # it is checked by property; every other sentence breaks exactly as the reference does.
    assert got[:7] + got[8:] == REF_96[:7] + REF_96[8:]
    assert 1 <= len(got[7]) <= 2 and "".join(got[7]) == VIDEO01[7]


# ---- 3. lines break between words, never inside a brand word -----------------------------------

# Without help the word splitter reads 燕麦肽 as 燕麦 + 肽, and the balanced break lands between them.
KEEP_CAPTION = "每天早上喝一勺燕麦肽冷热水都能冲泡"


def test_a_keep_word_is_never_split_across_two_lines(asm, tmp_path):
    (plain,) = _wrapped(asm, tmp_path, [KEEP_CAPTION], 96)
    if any("燕麦肽" in ln for ln in plain):
        pytest.skip("the word splitter already keeps 燕麦肽 whole, so this caption proves nothing")
    (lines,) = _wrapped(asm, tmp_path, [KEEP_CAPTION], 96, keep_words=["燕麦肽"])
    assert "".join(lines) == KEEP_CAPTION
    assert len(lines) == 2 and any("燕麦肽" in ln for ln in lines), lines


@pytest.mark.parametrize("size", [84, 96])
def test_english_words_are_never_glued_together_at_a_break(asm, tmp_path, size):
    # The old wrapper dropped the space where it broke, burning "ornight" / "morningor".
    caption = "Oatmeal, morning or night? It works either way"
    (lines,) = _wrapped(asm, tmp_path, [caption], size)
    assert " ".join(lines) == caption, lines
    assert 1 <= len(lines) <= 2 and all(ln == ln.strip() for ln in lines), lines


def test_a_two_line_caption_is_not_a_full_line_plus_one_character(asm, tmp_path):
    # 21 characters at 96 px (about 13 fit a line): breaking at the only comma would leave 19 + 2,
    # which does not fit, so the break has to land mid-way instead of after a full line.
    caption = "一二三四五六七八九十一二三四五六七八，九十"
    (lines,) = _wrapped(asm, tmp_path, [caption], 96)
    assert len(lines) == 2 and min(map(len, lines)) >= 6, lines


# ---- 4. the real command line: keep words reach the burned subtitles; too long is refused -------
#
# These run `assemble.py assemble` itself. A stand-in `ffmpeg` first on PATH records every call it
# gets and keeps a copy of the subtitle file handed to it, then runs the real ffmpeg. That shows
# what is actually burned, and that a refusal happens before any ffmpeg work.

cli = pytest.mark.skipif(
    os.name != "posix" or shutil.which("ffmpeg") is None, reason="needs a POSIX shell and ffmpeg"
)

TOO_LONG = "今天早上起来第一件事就是先喝一杯温水然后再冲一勺燕麦肽慢慢地喝下去"  # 32 characters


@pytest.fixture
def spy(tmp_path):
    real = shutil.which("ffmpeg")
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "ffmpeg"
    shim.write_text(
        """#!/bin/sh
echo "$*" >> "$SPY_LOG"
for a in "$@"; do
  case "$a" in
    subtitles=*) cp "$(printf %s "${a#subtitles=}" | tr -d "'")" "$SPY_ASS" ;;
  esac
done
exec "$REAL_FFMPEG" "$@"
"""
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    log, ass = tmp_path / "ffmpeg-calls.log", tmp_path / "burned.ass"
    env = {**os.environ, "PATH": f"{shim_dir}:{os.environ['PATH']}", "SPY_LOG": str(log),
           "SPY_ASS": str(ass), "REAL_FFMPEG": real}
    image = tmp_path / "shot.png"
    subprocess.run([real, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=1080x1920:d=1",
                    "-frames:v", "1", str(image)], check=True)

    def run(caption: str, extra: dict | None = None, image_path: Path = image, sub_size: str | None = "96"):
        sb = {"size": "1080x1920", "shots": [{"image": str(image_path), "duration": 1, "caption": caption}], **(extra or {})}
        sbf = tmp_path / "sb.json"
        sbf.write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
        ass.unlink(missing_ok=True)
        log.unlink(missing_ok=True)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "assemble", "--storyboard", str(sbf), "-o", str(tmp_path / "out.mp4"),
             *(["--sub-size", sub_size] if sub_size else [])], env=env, capture_output=True, text=True)
        calls = log.read_text().splitlines() if log.exists() else []
        burned = ass.read_text(encoding="utf-8") if ass.exists() else None
        return proc, calls, burned

    return run


def _burned_lines(ass_text: str) -> list[str]:
    row = next(ln for ln in ass_text.splitlines() if ln.startswith("Dialogue:"))
    return row.split(",", 9)[9].split("\\N")


@cli
def test_storyboard_keep_words_reach_the_burned_subtitles(spy):
    proc, _, plain = spy(KEEP_CAPTION)
    assert proc.returncode == 0, proc.stderr
    if any("燕麦肽" in ln for ln in _burned_lines(plain)):
        pytest.skip("the word splitter already keeps 燕麦肽 whole, so this caption proves nothing")
    proc, _, burned = spy(KEEP_CAPTION, {"subtitle_keep_words": ["燕麦肽"]})
    assert proc.returncode == 0, proc.stderr
    assert any("燕麦肽" in ln for ln in _burned_lines(burned)), burned


@cli
def test_a_caption_that_needs_three_lines_is_refused_before_any_ffmpeg_work(spy, tmp_path):
    missing_image = tmp_path / "not-made-yet.png"   # if the refusal came late, this would be the error
    proc, calls, _ = spy(TOO_LONG, image_path=missing_image)
    assert proc.returncode != 0
    assert TOO_LONG in proc.stderr and "96" in proc.stderr and "3" in proc.stderr, proc.stderr
    assert "不存在" not in proc.stderr
    assert calls == [], f"ffmpeg was already running: {calls}"


@cli
@pytest.mark.parametrize("bad", ["燕麦肽", [1], [""], {"燕麦肽": 1}])
def test_a_malformed_keep_word_list_is_refused_before_any_ffmpeg_work(spy, bad):
    proc, calls, _ = spy("你好", {"subtitle_keep_words": bad})
    assert proc.returncode != 0 and "subtitle_keep_words" in proc.stderr, proc.stderr
    assert calls == []


# ---- 5. the skill text tells Easel about the keep list and the two-line rule -------------------

SKILL = ROOT / "skills/builtin/auto-short-video/SKILL.md"


def test_skill_says_where_the_keep_words_come_from_and_states_the_two_line_rule():
    text = SKILL.read_text(encoding="utf-8")
    assert "subtitle_keep_words" in text.split("## Profile 感知")[0], "storyboard example must show the field"
    profile_section = text.split("## Profile 感知")[1]
    assert "subtitle_keep_words" in profile_section and "字幕规格" in profile_section, profile_section
    assert "最多 2 行" in text


# ---- 6. subtitle size comes from the storyboard (issue 44) -------------------------------------
#
# Same real command line and stand-in ffmpeg as section 4, but without the --sub-size flag unless a
# test names one. The size is read back from the Default style line of the subtitle file ffmpeg was
# handed; the expected numbers are literals (96 is the size the owner chose for video 01).

def _burned_size(ass_text: str) -> int:
    style = next(ln for ln in ass_text.splitlines() if ln.startswith("Style: Default,"))
    return int(style.split(",")[2])  # Name, Fontname, Fontsize


@cli
@pytest.mark.parametrize("size", [96, 72])
def test_a_storyboard_size_reaches_the_burned_subtitles_with_no_flag(spy, size):
    proc, _, burned = spy("你好", {"subtitle_size": size}, sub_size=None)
    assert proc.returncode == 0, proc.stderr
    assert _burned_size(burned) == size


@cli
def test_with_no_size_anywhere_the_default_54_is_burned(spy):
    proc, _, burned = spy("你好", sub_size=None)
    assert proc.returncode == 0, proc.stderr
    assert _burned_size(burned) == 54


@cli
def test_the_command_line_size_wins_over_the_storyboard_size(spy):
    proc, _, burned = spy("你好", {"subtitle_size": 96}, sub_size="72")
    assert proc.returncode == 0, proc.stderr
    assert _burned_size(burned) == 72


@cli
def test_line_breaks_follow_the_storyboard_size(spy):
    # 18 characters: one line at 54 px (about 24 fit), two at 96 px (about 13 fit)
    caption = "一二三四五六七八九十一二三四五六七八"
    _, _, small = spy(caption, sub_size=None)
    _, _, large = spy(caption, {"subtitle_size": 96}, sub_size=None)
    assert len(_burned_lines(small)) == 1
    assert len(_burned_lines(large)) == 2


@cli
@pytest.mark.parametrize("bad", [0, -5, "big", "96", 96.5, True, [96]])
def test_a_storyboard_size_that_is_not_a_positive_whole_number_is_refused_before_any_ffmpeg_work(spy, bad):
    proc, calls, _ = spy("你好", {"subtitle_size": bad}, sub_size=None)
    assert proc.returncode != 0 and "subtitle_size" in proc.stderr, proc.stderr
    assert calls == []


@cli
@pytest.mark.parametrize("flag", [None, "72"])
def test_a_size_with_a_ready_made_ass_file_is_refused_not_ignored(spy, tmp_path, flag):
    ready = tmp_path / "ready.ass"
    ready.write_text(READY_ASS, encoding="utf-8")
    extra = {"subtitle": str(ready), **({"subtitle_size": 96} if flag is None else {})}
    proc, calls, _ = spy("你好", extra, sub_size=flag)
    assert proc.returncode != 0, "the size was silently ignored"
    assert "ASS" in proc.stderr and "SRT" in proc.stderr, proc.stderr
    assert calls == []


@cli
def test_a_ready_made_ass_file_with_no_size_set_is_burned_unchanged(spy, tmp_path):
    ready = tmp_path / "ready.ass"
    ready.write_text(READY_ASS, encoding="utf-8")
    proc, calls, burned = spy("你好", {"subtitle": str(ready)}, sub_size=None)
    assert proc.returncode == 0, proc.stderr
    assert burned == READY_ASS and calls


READY_ASS = (
    "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
    "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Default,Noto Sans CJK SC,80,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,2,0,2,65,65,134,1\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,你好\n"
)

# The skill text that tells Easel to copy the brand's size into the storyboard is checked beside the skill,
# in skills/builtin/auto-short-video/video01-lessons.test.py (test_k4_...).
