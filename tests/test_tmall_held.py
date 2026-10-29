import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import json, pytest
import tmall_held as held

def test_both_tools_are_held_and_name_their_issues():
    data = json.loads(held.HELD_FILE.read_text(encoding="utf-8"))
    assert data["ai-image-gen"]["held"] is True and "95" in data["ai-image-gen"]["until"]
    assert data["skill-quality-gate"]["held"] is True and "94" in data["skill-quality-gate"]["until"]

@pytest.mark.parametrize("tool", ["ai-image-gen", "skill-quality-gate"])
def test_a_held_tool_is_refused(tool):
    with pytest.raises(held.HeldError, match=tool):
        held.require_released(tool)

def test_an_unknown_tool_is_refused_too(tmp_path):
    f = tmp_path / "h.json"; f.write_text("{}", encoding="utf-8")
    with pytest.raises(held.HeldError):
        held.require_released("anything", f)

def test_a_released_tool_passes(tmp_path):
    f = tmp_path / "h.json"
    f.write_text(json.dumps({"ai-image-gen": {"held": False, "until": "done"}}), encoding="utf-8")
    held.require_released("ai-image-gen", f)

@pytest.mark.parametrize("content", [None, "{not json", "[]"])
def test_a_missing_or_unreadable_hold_file_is_a_held_error_not_a_crash(tmp_path, content):
    # QA 2026-10-28 (review LOW): the skill page tells the agent to catch HeldError, skip the live step and tell the owner; a missing or garbled
    # hold file used to raise FileNotFoundError / JSONDecodeError instead, so that path crashed (it still refused, i.e. failed closed).
    f = tmp_path / "h.json"
    if content is not None: f.write_text(content, encoding="utf-8")
    with pytest.raises(held.HeldError, match="held.json|h.json"):
        held.require_released("ai-image-gen", f)
