"""SKILL.md must tell the agent what the default quality gates need from the build step.

Run: python -m pytest skills/builtin/video-production/skill-gate-inputs.test.py
(the file name keeps it out of the default pytest collection; name it explicitly).
The behaviour of the gate list itself is tested in tests/test_video_production_default_gates.py.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT = (HERE / "SKILL.md").read_text(encoding="utf-8")
GATES = json.loads((HERE / "default-gates.json").read_text(encoding="utf-8"))["gates"]


def test_skill_says_a_gate_list_is_required_and_what_the_default_is():
    assert "default-gates.json" in TEXT
    assert "质量门" in TEXT and "空单" in TEXT


def test_skill_names_every_build_step_file_the_default_gates_read():
    needed = set()
    for gate in GATES:
        needed |= set(re.findall(r"gate-inputs/([\w.-]+)", gate["cmd"]))
    needed.add("composition.json")  # read by gate_composition.py, not named in the command
    assert needed >= {"layout.json", "meta.json", "match.json", "composition.json"}
    missing = [name for name in sorted(needed) if name not in TEXT]
    assert missing == [], f"SKILL.md never tells the agent to write: {missing}"


def test_skill_mentions_the_work_folder_install_setting_and_the_interpreter_placeholder():
    assert "scaffold_install" in TEXT
    assert "{python}" in TEXT
