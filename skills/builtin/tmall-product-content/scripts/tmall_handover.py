"""Stage 8: the upload-ready folder. Checks first, writes only when everything passes."""
from __future__ import annotations
import shutil, sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_common as common, tmall_psd, tmall_rules

class HandoverError(RuntimeError):
    pass

def hand_over(src, out, *, mains: list[str], details: list[str], copy_text: str, main_sizes=None, detail_width=790) -> Path:
    """`main_sizes` is the set of sizes a main image may have; left out, it is read from the Tmall rules file (`main_image.sizes`)."""
    src, out = Path(src), Path(out)
    if out.exists():
        raise HandoverError(f"{out} already exists; move it aside or choose a new folder (a handover is never written over)")
    allowed = [tuple(s) for s in (tmall_rules.value(tmall_rules.load(), "main_image.sizes") if main_sizes is None else main_sizes)]
    problems = []
    for n in mains:
        size = Image.open(src / f"{n}.png").size
        if size not in allowed:
            problems.append(f"{n}: is {size[0]}×{size[1]}, not one of the sizes the rules file allows ({', '.join(f'{w}×{h}' for w, h in allowed)})")
    for n in details:
        width = Image.open(src / f"{n}.png").width
        if width != detail_width: problems.append(f"{n}: is {width} wide, not {detail_width}")
    for n in mains + details:
        if not (src / f"{n}.manifest.json").is_file(): problems.append(f"{n}: no layer manifest")
    if problems:
        raise HandoverError("; ".join(problems))
    work = out.with_name(out.name + ".partial")          # built aside, renamed at the end: a failed PSD never leaves a half-filled handover
    shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True)
    try:
        for n in mains + details:
            shutil.copy2(src / f"{n}.png", work / f"{n}.png")
            psd = tmall_psd.psd_from_manifest(src, common.read_json(src / f"{n}.manifest.json"))   # also leaves <n>.psd beside the working images
            shutil.copy2(psd, work / f"{n}.psd")
        (work / "copy.md").write_text(copy_text, encoding="utf-8")
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    work.rename(out)
    return out
