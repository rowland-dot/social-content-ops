"""The written and wired records of the LibTV update gate (issue 37), checked in this checkout (not a fixture repo).

Seams (the issue's Agent Brief): the project hook definition and whether git carries it, Easel's ignore file left as
upstream has it, the spec's table row and amendment note quoting the owner's four rulings, and the source note's pointer
to the on-demand command.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SETTINGS = REPO / ".claude" / "settings.json"
SPEC = REPO / "docs" / "specs" / "2026-10-12-easel-replatform-spec.md"
NOTE = REPO / "docs" / "vendored" / "libtv-cli-source.md"
IS_GIT = (REPO / ".git").exists() and shutil.which("git") is not None


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=60)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---- the hook definition -----------------------------------------------------------------------------


def test_the_hook_definition_runs_the_gates_hook_command_when_a_session_opens():
    data = json.loads(_text(SETTINGS))
    groups = data["hooks"]["SessionStart"]
    commands = [h for g in groups for h in g["hooks"]]
    assert len(commands) == 1 and commands[0]["type"] == "command"
    command = commands[0]["command"]
    assert "$CLAUDE_PROJECT_DIR/ops/libtv-update-gate/libtv_gate.py" in command and " hook" in command
    assert 10 < commands[0]["timeout"] <= 30, "longer than the gate's own deadline, short enough not to stall a session"
    assert "startup" in groups[0]["matcher"]


def test_the_hook_definition_survives_a_fresh_clone_without_touching_easels_ignore_file():
    ignore = _text(REPO / ".gitignore").splitlines()
    assert ".claude/" in ignore and ".scratch/" in ignore, "Easel's own ignore lines are still there"
    if not IS_GIT:
        pytest.skip("not a git checkout")
    assert _git("ls-files", "--error-unmatch", ".claude/settings.json").returncode == 0, "the definition is in git"
    assert _git("diff", "--quiet", "HEAD", "--", ".gitignore").returncode == 0, ".gitignore has no uncommitted edit"


def test_only_the_hook_definition_is_tracked_under_the_ignored_claude_folder():
    if not IS_GIT:
        pytest.skip("not a git checkout")
    tracked = _git("ls-files", ".claude").stdout.split()
    assert tracked == [".claude/settings.json"]


def test_the_gates_store_is_under_an_ignored_folder():
    if not IS_GIT:
        pytest.skip("not a git checkout")
    assert _git("check-ignore", "-q", ".scratch/libtv-update-gate/state.json").returncode == 0


# ---- the records -------------------------------------------------------------------------------------






def test_the_source_note_names_the_gates_on_demand_command():
    section = _text(NOTE).split("## Moving to a newer version", 1)[1]
    assert "python ops/libtv-update-gate/libtv_gate.py check" in section
    assert "libtv_gate.py candidate" in section
    assert "keep-pin" in section
