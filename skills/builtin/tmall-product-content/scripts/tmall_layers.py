"""Stage 6 layer checks, measured on the layered files rather than judged by eye."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import colorsys, hashlib
from PIL import Image

def overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

def text_over_pack(layout: dict, pack_box) -> list[dict]:
    return [b for b in layout["boxes"] if b["kind"] in ("text", "note") and overlaps(b["box"], pack_box)]

def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

def luminance(rgb) -> float:
    r, g, b = (_lin(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast_ratio(a, b) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)

def _hex(c: str):
    c = c.lstrip("#")
    if len(c) == 3: c = "".join(ch * 2 for ch in c)        # #fff is #ffffff
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

def contrast_problem(block: dict, base: Image.Image, minimum: float) -> str:
    l, t, r, b = block["box"]
    px = np.asarray(base.convert("RGB").crop((l, t, r, b))).reshape(-1, 3)
    c = px / 255.0
    lum = (np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4) @ np.array([0.2126, 0.7152, 0.0722]))
    order = np.argsort(lum)
    worst = min(contrast_ratio(_hex(block["color"]), px[order[int(len(px) * q)]]) for q in (0.05, 0.95))
    return "" if worst >= minimum else f"{block['id']}: contrast {worst:.1f} to 1 is below {minimum}"

def size_problem(block: dict, minimum: int) -> str:
    return "" if block["px"] >= minimum else f"{block['id']}: type {block['px']} px is below the minimum {minimum} px (cut words, never shrink)"

def thumbnail_problem(manifest: dict, thumb_px: int, min_headline_px: float) -> str:
    scale = thumb_px / max(manifest["size"])
    for t in manifest["texts"]:
        if t["tier"] == "headline" and t["px"] * scale < min_headline_px:
            return f"{t['id']}: headline is {t['px'] * scale:.1f} px at {thumb_px} px thumbnail, below {min_headline_px}"
    return ""

def size_weight_problem(path, sizes, max_kb) -> str:
    size = list(Image.open(path).size)
    if size not in [list(s) for s in sizes]:
        return f"size {size} is not one of {sizes}"
    kb = Path(path).stat().st_size / 1024
    return "" if kb <= max_kb else f"file weighs {kb:.1f} KB, over {max_kb} KB"

def _full(t: dict):
    return t.get("full_box") or t.get("box")     # full_box is measured unclipped by compose; render_card's layout boxes are clipped to the frame

def off_frame(texts: list[dict], size) -> list[str]:
    w, h = size
    return [f"text '{t['id']}' runs off the frame" for t in texts
            if _full(t) and (_full(t)[0] < 0 or _full(t)[1] < 0 or _full(t)[2] > w or _full(t)[3] > h)]

def text_on_text(texts: list[dict]) -> list[str]:
    boxed = [t for t in texts if _full(t)]
    return [f"text '{a['id']}' overlaps text '{b['id']}'" for i, a in enumerate(boxed) for b in boxed[i + 1:] if overlaps(_full(a), _full(b))]

def outside_frame(layout: dict) -> list[dict]:
    return [b for b in layout["boxes"] if b["box"][0] < 0 or b["box"][1] < 0
            or b["box"][2] > layout["width"] or b["box"][3] > layout["height"]]


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def pack_problem(folder, manifest: dict) -> str:
    p = manifest.get("pack")
    if not p: return "no pack layer"
    if p.get("rotation", 0) != 0: return "pack layer is rotated"
    if sha(p["source"]) != p["source_sha256"]: return "pack source file differs from the one recorded"
    src, layer = Image.open(p["source"]).convert("RGBA"), Image.open(Path(folder) / p["layer"]).convert("RGBA")
    if abs(layer.width / layer.height - src.width / src.height) > 0.005 * src.width / src.height:
        return "pack layer aspect ratio differs from the source (stretched)"
    diff = np.abs(np.asarray(src.resize(layer.size, Image.LANCZOS), float) - np.asarray(layer, float)).mean()
    return "" if diff <= 2.0 else f"pack layer pixels differ from the scaled source (mean difference {diff:.1f})"

def _centroid(gray: np.ndarray, mask: np.ndarray):
    ys, xs = np.nonzero(mask); w = gray[mask]
    if w.sum() == 0: return 0.0, 0.0
    return ((xs * w).sum() / w.sum() - xs.mean()) / (np.ptp(xs) + 1), ((ys * w).sum() / w.sum() - ys.mean()) / (np.ptp(ys) + 1)

def light_side(img: Image.Image, mask=None, flat: float = 0.03) -> str:
    rgba = img.convert("RGBA"); gray = np.asarray(rgba.convert("L"), float)
    m = (np.asarray(rgba.getchannel("A")) > 128) if mask is None else mask
    dx, _dy = _centroid(gray, m)
    return "left" if dx < -flat else "right" if dx > flat else "flat"

def light_problem(pack_side: str, scene_side: str) -> str:
    if pack_side == "flat" or scene_side == "flat":
        return ""          # no clear side on one of them: nothing to contradict
    return "" if pack_side == scene_side else f"scene light comes from the {scene_side}, pack photo light from the {pack_side}"

def shadow_problem(m: dict) -> str:
    if not m.get("shadow") or not m.get("pack"): return "no contact shadow layer"
    px0, py0, px1, py1 = m["pack"]["box"]; sx0, sy0, sx1, sy1 = m["shadow"]["box"]
    foot_ok = abs((sy0 + sy1) / 2 - py1) <= 0.06 * (py1 - py0)
    width_ok = min(px1, sx1) - max(px0, sx0) >= 0.6 * (px1 - px0)
    return "" if foot_ok and width_ok else "contact shadow does not sit under the pack foot"

def surface_problem(scene: Image.Image, pack_box, band=(-10, 40), minimum: float = 6.0) -> str:
    g = np.asarray(scene.convert("L"), float); x0, _y0, x1, y1 = pack_box
    rows = g[max(0, y1 + band[0]): y1 + band[1], x0:x1]
    if rows.shape[0] < 2: return "no room under the pack to look for a surface"
    edge = np.abs(np.diff(rows, axis=0)).mean(axis=1).max()
    return "" if edge >= minimum else "no surface edge under the pack (proxy; also needs the looked verdict)"

def frame_problem(m: dict, minimum: float) -> str:
    p = m["pack"]; share = (p["box"][3] - p["box"][1]) / m["size"][1]
    if p.get("rotation", 0) != 0: return "pack is not upright"
    return "" if share >= minimum else f"pack is {share:.0%} of the frame height, below {minimum:.0%}"

def glare_problem(img: Image.Image, box, max_share: float, pack_layer: Image.Image | None = None) -> str:
    """Blown-out pixels in the pack area. With the pack layer given, a pixel that is already white in the pack photo itself (a white
    pack, white print) does not count: the pack may not be changed, so counting it would fail a white pack for good (autoplan review)."""
    a = np.asarray(img.convert("RGB").crop(tuple(box)))
    blown = a.min(axis=2) >= 250
    if pack_layer is not None:
        p = np.asarray(pack_layer.convert("RGBA").resize(blown.shape[::-1]))
        blown &= ~((p[..., :3].min(axis=2) >= 250) & (p[..., 3] > 128))
    share = float(blown.mean())
    return "" if share <= max_share else f"{share:.0%} of the pack area is blown out (proxy for glare)"

def gold_on_light_problem(block: dict, base: Image.Image) -> str:
    h, s, _v = colorsys.rgb_to_hsv(*(c / 255 for c in _hex(block["color"])))
    l, t, r, b = block["box"]
    mean = np.asarray(base.convert("RGB").crop((l, t, r, b))).reshape(-1, 3).mean(axis=0)
    return f"{block['id']}: gold text on a light backdrop" if 35 / 360 <= h <= 55 / 360 and s > 0.4 and luminance(mean) > 0.6 else ""
