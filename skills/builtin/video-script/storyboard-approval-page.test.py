"""The storyboard approval page (issue 51) must be written into the skills Easel reads.

Seam: the text the agent reads, the SKILL.md of video-script (it defines the shot table the page is built from) and of
auto-short-video (it must call the builder whenever a script or timeline goes for approval). The behaviour of the
builder itself is tested in tests/test_storyboard_page.py.
Run: .venv/bin/python -m pytest skills/builtin/video-script/storyboard-approval-page.test.py
CI runs it through tests/test_storyboard_page_in_skills.py, because pytest does not collect *.test.py by name.
"""
import re
import subprocess
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1]
BUILDER = SKILLS.parents[1] / "skills" / "shared" / "scripts" / "storyboard_page.py"


def skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def test_video_script_defines_the_shot_table_the_approval_page_reads():
    text = skill("video-script")
    assert "计划里的分镜表" in text
    section = text.split("计划里的分镜表", 1)[1]
    assert "镜 | 时间 | 口播 | 画面 | 来源 | 分镜图 | 备注" in section  # the columns, in the order the builder expects
    assert "storyboard_page.py" in section


def test_video_script_says_where_rulings_go_and_what_the_still_cell_holds():
    section = skill("video-script").split("计划里的分镜表", 1)[1]
    assert "备注" in section and "不写进口播" in section  # a ruling note never joins the spoken line
    assert "只写文件名" in section and "storyboard/" in section


def test_video_script_still_keeps_the_current_state_first_and_the_change_log_last_in_a_plan():
    text = skill("video-script")  # the shot table section was added after this line; it must not displace it
    assert text.index("当前状态") < text.index("计划里的分镜表")
    assert "变更记录" in text.split("计划里的分镜表", 1)[0]


def test_video_script_says_each_open_ending_gets_its_own_table():
    section = skill("video-script").split("计划里的分镜表", 1)[1]
    assert "待定结尾：" in section
    assert "每个方案各一个" in section


def test_auto_short_video_calls_the_builder_when_a_script_or_timeline_goes_for_approval():
    text = skill("auto-short-video")
    step1 = text.split("1. **写脚本分镜**", 1)[1].split("2. **生成画面**", 1)[0]
    assert "审批" in step1
    assert "skills/shared/scripts/storyboard_page.py build --plan" in step1
    assert "不要在对话里贴表格" in step1
    assert "不要手写网页" in step1


def test_auto_short_video_tells_the_script_stage_from_the_stage_when_the_stills_exist():
    step1 = skill("auto-short-video").split("1. **写脚本分镜**", 1)[1].split("2. **生成画面**", 1)[0]
    assert "--script-only" in step1  # no stills yet: the page shows the script and says the stills are not made
    assert step1.count("storyboard_page.py build") >= 2  # one command for each stage


def test_every_flag_the_skills_pass_to_the_builder_is_one_the_builder_has():
    help_text = subprocess.run([sys.executable, str(BUILDER), "build", "--help"], capture_output=True, text=True,
                               encoding="utf-8").stdout
    commands = 0
    for name in ("video-script", "auto-short-video"):
        for command in re.findall(r"storyboard_page\.py build([^\n`]*)", skill(name)):
            commands += 1
            for flag in re.findall(r"(--[a-z][a-z-]*)", command):
                assert flag in help_text, f"{name} passes {flag}, which the builder does not have"
    assert commands >= 2  # the skills really do carry commands, so an empty loop cannot pass
