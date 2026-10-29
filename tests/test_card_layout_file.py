"""render_card.py saves a layout file beside every card picture (issue 50).

Seam: the command line of skills/shared/scripts/render_card.py, run for real against headless
Chromium. For each picture it saves, it must also save `<picture name>.layout.json` next to it, in
picture pixels: the rendered text lines, and every note (a block with its own background that holds
text). The picture's own backdrop, inline highlighter backgrounds and picture frames with no text are
not notes. The subtitle-over-card check in the assembler reads this file.

Pages are built from absolutely positioned boxes, so every expected number is a literal that follows
from the CSS written in the test, never from what the script returns.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/shared/scripts/render_card.py"

RESET = "*{margin:0;padding:0;box-sizing:border-box}"
CARD = ".card{position:relative;width:1080px;height:1920px;overflow:hidden;margin-bottom:20px;" \
       "background:#FBF8F3 radial-gradient(#E3DCCF 2px,transparent 2.4px) 0 0/40px 40px}"
ABS = "position:absolute;"


def render(*args: str):
    return subprocess.run([sys.executable, str(SCRIPT), "--wait", "100", *args],
                          capture_output=True, text=True, timeout=180)


def layout_of(picture: Path) -> dict:
    file = picture.with_name(picture.stem + ".layout.json")
    assert file.is_file(), f"no layout file beside {picture.name}: {sorted(p.name for p in picture.parent.iterdir())}"
    return json.loads(file.read_text(encoding="utf-8"))


def notes(layout: dict) -> list[list[int]]:
    return sorted(b["box"] for b in layout["boxes"] if b["kind"] == "note")


def texts(layout: dict) -> list[dict]:
    return [b for b in layout["boxes"] if b["kind"] == "text"]


def end_card_page(tmp_path: Path) -> Path:
    """One 1080x1920 card shaped like video 01's end card, plus one example of each thing that is NOT a note."""
    body = (
        # a paper sheet over the whole card with its own background: the backdrop, not a note
        f"<div id='paper' style='{ABS}left:0;top:0;width:1080px;height:1920px;background:#fffdf8'>"
        f"<div style='{ABS}left:84px;top:112px;font-size:84px;line-height:100px;white-space:nowrap'>燕麦肽，早上喝</div>"
        # the comment note: x 82-998, y 1309-1515
        f"<div id='note' style='{ABS}left:82px;top:1309px;width:916px;height:206px;padding:34px 42px;"
        f"font-size:42px;line-height:1.5;background:#F1E9F4'>你打算把它放进一天里的哪个时间？<br>评论区说说。</div>"
        # a note turned a quarter turn: its box is the upright bounding box of the turned note
        f"<div style='{ABS}left:100px;top:600px;width:300px;height:100px;background:#FFF4D2;transform:rotate(90deg);"
        f"font-size:40px'>转</div>"
        # an inline highlighter background on a word: a text line, not a note
        f"<div style='{ABS}left:500px;top:300px;font-size:40px'>先<span style='background:#ffcb43'>高亮</span>后</div>"
        # a white picture frame holding no text: not a note
        f"<div style='{ABS}left:700px;top:600px;width:200px;height:200px;background:#fff'></div>"
        # a note running off the card's right edge is cut to the picture; one wholly outside is left out
        f"<div style='{ABS}left:1000px;top:1700px;width:200px;height:100px;background:#FFF4D2'>出界</div>"
        f"<div style='{ABS}left:1300px;top:1700px;width:200px;height:100px;background:#FFF4D2'>屏外</div>"
        "</div>"
    )
    page = tmp_path / "cards.html"
    page.write_text(f"<!doctype html><meta charset='utf-8'><style>{RESET}{CARD}</style>"
                    f"<body><section class='card' id='end'>{body}</section></body>", encoding="utf-8")
    return page


@pytest.mark.usefixtures("chromium")
def test_the_layout_file_sits_beside_the_picture_and_covers_the_whole_picture(tmp_path):
    out = tmp_path / "card.png"
    r = render("--html", str(end_card_page(tmp_path)), "--out", str(out), "--selector", ".card", "--preset", "video")
    assert r.returncode == 0, r.stdout + r.stderr
    layout = layout_of(out)
    assert (layout["width"], layout["height"]) == (1080, 1920)


@pytest.mark.usefixtures("chromium")
def test_only_blocks_with_their_own_background_and_text_are_notes(tmp_path):
    out = tmp_path / "card.png"
    r = render("--html", str(end_card_page(tmp_path)), "--out", str(out), "--selector", ".card", "--preset", "video")
    assert r.returncode == 0, r.stdout + r.stderr
    # the comment note, the turned note's upright bounding box, the note cut at the picture's edge;
    # not the paper sheet, the highlighter, the frame or the note wholly outside the picture
    layout = layout_of(out)
    assert notes(layout) == [[82, 1309, 998, 1515], [200, 500, 300, 800], [1000, 1700, 1080, 1800]]
    assert not any("屏外" in b["text"] for b in layout["boxes"]), layout["boxes"]


@pytest.mark.usefixtures("chromium")
def test_every_rendered_text_line_is_listed_where_it_is_drawn(tmp_path):
    out = tmp_path / "card.png"
    r = render("--html", str(end_card_page(tmp_path)), "--out", str(out), "--selector", ".card", "--preset", "video")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = texts(layout_of(out))
    title = [t for t in lines if "燕麦肽" in t["text"]]
    assert len(title) == 1
    x0, y0, x1, y1 = title[0]["box"]
    assert x0 == 84 and x1 - x0 > 300, title      # starts at the CSS left edge and is several characters wide
    assert abs((y0 + y1) / 2 - 162) <= 2, title   # centred in its 100 px line that starts at y 112
    in_note = [t for t in lines if 1309 <= t["box"][1] and t["box"][3] <= 1515 and 82 <= t["box"][0]]
    assert any("评论区说说" in t["text"] for t in in_note), lines
    assert any("高亮" in t["text"] for t in lines), "text inside a highlighter span is still a text line"


@pytest.mark.usefixtures("chromium")
def test_each_card_of_a_batch_gets_its_own_layout_measured_from_its_own_corner(tmp_path):
    cards = ("".join(
        f"<section class='card'>{extra}</section>" for extra in (
            "<div style='%sleft:700px;top:50px;font-size:30px'>one</div>" % ABS,
            "<div style='%sleft:10px;top:20px;width:100px;height:50px;background:#F1E9F4'>two</div>" % ABS)))
    page = tmp_path / "batch.html"
    page.write_text(f"<!doctype html><meta charset='utf-8'><style>{RESET}{CARD}</style><body>{cards}</body>",
                    encoding="utf-8")
    outdir = tmp_path / "cards"
    r = render("--html", str(page), "--out-dir", str(outdir), "--all", ".card", "--preset", "video")
    assert r.returncode == 0, r.stdout + r.stderr
    assert notes(layout_of(outdir / "card_1.png")) == []
    assert notes(layout_of(outdir / "card_2.png")) == [[10, 20, 110, 70]]   # not shifted by the first card's 1940 px


@pytest.mark.usefixtures("chromium")
def test_boxes_are_in_picture_pixels_so_a_scale_of_two_doubles_them(tmp_path):
    page = tmp_path / "small.html"
    page.write_text(
        f"<!doctype html><meta charset='utf-8'><style>{RESET}.c{{position:relative;width:400px;height:300px}}</style>"
        # the card sits 200 px down and 50 px in from the page's corner: boxes are still counted from the card's own corner
        f"<div style='height:200px'></div><div class='c' style='margin-left:50px'>"
        f"<div style='{ABS}left:10px;top:20px;width:100px;height:50px;background:#F1E9F4'>n</div></div>",
        encoding="utf-8")
    out = tmp_path / "small.png"
    r = render("--html", str(page), "--out", str(out), "--selector", ".c")   # default scale 2: an 800x600 picture
    assert r.returncode == 0, r.stdout + r.stderr
    layout = layout_of(out)
    assert (layout["width"], layout["height"]) == (800, 600)
    assert notes(layout) == [[20, 40, 220, 140]]


@pytest.mark.usefixtures("chromium")
def test_a_full_page_picture_gets_a_layout_in_page_coordinates(tmp_path):
    page = tmp_path / "poster.html"
    page.write_text(
        f"<!doctype html><meta charset='utf-8'><style>{RESET}body{{position:relative;width:400px;height:300px}}</style>"
        f"<div style='{ABS}left:10px;top:20px;width:100px;height:50px;background:#F1E9F4'>n</div>"
        # below the body's 300 px, but part of the page: the full-page picture is 570 px tall
        f"<div style='{ABS}left:10px;top:520px;width:100px;height:50px;background:#F1E9F4'>m</div>",
        encoding="utf-8")
    out = tmp_path / "poster.png"
    r = render("--html", str(page), "--out", str(out), "--full-page", "--width", "400", "--height", "300", "--scale", "1")
    assert r.returncode == 0, r.stdout + r.stderr
    layout = layout_of(out)
    assert (layout["width"], layout["height"]) == (400, 570)
    assert notes(layout) == [[10, 20, 110, 70], [10, 520, 110, 570]]


@pytest.mark.usefixtures("chromium")
def test_a_jpeg_picture_gets_the_same_kind_of_layout_file(tmp_path):
    out = tmp_path / "card.jpg"
    r = render("--html", str(end_card_page(tmp_path)), "--out", str(out), "--selector", ".card", "--preset", "video",
               "--format", "jpeg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert notes(layout_of(out)) == [[82, 1309, 998, 1515], [200, 500, 300, 800], [1000, 1700, 1080, 1800]]
