"""skill-content-postmortem must not send the agent to a baseline that is not there.

Seam: the skill's SKILL.md text (mode A baseline step and report template).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "builtin" / "skill-content-postmortem"
TEXT = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def _baseline_step() -> str:
    match = re.search(r"\*\*基线建立\*\*[^\n]*", TEXT)
    assert match, "mode A baseline step (基线建立) not found"
    return match.group(0)


def test_no_comparison_branch_names_no_baseline_file():
    assert "平台通用基线" not in TEXT
    assert "中的平台特征数据" not in TEXT


def test_baseline_step_keeps_comparison_branch_and_states_no_baseline():
    step = _baseline_step()
    assert "同期对照" in step and "偏离度" in step
    assert "无基线" in step or "没有基线" in step
    assert "未使用基线" in step


def test_data_notes_section_records_no_baseline_was_used():
    notes = TEXT.split("## 数据备注", 1)[1].split("```", 1)[0]
    assert "基线" in notes


def test_every_skill_resource_path_resolves_to_a_file():
    # Code-span paths under references/ or scripts/ (bare folders included),
    # plus the shared helper the skill names, resolved against the skill folder.
    spans = re.findall(r"`((?:\.\./\.\./shared/)?(?:references|scripts)/[^`\s]*)`", TEXT)
    spans = [s.split(" ")[0] for s in spans]
    assert spans, "expected the skill to name resource paths"
    bad = [s for s in spans if not (SKILL_DIR / s).is_file()]
    assert bad == [], f"paths that are not existing files: {bad}"
