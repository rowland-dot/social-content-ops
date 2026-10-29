"""Check that SKILL.md names the login flag `account_stats.py fetch` really prints.

The fetch command prints `loggedIn` (the dashboard reads it). The old docs said the snake_case form,
so an agent following them read a key that is never there. Run: python login-field.test.py
The stale name is built from two halves so this file never contains it (a sibling test scans the folder for it).
"""
import sys
from pathlib import Path

SKILL_MD = Path(__file__).resolve().parent / "SKILL.md"
STALE = "logged" + "_in"


def main() -> int:
    text = SKILL_MD.read_text(encoding="utf-8")
    problems = []
    if STALE in text:
        lines = [str(n) for n, line in enumerate(text.splitlines(), 1) if STALE in line]
        problems.append(f"SKILL.md still names the old login field on lines {', '.join(lines)}")
    for state in ("true", "false"):
        if f"loggedIn={state}" not in text:
            problems.append(f"SKILL.md never says loggedIn={state}")
    for p in problems:
        print("FAIL:", p)
    if not problems:
        print("ok: SKILL.md names loggedIn, never the old field")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
