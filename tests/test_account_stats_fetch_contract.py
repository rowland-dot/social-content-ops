"""The my-account skill's instructions must name the keys `account_stats.py fetch` really prints."""
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "shared" / "scripts"))
import account_stats

SKILL = ROOT / "skills" / "builtin" / "skill-my-account"
COMMANDS_MD = SKILL / "references" / "commands.md"


def _guide_sample() -> dict:
    """The guide's sample output for `fetch`: the first ```json block, with its comments-free JSON."""
    text = COMMANDS_MD.read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)\n```", text, re.S).group(1)
    return json.loads(block)


def _login_flag_named_by_guide() -> str:
    flags = [key for key, value in _guide_sample().items() if isinstance(value, bool)]
    assert len(flags) == 1, f"guide sample should show exactly one login flag, got {flags}"
    return flags[0]


def _instruction_files_naming_old_login_field(folder: Path) -> list[str]:
    """Markdown instruction files under `folder` that still say `logged_in`."""
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*.md")
                  if "logged_in" in p.read_text(encoding="utf-8"))


def _run_fetch(monkeypatch, tmp_path, capsys, logged_in: bool) -> dict:
    scrape = {
        "logged_in": logged_in, "nickname": "测试号" if logged_in else None,
        "followers": 321 if logged_in else None, "likes": 7 if logged_in else None,
        "following": 5 if logged_in else None, "posts": 2 if logged_in else None,
        "metrics": [], "notes": [],
    }
    monkeypatch.setattr(account_stats, "_scrape", lambda *args, **kwargs: scrape)
    monkeypatch.setattr(account_stats, "ANALYTICS_DIR", tmp_path)  # fetch appends a snapshot here
    args = SimpleNamespace(platform="xiaohongshu", no_proxy=True, proxy=None,
                           headed=False, profile_base=None)
    assert account_stats.cmd_fetch(args) == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("logged_in", [True, False])
def test_fetch_prints_every_key_the_guide_shows(monkeypatch, tmp_path, capsys, logged_in):
    out = _run_fetch(monkeypatch, tmp_path, capsys, logged_in)
    missing = set(_guide_sample()) - set(out)
    assert not missing, f"guide sample keys that fetch does not print: {sorted(missing)}"


@pytest.mark.parametrize("logged_in", [True, False])
def test_login_flag_named_by_guide_carries_the_login_state(monkeypatch, tmp_path, capsys, logged_in):
    out = _run_fetch(monkeypatch, tmp_path, capsys, logged_in)
    assert out[_login_flag_named_by_guide()] is logged_in


def test_skill_instructions_never_name_the_old_login_field():
    stale = _instruction_files_naming_old_login_field(SKILL)
    assert not stale, f"still say logged_in: {stale}"


def test_old_login_field_check_flags_instruction_files(tmp_path):
    (tmp_path / "references").mkdir()
    (tmp_path / "SKILL.md").write_text("stop when logged_in=false", encoding="utf-8")
    (tmp_path / "references" / "commands.md").write_text("clean", encoding="utf-8")
    assert _instruction_files_naming_old_login_field(tmp_path) == ["SKILL.md"]


def test_old_login_field_check_ignores_non_instruction_files(tmp_path):
    # the skill-folder test must name logged_in to check for it; compiled caches are binary
    (tmp_path / "login-field.test.py").write_text('"logged_in"', encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "login-field.cpython-314.pyc").write_bytes(b"+\x0e\r\n\xb2logged_in")
    assert _instruction_files_naming_old_login_field(tmp_path) == []
