"""Behaviour 7: conversion, add-to-cart and time on page, four weeks before and after, neither inside Double 11."""
from __future__ import annotations
import datetime as dt, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tmall_common as common

WEEKS = 4

class NoDataError(RuntimeError):
    """The sheet is missing or a window has no days. Figures are never made up."""

def windows(go_live: dt.date, warmup_start: dt.date, double11_end: dt.date) -> dict:
    if go_live <= double11_end:
        raise ValueError("go-live falls inside Double 11; the after window must start once the sale has ended")
    span = dt.timedelta(days=7 * WEEKS)
    return {"before": (warmup_start - span, warmup_start - dt.timedelta(days=1)),
            "after": (go_live, go_live + span - dt.timedelta(days=1))}

def summarise(days: list[dict], window: tuple) -> dict:
    rows = [d for d in days if window[0] <= d["date"] <= window[1]]
    visitors = sum(d["visitors"] for d in rows)
    if not rows or not visitors:
        raise NoDataError(f"no days with visitors between {window[0]} and {window[1]} in the per-product sheet")
    return {"visitors": visitors, "conversion": round(sum(d["payers"] for d in rows) / visitors, 4),
            "cart_rate": round(sum(d["cart"] for d in rows) / visitors, 4),
            "minutes": round(sum(d["minutes"] for d in rows) / len(rows), 2), "days": len(rows), "measure": MEASURE}

MEASURE = ("conversion = the window's daily payers added up ÷ its daily visitors added up, from the per-product sheet; "
           "not 生意参谋's own window figure, which counts a visitor once across days")

def notes_in(events: list[dict], window: tuple) -> list[str]:
    return [f"{e['date'].isoformat()}: {e['note']}" for e in events if window[0] <= e["date"] <= window[1]]

def sale_days(year: int) -> list[dict]:
    """Tmall's own fixed-date sales that a four-week window after Double 11 can reach. The agent adds these to the team's price
    and promotion notes, so the report states them beside the result (spec stage 8); it does not move either window (The owner's design)."""
    return [{"date": dt.date(year, 12, 12), "note": "Double 12 (双12) sale day"}]

def read_sheet(path, sheet: str, columns=("日期", "访客", "加购", "付款人数", "停留分钟")) -> list[dict]:
    if not Path(path).is_file():
        raise NoDataError(f"{path}: the per-product sheet is missing; no figures are made up")
    ws = common.open_sheet(path, sheet)      # openpyxl is imported inside: not declared in pyproject.toml; the window arithmetic must work without it
    rows = ws.iter_rows(values_only=True); header = list(next(rows))
    idx = common.column_index(header, columns, f"{path}, sheet {sheet}")     # the team's real sheet will be compared with this layout: a missing column names the ones found
    out = []
    for n, r in enumerate(rows, 2):
        d = r[idx[0]]
        if d in (None, ""):
            continue                                   # a blank row (spreadsheets often end with some)
        if isinstance(d, str):
            try: d = dt.date.fromisoformat(d.strip().replace("/", "-"))
            except ValueError: raise ValueError(f"{path}, sheet {sheet}, row {n}: date {d!r} is not a date") from None
        out.append({"date": d.date() if isinstance(d, dt.datetime) else d, "visitors": r[idx[1]] or 0, "cart": r[idx[2]] or 0,
                    "payers": r[idx[3]] or 0, "minutes": r[idx[4]] or 0})
    return out
