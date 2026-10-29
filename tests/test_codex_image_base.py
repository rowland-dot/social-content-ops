"""An approved card as the base image on the Codex subscription route (issue 115).

The owner's step 5 (CLAUDE.md, "Photo-scene post images follow one approval process"): "A change to an approved
card keeps the approved version and changes only what the owner named" ("Redraw and keep the same hand and
background as I approved."). Seams (the issue's "Agreed seams"): the command line `ai_image.py img2img`
with its separate `--base-image` option, the helper's own command line (`codex_image.py`, used by the
WeChat script), and behind them `generate_png`, the prompt and the `codex` arguments. Only the outside
world is faked: a `codex` program on PATH that records its arguments and the prompt on standard input (the
`listening` fixture of test_codex_image_roles.py). No real image is drawn. Expected values are literals.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "codex_image_roles_helpers_for_base", Path(__file__).with_name("test_codex_image_roles.py"))
_roles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_roles)
AI_IMAGE, REPO, run = _roles.AI_IMAGE, _roles.REPO, _roles.run
world = _roles.world  # fixtures, used by name
listening = _roles.listening

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake codex is a POSIX script")

HELPER = REPO / "skills/shared/scripts/codex_image.py"
CHANGE = "same hand and background as I approved, only the cup is now blue"

PRODUCT_LINE = "Image 1 is the product: keep its shape, colours and printed label exactly."
BASE_LINE = ("Image 2 is the base image: keep this image's drawing as it is (hand, background, props, "
             "composition, colour) and change only what the prompt names.")
STYLE_LOOK = ("take only its look (light, scene, composition, lettering style), none of its products, "
              "people, hands or words.")


@pytest.fixture
def pictures(listening):
    for name in ("product.png", "approved.png", "model.png", "approved-2.png"):
        (listening.tmp / name).write_bytes((listening.tmp / "pack.png").read_bytes())
    return listening


def _img2img(w, images: list[str], base: list[str] | None = None, identity: list[str] | None = None, *,
             env_extra: dict | None = None):
    args = ["img2img", "--prompt", CHANGE, "--size", "3:4",
            "--output", str(w.root / "outputs/post/out.png")]
    for image in images:
        args += ["--image", str(w.tmp / image)]
    for image in base or []:
        args += ["--base-image", str(w.tmp / image)]
    for image in identity or []:
        args += ["--identity-image", str(w.tmp / image)]
    return run(w, AI_IMAGE, *args, env_extra=env_extra)


def _image_arguments(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, token in enumerate(argv) if token == "-i"]


def _helper(w, *args: str, stdin: bytes = CHANGE.encode()):
    return subprocess.run([sys.executable, str(HELPER), "--ratio", "3:4", *args], input=stdin,
                          env=w.env, cwd=w.tmp, capture_output=True, timeout=120)


def test_the_issue_command_img2img_image_product_base_image_approved_reaches_codex_in_that_order(pictures):
    # The issue's own words: `img2img --image product.png --base-image approved.png`, reaching Codex as
    # `-i product.png -i approved.png`, with image 2 named as the base image and not as a style reference.
    proc = run(pictures, AI_IMAGE, "img2img", "--image", "product.png", "--base-image", "approved.png",
               "--prompt", CHANGE, "--size", "3:4", "--output", str(pictures.root / "outputs/post/out.png"))
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == ["product.png", "approved.png"]
    prompt = call["prompt"]
    assert PRODUCT_LINE in prompt
    assert BASE_LINE in prompt
    assert "style reference" not in prompt
    assert "none of its products, people, hands or words" not in prompt


def test_the_base_image_is_not_an_image_it_does_not_count_against_the_three_and_is_never_by_order(pictures):
    # Three plain --image plus a base image: the three stay product + two style references, the base is extra.
    proc = _img2img(pictures, ["product.png", "style-main.png", "style-support.png"], ["approved.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / n) for n in
                                              ("product.png", "approved.png", "style-main.png",
                                               "style-support.png")]


def test_product_base_and_one_style_reference_are_numbered_in_attachment_order(pictures):
    proc = _img2img(pictures, ["product.png", "style-main.png"], ["approved.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / n) for n in
                                              ("product.png", "approved.png", "style-main.png")]
    prompt = call["prompt"]
    assert PRODUCT_LINE in prompt
    assert BASE_LINE in prompt
    assert f"Image 3 is a style reference: {STYLE_LOOK}" in prompt
    assert "Image 2 is a style reference" not in prompt


def test_product_two_styles_identity_and_base_together_are_five_images_numbered_in_attachment_order(pictures):
    proc = _img2img(pictures, ["product.png", "style-main.png", "style-support.png"], ["approved.png"],
                    ["model.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / n) for n in
                                              ("product.png", "approved.png", "style-main.png",
                                               "style-support.png", "model.png")]
    prompt = call["prompt"]
    assert PRODUCT_LINE in prompt
    assert BASE_LINE in prompt
    assert f"Image 3 is the main style reference: {STYLE_LOOK}" in prompt
    assert f"Image 4 is the supporting style reference: {STYLE_LOOK}" in prompt
    assert ("Image 5 is the identity reference: keep this person recognisably the same (face and "
            "identity) and redraw them in the pose, angle and clothing the prompt describes.") in prompt


def test_one_image_past_the_new_total_of_five_is_refused_before_codex_is_started_naming_the_limit(pictures):
    proc = _img2img(pictures, ["product.png", "style-main.png", "style-support.png", "extra.png"],
                    ["approved.png"], ["model.png"])
    assert proc.returncode == 1
    assert "at most 5" in proc.stderr
    assert pictures.calls() == []


def test_a_second_base_image_is_refused_before_codex_is_started_naming_the_limit(pictures):
    proc = _img2img(pictures, ["product.png"], ["approved.png", "approved-2.png"])
    assert proc.returncode == 1
    assert "at most 1 base image" in proc.stderr
    assert pictures.calls() == []


def test_a_base_image_with_no_product_image_is_refused_before_codex_is_started(pictures):
    proc = _img2img(pictures, [], ["approved.png"])
    assert proc.returncode == 1
    assert pictures.calls() == []
    # with an identity image beside it there is still no image 1, so it is refused the same way
    proc = _img2img(pictures, [], ["approved.png"], ["model.png"])
    assert proc.returncode == 1
    assert "product image" in proc.stderr
    assert pictures.calls() == []


def test_without_the_codex_route_a_base_image_is_refused_naming_the_codex_setting_and_nothing_is_sent(pictures):
    # issue 95: without the setting every generate command stops with the one plain message
    proc = _img2img(pictures, ["product.png"], ["approved.png"], env_extra={"IMG_PROVIDER": ""})
    assert proc.returncode == 1
    assert "IMG_PROVIDER=codex" in proc.stderr
    assert pictures.calls() == []


def test_the_helper_command_line_takes_the_base_image_as_its_own_option(pictures):
    done = _helper(pictures, "--image", str(pictures.tmp / "product.png"),
                   "--base-image", str(pictures.tmp / "approved.png"))
    assert done.returncode == 0, done.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / "product.png"),
                                              str(pictures.tmp / "approved.png")]
    assert BASE_LINE in call["prompt"]
    assert "style reference" not in call["prompt"]


def test_the_helper_command_line_refuses_a_second_base_image_before_codex_is_started(pictures):
    done = _helper(pictures, "--image", str(pictures.tmp / "product.png"),
                   "--base-image", str(pictures.tmp / "approved.png"),
                   "--base-image", str(pictures.tmp / "approved-2.png"))
    assert done.returncode == 1
    assert b"at most 1 base image" in done.stderr
    assert pictures.calls() == []


def test_the_codex_helper_function_takes_base_as_a_keyword_and_refuses_it_without_a_product(pictures,
                                                                                            monkeypatch):
    spec = importlib.util.spec_from_file_location("codex_image_under_test_for_base", HELPER)
    codex_image = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codex_image)
    for key, value in pictures.env.items():
        monkeypatch.setenv(key, value)
    assert codex_image.generate_png("x", images=[str(pictures.tmp / "product.png")],
                                    base=str(pictures.tmp / "approved.png"))
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / "product.png"),
                                              str(pictures.tmp / "approved.png")]
    assert BASE_LINE in call["prompt"]
    with pytest.raises(codex_image.CodexImageError):
        codex_image.generate_png("x", base=str(pictures.tmp / "approved.png"))
    assert len(pictures.calls()) == 1  # the refused call never started codex


def test_calls_that_pass_no_base_image_send_exactly_the_same_arguments_and_prompt_as_before(pictures):
    proc = _img2img(pictures, ["product.png", "style-main.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert call["argv"] == ["exec", "--json", "--skip-git-repo-check", "-s", "read-only", "--ephemeral",
                            "-i", str(pictures.tmp / "product.png"),
                            "-i", str(pictures.tmp / "style-main.png")]
    assert call["prompt"].splitlines()[:2] == [
        f"Use your built-in image_gen tool to make one new image from the attached images: {CHANGE}",
        f"Attached images, in the order given: {PRODUCT_LINE} Image 2 is a style reference: {STYLE_LOOK}"]
    assert "base image" not in call["prompt"]


# ── The help text and the skill texts ─────────────────────────────────────────────────────────────

SKILLS = REPO / "skills/builtin"


def test_the_image_help_text_describes_the_base_image_role():
    done = subprocess.run([sys.executable, str(AI_IMAGE), "img2img", "--help"], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    flat = " ".join(done.stdout.split())
    assert "--base-image" in flat
    assert "底图" in flat
    assert "已批准" in flat
    assert "不是风格参考" in flat


def test_the_image_skill_documents_the_base_image_role_and_the_new_total():
    text = (SKILLS / "ai-image-gen/SKILL.md").read_text(encoding="utf-8")
    for need in (
        "--base-image",
        "底图",
        "至多 1 张",
        "共最多 5 张",
        "只改提示词点名的地方",
        "商品图，不能没有",
    ):
        assert need in text, f"ai-image-gen does not say: {need}"
