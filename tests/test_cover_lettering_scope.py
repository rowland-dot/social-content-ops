"""Issue 96: CI runs the two document checks that sit beside the note writer and the carousel planner."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKS = [
    ROOT / "skills" / "builtin" / "xhs-note-creator" / "cover-lettering-scope.test.py",
    ROOT / "skills" / "builtin" / "skill-carousel-planner" / "cover-lettering-scope.test.py",
]


@pytest.mark.parametrize("check", CHECKS, ids=lambda p: p.parent.name)
def test_photo_scene_cover_lettering_is_not_overridden_by_html_card_rules(check: Path) -> None:
    result = subprocess.run([sys.executable, str(check)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"
