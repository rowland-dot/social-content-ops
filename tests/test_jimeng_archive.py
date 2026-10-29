"""Jimeng's dreamina route is archived, not active (issue 36).

The owner, 2026-10-14: "Let's bring libtv back and archive the jimeng implementation", then
"Fully off, code kept". Seams (issue 36 acceptance criteria): the real skill-library function
in web/app.py, the setup scripts' text, the archive folder and its README, and the two
instruction documents. The machine itself (login, program, workspace copy) is checked by a
script run in WSL, not here.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

import web.app as web

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive" / "jimeng-dreamina"
SETUP_DIR = ROOT / "ops" / "wsl-setup"
SPEC = ROOT / "docs" / "specs" / "2026-10-12-easel-replatform-spec.md"
JIMENG = re.compile(r"jimeng|即梦|dreamina", re.I)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_skill_library_no_longer_lists_dreamina_cli():
    assert "dreamina-cli" not in {s["name"] for s in web.get_skills()}
    assert not (ROOT / "skills" / "builtin" / "dreamina-cli").exists()


def test_active_setup_scripts_do_not_mention_dreamina():
    for name in ("setup.sh", "checks.sh", "fingerprint.sh", "setup.test.sh"):
        assert "dreamina" not in _text(SETUP_DIR / name).lower(), f"{name} still mentions dreamina"


def test_setup_runs_thirteen_steps_including_libtv_and_not_dreamina():
    # issue 32 added the libtv step to the eleven steps issue 36 left; later issues added one more; Jimeng's step stays out
    steps = re.search(r'^STEPS="([^"]*)"', _text(SETUP_DIR / "setup.sh"), re.M).group(1).split()
    assert len(steps) == 13
    assert "libtv" in steps
    assert "dreamina" not in steps


def test_credential_leak_check_stays_for_libtv():
    assert (SETUP_DIR / "credential-leak-check.sh").is_file()
    assert (SETUP_DIR / "credential-leak-check.test.sh").is_file()








def _blocks_naming_jimeng(path: Path) -> list[str]:
    blocks = re.split(r"\n\s*\n|\n(?=\s*[-|] )", _text(path))
    return [b for b in blocks if JIMENG.search(b)]




