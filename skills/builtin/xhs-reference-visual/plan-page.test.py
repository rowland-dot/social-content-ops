"""Check for issue 87: the plan-page command builds the owner's step-3 page from the set plan and stops on an unreadable plan.

Run: python skills/builtin/xhs-reference-visual/plan-page.test.py   (exit 0 = pass). The cases themselves (every cell
copied unchanged, each card beside its studied set's image, a swatch per colour row, each icon with its meaning, and the
stops for an unknown set, a missing image, a bad hex value and a missing table) are in tests/test_xhs_plan_page.py, which
CI collects; this file sits beside the skill because the edit guard for skill folders wants a check file here, and it runs
those cases.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_xhs_plan_page.py"], cwd=ROOT,
                      capture_output=True, text=True, timeout=240)
print(proc.stdout + proc.stderr)
sys.exit(proc.returncode)
