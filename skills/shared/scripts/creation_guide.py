#!/usr/bin/env python3
"""Find an account's creation guide (issue 125): `creation_guide.py check --brand <name> [--profiles-dir <dir>]`.

Exit 0 and print the guide's path and last-changed date; exit 2 and print the stop message when there is none.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from easel.persona import external_profile_dirs, profile_dir  # noqa: E402

STOP = (
    "There is no creation guide for the account '{brand}' (looked for {path}).\n"
    "STOP: tell the owner, and offer to create it from profiles/_template/creation-guide.md.\n"
    "Draw and write nothing until the guide exists."
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["check"])
    p.add_argument("--brand", required=True)
    p.add_argument("--profiles-dir")
    a = p.parse_args(argv)
    if a.profiles_dir and a.brand not in external_profile_dirs():
        folder = Path(a.profiles_dir) / a.brand
    else:
        folder = profile_dir(a.brand)
    guide = folder / "creation-guide.md"
    if not guide.is_file():
        print(STOP.format(brand=a.brand, path=guide))
        return 2
    changed = datetime.fromtimestamp(guide.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
    print(f"{guide}\nlast changed: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
