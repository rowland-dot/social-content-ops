"""Tests for diandian_reply.py: which 点点 replies are saved as a summary.

The refusal and incomplete-reply cases are FavSense's own real replies, copied verbatim into tests/fixtures
(repository C:\\Users\\<user>\\Codex\\小红书收藏整理, skills/xhs-favorites-organizer/test-fixtures, commits 62e8fce and
756ec6d), so the port is held to the table FavSense holds its own rule to.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "diandian_reply.py"
spec = importlib.util.spec_from_file_location("diandian_reply", SCRIPT)
reply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reply)

REFUSALS = json.loads((HERE / "fixtures" / "diandian-refusal-cases.json").read_text(encoding="utf-8"))["cases"]
INCOMPLETE = json.loads((HERE / "fixtures" / "diandian-incomplete-cases.json").read_text(encoding="utf-8"))["cases"]
GOOD = "这篇笔记讲了三个做法：\n- 先把底妆做薄\n- 再用散粉定妆\n- 最后补一层高光"


@pytest.mark.parametrize("case", REFUSALS, ids=[c["id"] for c in REFUSALS])
def test_refusal_rule_matches_favsense_cases(case):
    assert reply.is_refusal(case["text"]) is case["refused"]


@pytest.mark.parametrize("case", INCOMPLETE, ids=[c["id"] for c in INCOMPLETE])
def test_incomplete_rule_matches_favsense_cases(case):
    assert reply.is_incomplete(case["text"]) is case["incomplete"]


def test_only_a_recognised_trailing_footer_is_removed():
    cleaned, removed = reply.clean_summary(GOOD + "\n\n以上内容由 AI 生成，仅供参考。")
    assert cleaned == GOOD
    assert removed == ["以上内容由 AI 生成，仅供参考。"]


def test_a_last_paragraph_that_merely_starts_like_a_footer_stays():
    text = GOOD + "\n\n如果你觉得有用，可以先从第一步试起。"
    assert reply.clean_summary(text)[0] == text


def test_a_normal_finished_reply_is_saved_whole():
    assert reply.summary_problem(GOOD + "\n\n你还可以继续问我关于这篇笔记的问题。") is None
    assert reply.usable_summary(GOOD + "\n\n你还可以继续问我关于这篇笔记的问题。") == GOOD


@pytest.mark.parametrize("case", [c for c in REFUSALS if c["refused"]], ids=lambda c: c["id"])
def test_a_refusal_is_not_a_summary(case):
    assert reply.summary_problem(case["text"]) == "refusal"


@pytest.mark.parametrize("case", INCOMPLETE[:3], ids=lambda c: c["id"])
def test_a_reply_that_lost_list_text_is_not_a_summary(case):
    assert reply.summary_problem(case["text"] + "。" * 3 + "补足长度" * 6) == "incomplete"


@pytest.mark.parametrize("text, problem", [
    ("", "empty"),
    ("  \n ", "empty"),
    ("太短了", "too short"),
    (GOOD + "\n- 详见 https://www.xiaohongshu.com/explore/6aabad9400000000110328e1", "holds a note address or access code"),
    (GOOD + "\nxsec_token=ABC123", "holds a note address or access code"),
])
def test_other_replies_that_are_not_saved(text, problem):
    assert reply.summary_problem(text) == problem
