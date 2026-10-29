"""Check for issue 111: the approvals command records each approval per card and voids it when a dependency changes.

Run: python skills/builtin/xhs-reference-visual/approvals.test.py   (exit 0 = pass). The cases themselves (record then
check, a changed colour table, picked cover, card row, a second approval, a voided entry kept, and the stops for a missing
record, an unknown card and a missing image) are in tests/test_xhs_approvals.py, which CI collects; this file sits beside
the skill because the edit guard for skill folders wants a check file here, and it runs those cases.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_xhs_approvals.py"], cwd=ROOT,
                      capture_output=True, text=True, timeout=240)
print(proc.stdout + proc.stderr)
sys.exit(proc.returncode)
