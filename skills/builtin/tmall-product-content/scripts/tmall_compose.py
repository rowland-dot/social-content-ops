"""Stage 5: lay the real pack and set the Chinese text over a text-free scene. The pack is scaled and positioned only."""
from __future__ import annotations
import html, io, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageOps
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_common as common, tmall_fonts as fonts

RENDER = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "render_card.py"

class PackNeedsCutout(ValueError):
    """The pack photo has a solid background. Removing it edits pack pixels, so the owner decides first."""

def _pack_layer(src, height: int, cx: int, bottom: int):
    im = Image.open(src)
    if im.mode != "RGBA" or im.getpixel((0, 0))[3] != 0 or im.getpixel((im.width - 1, 0))[3] != 0:
        raise PackNeedsCutout(f"{src}: not a transparent cut-out")
    w = round(im.width * height / im.height)
    return im.resize((w, height), Image.LANCZOS), (round(cx - w / 2), bottom - height)

def _shadow(pack_w: int, pack_h: int):
    w, h = round(pack_w * 1.1), max(8, round(pack_h * 0.12))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((w * .05, h * .2, w * .95, h * .8), fill=(0, 0, 0, 150))
    return img.filter(ImageFilter.GaussianBlur(h * .12))

def _style(t: dict) -> str:
    return (f"left:{t['x']}px;top:{t['y']}px;width:{t['w']}px;font:{t['weight']} {t['px']}px/1.25 "
            f"'{t['font']}',sans-serif;color:{t['color']}")

def _page(size, folder: str, layers: dict, texts: list[dict], transparent=False) -> str:
    w, h = size
    bg = "transparent" if transparent else f"url('{folder}/scene.png') center/cover"
    parts = []
    if not transparent:
        for name in ("pack_shadow", "pack"):
            if name in layers:
                x, y = layers[name]["xy"]; iw, ih = layers[name]["size"]
                parts.append(f"<img style='position:absolute;left:{x}px;top:{y}px;width:{iw}px;height:{ih}px' src='{folder}/{name}.png'>")
    # double-quoted attribute: the font name inside _style is single-quoted, and a single-quoted attribute ended there, dropping font and colour
    parts += [f'<div style="position:absolute;white-space:pre-wrap;{_style(t)}">{html.escape(t["text"])}</div>' for t in texts]
    return (f"<!doctype html><meta charset='utf-8'><style>*{{margin:0;padding:0;box-sizing:border-box}}"
            f"body{{background:transparent}}.frame{{position:relative;width:{w}px;height:{h}px;overflow:hidden;"
            f"background:{bg}}}</style><div class='frame'>{''.join(parts)}</div>")

def _render(html_path: Path, png: Path, size) -> None:
    r = subprocess.run([sys.executable, str(RENDER), "--html", str(html_path), "--out", str(png), "--selector", ".frame",
                        "--width", str(size[0]), "--height", str(size[1]), "--scale", "1", "--wait", "300"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"rendering {html_path.name} to {png} failed (the layers and page are written, the manifest is not; "
                           f"running compose again replaces them): {(r.stderr or r.stdout).strip()[:800]}")

def _text_layers(size, texts):
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        for t in texts:
            page.set_content(_page(size, "", {}, [t], transparent=True)); page.wait_for_timeout(150)
            im = Image.open(io.BytesIO(page.screenshot(omit_background=True))).convert("RGBA")
            box = im.getchannel("A").getbbox()
            # the screenshot stops at the frame; the element's own rectangle does not, so text running off the frame can be seen
            full = page.eval_on_selector(".frame > div", "e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom].map(Math.round); }")
            out[t["id"]] = (im.crop(box), box, full) if box else (None, None, full)
        browser.close()
    return out

def compose(out_dir, name: str, *, scene, size, texts: list[dict], pack: dict | None = None, style_lock_version=None) -> dict:
    for t in texts:
        if t["weight"] not in (400, 700):      # checked first, so it holds on a machine without the font files (CI): the licence list reads the regular and bold files only; another weight renders from a file nobody checked
            raise fonts.FontNotLicensed(f"{t['font']} weight {t['weight']}: only 400 and 700 are set, the weights whose files' licence is read")
        fonts.assert_allowed(t["font"])
        if not str(t["id"]).isascii():      # it becomes a PSD layer name, which must be ASCII: refused here, not at handover after the owner approved
            raise ValueError(f"text id {t['id']!r} must be ASCII")
    out_dir = Path(out_dir); folder = f"{name}.layers"; layers_dir = out_dir / folder
    layers_dir.mkdir(parents=True, exist_ok=True)
    ImageOps.fit(Image.open(scene).convert("RGB"), size, Image.LANCZOS).save(layers_dir / "scene.png")   # crop to cover, never stretch
    layers = {"scene": {"xy": (0, 0), "size": size}}
    manifest = {"name": name, "size": list(size), "pack": None, "style_lock_version": style_lock_version}
    if pack:
        layer, (x, y) = _pack_layer(pack["file"], pack["height"], pack["cx"], pack["bottom"])
        layer.save(layers_dir / "pack.png")
        sh = _shadow(*layer.size); sx, sy = round(x + layer.width / 2 - sh.width / 2), pack["bottom"] - sh.height // 2
        sh.save(layers_dir / "pack_shadow.png")
        layers["pack"] = {"xy": (x, y), "size": layer.size}; layers["pack_shadow"] = {"xy": (sx, sy), "size": sh.size}
        manifest["pack"] = {"source": str(pack["file"]), "source_sha256": common.sha256(pack["file"]), "rotation": 0,
                            "box": [x, y, x + layer.width, y + layer.height], "layer": f"{folder}/pack.png"}
        manifest["shadow"] = {"box": [sx, sy, sx + sh.width, sy + sh.height], "layer": f"{folder}/pack_shadow.png"}
    measured = _text_layers(size, texts) if texts else {}
    manifest["texts"] = []
    for t in texts:
        img, box, full = measured[t["id"]]
        if img is not None:
            img.save(layers_dir / f"text_{t['id']}.png")
        manifest["texts"].append({**t, "box": list(box) if box else None, "full_box": full, "layer": f"{folder}/text_{t['id']}.png"})
    (out_dir / f"{name}.html").write_text(_page(size, folder, layers, texts), encoding="utf-8")
    (out_dir / f"{name}.base.html").write_text(_page(size, folder, layers, []), encoding="utf-8")
    _render(out_dir / f"{name}.html", out_dir / f"{name}.png", size)
    _render(out_dir / f"{name}.base.html", out_dir / f"{name}.base.png", size)
    manifest["layer_names"] = ["scene"] + (["pack_shadow", "pack"] if pack else []) + [f"text_{t['id']}" for t in texts]
    manifest["files"] = {"final": f"{name}.png", "base": f"{name}.base.png", "layout": f"{name}.layout.json"}
    common.write_json(out_dir / f"{name}.manifest.json", manifest)
    return manifest
