"""A small PSD writer: raw 8-bit RGB, one RGBA raster layer per name. Text blocks are named picture layers, not live type."""
from __future__ import annotations
import struct
from pathlib import Path
from PIL import Image

def _pascal(name: str) -> bytes:
    if not name.isascii():       # the legacy layer-name field is not Unicode; a Chinese text id would otherwise crash mid-write (autoplan review)
        raise ValueError(f"layer name {name!r} must be ASCII; give the text block an ASCII id")
    b = name.encode("ascii")[:255]
    raw = bytes([len(b)]) + b
    return raw + b"\0" * ((-len(raw)) % 4)

def write_psd(path, size, layers: list[dict]) -> None:
    W, H = size
    out = bytearray(b"8BPS" + struct.pack(">H6xHIIHH", 1, 3, H, W, 8, 3))
    out += struct.pack(">I", 0) + struct.pack(">I", 0)                    # colour mode data, image resources
    records, data = bytearray(), bytearray()
    for L in layers:
        img = L["image"].convert("RGBA"); x, y = L.get("x", 0), L.get("y", 0); w, h = img.size
        r, g, b, a = (c.tobytes() for c in img.split())
        rec = struct.pack(">iiiiH", y, x, y + h, x + w, 4)
        for cid, blob in ((-1, a), (0, r), (1, g), (2, b)):
            rec += struct.pack(">hI", cid, 2 + len(blob)); data += struct.pack(">H", 0) + blob
        extra = struct.pack(">II", 0, 0) + _pascal(L["name"])
        rec += b"8BIM" + b"norm" + struct.pack(">BBBB", 255, 0, 0, 0) + struct.pack(">I", len(extra)) + extra
        records += rec
    info = struct.pack(">h", len(layers)) + bytes(records) + bytes(data)
    if len(info) % 2:
        info += b"\0"
    section = struct.pack(">I", len(info)) + info + struct.pack(">I", 0)
    out += struct.pack(">I", len(section)) + section
    flat = Image.new("RGBA", size, (255, 255, 255, 255))
    for L in layers:
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))          # paste places a layer that starts left of or above the frame (on Pillow 12.3, the venv's, alpha_composite accepts it too: probed in the reviewed-plan audit)
        img = L["image"].convert("RGBA"); canvas.paste(img, (L.get("x", 0), L.get("y", 0)), img)
        flat = Image.alpha_composite(flat, canvas)
    out += struct.pack(">H", 0) + b"".join(c.tobytes() for c in flat.convert("RGB").split())
    Path(path).write_bytes(out)

def psd_from_manifest(folder, manifest: dict) -> Path:
    folder = Path(folder)
    layers = [{"name": "scene", "image": Image.open(folder / f"{manifest['name']}.layers" / "scene.png")}]
    if manifest.get("shadow"):
        sb = manifest["shadow"]["box"]
        layers.append({"name": "pack_shadow", "image": Image.open(folder / manifest["shadow"]["layer"]), "x": sb[0], "y": sb[1]})
    if manifest.get("pack"):
        pb = manifest["pack"]["box"]
        layers.append({"name": "pack", "image": Image.open(folder / manifest["pack"]["layer"]), "x": pb[0], "y": pb[1]})
    for t in manifest["texts"]:
        if t.get("box"):
            layers.append({"name": f"text_{t['id']}", "image": Image.open(folder / t["layer"]), "x": t["box"][0], "y": t["box"][1]})
    out = folder / f"{manifest['name']}.psd"
    write_psd(out, tuple(manifest["size"]), layers)
    return out
