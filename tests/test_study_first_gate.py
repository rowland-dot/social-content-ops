"""Issue 97: CI runs the two document checks that keep the content calendar and the hook library off invented benchmarks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    ROOT / "skills" / "builtin" / "skill-content-calendar" / "study-first.test.py",
    ROOT / "skills" / "builtin" / "skill-carousel-planner" / "no-verified-claim.test.py",
]


@pytest.mark.parametrize("check", CHECKS, ids=lambda p: p.parent.name)
def test_plans_and_hook_formulas_are_not_built_from_invented_benchmarks(check: Path) -> None:
    result = subprocess.run([sys.executable, str(check)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"
