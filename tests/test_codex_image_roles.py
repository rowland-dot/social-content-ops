"""Image editing with roles on the Codex subscription route (issue 58).

Seams (the issue's "Agreed seams"): the command line `ai_image.py img2img --image` (one value or
more) and, behind it, the shared Codex helper that builds the prompt and the `codex` arguments.
The only thing faked is the outside world: a `codex` program on PATH that records its arguments and
the prompt it was given on standard input. Expected values are literals.
"""
from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

# Loaded by file path: under --import-mode=importlib, `tests` is also the name of the WeChat
# publisher's test package, so `from tests.test_codex_image_route import ...` fails in a full run.
_spec = importlib.util.spec_from_file_location(
    "codex_image_route_helpers", Path(__file__).with_name("test_codex_image_route.py"))
_route = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_route)
AI_IMAGE, FAKE_CODEX, PNG_BYTES, REPO, run = (
    _route.AI_IMAGE, _route.FAKE_CODEX, _route.PNG_BYTES, _route.REPO, _route.run)
world = _route.world  # a fixture, used by name

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake codex is a POSIX script")

# The prompt a single-image edit has always produced; it must not change.
OLD_SINGLE_IMAGE_PROMPT = (
    "Use your built-in image_gen tool to edit the attached image: warm light, keep the pack\n"
    "Aspect ratio: 3:4.\n"
    "Rules: use only the built-in image_gen tool. Do not call the OpenAI API, do not use or "
    "ask for an API key, do not run image_gen.py or any CLI fallback, do not write scripts. "
    "If the built-in image_gen tool is not available, reply exactly CODEX_IMAGE_TOOL_MISSING "
    "and stop. When the image has been created, reply DONE."
)


@pytest.fixture
def listening(world):
    """The same fake codex, now also recording the prompt it receives on standard input."""
    recording = FAKE_CODEX.replace('{{"argv": argv,', '{{"argv": argv, "prompt": sys.stdin.read(),')
    assert recording != FAKE_CODEX
    exe = world.bin / "codex"
    exe.write_text(recording.format(python=sys.executable, png_hex=PNG_BYTES.hex()), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    for name in ("pack.png", "style-main.png", "style-support.png", "extra.png"):
        (world.tmp / name).write_bytes(PNG_BYTES)
    return world


def _img2img(w, *images: str, size: str = "3:4"):
    args = ["img2img", "--prompt", "warm light, keep the pack", "--size", size,
            "--output", str(w.root / "outputs/post/out.png")]
    for image in images:
        args += ["--image", str(w.tmp / image)]
    return run(w, AI_IMAGE, *args)


def _image_arguments(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, token in enumerate(argv) if token == "-i"]


def test_two_images_reach_codex_product_first_and_the_prompt_names_both_roles(listening):
    proc = _img2img(listening, "pack.png", "style-main.png")
    assert proc.returncode == 0, proc.stderr
    (call,) = listening.calls()
    assert _image_arguments(call["argv"]) == [str(listening.tmp / "pack.png"),
                                              str(listening.tmp / "style-main.png")]
    prompt = call["prompt"]
    assert "Image 1 is the product" in prompt
    assert "keep its shape, colours and printed label exactly" in prompt
    assert "Image 2 is a style reference" in prompt
    assert "none of its products, people, hands or words" in prompt


def test_three_images_name_one_product_and_two_style_references(listening):
    proc = _img2img(listening, "pack.png", "style-main.png", "style-support.png")
    assert proc.returncode == 0, proc.stderr
    (call,) = listening.calls()
    assert _image_arguments(call["argv"]) == [str(listening.tmp / n) for n in
                                              ("pack.png", "style-main.png", "style-support.png")]
    prompt = call["prompt"]
    assert "Image 1 is the product" in prompt
    assert "Image 2 is the main style reference" in prompt
    assert "Image 3 is the supporting style reference" in prompt


def test_a_single_image_edit_sends_exactly_the_arguments_and_prompt_it_always_did(listening):
    proc = _img2img(listening, "pack.png")
    assert proc.returncode == 0, proc.stderr
    (call,) = listening.calls()
    assert call["argv"] == ["exec", "--json", "--skip-git-repo-check", "-s", "read-only",
                            "--ephemeral", "-i", str(listening.tmp / "pack.png")]
    assert call["prompt"] == OLD_SINGLE_IMAGE_PROMPT


def test_more_than_three_images_are_refused_before_codex_is_started(listening):
    proc = _img2img(listening, "pack.png", "style-main.png", "style-support.png", "extra.png")
    assert proc.returncode == 1
    assert "at most 3" in proc.stderr
    assert "at most 4" in proc.stderr  # issue 92: the cap rises by the one identity slot
    assert "at most 5" in proc.stderr  # issue 115: and by the one base-image slot, on purpose
    assert listening.calls() == []


def test_a_missing_second_image_is_an_error_naming_the_file(listening):
    proc = _img2img(listening, "pack.png", "no-such-style.png")
    assert proc.returncode == 1
    assert "no-such-style.png" in proc.stderr


def test_several_images_without_the_codex_route_are_refused_not_silently_dropped(listening):
    proc = run(listening, AI_IMAGE, "img2img", "--prompt", "x", "--output", str(listening.root / "outputs/post/out.png"),
               "--image", str(listening.tmp / "pack.png"),
               "--image", str(listening.tmp / "style-main.png"),
               env_extra={"IMG_PROVIDER": ""})
    assert proc.returncode == 1
    assert "Codex" in proc.stderr
    assert listening.calls() == []


def test_the_helper_command_line_with_two_images_names_the_roles_too(listening):
    import subprocess
    done = subprocess.run(
        [sys.executable, str(REPO / "skills/shared/scripts/codex_image.py"), "--ratio", "3:4",
         "--image", str(listening.tmp / "pack.png"), "--image", str(listening.tmp / "style-main.png")],
        input=b"warm light", env=listening.env, cwd=listening.tmp, capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr
    (call,) = listening.calls()
    assert "Image 1 is the product" in call["prompt"]
    json.dumps(call)  # the recorded call is plain data
