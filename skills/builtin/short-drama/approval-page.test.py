"""The approval page for short dramas (issue 54) must be written into the short-drama skill Easel reads.

Seam: the text of skills/builtin/short-drama/SKILL.md. The builder's own behaviour is tested in
tests/test_storyboard_page.py. CI runs this file through tests/test_short_drama_approval_page_in_skills.py, because
pytest does not collect *.test.py by name.
"""
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
BUILDER = SKILL_DIR.parents[2] / "skills" / "shared" / "scripts" / "storyboard_page.py"
TEXT = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def test_the_script_page_comes_after_validating_the_shots_and_before_any_still():
    after = TEXT.split("shots validate --series", 1)[1].split("### 4.", 1)[0]
    assert "--script-only" in after
    assert "storyboard_page.py build --drama-episode episodes/epNN" in after
    assert "不要在对话里贴表格" in after and "不要手写网页" in after


def test_the_stills_page_comes_after_the_first_frames_and_before_the_paid_video():
    section = TEXT.split("### 4. 关键帧生成", 1)[1].split("### 5.", 1)[0]
    assert "storyboard_page.py build --drama-episode episodes/epNN" in section
    assert "--script-only" not in section  # the stills stage is the build without the flag
    assert "审批" in section


def test_both_pages_come_before_drama_ops_generate_which_still_needs_ros_yes():
    first_page = TEXT.index("--script-only")
    generate = TEXT.index("drama_ops.py generate --series")
    assert TEXT.index("storyboard_page.py build --drama-episode") < generate
    assert first_page < TEXT.index("### 4. 关键帧生成") < TEXT.rindex("storyboard_page.py build --drama-episode") < generate
    paid = TEXT.split("### 5.", 1)[1].split("### 6.", 1)[0]
    assert "BytePlus Seedance" in paid and "同意" in paid  # the page is not the yes: a paid run asks the owner every time


def test_one_page_per_episode_and_the_bible_and_script_stay_off_the_page():
    after = TEXT.split("shots validate --series", 1)[1].split("### 4.", 1)[0]
    assert "每集一页" in after
    assert "series-bible.md" in after and "script.md" in after and "不上页" in after


def test_every_flag_the_skill_passes_to_the_builder_is_one_the_builder_has():
    help_text = subprocess.run([sys.executable, str(BUILDER), "build", "--help"], capture_output=True, text=True,
                               encoding="utf-8").stdout
    commands = re.findall(r"storyboard_page\.py build([^\n`]*)", TEXT)
    assert len(commands) >= 2  # one for each stage, so an empty loop cannot pass
    for command in commands:
        for flag in re.findall(r"(--[a-z][a-z-]*)", command):
            assert flag in help_text, f"short-drama passes {flag}, which the builder does not have"
