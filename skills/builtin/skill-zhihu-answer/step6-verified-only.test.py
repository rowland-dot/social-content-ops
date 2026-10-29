"""Check that SKILL.md Step 6 only allows a publish-log entry for a verified result.

Run: python skills/builtin/skill-zhihu-answer/step6-verified-only.test.py
(Plain asserts, no pytest needed; exits non-zero on failure.)
"""
import re
import sys
from pathlib import Path

SKILL = Path(__file__).with_name("SKILL.md")


def step6_section() -> str:
    text = SKILL.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = re.search(r"^## Step 6.*?(?=^---$|^## )", text, re.S | re.M)
    assert m, "SKILL.md has no '## Step 6' section"
    return m.group(0)


def test_step6_logs_only_verified_results():
    s = step6_section()
    # The rule must name the result field and every non-logging outcome.
    for word in ("outcome", "verified", "unverified", "login_required"):
        assert word in s, f"Step 6 does not mention '{word}'"
    # And it must say the account is checked by hand before anything is logged.
    assert "手工" in s or "人工" in s, "Step 6 does not say to check by hand"


def test_rule_comes_before_the_log_command():
    s = step6_section()
    rule_at = s.find("unverified")
    record_at = s.find("log.py record")
    assert record_at != -1, "Step 6 lost its publish-log record command"
    assert 0 <= rule_at < record_at, "verified-only rule must come before the log command"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
