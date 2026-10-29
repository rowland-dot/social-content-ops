"""Image generation through the Codex (ChatGPT) subscription instead of a per-call paid API.

Seams (from issue 06's acceptance criteria): the command lines of
  - skills/shared/scripts/ai_image.py            (ai-image-gen; short-drama images delegate to it)
  - skills/builtin/ecom-details-image/scripts/generate_image.py
  - the WeChat publisher's baoyu_image_gen_core.ts (generateImage / detectProvider)
with IMG_PROVIDER=codex. The only thing faked is the outside world: a `codex` program on PATH
(the real one costs minutes and subscription usage per image; the real route is run separately
and recorded under .scratch/easel-setup-gaps/evidence/06-codex-image-probe/).

Expected values are literals: the PNG bytes the fake writes, the exit codes, the file names.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AI_IMAGE = REPO / "skills/shared/scripts/ai_image.py"
ECOM = REPO / "skills/builtin/ecom-details-image/scripts/generate_image.py"
WECHAT_CORE = REPO / "skills/builtin/skill-wechat-publisher/scripts/baoyu_image_gen_core.ts"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake codex is a POSIX script")

# A real 1x1 PNG, written as a literal so the tests never recompute what the code under test does.
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_BYTES = base64.b64decode(PNG_B64)

FAKE_CODEX = r'''#!{python}
import json, os, sys, uuid
from pathlib import Path

home = Path(os.environ["CODEX_HOME"])
mode = os.environ.get("FAKE_CODEX_MODE", "ok")
argv = sys.argv[1:]
with open(home / "calls.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps({{"argv": argv, "has_openai_key": bool(os.environ.get("OPENAI_API_KEY"))}}) + "\n")
if mode == "crash":
    print("boom", file=sys.stderr)
    sys.exit(7)
# Shape of the real `codex exec --json` stream: first event names the thread, and the image
# tool saves into $CODEX_HOME/generated_images/<thread id>/exec-<uuid>.png (seen on this PC).
thread = str(uuid.uuid4())
print(json.dumps({{"type": "thread.started", "thread_id": thread}}))
if mode == "tool-missing":
    print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message",
                      "text": "CODEX_IMAGE_TOOL_MISSING"}}}}))
    sys.exit(0)
# an unrelated thread's image sitting in the shared folder must never be picked up
other = home / "generated_images" / "other-thread"
other.mkdir(parents=True, exist_ok=True)
(other / "exec-unrelated.png").write_bytes(b"NOT-OURS")
if mode != "no-image":
    out = home / "generated_images" / thread
    out.mkdir(parents=True)
    # FAKE_CODEX_IMAGE: a PNG file the test made, to be handed back instead of the 1x1 literal
    # (the real Codex returns ~1.57 megapixel pictures, e.g. 941x1672 when 1080x1920 is asked for).
    chosen = os.environ.get("FAKE_CODEX_IMAGE")
    data = Path(chosen).read_bytes() if chosen else bytes.fromhex("{png_hex}")
    (out / ("exec-" + str(uuid.uuid4()) + ".png")).write_bytes(data)
print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": "DONE"}}}}))
'''


@pytest.fixture
def world(tmp_path):
    """An isolated outside world: Easel root, CODEX_HOME, a bin dir holding the fake codex."""
    root = tmp_path / "easel"
    (root / "outputs").mkdir(parents=True)
    home = tmp_path / "codex-home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "codex"
    exe.write_text(FAKE_CODEX.format(python=sys.executable, png_hex=PNG_BYTES.hex()), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("IMG_", "OPENAI_", "FAKE_CODEX", "CODEX_"))}
    env.update({
        "EASEL_ROOT": str(root),
        "CODEX_HOME": str(home),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "IMG_PROVIDER": "codex",
        "HOME": str(tmp_path),
    })

    class World:
        pass

    w = World()
    w.root, w.home, w.bin, w.env, w.tmp = root, home, bin_dir, env, tmp_path
    w.calls = lambda: [json.loads(line) for line in
                       (home / "calls.jsonl").read_text(encoding="utf-8").splitlines()] \
        if (home / "calls.jsonl").exists() else []
    return w


def run(w, script: Path, *args: str, env_extra: dict | None = None, timeout: int = 120):
    env = {**w.env, **(env_extra or {})}
    return subprocess.run([sys.executable, str(script), *args], env=env, cwd=w.tmp,
                          capture_output=True, text=True, timeout=timeout)


class RecordingServer:
    """A stand-in for a paid image API. Any request that reaches it is a billed call."""

    def __init__(self):
        self.hits: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _any(self):
                outer.hits.append(f"{self.command} {self.path}")
                self.send_response(500)
                self.end_headers()

            do_GET = do_POST = _any

            def log_message(self, *a):  # keep test output quiet
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def paid_api():
    s = RecordingServer()
    yield s
    s.close()


# ---- ai_image.py (ai-image-gen, and the image half of short-drama) ------------------------

def test_text2img_writes_the_png_codex_produced_into_outputs_with_no_key_configured(world):
    out = world.root / "outputs/咖啡新品/cover.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "a red circle", "--output", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.read_bytes() == PNG_BYTES
    assert str(out) in r.stdout
    assert len(world.calls()) == 1


def test_img2img_attaches_the_input_image_and_saves_the_result(world):
    src = world.tmp / "in.png"
    src.write_bytes(PNG_BYTES)
    out = world.root / "outputs/咖啡新品/edited.png"
    r = run(world, AI_IMAGE, "img2img", "--prompt", "make it blue", "--image", str(src),
            "--output", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.read_bytes() == PNG_BYTES
    argv = world.calls()[0]["argv"]
    assert str(src) in argv, argv


def test_variations_make_one_file_per_requested_variant(world):
    src = world.tmp / "in.png"
    src.write_bytes(PNG_BYTES)
    outdir = world.root / "outputs/咖啡新品/variants"
    r = run(world, AI_IMAGE, "variations", "--image", str(src), "--n", "2", "--output", str(outdir))
    assert r.returncode == 0, r.stdout + r.stderr
    files = sorted(outdir.glob("*.png"))
    assert len(files) == 2
    assert all(f.read_bytes() == PNG_BYTES for f in files)
    assert len(world.calls()) == 2


def test_a_request_over_the_per_run_limit_is_refused_before_codex_is_started(world):
    out = world.root / "outputs/咖啡新品/many"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--n", "5", "--output", str(out))
    assert r.returncode != 0
    assert "4" in r.stderr
    assert world.calls() == []


def test_tool_missing_fails_loudly_and_never_reaches_a_paid_api_even_with_a_key_configured(world, paid_api):
    out = world.root / "outputs/咖啡新品/cover.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--output", str(out),
            env_extra={"FAKE_CODEX_MODE": "tool-missing", "IMG_BASE_URL": paid_api.url,
                       "IMG_MODEL": "gpt-image-1", "IMG_API_KEY": "sk-not-real",
                       "OPENAI_API_KEY": "sk-not-real"})
    assert r.returncode != 0
    assert "Codex" in r.stderr
    assert not out.exists()
    assert paid_api.hits == []
    assert all(c["has_openai_key"] is False for c in world.calls()), "key leaked to codex process"


def test_codex_producing_no_image_is_an_error_not_an_empty_success(world):
    out = world.root / "outputs/咖啡新品/cover.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--output", str(out),
            env_extra={"FAKE_CODEX_MODE": "no-image"})
    assert r.returncode != 0
    assert not out.exists()


def test_codex_exiting_nonzero_is_an_error_that_shows_its_message(world):
    out = world.root / "outputs/咖啡新品/cover.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--output", str(out),
            env_extra={"FAKE_CODEX_MODE": "crash"})
    assert r.returncode != 0
    assert "boom" in r.stderr
    assert not out.exists()


def test_codex_not_installed_says_so(world):
    out = world.root / "outputs/咖啡新品/cover.png"
    (world.bin / "codex").unlink()
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--output", str(out),
            env_extra={"PATH": "/usr/bin:/bin"})
    assert r.returncode != 0
    assert "codex" in r.stderr.lower()
    assert not out.exists()


def test_only_png_can_be_asked_for_because_codex_returns_png(world):
    out = world.root / "outputs/咖啡新品/cover.jpg"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--format", "jpeg", "--output", str(out))
    assert r.returncode != 0
    assert "png" in r.stderr.lower()
    assert world.calls() == []


def test_check_is_ready_with_no_key_when_codex_is_present(world):
    r = run(world, AI_IMAGE, "check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "codex" in r.stdout.lower()


def test_check_is_not_ready_when_codex_is_absent(world):
    (world.bin / "codex").unlink()
    r = run(world, AI_IMAGE, "check", env_extra={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 2
    assert "codex" in r.stdout.lower()


# ---- issue 95: without the Codex setting nothing runs, and no paid image service is reached ----

CODEX_SETTING = "IMG_PROVIDER=codex"
# Words that would send the reader to a paid image service; the refusal must never contain them.
PAID_HINTS = ("IMG_API_KEY", "IMG_BASE_URL", "OPENAI_API_KEY", "apimart", "API key")


def without_codex_setting(world, paid_api) -> dict:
    """The world as it is on a machine that lacks the setting but has a paid key lying around."""
    env = {k: v for k, v in world.env.items() if k != "IMG_PROVIDER"}
    env.update({"IMG_BASE_URL": paid_api.url, "IMG_MODEL": "gpt-image-1",
                "IMG_API_KEY": "sk-not-real", "OPENAI_API_KEY": "sk-not-real"})
    return env


def run_without_setting(world, paid_api, script: Path, *args: str):
    return subprocess.run([sys.executable, str(script), *args], env=without_codex_setting(world, paid_api),
                          cwd=world.tmp, capture_output=True, text=True, timeout=60)


def assert_refused_in_plain_words(r, paid_api, world) -> None:
    assert r.returncode != 0, r.stdout + r.stderr
    assert CODEX_SETTING in r.stderr, r.stderr
    for hint in PAID_HINTS:
        assert hint not in r.stderr, f"the refusal points at a paid route ({hint}): {r.stderr}"
    assert paid_api.hits == [], f"a paid image request was sent: {paid_api.hits}"
    assert world.calls() == [], "Codex was started although the setting is missing"


@pytest.mark.parametrize("extra", [[], ["--mode", "sync"], ["--mode", "async"]])
def test_text2img_without_the_codex_setting_is_refused_and_sends_no_request(world, paid_api, extra):
    out = world.root / "outputs/咖啡新品/cover.png"
    r = run_without_setting(world, paid_api, AI_IMAGE, "text2img", "--prompt", "x", *extra,
                            "--output", str(out))
    assert_refused_in_plain_words(r, paid_api, world)
    assert not out.exists()


@pytest.mark.parametrize("extra", [[], ["--mode", "async"]])
def test_img2img_without_the_codex_setting_is_refused_and_sends_no_request(world, paid_api, extra):
    src = world.tmp / "in.png"
    src.write_bytes(PNG_BYTES)
    out = world.root / "outputs/咖啡新品/edited.png"
    r = run_without_setting(world, paid_api, AI_IMAGE, "img2img", "--prompt", "x", "--image", str(src),
                            *extra, "--output", str(out))
    assert_refused_in_plain_words(r, paid_api, world)
    assert not out.exists()


def test_variations_without_the_codex_setting_are_refused_and_send_no_request(world, paid_api):
    src = world.tmp / "in.png"
    src.write_bytes(PNG_BYTES)
    outdir = world.root / "outputs/咖啡新品/variants"
    r = run_without_setting(world, paid_api, AI_IMAGE, "variations", "--image", str(src), "--n", "2",
                            "--output", str(outdir))
    assert_refused_in_plain_words(r, paid_api, world)
    assert not outdir.exists() or list(outdir.iterdir()) == []


def test_check_without_the_codex_setting_is_not_ready_and_names_the_codex_setting(world, paid_api):
    r = run_without_setting(world, paid_api, AI_IMAGE, "check")
    assert r.returncode == 2, r.stdout + r.stderr
    assert CODEX_SETTING in r.stdout, r.stdout
    for hint in PAID_HINTS:
        assert hint not in r.stdout, f"check points at a paid route ({hint}): {r.stdout}"


# ---- exact pixel size (issue 48): Codex only hints the ratio, so an asked-for size is enforced --

# Literals worked out by hand: a 400 px white square centred in the Codex picture is scaled by
# 1920/1672 (about 1.148) to about 459 px and stays centred at (540, 960) in 1080x1920, so its
# edges sit near 310 / 730 / 770 / 1190.
SQUARE_BOX = (310, 730, 770, 1190)


def make_marker_png(path: Path, width: int, height: int, square: int = 400) -> Path:
    """A black picture with a white square in the middle (what the stand-in Codex hands back)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (0, 0, 0))
    left, top = (width - square) // 2, (height - square) // 2
    ImageDraw.Draw(img).rectangle([left, top, left + square - 1, top + square - 1], fill=(255, 255, 255))
    img.save(path)
    return path


def size_and_square(path: Path):
    """(width, height) of a saved picture and the bounding box of its white square."""
    from PIL import Image

    with Image.open(path) as img:
        gray = img.convert("L").point(lambda p: 255 if p > 128 else 0)
        return img.size, gray.getbbox()


def assert_fitted_1080x1920(path: Path) -> None:
    size, box = size_and_square(path)
    assert size == (1080, 1920), f"{path.name} came out {size[0]}x{size[1]}"
    assert all(abs(got - want) <= 3 for got, want in zip(box, SQUARE_BOX)), \
        f"{path.name}: square at {box}, expected about {SQUARE_BOX} (scaled, centred, not stretched or padded)"


@pytest.fixture
def near_miss(world):
    """What Codex really returned for a 1080x1920 request on video 01: 941x1672."""
    return make_marker_png(world.tmp / "codex-941x1672.png", 941, 1672)


def test_text2img_with_a_pixel_size_saves_exactly_that_size(world, near_miss):
    out = world.root / "outputs/咖啡新品/still.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--size", "1080x1920", "--output", str(out),
            env_extra={"FAKE_CODEX_IMAGE": str(near_miss)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert_fitted_1080x1920(out)


def test_img2img_with_a_pixel_size_saves_exactly_that_size(world, near_miss):
    src = world.tmp / "in.png"
    src.write_bytes(PNG_BYTES)
    out = world.root / "outputs/咖啡新品/edited.png"
    r = run(world, AI_IMAGE, "img2img", "--prompt", "x", "--image", str(src), "--size", "1080x1920",
            "--output", str(out), env_extra={"FAKE_CODEX_IMAGE": str(near_miss)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert_fitted_1080x1920(out)


def test_variations_with_a_pixel_size_save_every_file_at_exactly_that_size(world, near_miss):
    src = world.tmp / "in.png"
    src.write_bytes(PNG_BYTES)
    outdir = world.root / "outputs/咖啡新品/variants"
    r = run(world, AI_IMAGE, "variations", "--image", str(src), "--n", "2", "--size", "1080x1920",
            "--output", str(outdir), env_extra={"FAKE_CODEX_IMAGE": str(near_miss)})
    assert r.returncode == 0, r.stdout + r.stderr
    files = sorted(outdir.glob("*.png"))
    assert len(files) == 2
    for f in files:
        assert_fitted_1080x1920(f)


def test_the_overflow_is_cut_equally_from_top_and_bottom(world):
    """1080x1936 against 1080x1920: 16 rows too many (0.8 percent, inside the limit), so 8 go from each
    end. White 8-row bands sit on the very first and last rows; a centred crop removes both."""
    from PIL import Image, ImageDraw

    tall = Image.new("RGB", (1080, 1936), (0, 0, 0))
    draw = ImageDraw.Draw(tall)
    draw.rectangle([0, 0, 1079, 7], fill=(255, 255, 255))
    draw.rectangle([0, 1928, 1079, 1935], fill=(255, 255, 255))
    src = world.tmp / "codex-1080x1936.png"
    tall.save(src)
    out = world.root / "outputs/咖啡新品/still.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--size", "1080x1920", "--output", str(out),
            env_extra={"FAKE_CODEX_IMAGE": str(src)})
    assert r.returncode == 0, r.stdout + r.stderr
    with Image.open(out) as img:
        assert img.size == (1080, 1920)
        assert img.convert("L").getextrema() == (0, 0), "a white edge band survived: the crop is not centred"


def test_a_codex_picture_at_the_wrong_ratio_is_refused_with_both_sizes_and_nothing_is_saved(world):
    far_off = make_marker_png(world.tmp / "codex-1024x1536.png", 1024, 1536)  # 2:3, asked for 9:16
    out = world.root / "outputs/咖啡新品/still.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--size", "1080x1920", "--output", str(out),
            env_extra={"FAKE_CODEX_IMAGE": str(far_off)})
    assert r.returncode != 0
    assert "1024x1536" in r.stderr and "1080x1920" in r.stderr, r.stderr
    assert not out.exists()


def test_a_wrong_ratio_in_a_batch_saves_none_of_the_files(world):
    far_off = make_marker_png(world.tmp / "codex-1024x1536.png", 1024, 1536)
    src = world.tmp / "in.png"
    src.write_bytes(PNG_BYTES)
    outdir = world.root / "outputs/咖啡新品/variants"
    r = run(world, AI_IMAGE, "variations", "--image", str(src), "--n", "2", "--size", "1080x1920",
            "--output", str(outdir), env_extra={"FAKE_CODEX_IMAGE": str(far_off)})
    assert r.returncode != 0
    assert not outdir.exists() or list(outdir.iterdir()) == []


@pytest.mark.parametrize("size_args", [[], ["--size", "9:16"]])
def test_without_a_pixel_size_the_codex_picture_is_saved_byte_for_byte(world, near_miss, size_args):
    out = world.root / "outputs/咖啡新品/still.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", *size_args, "--output", str(out),
            env_extra={"FAKE_CODEX_IMAGE": str(near_miss)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.read_bytes() == near_miss.read_bytes()


def hide_pillow(world) -> dict:
    """PYTHONPATH entry whose PIL refuses to import: the script runs as if Pillow were not installed."""
    blocker = world.tmp / "no-pillow"
    (blocker / "PIL").mkdir(parents=True)
    (blocker / "PIL/__init__.py").write_text('raise ImportError("hidden for this test")\n', encoding="utf-8")
    return {"PYTHONPATH": str(blocker)}


def test_a_pixel_size_without_pillow_prints_the_install_hint_with_its_own_exit_code_and_never_calls_codex(
        world, near_miss):
    out = world.root / "outputs/咖啡新品/still.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--size", "1080x1920", "--output", str(out),
            env_extra={**hide_pillow(world), "FAKE_CODEX_IMAGE": str(near_miss)})
    assert r.returncode == 3, r.stdout + r.stderr
    assert "Pillow" in r.stderr and "pip install" in r.stderr, r.stderr
    assert "Traceback" not in r.stderr
    assert world.calls() == [], "Codex was started although the picture could not be resized afterwards"
    assert not out.exists()


def test_without_a_pixel_size_pillow_is_not_needed(world, near_miss):
    out = world.root / "outputs/咖啡新品/still.png"
    r = run(world, AI_IMAGE, "text2img", "--prompt", "x", "--output", str(out),
            env_extra={**hide_pillow(world), "FAKE_CODEX_IMAGE": str(near_miss)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.read_bytes() == near_miss.read_bytes()


# ---- ecom-details-image/scripts/generate_image.py -----------------------------------------

def test_ecom_generate_image_saves_the_codex_png_in_the_output_dir_with_no_key(world):
    outdir = world.tmp / "ecom-out"
    r = run(world, ECOM, "--prompt", "product on white", "--output-dir", str(outdir))
    assert r.returncode == 0, r.stdout + r.stderr
    files = list(outdir.glob("image-*.png"))
    assert len(files) == 1 and files[0].read_bytes() == PNG_BYTES
    assert str(files[0]) in r.stdout


def test_ecom_generate_image_attaches_the_reference_product_photo(world):
    src = world.tmp / "product.png"
    src.write_bytes(PNG_BYTES)
    r = run(world, ECOM, "--prompt", "x", "--image", str(src), "--output-dir", str(world.tmp / "o"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert str(src) in world.calls()[0]["argv"]


def test_ecom_generate_image_tool_missing_never_calls_the_paid_api(world, paid_api):
    r = run(world, ECOM, "--prompt", "x", "--output-dir", str(world.tmp / "o"),
            env_extra={"FAKE_CODEX_MODE": "tool-missing", "IMG_BASE_URL": paid_api.url,
                       "IMG_MODEL": "m", "IMG_API_KEY": "sk-not-real"})
    assert r.returncode != 0
    assert paid_api.hits == []
    assert not (world.tmp / "o").exists() or list((world.tmp / "o").iterdir()) == []


def test_ecom_generate_image_batch_over_the_limit_is_refused(world):
    r = run(world, ECOM, "--prompt", "x", "--n", "5", "--output-dir", str(world.tmp / "o"))
    assert r.returncode != 0
    assert world.calls() == []


@pytest.mark.parametrize("extra", [[], ["--mode", "sync"], ["--mode", "async"]])
def test_ecom_generate_image_without_the_codex_setting_is_refused_and_sends_no_request(
        world, paid_api, extra):
    outdir = world.tmp / "o"
    r = run_without_setting(world, paid_api, ECOM, "--prompt", "x", *extra, "--output-dir", str(outdir))
    assert_refused_in_plain_words(r, paid_api, world)
    assert not outdir.exists() or list(outdir.iterdir()) == []


# ---- WeChat publisher: baoyu_image_gen_core.ts ---------------------------------------------

NODE = shutil.which("node")


def _node_eval(world, body: str, env_extra: dict | None = None):
    """Run a few lines of JS that import the real core module (types stripped by node)."""
    script = world.tmp / "harness.mjs"
    script.write_text(
        f'import * as core from "{WECHAT_CORE.as_posix()}";\n{body}\n', encoding="utf-8")
    env = {**world.env, **(env_extra or {})}
    return subprocess.run([NODE, str(script)], env=env, cwd=world.tmp, capture_output=True,
                          text=True, timeout=120)


needs_node = pytest.mark.skipif(NODE is None, reason="node is not on PATH")


@needs_node
def test_wechat_core_chooses_codex_from_the_setting_with_no_key_configured(world):
    r = _node_eval(world, 'console.log(core.detectProvider({provider: null}));')
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "codex"


@needs_node
def test_wechat_core_chooses_codex_from_the_command_line_flag(world):
    r = _node_eval(world, 'console.log(core.detectProvider({provider: "codex"}));',
                   env_extra={"IMG_PROVIDER": ""})
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "codex"


@needs_node
def test_wechat_core_generates_the_codex_png_bytes(world):
    r = _node_eval(world, (
        'const b = await core.generateImage("codex", "m", "a red circle", '
        '{aspectRatio: "3:4", size: null, quality: "normal", referenceImages: [], n: 1});\n'
        'console.log(Buffer.from(b).toString("base64"));'))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == PNG_B64
    assert len(world.calls()) == 1


@needs_node
def test_wechat_core_tool_missing_throws_and_never_reaches_the_paid_api(world, paid_api):
    r = _node_eval(world, (
        'try { await core.generateImage("codex", "m", "x", '
        '{aspectRatio: null, size: null, quality: "normal", referenceImages: [], n: 1}); '
        'console.log("NO ERROR"); } catch (e) { console.log("ERR:" + e.message); }'),
        env_extra={"FAKE_CODEX_MODE": "tool-missing", "OPENAI_API_KEY": "sk-not-real",
                   "OPENAI_BASE_URL": paid_api.url})
    assert "ERR:" in r.stdout and "Codex" in r.stdout, r.stdout + r.stderr
    assert paid_api.hits == []


PAID_KEYS_IN_NODE = {"OPENAI_API_KEY": "sk-not-real", "GEMINI_PROXY_API_KEY": "sk-not-real"}


def _without_setting_env(paid_api) -> dict:
    return {"IMG_PROVIDER": "", **PAID_KEYS_IN_NODE, "OPENAI_BASE_URL": paid_api.url,
            "GEMINI_PROXY_BASE_URL": paid_api.url}


@needs_node
@pytest.mark.parametrize("provider", ["null", '"openai"', '"gemini-proxy"'])
def test_wechat_core_refuses_every_paid_provider_without_the_codex_setting(world, paid_api, provider):
    r = _node_eval(world, (
        f'try {{ console.log(core.detectProvider({{provider: {provider}}})); }} '
        'catch (e) { console.log("ERR:" + e.message); }'), env_extra=_without_setting_env(paid_api))
    assert "ERR:" in r.stdout and CODEX_SETTING in r.stdout, r.stdout + r.stderr
    for hint in ("OPENAI_API_KEY", "GEMINI_PROXY_API_KEY", "apimart"):
        assert hint not in r.stdout, f"the refusal points at a paid route ({hint}): {r.stdout}"
    assert paid_api.hits == []


@needs_node
@pytest.mark.parametrize("provider", ["openai", "gemini-proxy"])
def test_wechat_core_refuses_an_explicit_paid_provider_even_with_the_codex_setting(world, paid_api, provider):
    r = _node_eval(world, (
        f'try {{ console.log(core.detectProvider({{provider: "{provider}"}})); }} '
        'catch (e) { console.log("ERR:" + e.message); }'), env_extra=PAID_KEYS_IN_NODE)
    assert "ERR:" in r.stdout and CODEX_SETTING in r.stdout, r.stdout + r.stderr


@needs_node
@pytest.mark.parametrize("provider", ["openai", "gemini-proxy"])
def test_wechat_core_generate_image_sends_no_request_to_a_paid_provider(world, paid_api, provider):
    r = _node_eval(world, (
        f'try {{ await core.generateImage("{provider}", "m", "x", '
        '{aspectRatio: null, size: null, quality: "normal", referenceImages: [], n: 1}); '
        'console.log("NO ERROR"); } catch (e) { console.log("ERR:" + e.message); }'),
        env_extra=_without_setting_env(paid_api))
    assert "ERR:" in r.stdout and CODEX_SETTING in r.stdout, r.stdout + r.stderr
    assert paid_api.hits == []
