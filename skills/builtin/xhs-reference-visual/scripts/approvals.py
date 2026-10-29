#!/usr/bin/env python3
"""approvals.py — the photo-scene approval record, one per post (issue 111).

The owner's approvals are kept in `approvals.json` beside the set plan: one entry per approval, never deleted. An entry holds
the card (a plan card, or `set`), the kind, the approved image, the date, the user's words and a fingerprint of each thing
it depended on. `check` compares every fingerprint with the files on disk and marks an entry no longer valid when one
differs; a voided entry is never revived (re-approval is a new entry). Fields and the dependency list are written once in
references/photo-scene-approvals.md. Fingerprints are of plan text and files only; nothing reads the words on a pack.

Usage:
    approvals.py record --plan <set-plan.md> --card <card|set> --kind <kind> --file <image> --date <YYYY-MM-DD>
                        --words <text> [--base-file <image>] [--prompt-file <file, relative to the plan's folder>] [--record <approvals.json>]
    approvals.py check  --plan <set-plan.md> [--record <approvals.json>] [--today <YYYY-MM-DD>]
Exit codes: 0 all entries valid (or a record written), 1 some entry is not valid, 2 bad input (nothing written).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_page import NO_ICONS, SECTIONS, _die, rows_of, tables  # noqa: E402  (the plan page's table reading, unchanged)

KINDS = ("plan-page", "cover-pick", "lettering-pick", "set-page", "card-change")
TYPED = "typed-styling.json"
SET_TABLES = ("研究的图集", "封面方向", "逐张计划", "颜色和层级", "图标清单")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_tables(plan: Path) -> tuple[str, dict]:
    text = plan.read_text(encoding="utf-8")
    found = tables(text)
    return text, {name: rows_of(name, found) for name in SECTIONS}


def fingerprint(dep: str, plan: Path, text: str, rows: dict) -> str:
    kind, _, name = dep.partition(":")
    if kind == "file":
        path = plan.parent / name
        return sha(path.read_bytes()) if path.is_file() else "missing"
    if kind == "row":
        row = next((r for r in rows["逐张计划"] if r["卡"] == name), None)
        return sha(json.dumps(row, ensure_ascii=False).encode())
    value = rows[name]
    if name == "图标清单" and value is None:
        value = NO_ICONS if NO_ICONS in text else None
    return sha(json.dumps(value, ensure_ascii=False).encode())


def cards_of(rows: dict) -> list[str]:
    if rows["逐张计划"] is None:
        _die("计划里没有「逐张计划」表")
    return [r["卡"] for r in rows["逐张计划"]]


def page_files(plan: Path, rows: dict) -> list[str]:
    """The companion files the plan page shows (issue 123): the icon list, the cover layout plan, each other card's."""
    cards = cards_of(rows)
    names = ["icon-list.md", "layout-plan-card_1-ABC.md", *[f"layout-plan-card_{c}.md" for c in cards[1:]]]
    return [f"file:{n}" for n in names if (plan.parent / n).is_file()]


def dependencies(plan: Path, rows: dict, card: str, entries: list[dict], prompt: Path | None, kind: str = "") -> list[str]:
    deps = [f"table:{n}" for n in SET_TABLES]
    if kind == "plan-page":  # the page shows the whole plan and these files, so any change to them voids it
        deps += [f"file:{plan.name}", *page_files(plan, rows)]
    if card != "set":
        deps = ["table:颜色和层级", "table:图标清单", f"row:{card}"]
        if (plan.parent / f"layout-plan-{card}.md").is_file():
            deps.append(f"file:layout-plan-{card}.md")
        picks = [e for e in entries if e["kind"] == "cover-pick"]
        if picks and card != cards_of(rows)[0]:
            deps.append(f"file:{picks[-1]['file']}")
    if (plan.parent / TYPED).is_file():
        deps.append(f"file:{TYPED}")
    if prompt is not None:
        for line in prompt.read_text(encoding="utf-8").splitlines():
            if line.startswith("image:"):
                deps.append(f"file:{line[6:].strip()}")
    return deps


def load(path: Path) -> dict:
    if not path.is_file():
        _die(f"没有批准记录文件：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def need_file(plan: Path, rel: str) -> None:
    if not (plan.parent / rel).is_file():
        _die(f"批准的图不在磁盘上：{rel}（找过 {plan.parent}）")


def do_record(a: argparse.Namespace) -> int:
    plan, path = Path(a.plan), Path(a.record or Path(a.plan).parent / "approvals.json")
    text, rows = read_tables(plan)
    if a.card != "set" and a.card not in cards_of(rows):
        _die(f"计划里没有卡 {a.card}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.date):
        _die(f"日期要写成 YYYY-MM-DD：{a.date}")
    for rel in (a.file, a.base_file):
        if rel:
            need_file(plan, rel)
    prompt = plan.parent / a.prompt_file if a.prompt_file else None
    if prompt is not None and not prompt.is_file():
        _die(f"提示词文件不在磁盘上：{prompt}")
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"entries": []}
    deps = dependencies(plan, rows, a.card, data["entries"], prompt, a.kind)
    for dep in deps:
        if dep.startswith("file:"):
            need_file(plan, dep[5:])
    entry = {"id": len(data["entries"]) + 1, "card": a.card, "kind": a.kind, "file": a.file, "date": a.date,
             "words": a.words, "deps": {d: fingerprint(d, plan, text, rows) for d in deps}, "valid": True, "voided": None}
    if a.base_file:
        entry["base_file"] = a.base_file
    data["entries"].append(entry)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def do_check(a: argparse.Namespace) -> int:
    plan, path = Path(a.plan), Path(a.record or Path(a.plan).parent / "approvals.json")
    data = load(path)
    text, rows = read_tables(plan)
    cards = cards_of(rows)
    for e in data["entries"]:
        if e["card"] != "set" and e["card"] not in cards:
            _die(f"批准记录里的卡 {e['card']} 不在计划里")
        need_file(plan, e["file"])
    bad = 0
    for e in data["entries"]:
        if not e["valid"]:
            bad += 1
            continue
        changed = next((d for d, f in e["deps"].items() if fingerprint(d, plan, text, rows) != f), None)
        if changed:
            e["valid"], e["voided"], bad = False, {"dependency": changed, "found_on": a.today}, bad + 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for e in data["entries"]:
        if not e["valid"]:
            print(f"不再有效：卡 {e['card']}（{e['kind']}，{e['date']}）改了：{e['voided']['dependency']}（{e['voided']['found_on']}）")
    return 1 if bad else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--plan", required=True)
    r.add_argument("--card", required=True)
    r.add_argument("--kind", required=True, choices=KINDS)
    r.add_argument("--file", required=True)
    r.add_argument("--base-file")
    r.add_argument("--date", required=True)
    r.add_argument("--words", required=True)
    r.add_argument("--prompt-file")
    r.add_argument("--record")
    c = sub.add_parser("check")
    c.add_argument("--plan", required=True)
    c.add_argument("--record")
    c.add_argument("--today", default=datetime.date.today().isoformat())
    a = p.parse_args()
    return do_record(a) if a.cmd == "record" else do_check(a)


if __name__ == "__main__":
    sys.exit(main())
