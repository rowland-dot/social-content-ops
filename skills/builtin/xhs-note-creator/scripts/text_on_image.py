#!/usr/bin/env python3
"""Draw Chinese text on top of an existing image (for xhs cover / ending cards).

Typical use: user provides a real photo, we overlay a hook line as a cover card.

- Preserves aspect ratio; optional center-crop + resize to 3:4 (900x1200 default)
- Text box with semi-transparent backdrop for legibility
- Expects a CJK-capable font in assets/fonts/ (falls back to PIL default w/ warning)

Usage:
    python3 text_on_image.py INPUT OUTPUT --text "一句钩子" \
        [--position top|center|bottom] [--font PATH] [--size 72] \
        [--color "#FFFFFF"] [--bg "#000000AA"] [--fit 3x4]

Typed-font sets (xhs-reference-visual, issue 81): the words of a card are set from one stored styling, on the
drawn image as it is (no crop, no resize), and each card writes a record of the values it used:
    python3 text_on_image.py INPUT OUTPUT --styling STYLING.json --blocks BLOCKS.json --record RECORD.json
    python3 text_on_image.py --check-records STYLING.json RECORD.json [RECORD.json ...]

STYLING.json  {"font_file": "NotoSerifCJK-Bold.ttc" (a path, or a file name found in the Noto, LXGW WenKai and on-demand font folders),
               "fill": "#FFFFFF", "outline_width": 5, "outline_color": "#B08050",
               "shadow": null or {"dx": 4, "dy": 4, "color": "#00000066"},
               "sizes": {"main title": 96, "subtitle": 48}}     one size per title level
BLOCKS.json   [{"text": "...", "level": "main title", "at": [0.5, 0.2], "max_width": 0.8}]
              "at" is the centre of the block as fractions of the image width and height (from the card's
              layout plan); "max_width" (fraction of the width, optional) wraps long lines.
STYLING.json may also hold "body" (issue 126: the picked lettering styles titles only; body text is one plain style):
               "body": {"font_file": "...", "fill": "#333333", "sizes": {"point": 36, "sub-line": 28}}
              A block whose "level" is a body level is set with it: no outline, no shadow. Without "body" the styling is title-only.
STYLING.json may also hold "title_size" (issue 127): one size for every block marked "role": "title" in BLOCKS.json
              (the cover's title and each card's page title), whatever its level. --check-records fails a title block of another size.
The check fails (exit 1) on any value other than the per-level size that differs from the styling.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow required (pip install Pillow)", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FONT_CANDIDATES = [
    REPO_ROOT / "assets" / "fonts" / "SourceHanSansCN-Bold.otf",
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
]
# where a bare font file name in a styling is looked for (fonts-noto-cjk installs under opentype/ on Ubuntu;
# the third typed font, LXGW WenKai Medium, is put in the last folder by ops/wsl-setup, issue 116)
FONT_DIRS = [
    Path("/usr/share/fonts/opentype/noto"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/local/share/fonts/lxgw-wenkai"),
]


def load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    candidates.extend(DEFAULT_FONT_CANDIDATES)
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    print("WARN: no CJK font found, using PIL default (CJK may render as boxes)",
          file=sys.stderr)
    return ImageFont.load_default()


def fit_aspect(img: Image.Image, ratio: str) -> Image.Image:
    if not ratio:
        return img
    w_r, h_r = map(int, ratio.lower().replace("x", ":").split(":"))
    target = w_r / h_r
    w, h = img.size
    cur = w / h
    if abs(cur - target) < 0.01:
        return img
    if cur > target:  # too wide -> crop sides
        new_w = int(h * target)
        off = (w - new_w) // 2
        return img.crop((off, 0, off + new_w, h))
    # too tall -> crop top/bottom
    new_h = int(w / target)
    off = (h - new_h) // 2
    return img.crop((0, off, w, off + new_h))


def parse_color(s: str) -> tuple[int, int, int, int]:
    s = s.lstrip("#")
    if len(s) == 6:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        return r, g, b, 255
    if len(s) == 8:
        return (int(s[0:2], 16), int(s[2:4], 16),
                int(s[4:6], 16), int(s[6:8], 16))
    raise ValueError(f"bad color {s!r}")


def wrap_cjk(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines, buf = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(buf)
            buf = ""
            continue
        trial = buf + ch
        w = draw.textlength(trial, font=font)
        if w > max_width and buf:
            lines.append(buf)
            buf = ch
        else:
            buf = trial
    if buf:
        lines.append(buf)
    return lines


# ---- typed-font sets: words set from one stored styling (issue 81) --------------------------------

SAFE_MARGIN = 0.05  # issue 104: of the width left and right, of the height top and bottom; fixed, not a styling field

STYLE_KEYS = ("font_file", "fill", "outline_width", "outline_color", "shadow")


def font_search_dirs() -> list[Path]:
    """FONT_DIRS plus one folder per font installed on demand (issue 119, xhs-reference-visual's install_font.py).
    The root is a setting so tests can point it at a temporary folder; keep the default in step with install_font.py."""
    root = Path(os.environ.get("EASEL_ONDEMAND_FONT_ROOT", "/usr/local/share/fonts/on-demand"))
    on_demand = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    return [*FONT_DIRS, *on_demand]


def find_font_file(name: str) -> Path:
    """The styling's font: a path that exists, or a file name found in the font folders. Never a silent fallback."""
    direct = Path(name)
    if direct.is_file():
        return direct
    folders = font_search_dirs()
    for folder in folders:
        if (folder / name).is_file():
            return folder / name
    raise SystemExit(f"ERROR: font {name!r} not found (looked in {[str(d) for d in folders]})")


def _norm(value):
    """Colours compare without case; a shadow compares by its parts."""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    return value


def set_typed_words(src: Image.Image, style: dict, blocks: list[dict]) -> tuple[Image.Image, dict]:
    """Set the blocks on src from the styling; return the image (same size) and the card's record."""
    font_path = find_font_file(style["font_file"])
    body = style.get("body")
    body_font_path = find_font_file(body["font_file"]) if body else None
    img = src.convert("RGBA")
    W, H = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    title_fill = parse_color(style["fill"])
    outline = parse_color(style["outline_color"])
    title_width = int(style["outline_width"])
    title_shadow = style.get("shadow")
    used = []
    for block in blocks:
        level = block["level"]
        is_body = bool(body) and level in body["sizes"] and level not in style["sizes"]
        if not is_body and level not in style["sizes"]:
            raise SystemExit(f"ERROR: level {level!r} is not in the styling's title sizes {list(style['sizes'])}"
                             + (f" or body sizes {list(body['sizes'])}" if body else " (the styling has no body style)"))
        sizes, face = (body["sizes"], body_font_path) if is_body else (style["sizes"], font_path)
        is_title = block.get("role") == "title" and not is_body and style.get("title_size") is not None
        size = int(style["title_size"] if is_title else sizes[level])
        font = ImageFont.truetype(str(face), size)
        fill = parse_color(body["fill"]) if is_body else title_fill
        width = 0 if is_body else title_width
        shadow = None if is_body else title_shadow
        text = block["text"]
        if block.get("max_width"):
            text = "\n".join(wrap_cjk(text, font, int(W * block["max_width"]), draw))
        cx, cy = block["at"][0] * W, block["at"][1] * H
        x0, y0, x1, y1 = draw.multiline_textbbox((cx, cy), text, font=font, stroke_width=width, anchor="mm", align="center")
        if shadow:  # the box grows by the shadow offset on the side it falls
            x0, x1 = x0 + min(0, shadow["dx"]), x1 + max(0, shadow["dx"])
            y0, y1 = y0 + min(0, shadow["dy"]), y1 + max(0, shadow["dy"])
        mx, my = W * SAFE_MARGIN, H * SAFE_MARGIN
        if x0 < mx or y0 < my or x1 > W - mx or y1 > H - my:
            raise SystemExit(f"ERROR: block {block['text']!r} is drawn at ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f}), outside the "
                             f"safe margin ({mx:.0f}px left/right, {my:.0f}px top/bottom of {W}x{H}); correct the layout plan and set the words again")
        if shadow:
            sc = parse_color(shadow["color"])
            draw.multiline_text((cx + shadow["dx"], cy + shadow["dy"]), text, font=font, fill=sc,
                                stroke_width=width, stroke_fill=sc, anchor="mm", align="center")
        draw.multiline_text((cx, cy), text, font=font, fill=fill, stroke_width=width, stroke_fill=outline,
                            anchor="mm", align="center")
        entry = {"text": block["text"], "level": level, "size": size, "at": block["at"]}
        if is_body:
            entry["kind"] = "body"
        if is_title:
            entry["role"] = "title"
        used.append(entry)
    record = {key: style.get(key) for key in STYLE_KEYS}
    if any(b.get("kind") == "body" for b in used):
        record["body"] = {"font_file": body["font_file"], "fill": body["fill"], "outline_width": 0, "shadow": None}
    record["blocks"] = used
    return img.convert("RGB"), record


def compare_records(style: dict, records: dict[str, dict]) -> list[str]:
    """Differences between each card's record and the set's styling. Only the size may differ between
    levels, and each level's size must be the set's size for that level."""
    problems = []
    for name, record in records.items():
        for key in STYLE_KEYS:
            if _norm(record.get(key)) != _norm(style.get(key)):
                problems.append(f"{name}: {key} is {record.get(key)!r}, the set's styling has {style.get(key)!r}")
        body = style.get("body")
        rec_body = record.get("body")
        if rec_body is not None:
            want = {"font_file": body["font_file"], "fill": body["fill"], "outline_width": 0, "shadow": None} if body else None
            if want is None:
                problems.append(f"{name}: body text is set but the set's styling has no body style")
            else:
                for key, value in want.items():
                    if _norm(rec_body.get(key)) != _norm(value):
                        problems.append(f"{name}: body {key} is {rec_body.get(key)!r}, the body style has {value!r}")
        for block in record.get("blocks", []):
            level, size = block.get("level"), block.get("size")
            if block.get("kind") == "body":
                if not body or level not in body["sizes"]:
                    problems.append(f"{name}: body block at level {level!r} uses title styling or a level not in the body style")
                elif size != body["sizes"][level]:
                    problems.append(f"{name}: body {level} is size {size}, the body style has {body['sizes'][level]}")
            elif block.get("role") == "title" and style.get("title_size") is not None:
                if size != style["title_size"]:
                    problems.append(f"{name}: title {block.get('text')!r} is size {size}, title_size is {style['title_size']}")
            elif level not in style["sizes"]:
                problems.append(f"{name}: title level {level!r} is not in the set's styling")
            elif size != style["sizes"][level]:
                problems.append(f"{name}: {level} is size {size}, the set's styling has {style['sizes'][level]}")
    return problems


def _load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def typed_main(args: argparse.Namespace) -> int:
    if not args.blocks or not args.input or not args.output:
        print("ERROR: --styling needs INPUT OUTPUT and --blocks", file=sys.stderr)
        return 2
    out, record = set_typed_words(Image.open(args.input), _load_json(args.styling), _load_json(args.blocks))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.save(args.output)
    if args.record:
        Path(args.record).parent.mkdir(parents=True, exist_ok=True)
        Path(args.record).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {args.output} ({out.size[0]}x{out.size[1]}, {len(record['blocks'])} block(s))")
    return 0


def check_main(styling_path: str, record_paths: list[str]) -> int:
    if not record_paths:
        print("ERROR: --check-records needs STYLING.json and at least one RECORD.json", file=sys.stderr)
        return 2
    problems = compare_records(_load_json(styling_path), {p: _load_json(p) for p in record_paths})
    for line in problems:
        print("FAIL", line)
    print("PASS" if not problems else f"{len(problems)} difference(s)")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--text", default=None)
    ap.add_argument("--styling", default=None, help="typed-font set: the stored styling file")
    ap.add_argument("--blocks", default=None, help="typed-font set: this card's text blocks")
    ap.add_argument("--record", default=None, help="typed-font set: where to write this card's record")
    ap.add_argument("--check-records", nargs="+", metavar=("STYLING", "RECORD"), default=None,
                    help="compare cards' records with the set's styling")
    ap.add_argument("--position", choices=("top", "center", "bottom"),
                    default="bottom")
    ap.add_argument("--font", default=None)
    ap.add_argument("--size", type=int, default=72)
    ap.add_argument("--color", default="#FFFFFF")
    ap.add_argument("--bg", default="#000000AA",
                    help="backdrop color w/ alpha; empty to disable")
    ap.add_argument("--fit", default="3:4",
                    help="target aspect ratio, e.g. 3:4; empty to skip")
    ap.add_argument("--padding", type=int, default=48)
    args = ap.parse_args()
    if args.check_records:
        return check_main(args.check_records[0], args.check_records[1:])
    if args.styling:
        return typed_main(args)
    if args.text is None or not args.input or not args.output:
        ap.error("INPUT, OUTPUT and --text are required")

    src = Image.open(args.input).convert("RGBA")
    src = fit_aspect(src, args.fit)
    W, H = src.size

    overlay = Image.new("RGBA", src.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(args.font, args.size)

    max_w = W - 2 * args.padding
    lines = wrap_cjk(args.text, font, max_w, draw)
    line_h = args.size + 12
    block_h = line_h * len(lines)

    if args.position == "top":
        y0 = args.padding
    elif args.position == "center":
        y0 = (H - block_h) // 2
    else:
        y0 = H - block_h - args.padding

    if args.bg:
        bg = parse_color(args.bg)
        draw.rectangle(
            (args.padding // 2, y0 - 24,
             W - args.padding // 2, y0 + block_h + 24),
            fill=bg,
        )

    color = parse_color(args.color)
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=font)
        x = (W - w) / 2
        draw.text((x, y0 + i * line_h), line, font=font, fill=color)

    out = Image.alpha_composite(src, overlay).convert("RGB")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.save(args.output, quality=92)
    print(f"OK: {args.output} ({W}x{H}, {len(lines)} line(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
