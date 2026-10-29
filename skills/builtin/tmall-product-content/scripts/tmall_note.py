"""The competitor pattern note: every captured listing needs the four parts the owner asked for."""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

PARTS = ["主图分工 Main-image jobs", "详情页屏序 Screen order", "主打卖点 Headline claims", "证明方式 Proof style"]   # Chinese first: the team reads the note (新媒体同事 reads Chinese only)

def check(text: str, item_ids: list[str]) -> list[str]:
    problems = []
    for iid in item_ids:
        m = re.search(rf"## Listing {iid}\n(.*?)(?=\n## Listing |\Z)", text, re.S)
        if not m:
            problems.append(f"listing {iid}: not in the note"); continue
        problems += [f"listing {iid}: missing '{p}'" for p in PARTS if f"### {p}" not in m.group(1)]
    return problems

def competitor_strings(text: str) -> list[str]:
    """What our copy must not repeat (the no-copying check): the lines under each listing's 'Headline claims', and under an
    optional 'Names and badges' part for brand names and badge wording. Read from the note at run time, never committed."""
    out = []
    for part in ("主打卖点 Headline claims", "品牌名与徽标 Names and badges"):
        for m in re.finditer(rf"### {part}\n(.*?)(?=\n#|\Z)", text, re.S):
            out += [line.lstrip("-* ").strip() for line in m.group(1).splitlines() if line.strip()]
    return [s for s in dict.fromkeys(out) if len(s) >= 2]

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("note"); c.add_argument("ids", nargs="+")
    a = ap.parse_args(argv)
    problems = check(Path(a.note).read_text(encoding="utf-8"), a.ids)
    print("\n".join(problems) or "OK")
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
