"""Red/green check for issue 57: lrb-monthly-excel's SKILL.md names the one route and its five steps.

Run: python skills/builtin/lrb-monthly-excel/skill-text.test.py   (exit 0 = pass). The behaviours of the script
itself, and the same text checks, are covered by tests/test_lrb_monthly_excel.py, which CI collects; this copy
sits beside the skill because the edit guard for skill folders wants a check file here.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
failures = []

skill = HERE / "SKILL.md"
if not skill.is_file():
    failures.append("SKILL.md does not exist")
else:
    text = skill.read_text(encoding="utf-8")
    if not re.search(r"(?m)^name: lrb-monthly-excel\s*$", text):
        failures.append("the header has no 'name: lrb-monthly-excel'")
    if "scripts/lrb_excel.py" not in text:
        failures.append("SKILL.md does not name scripts/lrb_excel.py")
    positions = [text.find(word) for word in ("来源", "内容改动", "整理形状", "排版", "检查")]
    if -1 in positions or positions != sorted(positions):
        failures.append("the five steps (source, content changes, shape, formatting, checks) are missing or out of order in the text")
    # The owner, 2026-10-17, "No colours, per template (Recommended)": the build clears every colour and a colour left fails the run
    if "CLEARED" not in text or "`fills`" not in text:
        failures.append("SKILL.md does not say the build clears colours (CLEARED) and checks them (`fills`)")
    for stale in ("只报告，不改", "要等负责人定", "不让运行失败", "FILLS"):
        if stale in text:
            failures.append(f"SKILL.md still carries the old fills rule: {stale}")
    # round 3: a change can name its cell (text repeated in other cells is no blocker) and a ruling is the owner's quoted words
    step2 = text[text.find("## 2."):text.find("## 3.")]
    for needle in ('"cell"', '"date"', '"column"', "原话", "引号"):
        if needle not in step2:
            failures.append(f"step 2 of SKILL.md does not say: {needle}")

if not (HERE / "scripts" / "lrb_excel.py").is_file():
    failures.append("scripts/lrb_excel.py does not exist")

calendar = HERE.parent / "skill-content-calendar" / "SKILL.md"
calendar_text = calendar.read_text(encoding="utf-8") if calendar.is_file() else ""
if "lrb-monthly-excel" not in calendar_text or "不要自己写" not in calendar_text:
    failures.append("skill-content-calendar does not hand the client Excel to lrb-monthly-excel (it must say not to write xlsx itself)")

for line in failures:
    print("FAIL", line)
print("PASS" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
