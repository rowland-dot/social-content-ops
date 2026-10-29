"""Product-state source images on the Codex subscription route (issue 109).

A card that shows the powder, an opened pack or the mixed drink gets the real image of that state
from this brand's own product. Seam: `ai_image.py img2img --state-image` (fake `codex` on PATH, as in
test_codex_image_identity.py). Expected values are literals. No real image is drawn.
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
world, listening = _ident.world, _ident.listening  # fixtures, by name

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake codex is a POSIX script")

STATE_ROLE = ("is a state reference: it shows the real state of this brand's own product (colour, texture, "
              "clarity, the inside of the pack). Copy that look only; do not borrow its scene, props, "
              "people, hands or words.")


@pytest.fixture
def pictures(listening):
    for name in ("state-1.png", "state-2.png", "state-3.png", "model.png", "base.png"):
        (listening.tmp / name).write_bytes((listening.tmp / "pack.png").read_bytes())
    return listening


def _draw(w, *, images=("pack.png",), states=(), identity=(), base=(), env_extra=None):
    args = ["img2img", "--prompt", "a scoop of powder over a glass", "--size", "3:4",
            "--output", str(w.root / "outputs/post/out.png")]
    for flag, names in (("--image", images), ("--state-image", states),
                        ("--identity-image", identity), ("--base-image", base)):
        for n in names:
            args += [flag, str(w.tmp / n)]
    return run(w, AI_IMAGE, *args, env_extra=env_extra)


def _imgs(argv):
    return [argv[i + 1] for i, t in enumerate(argv) if t == "-i"]


def test_state_image_follows_the_product_and_is_labelled_a_state_reference(pictures):
    proc = _draw(pictures, states=["state-1.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _imgs(call["argv"]) == [str(pictures.tmp / "pack.png"), str(pictures.tmp / "state-1.png")]
    assert "Image 1 is the product: keep its shape, colours and printed label exactly." in call["prompt"]
    assert f"Image 2 {STATE_ROLE}" in call["prompt"]
    assert "style reference" not in call["prompt"]


def test_numbering_follows_attachment_order_product_style_two_states_identity(pictures):
    proc = _draw(pictures, images=["pack.png", "style-main.png"], states=["state-1.png", "state-2.png"],
                 identity=["model.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _imgs(call["argv"]) == [str(pictures.tmp / n) for n in
                                   ("pack.png", "style-main.png", "state-1.png", "state-2.png", "model.png")]
    prompt = call["prompt"]
    assert "Image 2 is a style reference" in prompt
    assert f"Image 3 {STATE_ROLE}" in prompt
    assert f"Image 4 {STATE_ROLE}" in prompt
    assert "Image 5 is the identity reference" in prompt


def test_base_image_stays_second_and_states_come_after_the_styles(pictures):
    proc = _draw(pictures, images=["pack.png", "style-main.png"], states=["state-1.png"], base=["base.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _imgs(call["argv"]) == [str(pictures.tmp / n) for n in
                                   ("pack.png", "base.png", "style-main.png", "state-1.png")]
    assert "Image 2 is the base image" in call["prompt"]
    assert "Image 3 is a style reference" in call["prompt"]
    assert f"Image 4 {STATE_ROLE}" in call["prompt"]


def test_a_third_state_image_is_refused_before_codex_starts(pictures):
    proc = _draw(pictures, states=["state-1.png", "state-2.png", "state-3.png"])
    assert proc.returncode == 1
    assert "at most 2" in proc.stderr
    assert pictures.calls() == []


def test_state_image_without_a_product_image_is_refused_before_codex_starts(pictures):
    proc = _draw(pictures, images=(), states=["state-1.png"], identity=["model.png"])
    assert proc.returncode == 1
    assert "--state-image" in proc.stderr
    assert pictures.calls() == []


def test_state_image_needs_the_codex_route(pictures):
    proc = _draw(pictures, states=["state-1.png"], env_extra={"IMG_PROVIDER": ""})
    assert proc.returncode == 1
    assert "IMG_PROVIDER=codex" in proc.stderr
    assert pictures.calls() == []


def test_calls_without_a_state_image_are_unchanged(pictures):
    proc = _draw(pictures, images=["pack.png", "style-main.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert "state reference" not in call["prompt"]
