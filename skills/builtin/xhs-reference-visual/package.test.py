"""Check for issue 136, answer 8: the skill finds the team's package or offers the default package.

Run: python skills/builtin/xhs-reference-visual/package.test.py   (exit 0 = pass). The cases (team package present and
nothing asked, no package and the default chosen, no package and their own chosen, the ten default files with no image,
and the default style memory) are in tests/test_xhs_package.py, which CI collects; this file sits beside the skill
because the edit guard for skill folders wants a check file here, and it runs those cases.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_xhs_package.py"], cwd=ROOT,
                      capture_output=True, text=True, timeout=240)
print(proc.stdout + proc.stderr)
sys.exit(proc.returncode)
