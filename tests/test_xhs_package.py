"""The photo-scene skill finds its style package, or offers the default (issue 136, answer 8).

Seam: the command line of skills/builtin/xhs-reference-visual/scripts/package.py, run against a throwaway project
root, plus the default package's files. Three cases: the team's package is present (nothing is asked), no package
and the default is chosen, no package and the user's own is chosen. Expected values are literals.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "builtin" / "xhs-reference-visual"
SCRIPT = SKILL / "scripts" / "package.py"
DEFAULTS = SKILL / "references" / "defaults"

TEAM_REL = "work/team-packages/xhs-reference-visual"
DEFAULT_REL = "skills/builtin/xhs-reference-visual/references/defaults"
TEN_FILES = [
    "INDEX.md", "skill/SKILL.md", "file/DESIGN-MEMORY.md", "playbook/PLAYBOOK.md", "playbook/EXECUTION-BRIEF.md",
    "standards/STANDARD.md", "standards/REFERENCE-BREAKDOWN.md", "methods/PRODUCT-REPLACEMENT.md",
    "methods/PORTRAIT-WORKFLOW.md", "methods/PORTRAIT-PROMPT-RULES.md",
]
CHOICE_MESSAGE = (
    "没有找到团队的风格资料包。你可以选：\n"
    "A. 使用默认资料包：通用的风格记忆、流程手册和设计标准，不含参考图；参考来自这篇帖子主题下的真实高赞帖子。\n"
    "B. 建立你自己的资料包：我列出需要哪几个文件、每个文件写什么，你填好后放进资料包文件夹。\n"
    "想先看看默认资料包里写了什么，随时说一声，我把文件拿给你看。")


def run(root: Path, *args: str):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args],
                          capture_output=True, text=True, timeout=60)


def test_with_the_team_package_present_it_is_used_and_nothing_is_asked(tmp_path):
    (tmp_path / TEAM_REL / "skill").mkdir(parents=True)
    (tmp_path / TEAM_REL / "skill" / "SKILL.md").write_text("team", encoding="utf-8")
    proc = run(tmp_path, "find")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == f"资料包目录：{TEAM_REL}（团队资料包）"


def test_with_no_package_the_user_is_offered_the_default_or_their_own(tmp_path):
    proc = run(tmp_path, "find")
    assert proc.returncode == 3, proc.stderr
    assert proc.stdout.strip() == CHOICE_MESSAGE


def test_choosing_the_default_uses_the_package_in_the_skill_folder(tmp_path):
    proc = run(tmp_path, "find", "--choice", "default")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == f"资料包目录：{DEFAULT_REL}（默认资料包）"


def test_choosing_their_own_lists_each_file_needed_and_what_it_holds_and_where_it_goes(tmp_path):
    proc = run(tmp_path, "find", "--choice", "own")
    assert proc.returncode == 4, proc.stderr
    lines = proc.stdout.splitlines()
    assert f"把你的资料包放进这个文件夹：{TEAM_REL}" in lines
    for rel in ("file/DESIGN-MEMORY.md", "playbook/PLAYBOOK.md", "playbook/EXECUTION-BRIEF.md", "skill/SKILL.md"):
        assert any(line.startswith(f"- {rel}：") and len(line) > len(rel) + 6 for line in lines), rel


def test_asking_to_see_the_default_lists_its_ten_files(tmp_path):
    proc = run(tmp_path, "show-default")
    assert proc.returncode == 0, proc.stderr
    assert [line.split("：")[0] for line in proc.stdout.splitlines() if line.startswith(DEFAULT_REL)] == [
        f"{DEFAULT_REL}/{rel}" for rel in TEN_FILES]


def test_the_default_package_has_exactly_the_ten_files_and_no_image():
    found = sorted(p.relative_to(DEFAULTS).as_posix() for p in DEFAULTS.rglob("*") if p.is_file())
    assert found == sorted(TEN_FILES)


def test_the_default_package_carries_no_date_path_image_number_or_pack_wording_check():
    for rel in TEN_FILES:
        text = (DEFAULTS / rel).read_text(encoding="utf-8")
        assert not re.search(r"20\d\d-\d\d-\d\d|20\d\d 年", text), (rel, "a date")
        assert not re.search(r"[A-Za-z]:[/\\]|/mnt/|/Users/|~/", text), (rel, "a path")
        assert not re.search(r"图 ?\d\d|\.jpg|\.png", text), (rel, "an image")
        assert not re.search(r"包装文字|包装小字|包装上印|核对.{0,8}(容量|标签上)|放大比对", text), (rel, "a pack-wording check")
        assert "先做小样" not in text and "先一张代表性小样" not in text and "微变体" not in text, (rel, "one sample first")


def test_the_default_style_memory_is_the_approved_sample():
    text = (DEFAULTS / "file/DESIGN-MEMORY.md").read_text(encoding="utf-8")
    for needle in ("# 小红书图文视觉：默认风格记忆",
                   "这是默认资料包，不属于任何品牌或团队。用户有自己的风格资料时，用用户自己的。",
                   "## 六个风格分支", "| 刷痕手账 |", "| 自然植物剪贴簿 |", "## 默认摄影调性"):
        assert needle in text, needle
