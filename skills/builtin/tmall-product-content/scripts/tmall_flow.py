"""Gates between the stages: headline A/B/C, pick or ruling, affected-only re-make, and who may reach the approval page."""
from __future__ import annotations

class FlowError(RuntimeError):
    pass

def new_state() -> dict:
    return {"style_lock_version": 1, "headline": {"versions": None, "picked": None, "rulings": []}, "images": {}}

def register_versions(state: dict, versions: dict) -> None:
    if sorted(versions) != ["A", "B", "C"]:
        raise FlowError("the headline needs versions A, B and C")
    if len({v["listing_id"] for v in versions.values()}) != 3:
        raise FlowError("each version must follow a different leading listing")
    if len({v["direction"] for v in versions.values()}) != 3:
        raise FlowError("each version must differ in direction")
    if not all(v["checks_passed"] for v in versions.values()):
        raise FlowError("all three versions must pass the checks before the owner sees them")
    state["headline"]["versions"], state["headline"]["picked"] = versions, None

def pick(state: dict, key: str) -> None:
    if not state["headline"]["versions"] or key not in state["headline"]["versions"]:
        raise FlowError("no such headline version to pick")
    state["headline"]["picked"] = key

def rule_on_versions(state: dict, ruling: str) -> None:
    h = state["headline"]
    h["rulings"].append(ruling); h["versions"], h["picked"] = None, None
    state["style_lock_version"] += 1          # a ruling changes the style lock before anything else is made

def may_make(state: dict, image_id: str) -> bool:
    return image_id == "M1" or state["headline"]["picked"] is not None

def reject(state: dict, ruling: str, affected: list[str]) -> list[str]:
    if state["headline"]["picked"] is None:
        raise FlowError("nothing is approved yet to reject")
    for i in affected:
        state["images"][i] = {"status": "to_remake", "ruling": ruling}
    return sorted(affected)

def changed_outside(before: dict, after: dict, affected: list[str]) -> list[str]:
    return sorted(k for k in before if k not in affected and after.get(k) != before[k])

def may_show_approval(reports: dict, image_ids: list[str]) -> bool:
    return all(i in reports and reports[i]["complete"] and reports[i]["passed"] for i in image_ids)

import shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_common as common

def promote_pick(product_dir, state: dict) -> list[str]:
    """Copy the picked headline version's files (composed as M1 in headline/<key>/, Task 27) up into the product folder, byte for byte,
    so the handover finds M1 beside M2 to M5 and the version's stage 6 report still matches its image (reviewed-plan audit pass 3)."""
    key = state["headline"]["picked"]
    if key is None:
        raise FlowError("no headline version picked yet")
    product_dir = Path(product_dir); src = product_dir / "headline" / key
    if not (src / "M1.png").is_file():
        raise FlowError(f"{src} has no M1.png; compose version {key} there first")
    for old in product_dir.glob("M1.*"):          # an earlier pick's copy goes first, so no layer of another version is left behind
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    for p in src.glob("M1.*"):
        (shutil.copytree if p.is_dir() else shutil.copy2)(p, product_dir / p.name)
    return sorted(p.name for p in src.glob("M1.*"))

def load_state(product_dir) -> dict:
    """The one way to read flow.json; the agent's short scripts call this and save_state, never their own JSON code."""
    f = Path(product_dir) / "flow.json"
    return common.read_json(f) if f.is_file() else new_state()

def save_state(product_dir, state: dict) -> None:
    common.write_json(Path(product_dir) / "flow.json", state)          # atomic: an interrupted save leaves the old file whole

def main(argv=None) -> int:
    import argparse, json
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["status"]); ap.add_argument("product_dir")
    a = ap.parse_args(argv)
    state = load_state(a.product_dir)
    save_state(a.product_dir, state)
    h = state["headline"]
    print(json.dumps({"style_lock_version": state["style_lock_version"], "versions_ready": h["versions"] is not None, "picked": h["picked"]}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
