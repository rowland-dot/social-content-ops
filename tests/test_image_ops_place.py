"""image_ops.py place: lay a cut-out RGBA layer on a scene with a code-made contact shadow (issue 108).

Seam: the command line `image_ops.py place`. Scene and pack are synthetic stand-ins built in memory
with Pillow; the real background-removal model is not used. Expected values are literals.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

OPS = Path(__file__).resolve().parents[1] / "skills/shared/scripts/image_ops.py"
BG = (200, 200, 200, 255)


def _run(*args: str):
    return subprocess.run([sys.executable, str(OPS), "place", *map(str, args)],
                          capture_output=True, text=True, timeout=60)


@pytest.fixture
def files(tmp_path):
    Image.new("RGBA", (200, 200), BG).save(tmp_path / "scene.png")
    # 60x40 pack stand-in: left 20 columns transparent, the rest opaque with a per-pixel pattern
    pack = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
    for x in range(20, 60):
        for y in range(40):
            pack.putpixel((x, y), (x * 4, y * 6, 90, 255))
    pack.save(tmp_path / "pack.png")
    return tmp_path


def test_pack_pixels_come_through_unchanged_and_position_follows_the_fractions(files):
    # width 0.3 of 200 = 60 px = the layer's own width, so no resampling; centre (0.5, 0.5) -> top-left (70, 80)
    proc = _run("--scene", files / "scene.png", "--layer", files / "pack.png", "--x", 0.5, "--y", 0.5,
                "--width", 0.3, "-o", files / "out.png")
    assert proc.returncode == 0, proc.stderr
    out = Image.open(files / "out.png").convert("RGBA")
    assert out.size == (200, 200)
    for (lx, ly) in ((20, 0), (35, 17), (59, 39)):
        assert out.getpixel((70 + lx, 80 + ly)) == (lx * 4, ly * 6, 90, 255)
    assert out.getpixel((70 + 5, 80 + 20)) == BG  # transparent part of the layer leaves the scene as it was
    assert out.getpixel((5, 5)) == BG


def test_width_fraction_scales_evenly_keeping_the_aspect(files):
    Image.new("RGBA", (60, 40), (250, 0, 0, 255)).save(files / "solid.png")
    proc = _run("--scene", files / "scene.png", "--layer", files / "solid.png", "--x", 0.5, "--y", 0.5,
                "--width", 0.6, "-o", files / "out.png", "--shadow-opacity", 0)
    assert proc.returncode == 0, proc.stderr
    out = Image.open(files / "out.png").convert("RGBA")
    # 120x80 box centred at (100,100) -> x 40..159, y 60..139
    changed = [(x, y) for x in range(200) for y in range(200) if out.getpixel((x, y)) != BG]
    xs, ys = [p[0] for p in changed], [p[1] for p in changed]
    assert (min(xs), max(xs), min(ys), max(ys)) == (40, 159, 60, 139)
    assert out.getpixel((100, 100)) == (250, 0, 0, 255)


def test_shadow_falls_on_the_side_away_from_the_light_and_nowhere_else(files):
    proc = _run("--scene", files / "scene.png", "--layer", files / "pack.png", "--x", 0.5, "--y", 0.5,
                "--width", 0.3, "-o", files / "out.png", "--shadow-dx", 0.2, "--shadow-dy", 0.0,
                "--shadow-blur", 0.01, "--shadow-opacity", 0.5)
    assert proc.returncode == 0, proc.stderr
    out = Image.open(files / "out.png").convert("RGBA")
    right = out.getpixel((70 + 60 + 4, 100))  # just right of the pack (box ends at x=130)
    assert right[0] < 190 and right[3] == 255
    assert out.getpixel((70 - 6, 100)) == BG  # light side stays clean
    assert out.getpixel((100, 80 - 6)) == BG  # above stays clean
    assert out.getpixel((5, 5)) == BG


def test_record_keeps_photo_position_scale_and_shadow_settings(files):
    proc = _run("--scene", files / "scene.png", "--layer", files / "pack.png", "--x", 0.4, "--y", 0.6,
                "--width", 0.3, "-o", files / "out.png", "--record", files / "rec.json",
                "--shadow-dx", 0.1, "--shadow-dy", 0.05, "--shadow-blur", 0.02, "--shadow-opacity", 0.4)
    assert proc.returncode == 0, proc.stderr
    rec = json.loads((files / "rec.json").read_text(encoding="utf-8"))
    assert rec == {"layer": str(files / "pack.png"), "scene": str(files / "scene.png"),
                   "x": 0.4, "y": 0.6, "width": 0.3, "scale": 1.0,
                   "shadow": {"dx": 0.1, "dy": 0.05, "blur": 0.02, "opacity": 0.4}}


@pytest.mark.parametrize("bad", [["--width", 0], ["--width", 1.5], ["--x", 1.2], ["--y", -0.1]])
def test_bad_fractions_fail_with_a_message_and_write_nothing(files, bad):
    args = ["--scene", files / "scene.png", "--layer", files / "pack.png", "--x", 0.5, "--y", 0.5,
            "--width", 0.3, "-o", files / "out.png"]
    for i in range(0, len(bad), 2):
        args[args.index(bad[i]) + 1] = bad[i + 1]
    proc = _run(*args)
    assert proc.returncode != 0
    assert "ERROR" in proc.stderr
    assert not (files / "out.png").exists()


def test_missing_layer_file_fails_with_a_message(files):
    proc = _run("--scene", files / "scene.png", "--layer", files / "nope.png", "--x", 0.5, "--y", 0.5,
                "--width", 0.3, "-o", files / "out.png")
    assert proc.returncode != 0 and "ERROR" in proc.stderr
