"""Scenes (no text, no pack) from Easel's image script on the Codex subscription. Held, and never paid."""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_held

AI_IMAGE = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "ai_image.py"

class PaidRouteRefused(RuntimeError):
    pass

class ReferencesNotSettled(ValueError):
    """ai_image.py treats the first --image as the product and keeps it as it is ("第 1 张是商品图（原样保留）", the --image help text), so a
    style reference passed alone would enter the scene as the product. Reference photos wait until Task 29 settles the inputs."""

def build_command(prompt: str, out, *, size, refs=()) -> list[str]:        # no default size: stage 3 chooses it (plan.json "main_size", from the Tmall rules file)
    if refs:
        raise ReferencesNotSettled("reference photos are not passed to the image tool yet; see Task 29")
    # exact pixels: a ratio keeps Codex's own size ("写比例则存 Codex 原图", line 862), which compose would then have to crop
    return [sys.executable, str(AI_IMAGE), "text2img", "--prompt", prompt, "-o", str(out), "--size", f"{size[0]}x{size[1]}"]

def generate_scene(prompt, out, *, size, refs=(), env=None, runner=subprocess.run, held_file=tmall_held.HELD_FILE):
    tmall_held.require_released("ai-image-gen", held_file)
    env = dict(os.environ if env is None else env)
    if env.get("IMG_PROVIDER", "").strip().lower() != "codex":
        raise PaidRouteRefused("IMG_PROVIDER=codex is not set; no paid image route is ever used")
    runner(build_command(prompt, out, size=size, refs=refs), env=env, check=True)

def stand_in_scene(out, size) -> None:
    Image.linear_gradient("L").resize(size).convert("RGB").save(out)
