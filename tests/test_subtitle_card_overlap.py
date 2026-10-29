"""auto-short-video assembler: report where burned subtitles cover a card's text or note (issue 50).

Seam: the `assemble` command line of skills/builtin/auto-short-video/scripts/assemble.py, run for
real (ffmpeg) on video 01's own subtitle file (the hand-broken 96 px ASS, MarginV 280) and the
card layout that render_card.py saves beside the card picture. The card layout here is written by
hand from the numbers measured on video 01's end card (issue 50 triage notes): the comment note box
x 82-998, y 1309-1515 and its three text lines. One test at the end runs the real render_card.py on a
page with the same note, so the file the card maker writes and the file the check reads are proved to
agree (that one needs Chromium and is skipped where Chromium cannot start).

Expected numbers are literals from the issue, never recomputed from the assembler's own formula:
- the burned subtitle box is y 1440-1640 (two lines of 96 px with a 2 px outline, 280 px from the bottom);
- it covers the note from y 1440 to 1515, and the text line "评论区说说。" from y 1440 to 1473;
- the card starts at 18.76 s; the first cue (15.18-19.05 s) is on the card for 0.29 s, the next two
  (19.05-22.62 s and 22.62-25.93 s) for their whole length, 3.57 s and 3.31 s.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "builtin" / "auto-short-video" / "scripts" / "assemble.py"
RENDER_CARD = ROOT / "skills" / "shared" / "scripts" / "render_card.py"

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

# Video 01's subtitle file (a video's assets/字幕-96px-手动断行.ass), MarginV made a parameter.
ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans CJK SC,96,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,54,54,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:03.57,Default,,0,0,0,,燕麦蛋白，到底早上喝，\\N还是晚上喝？
Dialogue: 0,0:00:03.57,0:00:06.88,Default,,0,0,0,,答案比你想的简单：\\N什么时候喝都行。
Dialogue: 0,0:00:06.88,0:00:12.05,Default,,0,0,0,,立冬天冷，早上加进热咖啡、\\N热豆浆，燕麦肽冷热都能冲。
Dialogue: 0,0:00:12.05,0:00:15.18,Default,,0,0,0,,上班装一勺去工位，\\N温水摇一摇也行。
Dialogue: 0,0:00:15.18,0:00:19.05,Default,,0,0,0,,晚上习惯喝杯温牛奶，\\N就顺手放进牛奶里。
Dialogue: 0,0:00:19.05,0:00:22.62,Default,,0,0,0,,比起几点喝，\\N更要紧的是每天都记得喝。
Dialogue: 0,0:00:22.62,0:00:25.93,Default,,0,0,0,,挑一件你天天都会做的事，\\N跟它绑在一起。
"""

# The end card's boxes as measured on video 01 (image pixels, 1080x1920).
END_CARD_LAYOUT = {
    "width": 1080,
    "height": 1920,
    "boxes": [
        {"kind": "note", "text": "你打算把它放进一天里的哪个时间？评论区说说。", "box": [82, 1309, 998, 1515]},
        {"kind": "text", "text": "你打算把它放进一天里的", "box": [124, 1345, 587, 1414]},
        {"kind": "text", "text": "哪个时间？", "box": [586, 1353, 797, 1418]},
        {"kind": "text", "text": "评论区说说。", "box": [123, 1408, 376, 1473]},
        # two text bits at the card's edges, level with the subtitles but outside the 54 px side margins
        {"kind": "text", "text": "边角", "box": [1040, 1500, 1075, 1560]},
        {"kind": "text", "text": "左边", "box": [10, 1500, 40, 1560]},
    ],
}

CARD_STARTS_AT = 18.76
VIDEO_SECONDS = 25.93


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _picture(path: Path, color: str, size: str = "1080x1920") -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"color=c={color}:s={size}:d=1", "-frames:v", "1", str(path))
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Video:
    """One storyboard of two stills (a filler, then the card) with video 01's subtitles over it."""

    def __init__(self, tmp_path: Path, margin_v: int = 280):
        self.tmp = tmp_path
        self.filler = _picture(tmp_path / "filler.png", "white")
        self.card = _picture(tmp_path / "card.png", "pink")
        self.layout = tmp_path / "card.layout.json"
        self.layout.write_text(json.dumps(END_CARD_LAYOUT, ensure_ascii=False), encoding="utf-8")
        self.ass = tmp_path / "sub.ass"
        self.ass.write_text(ASS.format(margin_v=margin_v), encoding="utf-8")
        self.out = tmp_path / "final.mp4"

    def storyboard(self, **over) -> dict:
        board = {
            "size": "1080x1920", "image_motion": "static", "subtitle": str(self.ass),
            "shots": [{"image": str(self.filler), "duration": CARD_STARTS_AT},
                      {"image": str(self.card), "duration": round(VIDEO_SECONDS - CARD_STARTS_AT, 2)}],
        }
        board.update(over)
        return board

    def assemble(self, board: dict | None = None, *flags: str) -> subprocess.CompletedProcess:
        sb_file = self.tmp / "sb.json"
        sb_file.write_text(json.dumps(board or self.storyboard()), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "assemble", "--storyboard", str(sb_file), "-o", str(self.out), *flags],
            cwd=ROOT, capture_output=True, text=True,
        )


def _lines(result: subprocess.CompletedProcess, *needles: str) -> list[str]:
    return [ln for ln in result.stdout.splitlines() if all(n in ln for n in needles)]


# --- a layout that overlaps: video 01's real case --------------------------------------------------

@needs_ffmpeg
def test_the_note_is_reported_for_every_cue_that_is_on_the_card_with_the_pixel_range_and_seconds(tmp_path):
    video = Video(tmp_path)
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    spill, full_a, full_b = (_lines(result, "便签", c) for c in ("15.18–19.05", "19.05–22.62", "22.62–25.93"))
    assert len(spill) == 1 and "镜头 2" in spill[0] and "y 1440–1515" in spill[0] and "0.29" in spill[0], result.stdout
    assert len(full_a) == 1 and "y 1440–1515" in full_a[0] and "3.57" in full_a[0], result.stdout
    assert len(full_b) == 1 and "y 1440–1515" in full_b[0] and "3.31" in full_b[0], result.stdout


@needs_ffmpeg
def test_a_text_line_the_subtitles_reach_is_reported_and_text_they_miss_is_not(tmp_path):
    result = Video(tmp_path).assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "评论区说说", "y 1440–1473"), result.stdout
    # these two lines end at y 1414 and 1418, above the subtitle box that starts at 1440
    assert not _lines(result, "文字「你打算"), result.stdout
    assert not _lines(result, "文字「哪个时间"), result.stdout
    assert "边角" not in result.stdout and "左边" not in result.stdout, result.stdout   # beside the subtitle box, not under it


@needs_ffmpeg
def test_cues_that_are_not_on_the_card_are_not_reported(tmp_path):
    result = Video(tmp_path).assemble()
    for cue in ("0.00–3.57", "3.57–6.88", "6.88–12.05", "12.05–15.18"):
        assert cue not in result.stdout, f"cue {cue} s is not on the card but was reported: {result.stdout}"
    assert not _lines(result, "镜头 1", "盖住"), "the filler shot was reported as covered"


@needs_ffmpeg
def test_the_check_changes_nothing_and_the_exit_status_is_the_same(tmp_path):
    video = Video(tmp_path)
    before = (_digest(video.ass), _digest(video.layout), _digest(video.card))
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert video.out.is_file() and video.out.stat().st_size > 0
    assert (_digest(video.ass), _digest(video.layout), _digest(video.card)) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        ["filler.png", "card.png", "card.layout.json", "sub.ass", "sb.json", "final.mp4"]), "the check left a file behind"


# --- a layout that is clear ------------------------------------------------------------------------

@needs_ffmpeg
def test_subtitles_moved_down_until_they_clear_the_note_report_no_overlap(tmp_path):
    result = Video(tmp_path, margin_v=150).assemble()   # box y 1570-1770, below the note's 1515
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "镜头 2", "没有重叠"), result.stdout
    assert "盖住" not in result.stdout, result.stdout


@needs_ffmpeg
def test_subtitles_that_only_touch_the_notes_bottom_edge_do_not_overlap(tmp_path):
    result = Video(tmp_path, margin_v=205).assemble()   # box y 1515-1715: shares the line y 1515, covers nothing
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "镜头 2", "没有重叠"), result.stdout
    assert "盖住" not in result.stdout, result.stdout


@needs_ffmpeg
def test_subtitles_one_pixel_into_the_note_overlap(tmp_path):
    result = Video(tmp_path, margin_v=206).assemble()   # box y 1514-1714: one pixel inside the note
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "便签", "y 1514–1515"), result.stdout


# --- what is read from the burned subtitle file ----------------------------------------------------------

@needs_ffmpeg
def test_a_cue_with_its_own_bottom_margin_is_measured_with_that_margin(tmp_path):
    video = Video(tmp_path)
    video.ass.write_text(ASS.format(margin_v=280).replace("Default,,0,0,0,,晚上习惯", "Default,,0,0,150,,晚上习惯"),
                         encoding="utf-8")   # only the cue 15.18-19.05 sits lower: box y 1570-1770, clear of the note
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert not _lines(result, "便签", "15.18–19.05"), result.stdout
    assert _lines(result, "便签", "19.05–22.62", "y 1440–1515"), result.stdout


@needs_ffmpeg
def test_a_subtitle_file_with_a_different_play_resolution_is_scaled_to_the_video(tmp_path):
    video = Video(tmp_path)
    half = (ASS.format(margin_v=140).replace("PlayResX: 1080", "PlayResX: 540").replace("PlayResY: 1920", "PlayResY: 960")
            .replace("Noto Sans CJK SC,96,", "Noto Sans CJK SC,48,").replace("0,0,1,2,0,2,54,54,", "0,0,1,1,0,2,27,27,"))
    video.ass.write_text(half, encoding="utf-8")   # everything half size: the same burned box, y 1440-1640
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "便签", "15.18–19.05", "y 1440–1515"), result.stdout


@needs_ffmpeg
def test_subtitles_that_are_not_bottom_aligned_are_not_called_clear(tmp_path):
    video = Video(tmp_path)
    video.ass.write_text(ASS.format(margin_v=280).replace("0,0,1,2,0,2,54,54,", "0,0,1,2,0,8,54,54,"), encoding="utf-8")
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "镜头 2", "不是底部对齐"), result.stdout
    assert "没有重叠" not in result.stdout and "盖住" not in result.stdout, result.stdout


@needs_ffmpeg
def test_a_cue_whose_text_has_ascii_commas_still_counts_its_two_lines(tmp_path):
    video = Video(tmp_path)
    video.ass.write_text(ASS.format(margin_v=280).replace(
        "晚上习惯喝杯温牛奶，\\N就顺手放进牛奶里。", "Warm milk, at night, works\\Nfor me, too."), encoding="utf-8")
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "便签", "15.18–19.05", "y 1440–1515"), result.stdout   # two lines, not one


# --- shots that cannot be checked are said so, never called clear --------------------------------------

@needs_ffmpeg
def test_an_image_shot_with_no_layout_file_is_listed_as_not_checked_and_never_as_clear(tmp_path):
    video = Video(tmp_path)
    video.layout.unlink()
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "镜头 2", "未检查", "没有版面文件", "card.layout.json"), result.stdout
    assert "没有重叠" not in result.stdout, result.stdout


@needs_ffmpeg
def test_a_layout_file_that_cannot_be_read_is_not_checked_and_the_video_is_still_made(tmp_path):
    video = Video(tmp_path)
    video.layout.write_text("{not json", encoding="utf-8")
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert video.out.is_file()
    assert _lines(result, "镜头 2", "未检查"), result.stdout
    assert "没有重叠" not in result.stdout, result.stdout


@needs_ffmpeg
def test_a_layout_file_with_a_broken_box_entry_does_not_stop_the_video(tmp_path):
    video = Video(tmp_path)
    video.layout.write_text(json.dumps({**END_CARD_LAYOUT, "boxes": [{"kind": "note"}]}), encoding="utf-8")
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert video.out.is_file() and video.out.stat().st_size > 0
    assert "没能运行" in result.stdout and "成片不受影响" in result.stdout, result.stdout


@needs_ffmpeg
def test_a_layout_for_a_differently_sized_picture_is_not_checked(tmp_path):
    video = Video(tmp_path)
    video.layout.write_text(json.dumps({**END_CARD_LAYOUT, "width": 2160, "height": 3840}), encoding="utf-8")
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "镜头 2", "未检查", "2160x3840"), result.stdout
    assert "没有重叠" not in result.stdout and "盖住" not in result.stdout, result.stdout


@needs_ffmpeg
def test_a_card_that_the_video_zooms_is_not_checked(tmp_path):
    video = Video(tmp_path)
    board = video.storyboard(image_motion="ken-burns")   # the default: the picture is zoomed while it plays
    result = video.assemble(board)
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "镜头 2", "未检查", "缩放"), result.stdout
    assert "盖住" not in result.stdout, result.stdout


@needs_ffmpeg
def test_a_shot_can_be_static_even_when_the_video_default_is_not(tmp_path):
    video = Video(tmp_path)
    board = video.storyboard(image_motion="ken-burns")
    board["shots"][1]["motion"] = "static"
    result = video.assemble(board)
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "便签", "y 1440–1515"), result.stdout


# --- the subtitle box comes from what is burned, including subtitles the assembler builds ------------------

@needs_ffmpeg
def test_subtitles_the_assembler_builds_from_captions_are_measured_from_the_style_it_burns(tmp_path):
    video = Video(tmp_path)
    board = {
        "size": "1080x1920", "image_motion": "static", "subtitle_size": 96,
        "shots": [{"image": str(video.card), "duration": 3.0, "caption": "燕麦蛋白，到底早上喝，还是晚上喝？"}],
    }
    result = video.assemble(board, "--sub-margin-v", "280")
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "便签", "y 1440–1515", "3.00"), result.stdout   # same box as the ready-made ASS


@needs_ffmpeg
def test_a_one_line_caption_makes_a_shorter_box_that_clears_the_note(tmp_path):
    video = Video(tmp_path)
    board = {
        "size": "1080x1920", "image_motion": "static", "subtitle_size": 96,
        "shots": [{"image": str(video.card), "duration": 3.0, "caption": "什么时候喝都行"}],
    }
    result = video.assemble(board, "--sub-margin-v", "280")   # one line: box y 1540-1640, under the note's 1515
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "镜头 1", "没有重叠"), result.stdout


# --- the card maker's own layout file and this check agree ----------------------------------------------

NOTE_PAGE = (
    "<!doctype html><meta charset='utf-8'><style>*{margin:0;padding:0;box-sizing:border-box}"
    ".card{position:relative;width:1080px;height:1920px;overflow:hidden;background:#FBF8F3}"
    ".note{position:absolute;left:82px;top:1309px;width:916px;height:206px;padding:34px 42px;"
    "font-size:42px;line-height:1.5;background:#F1E9F4}</style>"
    "<section class='card'><div class='note'>你打算把它放进一天里的哪个时间？<br>评论区说说。</div></section>"
)


@needs_ffmpeg
@pytest.mark.usefixtures("chromium")
def test_a_card_rendered_by_the_card_maker_is_checked_end_to_end(tmp_path):
    video = Video(tmp_path)
    page = tmp_path / "cards.html"
    page.write_text(NOTE_PAGE, encoding="utf-8")
    video.card.unlink()
    video.layout.unlink()
    rendered = subprocess.run(
        [sys.executable, str(RENDER_CARD), "--wait", "100", "--html", str(page), "--out", str(video.card),
         "--selector", ".card", "--preset", "video"], capture_output=True, text=True, timeout=180)
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    result = video.assemble()
    assert result.returncode == 0, result.stderr[-600:]
    assert _lines(result, "便签", "y 1440–1515", "0.29"), result.stdout
    assert not _lines(result, "镜头 2", "未检查"), result.stdout   # (the plain filler shot has no layout, and says so)
