"""Check for the photo-scene skill's wording (issues 58 to 127 and 136, including the emoji-in-lettering wording of issue 100).

Run: python skills/builtin/xhs-reference-visual/wrapper.test.py   (exit 0 = pass). The cases are in
tests/test_xhs_reference_visual_skill.py, which CI collects; this file sits beside the skill because the edit guard
for skill folders wants a check file here, and it runs those cases. The cases that compare the skill with the team's
own package run only where the private work folder (work/) is present; they are in work/tests/.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_xhs_reference_visual_skill.py"],
                      cwd=ROOT, capture_output=True, text=True, timeout=240)
print(proc.stdout + proc.stderr)
sys.exit(proc.returncode)
