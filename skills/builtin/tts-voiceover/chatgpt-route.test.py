"""tts-voiceover must tell the agent how to use the ChatGPT-subscription voice route and what it cannot do.

Seam: the text the agent reads (SKILL.md) and the .env.example line that lists the provider.
Run:  .venv/bin/python -m pytest skills/builtin/tts-voiceover/chatgpt-route.test.py
The route itself is tested in tests/test_chatgpt_voice.py.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL = (Path(__file__).resolve().parent / "SKILL.md").read_text(encoding="utf-8")


def test_skill_says_how_to_switch_the_route_on_and_how_to_see_it_is_ready():
    assert "VOICE_PROVIDER=chatgpt" in SKILL
    assert "voice_clone.py check --provider chatgpt" in SKILL


NINE_VOICES = {"Sol": "glimmer", "Cove": "cove", "Vale": "vale", "Spruce": "orbit", "Arbor": "fathom",
               "Juniper": "juniper", "Breeze": "breeze", "Ember": "ember", "Maple": "maple"}  # issue 41, read from ChatGPT


def test_skill_names_the_limits():
    assert "不能克隆" in SKILL
    assert "没有 key" in SKILL


def test_skill_lists_all_nine_voices_by_settings_name_with_the_id_each_one_uses():
    for name, voice_id in NINE_VOICES.items():
        assert name in SKILL, name
        assert f"`{voice_id}`" in SKILL, voice_id


def test_skill_no_longer_says_sol_does_not_exist_or_that_only_two_voices_work():
    assert "报不存在" not in SKILL  # Sol exists; its id is glimmer
    assert "这两个实测能出声" not in SKILL
    assert "最多只有这两种声线" not in SKILL


def test_skill_says_an_unknown_voice_is_refused_and_that_every_listed_voice_has_a_recorded_sample():
    assert "不认识的声线名会直接报错" in SKILL
    assert "九个都录过试音" in SKILL


def test_skill_tells_the_agent_how_to_refuse_the_quiet_fall_back_to_the_free_voice():
    assert "--engine closed" in SKILL


def test_env_example_lists_chatgpt_as_a_voice_provider():
    assert "chatgpt" in (ROOT / ".env.example").read_text(encoding="utf-8")
