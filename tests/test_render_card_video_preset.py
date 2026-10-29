"""render_card.py --preset video (issue 48): one flag renders a card at exactly 1080x1920.

Seam: the command line of skills/shared/scripts/render_card.py, run for real against headless
Chromium (the only thing it talks to is a local HTML file). The expected sizes are literals taken
from the issue: video 01's own card page (three 1080x1920 cards, 20 px apart) renders 2160x3840
by default, and as a full page it is 1080x5820 (3 x 1920 + 3 x 20).

Sizes are read straight from the PNG header with struct, never through the script's own helper.
"""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/shared/scripts/render_card.py"


CSS = "*{margin:0;padding:0;box-sizing:border-box}.card{width:1080px;height:1920px;margin-bottom:20px;background:#fbf8f3}"


def page(tmp_path: Path, cards: int) -> Path:
    body = "".join(f'<section class="card" id="c{i}">card {i}</section>' for i in range(1, cards + 1))
    html = tmp_path / "cards.html"
    html.write_text(f"<!doctype html><meta charset='utf-8'><style>{CSS}</style><body>{body}</body>",
                    encoding="utf-8")
    return html


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    return struct.unpack(">II", head[16:24])


def render(*args: str):
    return subprocess.run([sys.executable, str(SCRIPT), "--wait", "100", *args],
                          capture_output=True, text=True, timeout=180)


@pytest.mark.usefixtures("chromium")
def test_video_preset_with_a_selector_saves_a_1080x1920_card(tmp_path):
    out = tmp_path / "card.png"
    r = render("--html", str(page(tmp_path, 1)), "--out", str(out), "--preset", "video",
               "--selector", ".card")
    assert r.returncode == 0, r.stdout + r.stderr
    assert png_size(out) == (1080, 1920)


@pytest.mark.usefixtures("chromium")
def test_video_preset_saves_every_card_of_a_batch_at_1080x1920(tmp_path):
    outdir = tmp_path / "cards"
    r = render("--html", str(page(tmp_path, 3)), "--out-dir", str(outdir), "--all", ".card",
               "--preset", "video")
    assert r.returncode == 0, r.stdout + r.stderr
    files = sorted(outdir.glob("*.png"))
    assert len(files) == 3
    assert [png_size(f) for f in files] == [(1080, 1920)] * 3


@pytest.mark.usefixtures("chromium")
def test_video_preset_checks_every_card_of_a_batch_not_just_the_first(tmp_path):
    html = tmp_path / "mixed.html"
    html.write_text(f"<!doctype html><meta charset='utf-8'><style>{CSS}.short{{height:1600px}}</style><body>"
                    "<section class='card'>ok</section><section class='card short'>short</section></body>",
                    encoding="utf-8")
    outdir = tmp_path / "cards"
    r = render("--html", str(html), "--out-dir", str(outdir), "--all", ".card", "--preset", "video")
    assert r.returncode == 4, r.stdout + r.stderr
    assert "card_2.png" in r.stderr and "1080x1600" in r.stderr, r.stderr
    assert "card_1.png" not in r.stderr, "the correctly sized card was reported as wrong"


@pytest.mark.usefixtures("chromium")
def test_video_preset_as_a_jpeg_is_checked_too(tmp_path):
    Image = pytest.importorskip("PIL.Image")

    out = tmp_path / "card.jpg"
    r = render("--html", str(page(tmp_path, 1)), "--out", str(out), "--preset", "video",
               "--selector", ".card", "--format", "jpeg")
    assert r.returncode == 0, r.stdout + r.stderr
    with Image.open(out) as img:
        assert img.size == (1080, 1920)


@pytest.mark.usefixtures("chromium")
def test_video_preset_fails_and_names_the_size_when_a_full_page_of_three_cards_is_taller(tmp_path):
    out = tmp_path / "card.png"
    r = render("--html", str(page(tmp_path, 3)), "--out", str(out), "--preset", "video",
               "--selector", ".card", "--full-page")
    assert r.returncode == 4, r.stdout + r.stderr
    assert "1080x5820" in r.stderr, r.stderr
    assert "card.png" in r.stderr, r.stderr
    assert "1080x1920" in r.stderr, r.stderr


def test_video_preset_cannot_be_combined_with_explicit_size_flags(tmp_path):
    out = tmp_path / "card.png"
    r = render("--html", str(page(tmp_path, 1)), "--out", str(out), "--preset", "video",
               "--selector", ".card", "--scale", "2")
    assert r.returncode == 2, r.stdout + r.stderr
    # argparse's own "unrecognized arguments: --preset" also exits 2 and mentions both words, so
    # that answer must be ruled out: the refusal has to come from a preset that exists.
    assert "unrecognized arguments" not in r.stderr, r.stderr
    reason = r.stderr.strip().splitlines()[-1]  # the error line itself, not the usage block above it
    assert "--preset video" in reason and "--scale" in reason, reason
    assert not out.exists()


@pytest.mark.usefixtures("chromium")
def test_without_the_preset_the_same_render_is_still_2160x3840(tmp_path):
    out = tmp_path / "card.png"
    r = render("--html", str(page(tmp_path, 3)), "--out", str(out), "--selector", ".card")
    assert r.returncode == 0, r.stdout + r.stderr
    assert png_size(out) == (2160, 3840)
