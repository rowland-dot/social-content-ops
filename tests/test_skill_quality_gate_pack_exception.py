"""Issue 94: the quality gate never reads, lists or flags what is printed on the real product pack.

The owner's rule (CLAUDE.md, "Product pack wording is never checked"). The assertions live in the check file beside
the skill, so the script and this test cannot drift apart; each finding is one pytest failure line.
"""

import importlib.util
from pathlib import Path

import pytest

CHECK = Path(__file__).resolve().parents[1] / "skills" / "builtin" / "skill-quality-gate" / "pack-exception.test.py"


def _load():
    spec = importlib.util.spec_from_file_location("quality_gate_pack_exception_check", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_with_backup():
    module = _load()
    if not module.BACKUP.is_dir():
        pytest.skip("skill backups are kept only on the owner's PC")
    return module


def test_gate_states_the_pack_exception_and_loses_no_rule_line():
    found = _load_with_backup().problems()
    assert not found, "\n".join(found)


def test_easel_own_words_and_post_text_are_still_checked():
    module = _load()
    skill = (module.HERE / "SKILL.md").read_text(encoding="utf-8")
    assert "Easel 自己加到图上的字" in skill
    assert "帖子的标题、正文、话题标签和任何脚本或文案" in skill
    assert "照旧按全部规则检查" in skill


def test_output_format_is_unchanged():
    module = _load_with_backup()
    old = (module.BACKUP / "SKILL.md").read_text(encoding="utf-8")
    new = (module.HERE / "SKILL.md").read_text(encoding="utf-8")
    block = old.split("## 输出", 1)[1].split("## 执行步骤", 1)[0]
    assert block in new
