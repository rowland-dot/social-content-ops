"""Red/green check for issue 32: libtv-cli's SKILL.md is Easel's wrapper, LibTV's own package is untouched.

Run: python skills/builtin/libtv-cli/wrapper.test.py   (exit 0 = pass). The same behaviours, and the
full 44-file comparison, are covered by tests/test_libtv_cli_skill.py, which CI collects; this copy sits
beside the skill because the edit guard for skill folders wants a check file here.
"""

import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "references" / "vendor" / "SKILL.md"
WRAPPER = HERE / "SKILL.md"
# LibTV's own SKILL.md, from libtv-cli-skill.zip 1.1.3 (the package is pinned by sha256 in docs/vendored/libtv-cli-source.md)
VENDOR_SHA256 = "12ea7fa0c4ac0b4724664ea7e2d0a709ef44f4d58127a72d6c01802679147261"

failures = []

if not VENDOR.is_file():
    failures.append("LibTV's own SKILL.md is not at references/vendor/SKILL.md")
elif hashlib.sha256(VENDOR.read_bytes()).hexdigest() != VENDOR_SHA256:
    failures.append("LibTV's own SKILL.md no longer has the bytes of package 1.1.3")

if not WRAPPER.is_file():
    failures.append("SKILL.md (the wrapper) does not exist")
else:
    text = WRAPPER.read_text(encoding="utf-8")
    if not re.search(r"(?m)^layer: produce\s*$", text):
        failures.append("the wrapper header has no 'layer: produce'")
    if "`references/vendor/SKILL.md`" not in text:
        failures.append("the wrapper does not name references/vendor/SKILL.md in a code span")

for line in failures:
    print("FAIL", line)
print("PASS" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
