#!/usr/bin/env python3
"""render_card.py — HTML → 图片 的确定性渲染（playwright + chromium）。

所有"HTML 单图 → 截图"类 SKILL（card-quote / card-xiaohongshu / poster-hero /
comparison-card 等）共用此脚本，避免每次现场即兴起 headless 浏览器导致慢/卡/超时。

依赖：playwright（`pip install playwright` + `playwright install chromium`）。

用法：
    # 截取单个元素
    render_card.py --html card.html --out card.png --selector ".card"

    # 整页截图（竖版海报常用）
    render_card.py --html poster.html --out poster.png --full-page --width 1080 --height 1920

    # 一个 HTML 里多张卡片，批量导出（selector 命中多个元素，逐个存 <out前缀>_1.png ...）
    render_card.py --html cards.html --out-dir ./out --all ".card" --prefix card

    # 9:16 视频卡（1080x1920，scale 1）：一个 --preset 搞定，不要再手敲 --scale 1 --height 1920。
    # 保存后逐张核对像素尺寸，不是 1080x1920（例如 --full-page 整页拍了三张卡）就退出码 4 并点名文件和尺寸。
    render_card.py --html cards.html --out card.png --selector ".card" --preset video

    # 自检（不需要 HTML，验证浏览器可用）
    render_card.py --selftest

版面文件：元素截图（--selector / --all）和整页截图（--full-page）每存一张图，同名旁边再存一份
<图片名>.layout.json（card.png → card.layout.json）。只截 viewport 一角的图不存。它记下这张图上
每一行渲染出来的文字、和每一块「自带背景且里面有字」的便签的位置（图片像素，左上角为 0,0）。合成视频时
assemble.py 读它来检查字幕有没有盖住卡片上的字或便签。整张图的底纸/背景不算便签；行内高亮、没有字的相框也不算。

退出码：2 参数/输入错误，3 缺 playwright/chromium，4 --preset 的成品尺寸不对。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import sys
from pathlib import Path

# 不写 --width/--height/--scale 时的默认视口；--preset 则整套换成自己的值。
DEFAULT_VIEW = {"width": 1080, "height": 1440, "scale": 2}
PRESETS = {"video": {"width": 1080, "height": 1920, "scale": 1}}
EXIT_WRONG_SIZE = 4

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--font-render-hinting=none",
    "--disable-dev-shm-usage",
]


def _env_proxy() -> str | None:
    """从环境变量取外网代理（CDN/Google Fonts 需要）。"""
    for k in ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY"):
        v = os.environ.get(k)
        if v:
            return v
    return None


def _image_size(path: str) -> tuple[int, int] | None:
    """PNG / JPEG 的像素宽高，只读文件头（不依赖 Pillow）；认不出来返回 None。"""
    data = Path(path).read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 <= len(data) and data[i] == 0xFF:
            marker = data[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):  # SOFn：帧头，含宽高
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return width, height
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return None


def _wrong_sizes(saved: list[str], want: tuple[int, int]) -> list[tuple[str, tuple[int, int] | None]]:
    return [(s, size) for s in saved if (size := _image_size(s)) != want]


# 在浏览器里量版面：root 是被截图的元素（整页截图时是 <html>），返回图片像素下的文字行和便签。
# 文字行：每个文字节点按渲染出的行各取一个框（Range.getClientRects），不需要任何 class 约定。
# 便签：自带背景（底色或背景图）、不是行内元素、里面有字的块；整张卡的底纸（面积 ≥ 90%）不算；
# 旋转过的便签取外接的正框。
_LAYOUT_JS = """(root, scale) => {
  const o = root.getBoundingClientRect(), whole = root === document.documentElement;   // 整页截图量的是整份文档
  const W = whole ? root.scrollWidth : o.width, H = whole ? root.scrollHeight : o.height;
  const clip = r => {
    const x0 = Math.max(0, r.left - o.left), y0 = Math.max(0, r.top - o.top);
    const x1 = Math.min(W, r.right - o.left), y1 = Math.min(H, r.bottom - o.top);
    return x1 > x0 && y1 > y0 ? [x0, y0, x1, y1].map(v => Math.round(v * scale)) : null;
  };
  const label = s => s.replace(/\\s+/g, ' ').trim().slice(0, 24);
  const shown = el => { const cs = getComputedStyle(el); return cs.display !== 'none' && cs.visibility !== 'hidden'; };
  const boxes = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode, el = t.parentElement;
    if (!t.textContent.trim() || !shown(el) || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue;
    const range = document.createRange();
    range.selectNodeContents(t);
    for (const r of range.getClientRects()) {
      const b = clip(r);
      if (b) boxes.push({kind: 'text', text: label(t.textContent), box: b});
    }
  }
  for (const el of root.querySelectorAll('*')) {
    if (!shown(el) || !el.textContent.trim()) continue;
    const cs = getComputedStyle(el);
    const hasBackground = cs.backgroundImage !== 'none' || !/^(transparent|rgba\\(.*,\\s*0\\))$/.test(cs.backgroundColor);
    const r = el.getBoundingClientRect();
    if (cs.display === 'inline' || !hasBackground || r.width * r.height >= 0.9 * W * H) continue;
    const b = clip(r);
    if (b) boxes.push({kind: 'note', text: label(el.textContent), box: b});
  }
  return {width: Math.round(W * scale), height: Math.round(H * scale), boxes};
}"""


async def _save_layout(root, picture: str, scale: int) -> None:
    """量出 root 里的文字行和便签，存成图片旁边的 <图片名>.layout.json。出图是正事，量不出来只警告，不改退出码。"""
    try:
        layout = await root.evaluate(_LAYOUT_JS, scale)
        Path(picture).with_suffix(".layout.json").write_text(
            json.dumps(layout, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 没能保存 {picture} 的版面文件（图片已正常保存）: {e}", file=sys.stderr)


async def _render(args) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("ERROR: 未安装 playwright。请运行：pip install playwright && playwright install chromium",
              file=sys.stderr)
        return 3

    html_path = Path(args.html).resolve()
    if not html_path.is_file():
        print(f"ERROR: HTML 文件不存在: {html_path}", file=sys.stderr)
        return 2

    fmt = args.format
    proxy = args.proxy or _env_proxy()
    launch_kwargs: dict = {"args": _LAUNCH_ARGS}
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: 无法启动 chromium（可能未 `playwright install chromium`）: {e}", file=sys.stderr)
            return 3
        page = await browser.new_page(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=args.scale,
        )
        # 不用 networkidle：外部 CDN/字体可能永不 idle 导致挂起。
        # 用 "load" + 有界超时，超时也继续（页面通常已可视），再靠 --wait 等字体。
        try:
            await page.goto(f"file://{html_path}", wait_until="load",
                            timeout=args.nav_timeout)
        except Exception as e:  # noqa: BLE001
            print(f"WARN: 页面加载未在 {args.nav_timeout}ms 内完成（外部资源慢），继续渲染: {e}",
                  file=sys.stderr)
        # 等 web 字体 / 布局稳定
        try:
            await page.evaluate("document.fonts && document.fonts.ready")
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(args.wait)

        saved: list[str] = []

        def _shot_kwargs(path: str) -> dict:
            kw: dict = {"path": path, "type": fmt}
            if fmt == "jpeg":
                kw["quality"] = args.quality
            return kw

        if args.all:
            out_dir = Path(args.out_dir or ".").resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            els = await page.query_selector_all(args.all)
            if not els:
                print(f"ERROR: selector 未命中任何元素: {args.all}", file=sys.stderr)
                await browser.close()
                return 2
            for i, el in enumerate(els, 1):
                out_path = out_dir / f"{args.prefix}_{i}.{fmt}"
                await el.screenshot(**_shot_kwargs(str(out_path)))
                await _save_layout(el, str(out_path), args.scale)
                saved.append(str(out_path))
        else:
            if not args.out:
                print("ERROR: 需要 --out（或用 --all + --out-dir 批量）", file=sys.stderr)
                await browser.close()
                return 2
            out_path = Path(args.out).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if args.full_page:
                await page.screenshot(**_shot_kwargs(str(out_path)), full_page=True)
                await _save_layout(await page.query_selector("html"), str(out_path), args.scale)
            elif args.selector:
                el = await page.query_selector(args.selector)
                if el is None:
                    print(f"ERROR: selector 未命中: {args.selector}", file=sys.stderr)
                    await browser.close()
                    return 2
                await el.screenshot(**_shot_kwargs(str(out_path)))
                await _save_layout(el, str(out_path), args.scale)
            else:
                # 无 selector 无 full-page：截 viewport 区域（图只是页面的一角，量不准，不存版面文件）
                await page.screenshot(**_shot_kwargs(str(out_path)))
            saved.append(str(out_path))

        await browser.close()

    if args.preset:
        want = (PRESETS[args.preset]["width"], PRESETS[args.preset]["height"])
        wrong = _wrong_sizes(saved, want)
        for s, size in wrong:
            got = f"{size[0]}x{size[1]}" if size else "读不出尺寸"
            print(f"ERROR: --preset {args.preset} 要 {want[0]}x{want[1]}，但 {s} 是 {got}", file=sys.stderr)
        if wrong:
            return EXIT_WRONG_SIZE

    for s in saved:
        kb = Path(s).stat().st_size / 1024
        print(f"✅ {s} ({kb:.0f} KB)")
    print(f"共渲染 {len(saved)} 张")
    return 0


async def _selftest() -> int:
    """渲染一张最小卡片验证浏览器链路可用。"""
    import tempfile

    html = (
        "<html><head><meta charset='utf-8'><style>"
        ".card{width:400px;height:225px;display:flex;align-items:center;"
        "justify-content:center;background:#1a1a2e;color:#fff;"
        "font:600 28px sans-serif;}</style></head>"
        "<body><div class='card'>Easel 渲染自检 OK</div></body></html>"
    )
    with tempfile.TemporaryDirectory() as d:
        hp = Path(d) / "t.html"
        hp.write_text(html, encoding="utf-8")
        op = Path(d) / "t.png"
        ns = argparse.Namespace(
            html=str(hp), out=str(op), out_dir=None, selector=".card", all=None,
            prefix="card", full_page=False, width=400, height=225, scale=2, preset=None,
            format="png", quality=90, wait=300, nav_timeout=20000, proxy=None,
        )
        rc = await _render(ns)
        if rc == 0 and op.is_file() and op.stat().st_size > 0:
            print("[PASS] 渲染链路正常")
            return 0
        print("[FAIL] 渲染自检失败", file=sys.stderr)
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="HTML → 图片 确定性渲染（playwright）")
    ap.add_argument("--html", help="输入 HTML 文件路径")
    ap.add_argument("--out", help="输出图片路径（单图模式）")
    ap.add_argument("--out-dir", help="输出目录（--all 批量模式）")
    ap.add_argument("--selector", help="要截取的元素 CSS selector（单图）")
    ap.add_argument("--all", help="批量截取命中该 selector 的所有元素")
    ap.add_argument("--prefix", default="card", help="批量模式文件名前缀（默认 card）")
    ap.add_argument("--full-page", action="store_true", help="整页截图")
    ap.add_argument("--width", type=int, help="视口宽（默认 1080）")
    ap.add_argument("--height", type=int, help="视口高（默认 1440）")
    ap.add_argument("--scale", type=int, help="设备像素比，越高越清晰（默认 2）")
    ap.add_argument("--preset", choices=sorted(PRESETS),
                    help="一套尺寸：video = 9:16 视频卡，1080x1920、scale 1；保存后逐张核对像素尺寸。"
                         "不能和 --width/--height/--scale 同用")
    ap.add_argument("--format", choices=["png", "jpeg"], default="png", help="输出格式")
    ap.add_argument("--quality", type=int, default=90, help="jpeg 质量 1-100（默认 90）")
    ap.add_argument("--wait", type=int, default=1200, help="渲染等待毫秒（默认 1200，等字体）")
    ap.add_argument("--nav-timeout", type=int, default=20000, help="页面加载超时毫秒（默认 20000，超时也继续）")
    ap.add_argument("--proxy", help="外网代理（默认读 https_proxy/http_proxy 环境变量，供 CDN/字体加载）")
    ap.add_argument("--selftest", action="store_true", help="运行渲染自检")
    args = ap.parse_args()

    if args.selftest:
        return asyncio.run(_selftest())
    if not args.html:
        ap.error("需要 --html（或 --selftest）")
    explicit = [f"--{n}" for n in DEFAULT_VIEW if getattr(args, n) is not None]
    if args.preset and explicit:
        ap.error(f"--preset {args.preset} 自带宽、高、scale，请去掉 {', '.join(explicit)}")
    for name, value in (PRESETS[args.preset] if args.preset else DEFAULT_VIEW).items():
        if getattr(args, name) is None:
            setattr(args, name, value)
    return asyncio.run(_render(args))


if __name__ == "__main__":
    sys.exit(main())
