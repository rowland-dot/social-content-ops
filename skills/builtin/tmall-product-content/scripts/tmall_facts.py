"""Stage 1 fact and claims sheet: settle conflicts, validate, render the readable copy."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_common as common, tmall_prices

KINDS = {"spec", "dose", "origin", "type", "shelf_life", "certification", "price", "shipping"}
ANGLES = {"front", "back", "side", "top", "open"}
USES = {"use as is", "crop", "reference only"}

def settle(kind: str, candidates: list[dict]) -> dict:
    if kind == "price":                                  # prices come from the price list only (The owner)
        pool = [dict(c, text=str(tmall_prices.money(c["text"]))) for c in candidates if c["source_type"] == "price_list"]   # one money rule: "300" and "300.00" agree
        texts = {c["text"] for c in pool}
        if len(pool) >= 2 and len(texts) == 1:
            return {"status": "settled", "text": pool[0]["text"], "source": ", ".join(c["source"] for c in pool), "conflict": []}
        return {"status": "waiting_on_ro", "text": _each(pool), "source": "price list", "conflict": []}
    website = [c for c in candidates if c["source_type"] == "website"]
    if website:
        win = website[0]
        return {"status": "settled", "text": win["text"], "source": win["source"],
                "conflict": [{"source": c["source"], "text": c["text"]} for c in candidates if c["text"] != win["text"]]}
    texts = {c["text"] for c in candidates}
    if candidates and len(texts) == 1:
        return {"status": "settled", "text": candidates[0]["text"], "source": ", ".join(c["source"] for c in candidates), "conflict": []}
    return {"status": "waiting_on_ro", "text": _each(candidates), "source": ", ".join(c["source"] for c in candidates), "conflict": []}

def _each(candidates: list[dict]) -> str:
    """Every value with the source that gave it, so the owner sees which copy said what (autoplan review)."""
    return " or ".join(f"{c['text']} ({c['source']})" for c in candidates) or "no source gave a value"

def validate(sheet: dict) -> list[str]:
    problems, facts = [], {f["id"]: f for f in sheet.get("facts", [])}
    for f in facts.values():
        if not f.get("source"): problems.append(f"{f['id']}: no source")
        if f.get("kind") not in KINDS: problems.append(f"{f['id']}: kind {f.get('kind')!r}")
    for c in sheet.get("claims", []):
        if not c.get("source"): problems.append(f"{c['id']}: no source")
        for fid in c.get("fact_ids", []):
            if fid not in facts: problems.append(f"{c['id']}: unknown fact {fid}")
            elif facts[fid]["status"] != "settled": problems.append(f"{c['id']}: rests on {fid}, which is waiting on the owner")
    if not sheet.get("forbidden"): problems.append("no forbidden claims listed")
    if not sheet.get("shipping", {}).get("route"): problems.append("no shipping route")
    for i in sheet.get("inventory", []):
        if i.get("angle") not in ANGLES: problems.append(f"{i.get('file')}: angle {i.get('angle')!r}")
        if i.get("use") not in USES: problems.append(f"{i.get('file')}: use {i.get('use')!r}")
    return problems

def render(sheet: dict) -> str:
    waiting = [f for f in sheet["facts"] if f["status"] != "settled"]
    out = [f"# Fact and claims sheet: {sheet['product']}", ""]
    if waiting:
        out += ["## Waiting on the owner", ""] + [f"- {f['id']} ({f['kind']}): {f['text']} (source: {f['source']})" for f in waiting] + [""]
    out += ["## Facts", ""] + [f"- {f['id']} ({f['kind']}): {f['text']} (source: {f['source']})" for f in sheet["facts"] if f["status"] == "settled"]
    out += ["", "## Allowed claims", ""] + [f"- {c['id']}: {c['text']} (facts {', '.join(c['fact_ids'])}; source: {c['source']})" for c in sheet["claims"]]
    out += ["", "## Forbidden claims", ""] + [f"- {x['text']} (source: {x['source']})" for x in sheet["forbidden"]]
    out += ["", f"## Shipping route", "", f"{sheet['shipping']['route']} (source: {sheet['shipping']['source']})", "", "## Picture inventory", ""]
    out += [f"- {i['file']}: {i['angle']}, {i['use']}" for i in sheet["inventory"]]
    return "\n".join(out) + "\n"

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "render"):
        sub.add_parser(name).add_argument("product_dir")
    a = ap.parse_args(argv)
    path = Path(a.product_dir) / "fact-sheet.json"
    sheet = common.read_json(path)
    if a.cmd == "check":
        problems = validate(sheet)
        print("\n".join(problems) or "OK")
        return 1 if problems else 0
    (Path(a.product_dir) / "fact-sheet.md").write_text(render(sheet), encoding="utf-8")
    return 0

if __name__ == "__main__":
    sys.exit(main())
