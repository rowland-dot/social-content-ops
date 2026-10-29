"""Style references without a product image on the Codex subscription route (issue 108).

The real-pack layer fallback has Codex draw only the scene: the card's reference lends light, scene and
composition, and no product image is passed in the product role. Seam: `ai_image.py img2img
--style-image` (fake `codex` on PATH, as in test_codex_image_identity.py). No real image is drawn.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "codex_image_identity_helpers", Path(__file__).with_name("test_codex_image_identity.py"))
_ident = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ident)
AI_IMAGE, run = _ident.AI_IMAGE, _ident.run
world, listening, pictures = _ident.world, _ident.listening, _ident.pictures  # fixtures, by name

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake codex is a POSIX script")


def _styled(w, styles, *, images=(), identity=(), env_extra=None):
    args = ["img2img", "--prompt", "empty flat table top, soft window light", "--size", "3:4",
            "--output", str(w.root / "outputs/post/out.png")]
    for s in styles:
        args += ["--style-image", str(w.tmp / s)]
    for i in images:
        args += ["--image", str(w.tmp / i)]
    for i in identity:
        args += ["--identity-image", str(w.tmp / i)]
    return run(w, AI_IMAGE, *args, env_extra=env_extra)


def _imgs(argv):
    return [argv[i + 1] for i, t in enumerate(argv) if t == "-i"]


def test_style_images_alone_reach_codex_with_no_product_role(pictures):
    proc = _styled(pictures, ["style-main.png", "style-support.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _imgs(call["argv"]) == [str(pictures.tmp / "style-main.png"),
                                   str(pictures.tmp / "style-support.png")]
    prompt = call["prompt"]
    assert "Image 1 is the main style reference" in prompt
    assert "Image 2 is the supporting style reference" in prompt
    assert "none of its products, people, hands or words" in prompt
    assert "No product or pack is drawn unless the prompt describes one." in prompt
    assert "Image 1 is the product" not in prompt


def test_one_style_image_is_a_style_reference_and_the_identity_image_stays_last(pictures):
    proc = _styled(pictures, ["style-main.png"], identity=["model.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _imgs(call["argv"]) == [str(pictures.tmp / "style-main.png"), str(pictures.tmp / "model.png")]
    assert "Image 1 is a style reference" in call["prompt"]
    assert "Image 2 is the identity reference" in call["prompt"]
    assert "is the product" not in call["prompt"]


def test_style_image_with_product_image_is_refused_before_codex_starts(pictures):
    proc = _styled(pictures, ["style-main.png"], images=["pack.png"])
    assert proc.returncode == 1
    assert "--style-image" in proc.stderr
    assert pictures.calls() == []


def test_a_third_style_image_is_refused_before_codex_starts(pictures):
    proc = _styled(pictures, ["style-main.png", "style-support.png", "extra.png"])
    assert proc.returncode == 1
    assert "at most 2" in proc.stderr
    assert pictures.calls() == []


def test_style_image_needs_the_codex_route(pictures):
    proc = _styled(pictures, ["style-main.png"], env_extra={"IMG_PROVIDER": ""})
    assert proc.returncode == 1
    assert "IMG_PROVIDER=codex" in proc.stderr
    assert pictures.calls() == []
