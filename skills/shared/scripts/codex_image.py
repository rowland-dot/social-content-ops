#!/usr/bin/env python3
"""codex_image.py — 经 Codex（ChatGPT 订阅）内置 image_gen 工具出图，不走任何按次计费的 API。

用法：在 .env 里写 IMG_PROVIDER=codex（不是 key，不计费），ai_image.py / ecom-details-image 的
generate_image.py / 公众号 baoyu_image_gen_core.ts 就会改走这里。标准库；只有调用方要精确像素尺寸
（fit_to_size）时才用 Pillow，用到才 import。

做法：`codex exec --json` 让 Codex 用它自带的 image_gen 工具画一张图；Codex 把图存到
$CODEX_HOME/generated_images/<thread_id>/ 下，thread_id 取自 --json 输出的第一个事件，
所以只会取到本次运行的图，不会误取共享目录里别的会话的图。

硬规矩：
  - 内置工具不可用就明确报错，绝不回退到 Codex 图像技能里需要 OPENAI_API_KEY 的付费 CLI 模式
    （提示词里明令禁止，并且子进程环境里清掉 OPENAI_API_KEY 等变量）。
  - 每张图在订阅里要几十秒到几分钟、几万 token 额度，所以一次最多 MAX_PER_RUN 张。
  - Codex 只产出 PNG，尺寸只能给比例提示、不保证像素精确（要 1080x1920 实测回来 941x1672）。
    调用方要精确像素就用 fit_to_size 缩放、裁边。
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

MAX_PER_RUN = 4
# 改图最多带的商品图和风格参考：1 张商品图 + 至多 1 张主风格参考 + 1 张辅助风格参考
# （小红书参考视觉手册的上限，不因身份参考而变）。
MAX_STYLED_IMAGES = 3
# 身份参考（品牌自己的模特图，负责人 2026-10-28 的规则）是额外的一个名额，总数只多这一张。
MAX_IDENTITY_IMAGES = 1
MAX_IMAGES_WITH_IDENTITY = MAX_STYLED_IMAGES + MAX_IDENTITY_IMAGES
# 底图（已批准的卡，负责人 2026-10-28 的第 5 步规则）是再多的一个名额，总数只多这一张。
MAX_BASE_IMAGES = 1
MAX_IMAGES = MAX_IMAGES_WITH_IDENTITY + MAX_BASE_IMAGES
# 状态参考（issue 109：这个品牌自己商品的粉末、打开的包装、冲好的饮品的真实图）是单独的名额，不占上面的数。
MAX_STATE_IMAGES = 2
TIMEOUT_SECONDS = 900
# fit_to_size 为凑精确尺寸最多裁掉任一边的这个比例；再多说明 Codex 给的比例不对，不是差一点。
MAX_CROP = 0.01
TOOL_MISSING = "CODEX_IMAGE_TOOL_MISSING"
# 子进程里不留这些变量：有了它们 Codex 才可能走按次计费的付费模式。
SCRUBBED_ENV = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_API_KEY",
                "IMG_API_KEY", "IMG_BASE_URL")


class CodexImageError(RuntimeError):
    """Codex 路线失败。调用方把它当作终止错误，不得改走别的路线。"""


class PillowMissingError(CodexImageError):
    """要精确尺寸却没装 Pillow。调用方用自己的退出码报告安装提示。"""


def enabled() -> bool:
    return os.environ.get("IMG_PROVIDER", "").strip().lower() == "codex"


# 没有 Codex 设置时所有出图命令只说这一句就停下：不发请求、不存文件，也不指向任何别的出图服务。
CODEX_ONLY_MESSAGE = (
    "本项目的图片只通过 Codex（ChatGPT 订阅）生成，项目设置里没有 IMG_PROVIDER=codex，所以这次没有出图。"
    "请在项目设置（.env）里加上 IMG_PROVIDER=codex 后再试。"
    " Image generation here runs only through the Codex subscription; "
    "the project settings need IMG_PROVIDER=codex."
)


def find_codex() -> str:
    path = shutil.which("codex")
    if not path:
        raise CodexImageError(
            "找不到 codex 命令。IMG_PROVIDER=codex 需要本机装好 Codex CLI 并已用 ChatGPT 账号登录"
            "（不会改用付费 API）。")
    return path


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def require_count(n: int) -> None:
    if n < 1 or n > MAX_PER_RUN:
        raise CodexImageError(
            f"Codex 订阅路线一次最多生成 {MAX_PER_RUN} 张（每张要几分钟、几万 token 额度），"
            f"收到 {n}。请分批。")


def single_identity(paths: list[str] | None) -> str | None:
    """命令行给的 --identity-image 至多一张；多了在启动 Codex 之前就拒绝，不悄悄取第一张。"""
    if not paths:
        return None
    if len(paths) > MAX_IDENTITY_IMAGES:
        raise CodexImageError(
            f"身份参考图最多 {MAX_IDENTITY_IMAGES} 张，收到 {len(paths)} 张。"
            f" Codex edit takes at most {MAX_IDENTITY_IMAGES} identity image.")
    return paths[0]


def single_base(paths: list[str] | None) -> str | None:
    """命令行给的 --base-image 至多一张；多了在启动 Codex 之前就拒绝，不悄悄取第一张。"""
    if not paths:
        return None
    if len(paths) > MAX_BASE_IMAGES:
        raise CodexImageError(
            f"底图最多 {MAX_BASE_IMAGES} 张，收到 {len(paths)} 张。"
            f" Codex edit takes at most {MAX_BASE_IMAGES} base image.")
    return paths[0]


def pixel_size(size: str | None) -> tuple[int, int] | None:
    """'1080x1920' → (1080, 1920)；比例（'9:16'）/ 'auto' / 空 / 看不懂 → None。"""
    value = (size or "").strip().lower()
    if ":" in value or "x" not in value:
        return None
    try:
        width, height = (int(part) for part in value.split("x", 1))
    except ValueError:
        return None
    return (width, height) if width > 0 and height > 0 else None


def ratio_from_size(size: str | None) -> str | None:
    """'3:4' 原样返回；'1024x1536' 约分成 '2:3'；'auto' / 空 / 看不懂 → None。"""
    value = (size or "").strip().lower()
    if not value or value == "auto":
        return None
    if ":" in value:
        return value
    pixels = pixel_size(value)
    if pixels is None:
        return None
    g = math.gcd(*pixels)
    return f"{pixels[0] // g}:{pixels[1] // g}"


def _pillow():
    try:
        from PIL import Image
    except ImportError as exc:
        raise PillowMissingError(f"缺少依赖 Pillow：{exc}\n  pip install Pillow") from exc
    return Image


def require_pillow() -> None:
    """要精确尺寸的调用方在出图前先查：出完图（几分钟订阅额度）才发现没法缩放就白花了。"""
    _pillow()


def fit_to_size(data: bytes, width: int, height: int) -> bytes:
    """把一张 PNG 变成刚好 width x height：保持比例缩放到盖住目标，再从两边对称裁掉多出来的。

    已经是目标尺寸就原样返回。要裁掉的超过任一边的 MAX_CROP 就抛 CodexImageError——那是比例
    错了，硬裁会丢内容；此时什么都不返回。"""
    Image = _pillow()
    with Image.open(io.BytesIO(data)) as img:
        got_w, got_h = img.size
        if (got_w, got_h) == (width, height):
            return data
        scale = max(width / got_w, height / got_h)
        cover_w = max(width, round(got_w * scale))
        cover_h = max(height, round(got_h * scale))
        if (cover_w - width) / cover_w > MAX_CROP or (cover_h - height) / cover_h > MAX_CROP:
            raise CodexImageError(
                f"Codex 返回的图是 {got_w}x{got_h}，和要求的 {width}x{height} 比例差太多，"
                f"硬裁会丢内容，没有保存。请重新生成，或把 --size 改成比例（如 9:16）。")
        if img.mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGBA")
        left, top = (cover_w - width) // 2, (cover_h - height) // 2
        fitted = img.resize((cover_w, cover_h), Image.Resampling.LANCZOS).crop(
            (left, top, left + width, top + height))
        out = io.BytesIO()
        fitted.save(out, format="PNG")
        return out.getvalue()


def single_states(paths: list[str] | None) -> list[str]:
    """命令行给的 --state-image 至多 2 张；多了在启动 Codex 之前就拒绝，不悄悄丢掉。"""
    paths = list(paths or [])
    if len(paths) > MAX_STATE_IMAGES:
        raise CodexImageError(
            f"状态参考图最多 {MAX_STATE_IMAGES} 张，收到 {len(paths)} 张。"
            f" Codex edit takes at most {MAX_STATE_IMAGES} state images.")
    return paths


def _roles(image_count: int, identity: bool = False, base: bool = False,
           style_only: bool = False, states: int = 0) -> str:
    """多于一张图（或只有身份参考一张）时逐张说明角色：第 1 张是商品（必须原样保留），
    base 为真时第 2 张是底图（已批准的卡：它的画面原样保留，只改提示词点名的地方，不当风格参考），
    其后的只借风格，identity 为真时最后一张是品牌自己的模特（保持是同一个人，姿势、角度、服装按提示词重画）；
    身份参考是唯一一张图时没有商品，提示词写明不画商品和包装。编号按实际附上的顺序。"""
    look = ("take only its look (light, scene, composition, lettering style), "
            "none of its products, people, hands or words.")
    if identity and image_count == 1:
        return " ".join([
            "Attached image:",
            "Image 1 is the identity reference: keep this person recognisably the same (face and "
            "identity) and redraw them in the pose, angle and clothing the prompt describes.",
            "No product or pack is drawn unless the prompt describes one."])
    styles = (image_count - (0 if style_only else 1) - (1 if identity else 0) - (1 if base else 0)
              - states)
    lines = ["Attached images, in the order given:"]
    if not style_only:  # style_only（issue 108）：没有商品图，卡里不画商品和包装
        lines.append("Image 1 is the product: keep its shape, colours and printed label exactly.")
    if base:
        lines.append("Image 2 is the base image: keep this image's drawing as it is (hand, background, "
                     "props, composition, colour) and change only what the prompt names.")
    first_style = (1 if style_only else 2) + (1 if base else 0)
    if styles == 1:
        lines.append(f"Image {first_style} is a style reference: {look}")
    elif styles >= 2:
        lines.append(f"Image {first_style} is the main style reference: {look}")
        lines.append(f"Image {first_style + 1} is the supporting style reference: {look}")
    for n in range(states):  # issue 109：只借这个商品真实的状态，不借它的场景、道具、人物、手、字
        lines.append(f"Image {first_style + styles + n} is a state reference: it shows the real state of "
                     "this brand's own product (colour, texture, clarity, the inside of the pack). "
                     "Copy that look only; do not borrow its scene, props, people, hands or words.")
    if identity:
        lines.append(f"Image {image_count} is the identity reference: keep this person recognisably "
                     "the same (face and identity) and redraw them in the pose, angle and clothing "
                     "the prompt describes.")
    if style_only:
        lines.append("No product or pack is drawn unless the prompt describes one.")
    return " ".join(lines)


def build_prompt(prompt: str, *, edit: bool, ratio: str | None, image_count: int = 1,
                 identity: bool = False, base: bool = False, style_only: bool = False,
                 states: int = 0) -> str:
    """image_count 是附上的全部图（含底图和身份参考）；identity 为真表示最后一张是身份参考，
    base 为真表示第 2 张是底图。"""
    alone = edit and identity and image_count == 1 and not style_only
    several = edit and (image_count > 1 or style_only)
    action = ("make one new image from the attached images" if several
              else "make one new image from the attached image" if alone
              else "edit the attached image" if edit else "generate exactly one image")
    lines = [f"Use your built-in image_gen tool to {action}: {prompt.strip()}"]
    if several or alone:
        lines.append(_roles(image_count, identity, base, style_only, states))
    if ratio:
        lines.append(f"Aspect ratio: {ratio}.")
    lines.append(
        "Rules: use only the built-in image_gen tool. Do not call the OpenAI API, do not use or "
        "ask for an API key, do not run image_gen.py or any CLI fallback, do not write scripts. "
        f"If the built-in image_gen tool is not available, reply exactly {TOOL_MISSING} and stop. "
        "When the image has been created, reply DONE.")
    return "\n".join(lines)


def _parse_stream(stdout: str) -> tuple[str | None, str]:
    """从 --json 事件流取 (thread_id, 最后一条 agent 消息)。看不懂的行直接跳过。"""
    thread_id, last_message = None, ""
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started" and thread_id is None:
            thread_id = event.get("thread_id")
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            last_message = str(item.get("text", ""))
    return thread_id, last_message


def generate_png(prompt: str, *, images: list[str] | None = None, ratio: str | None = None,
                 timeout: int = TIMEOUT_SECONDS, identity: str | None = None,
                 base: str | None = None, style_only: bool = False,
                 states: list[str] | None = None) -> bytes:
    """让 Codex 画一张图（给了 images 就是改图），返回 PNG 字节。失败抛 CodexImageError。

    images 多于一张时：第 1 张是商品（原样保留），其余是风格参考，提示词里逐张写明。
    base 是已批准的卡（底图）：只由调用方明确指定，紧跟在商品图后面，提示词里写明它的画面原样保留、
    只改提示词点名的地方；它必须和商品图一起给。
    identity 是品牌自己的模特图：排在最后，只由调用方明确指定，提示词里写明是要保持的那个人；
    不给 images 只给 identity 时它是唯一一张图，不当商品，提示词写明不画商品和包装。"""
    if style_only and (base or not images):
        raise CodexImageError(
            "只给风格参考图时（--style-image）要至少一张风格参考图，也不能带底图。"
            " Style-only images need at least one style image and no base image.")
    if style_only and len(images) > MAX_STYLED_IMAGES - 1:
        raise CodexImageError(
            f"风格参考图最多 {MAX_STYLED_IMAGES - 1} 张，收到 {len(images)} 张。"
            f" Codex edit takes at most {MAX_STYLED_IMAGES - 1} style images without a product image.")
    states = single_states(states)
    if states and (style_only or not images):
        raise CodexImageError(
            "状态参考图（--state-image）要和商品图一起给，商品图是第 1 张。"
            " A state image needs a product image as image 1.")
    if base and not images:
        raise CodexImageError(
            "底图（--base-image）要和商品图一起给，商品图是第 1 张。A base image needs a product "
            "image as image 1.")
    if images and len(images) > MAX_STYLED_IMAGES:
        raise CodexImageError(
            f"改图最多带 {MAX_STYLED_IMAGES} 张商品图和风格参考（1 张商品图 + 至多 2 张风格参考），"
            f"再加 1 张身份参考图共最多 {MAX_IMAGES_WITH_IDENTITY} 张，再加 1 张底图共最多 {MAX_IMAGES} 张，"
            f"收到 {len(images) + bool(identity) + bool(base)} 张。"
            f" Codex edit takes at most {MAX_STYLED_IMAGES} product and style images, "
            f"at most {MAX_IMAGES_WITH_IDENTITY} with an identity image, "
            f"at most {MAX_IMAGES} with a base image as well.")
    # 底图紧跟商品图（审批卡的命令保持原来的文件顺序），风格参考在后，身份参考排最后。
    attached = [*(images[:1] if base else images or []), *([base] if base else []),
                *(images[1:] if base else []), *states, *([identity] if identity else [])]
    exe = find_codex()
    cmd = [exe, "exec", "--json", "--skip-git-repo-check", "-s", "read-only", "--ephemeral"]
    for image in attached:
        if not Path(image).is_file():
            raise CodexImageError(f"输入图片不存在：{image}")
        cmd += ["-i", image]
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
    # -i 会吃掉后面所有参数，所以提示词走 stdin，不放在命令行里。
    try:
        done = subprocess.run(cmd, input=build_prompt(prompt, edit=bool(attached), ratio=ratio,
                                                      image_count=len(attached),
                                                      identity=bool(identity), base=bool(base),
                                                      style_only=style_only, states=len(states)),
                              env=env, capture_output=True, text=True, encoding="utf-8",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CodexImageError(f"Codex 出图超过 {timeout} 秒没有结束，已放弃。") from None
    except OSError as exc:
        raise CodexImageError(f"无法启动 codex：{exc}") from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip()[-600:]
        raise CodexImageError(f"Codex 退出码 {done.returncode}：{detail}")
    thread_id, last_message = _parse_stream(done.stdout)
    folder = codex_home() / "generated_images" / (thread_id or "")
    found = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime) if thread_id else []
    if not found:
        if TOOL_MISSING in last_message:
            raise CodexImageError(
                "Codex 的内置 image_gen 工具不可用。不会回退到需要 API key 的付费模式；"
                "请升级或重新登录 Codex 后再试。")
        raise CodexImageError(f"Codex 没有产出图片。它的最后一句话：{last_message or '（无）'}")
    data = found[-1].read_bytes()
    for leftover in found:  # 这是本次运行自己的目录，取走后清掉，免得堆积
        leftover.unlink(missing_ok=True)
    try:
        folder.rmdir()
    except OSError:
        pass
    return data


def check() -> tuple[bool, str]:
    try:
        return True, f"codex = {find_codex()}"
    except CodexImageError as exc:
        return False, str(exc)


def main(argv: list[str] | None = None) -> int:
    """命令行：给 TypeScript 的公众号出图脚本用。提示词走 stdin，PNG 字节写到 stdout。"""
    parser = argparse.ArgumentParser(description="经 Codex 订阅出一张 PNG（提示词从 stdin 读）")
    parser.add_argument("--ratio")
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--identity-image", action="append", default=[],
                        help="品牌自己的模特图（身份参考，至多 1 张），不是多一张 --image")
    parser.add_argument("--base-image", action="append", default=[],
                        help="已批准的卡（底图，至多 1 张，要和 --image 的商品图一起给）：画面原样保留，"
                             "只改提示词点名的地方；不是风格参考，也不是多一张 --image")
    parser.add_argument("--state-image", action="append", default=[],
                        help="这个品牌自己商品的状态真实图（至多 2 张，要和 --image 的商品图一起给）：只借状态的样子")
    args = parser.parse_args(argv)
    try:
        sys.stdout.buffer.write(generate_png(sys.stdin.read(), images=args.image,
                                             ratio=ratio_from_size(args.ratio),
                                             identity=single_identity(args.identity_image),
                                             base=single_base(args.base_image),
                                             states=single_states(args.state_image)))
    except CodexImageError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
