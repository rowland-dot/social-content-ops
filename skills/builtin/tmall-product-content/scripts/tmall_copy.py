"""Stage 4 copy rules: three tiers per screen, and every word traced to a claim or a worked-out price."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_prices

def fit_screen(blocks: list[dict], capacity: int) -> dict:
    kept, dropped, moved = list(blocks), [], []
    size = lambda: sum(len(b["text"]) for b in kept)
    for tier, bucket in (("extra", dropped), ("needed", moved)):
        for b in reversed([b for b in blocks if b["tier"] == tier]):
            if size() <= capacity: break
            kept.remove(b); bucket.insert(0, b)
    return {"kept": kept, "dropped_extras": dropped, "moved": moved, "overflow": size() > capacity}

def closing_problem(blocks: list[dict], capacity: int, min_fill: float) -> str:
    fill = sum(len(b["text"]) for b in blocks) / capacity
    return "" if fill >= min_fill else f"closing screen is only {fill:.0%} full; it must not be left half empty"

def trace(blocks: list[dict], sheet: dict, allowed_prices, bundle_rows: list) -> list[str]:
    """allowed_prices is a set of prices, or a dict of price -> basis so a mismatch shows where the right price comes from.
    bundle_rows are the price list's bundle rows; a bundle offer with none is a failure (no default: it cannot be skipped by omission)."""
    out, claims = [], {c["id"] for c in sheet["claims"]}
    basis = "; ".join(f"{p} = {b}" for p, b in allowed_prices.items()) if isinstance(allowed_prices, dict) else ""
    for b in blocks:
        prices = tmall_prices.extract_prices(b["text"])
        for cid in b.get("claims", []):
            if cid not in claims: out.append(f"{b['id']}: claim {cid} is not in the fact sheet")
        for f in sheet["forbidden"]:
            if f["text"] in b["text"]: out.append(f"{b['id']}: contains forbidden phrase {f['text']}")
        for p in tmall_prices.check_printed(b["text"], allowed_prices):
            out.append(f"{b['id']}: price {p} does not match the price list" + (f" (worked-out prices: {basis})" if basis else ""))
        if bundle := tmall_prices.bundle_problem(b["text"], bundle_rows): out.append(f"{b['id']}: {bundle}")
        if not b.get("claims") and not prices: out.append(f"{b['id']}: no claim and no worked-out price behind it")
    return out
