"""Stage 3 page-plan validator."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_rules

ROLES = ["headline", "ingredients_evidence", "scene_audience", "comparison_proof", "sizes_bundles"]

def validate(plan: dict, sheet: dict, rules: dict) -> list[str]:
    out = []
    mains = plan.get("main_images", [])
    if [m.get("role") for m in mains] != ROLES:
        out.append(f"need five main images in the diagnosis roles {ROLES}")
    allowed = [list(s) for s in tmall_rules.value(rules, "main_image.sizes")]
    size = plan.get("main_size")
    if size is None:
        out.append("main_size: the plan must choose the main-image size (stage 3: the competitor cases decide, the Tmall rules file's sizes are the fallback)")
    elif list(size) not in allowed:
        out.append(f"main_size: {size[0]}×{size[1]} is not one of the sizes the Tmall rules file allows ({', '.join(f'{w}×{h}' for w, h in allowed)})")
    items = mains + plan.get("detail_screens", [])
    settled = {f["id"] for f in sheet["facts"] if f["status"] == "settled"}
    seen_q, seen_f = {}, {}
    for it in items:
        q, fid = (it.get("question") or "").strip(), it.get("fact_id")
        if not q or not fid:
            out.append(f"{it['id']}: needs a buyer question and the fact that answers it"); continue
        if q in seen_q: out.append(f"{it['id']}: same buyer question as {seen_q[q]}")
        seen_q.setdefault(q, it["id"])
        if fid not in settled: out.append(f"{it['id']}: fact {fid} is not a settled fact")
        elif fid in seen_f: out.append(f"{it['id']}: restates the main point of {seen_f[fid]}; merge or cut")
        seen_f.setdefault(fid, it["id"])
    ids = {it["id"]: it for it in items}
    for c in sheet["claims"]:
        target = plan.get("selling_point_map", {}).get(c["id"])
        if target not in ids: out.append(f"{c['id']}: not assigned to an image or screen")
        elif c["id"] not in ids[target].get("claim_ids", []): out.append(f"{c['id']}: {target} does not carry it")
    usable = {i["angle"] for i in sheet["inventory"] if i["use"] != "reference only"}
    seen_a = set()
    for m in mains:
        a = m.get("pack_angle")
        if a and a not in usable: out.append(f"{m['id']}: pack angle {a} is not in the picture inventory")
        if a in seen_a and not m.get("varies"): out.append(f"{m['id']}: repeats an angle without varying scale, crop or scene")
        if a: seen_a.add(a)
        for w in tmall_rules.after_state_hits(m.get("scene", ""), rules):
            out.append(f"{m['id']}: scene implies a result ({w})")
        cmp_ = m.get("comparison")
        if cmp_:
            if cmp_.get("competitor") and not cmp_.get("verified_fact_ids"):
                out.append(f"{m['id']}: names a competitor without verified facts")
            for fid in cmp_.get("verified_fact_ids", []):
                if fid not in settled: out.append(f"{m['id']}: competitor fact {fid} is not a settled fact")
            for n in cmp_.get("numbers", []):
                if not n.get("fact_id"): out.append(f"{m['id']}: number without a fact behind it")
                elif n["fact_id"] not in settled: out.append(f"{m['id']}: number {n.get('value')} rests on {n['fact_id']}, which is not a settled fact")
    if len(seen_a) < len(mains) and not plan.get("angle_note"):
        out.append("repeated angles need an angle_note saying how the set is varied")
    for k in ("palette", "font", "layout"):
        if not plan.get("style_lock", {}).get(k): out.append(f"style lock lacks {k}")
    return out

def main(argv=None) -> int:
    """`check <product_dir>`: reads plan.json and fact-sheet.json there and the shipped Tmall rules file (autoplan review: the agent
    otherwise had to write a script for the one stage-3 check)."""
    import argparse, json
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("product_dir")
    a = ap.parse_args(argv)
    folder = Path(a.product_dir)
    missing = [n for n in ("plan.json", "fact-sheet.json") if not (folder / n).is_file()]
    if missing:
        print(f"{folder}: missing {', '.join(missing)}", file=sys.stderr); return 2
    read = lambda n: json.loads((folder / n).read_text(encoding="utf-8"))
    problems = validate(read("plan.json"), read("fact-sheet.json"), tmall_rules.load())
    print("\n".join(problems) or "OK")
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
