"""Brand-profile bans and cautions need a source (issue 65).

Seams (agreed in the issue): the written templates and instructions of the two
skills that create brand profiles, and the profile-reading rule in
agents/workspace/AGENTS.md that every content skill follows.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONBOARDING = ROOT / "skills" / "builtin" / "skill-brand-onboarding"
BUILDER = ROOT / "skills" / "builtin" / "skill-profile-builder"
AGENTS = ROOT / "agents" / "workspace" / "AGENTS.md"

# The same wording Easel already writes into the approved brand
# profiles, so skills and profiles agree on one marker.
NOTE_MARKER = "【备注：无客户或平台依据，不作禁令，不用来挡团队原话】"

BAN_WORDS = re.compile(r"禁区|红线|DON'T|Don't|绝对不做|绝对不发|不做的事|不想做|合规底线|禁令|避开")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_files(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*.md") if p.name != "EASEL-META.md"]


def _ban_asking_lines(folder: Path) -> list[tuple[str, str]]:
    """List, numbered, table and quoted lines that ask for or write a ban (headings name a section, the lines under them carry the source)."""
    found = []
    for path in _skill_files(folder):
        for line in _read(path).splitlines():
            shaped = re.match(r"\s*(?:[-*]|\d+\.|\||>)", line)
            if shaped and BAN_WORDS.search(line):
                found.append((path.name, line.strip()))
    return found


# --- slice 1: onboarding templates -------------------------------------------------


def test_onboarding_template_lines_that_write_a_ban_ask_for_its_source():
    lines = _ban_asking_lines(ONBOARDING)
    assert lines, "expected the onboarding skill to name bans and cautions"
    bare = [(f, l) for f, l in lines if "出处" not in l]
    assert bare == [], f"ban lines with no source slot: {bare}"


def test_onboarding_template_has_a_separate_note_line_for_unsourced_items():
    templates = _read(ONBOARDING / "references" / "profile-templates.md")
    assert NOTE_MARKER in templates
    # The note line sits outside the 禁区 and 合规底线 ban lists, not inside them.
    prefs = templates.split("## preferences.md", 1)[1].split("## memory.md", 1)[0]
    assert "## 备注" in prefs or NOTE_MARKER in prefs.split("## 合规底线", 1)[1]


# --- slice 2: profile builder --------------------------------------------------------


def test_builder_lines_that_write_or_ask_for_a_ban_ask_for_its_source():
    lines = _ban_asking_lines(BUILDER)
    assert lines, "expected the builder skill to name bans and cautions"
    bare = [(f, l) for f, l in lines if "出处" not in l]
    assert bare == [], f"ban lines with no source slot: {bare}"


def test_builder_writes_unsourced_items_as_notes_with_the_shared_marker():
    skill = _read(BUILDER / "SKILL.md")
    assert NOTE_MARKER in skill
    assert "不放进" in skill and "备注" in skill


# --- slice 3: rules both skills share -------------------------------------------------


def _both() -> dict[str, str]:
    return {
        "skill-brand-onboarding": "\n".join(_read(p) for p in _skill_files(ONBOARDING)),
        "skill-profile-builder": "\n".join(_read(p) for p in _skill_files(BUILDER)),
    }


def test_both_skills_resolve_client_file_conflicts_to_the_australian_website():
    for name, text in _both().items():
        assert "澳洲官网为准" in text, name
        assert "以官网为准" in text or "写明“以官网为准”" in text or "以澳洲官网为准" in text, name


def test_both_skills_say_a_team_past_post_is_not_a_client_ban():
    for name, text in _both().items():
        assert "团队往期帖子" in text and "不能当客户禁令" in text, name


def test_both_skills_apply_the_rule_to_reruns_and_edits_of_existing_profiles():
    for name, text in _both().items():
        assert "重跑" in text and "编辑" in text, name


# --- slice 4: the profile-reading rule every content skill follows --------------------


def test_profile_reading_rule_says_notes_never_block_or_rewrite_wording():
    text = _read(AGENTS)
    lines = [l for l in text.splitlines() if NOTE_MARKER in l]
    assert lines, "AGENTS.md must name the note marker in a profile-reading line"
    rule = lines[0]
    for needed in ("不拦截", "不标", "不改写"):
        assert needed in rule, f"missing {needed!r} in: {rule}"
    # Placed with the other profile-reading rules, ahead of 对外发布安全.
    assert text.index(NOTE_MARKER) < text.index("## 对外发布安全")
