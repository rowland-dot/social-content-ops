"""Selling prices from the 2026 price list, and every worked-out price. Costs and margins are never read."""
from __future__ import annotations
import re, sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_common as common

CENT = Decimal("0.01")
COST_WORDS = re.compile(r"成本|cost|margin|毛利|利润|进价|采购", re.I)
THRESHOLD = re.compile(r"满\s*\d+(?:\.\d+)?\s*元?\s*(?:[减送享]\s*\d*(?:\.\d+)?\s*元?)?")
PRICE = re.compile(r"[¥￥]\s*(\d+(?:\.\d{1,2})?)|(\d+(?:\.\d{1,2})?)\s*元|价格?\s*[:：]?\s*(\d+(?:\.\d{1,2})?)")   # the last form: a number right after 价 / 价格 (到手价199)
BUNDLE = re.compile(r"套装|组合|买\s*\d+\s*(?:送|享|件)")

def money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, ROUND_HALF_UP)

def read_selling_prices(xlsx, sheet: str, columns: dict[str, str], header_row: int = 1) -> list[dict]:
    """columns maps our key (sku, name, selling_price, ...) to the header text; a cost-like header is refused."""
    for header in columns.values():
        if COST_WORDS.search(header):
            raise ValueError(f"cost or margin column refused: {header}")
    ws = common.open_sheet(xlsx, sheet)    # openpyxl is imported inside: it is not declared in pyproject.toml, and every other function in this file must work without it
    rows = ws.iter_rows(min_row=header_row, values_only=True)
    header = list(next(rows))
    index = dict(zip(columns, common.column_index(header, columns.values(), f"{xlsx}, sheet {sheet}")))
    out = []
    for row in rows:
        if not row[index["sku"]]:
            continue
        item = {k: row[i] for k, i in index.items()}
        if "selling_price" in item:
            if item["selling_price"] in (None, ""):
                raise ValueError(f"{xlsx}, sheet {sheet}: SKU {item['sku']} has no selling price")
            item["selling_price"] = money(item["selling_price"])
        out.append(item)
    return out

def reconcile(first: dict, second: dict) -> tuple[dict, list]:
    """Settled only when both copies carry the SKU at the same price; everything else waits on the owner."""
    settled, waiting = {}, []
    for sku in sorted(set(first) | set(second)):
        if sku in first and sku in second and money(first[sku]) == money(second[sku]):
            settled[sku] = money(first[sku])
        else:
            waiting.append(sku)
    return settled, waiting

def per_day(price, pack_g, daily_g) -> Decimal:
    return money(Decimal(str(price)) * Decimal(str(daily_g)) / Decimal(str(pack_g)))

def per_serve(price, serves) -> Decimal:
    return money(Decimal(str(price)) / Decimal(str(serves)))

def per_day_line(price, pack_g, daily_g) -> dict:
    return {"kind": "per_day", "value": str(per_day(price, pack_g, daily_g)),
            "basis": f"¥{money(price)} ÷ ({pack_g} g ÷ {daily_g} g per day)"}

def extract_prices(text: str) -> list[Decimal]:
    cleaned = THRESHOLD.sub(" ", text)
    return [money(a or b or c) for a, b, c in PRICE.findall(cleaned)]

def check_printed(text: str, allowed: set) -> list[Decimal]:
    return [p for p in extract_prices(text) if p not in {money(a) for a in allowed}]

def bundle_problem(text: str, bundle_rows: list) -> str:
    return "bundle offer printed but the price list carries no bundle" if BUNDLE.search(text) and not bundle_rows else ""
