"""Issue 134: the project's rules files apply to every brand; skill backups stay on the owner's PC, out of git.

Seams: the text of CLAUDE.md and docs/agents/*.md as an agent reads it, the project's .gitignore, and
what git tracks under archive/skill-backups/. Brand-only facts live in the client knowledge base
(brands/<brand>/INDEX.md), never in these files.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
RULE_FILES = [ROOT / "CLAUDE.md", *sorted((ROOT / "docs" / "agents").glob("*.md"))]

# the search terms of issue 133, plus the commit id the profile rule used to cite
# the brackets keep this file from containing the names it hunts for
BRAND_TERMS = re.compile(r"collagen ?[x]|g[r]ahams|empire[ -]?[a]ustralia|glym[a]x|胶[原]|93481[1]9|97ae2[1]b", re.I)


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.name)
def test_rules_files_name_no_brand(path):
    found = sorted({m.group(0) for m in BRAND_TERMS.finditer(path.read_text(encoding="utf-8"))})
    assert found == [], f"{path.name} still names: {found}"














def test_git_ignores_the_skill_backups_folder():
    lines = [line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert "archive/skill-backups/" in lines


def test_git_tracks_no_skill_backup_file():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    tracked = subprocess.run(["git", "ls-files", "archive/skill-backups"], cwd=ROOT, capture_output=True, text=True)
    assert tracked.returncode == 0, tracked.stderr
    assert tracked.stdout.strip() == ""
