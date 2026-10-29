"""A settings-file value is used when the process variable is present but empty.

Issue 46: the OpenClaw gateway hands every agent shell the project's .env keys as
they were at gateway start, empty ones included. The shared scripts' settings-file
loaders skipped any key already present in the environment, so an empty variable
hid the file's value (video 01: 「未配置 VOICE_PROVIDER」).

Rule under test, for each of the four loaders in skills/shared/scripts:
  - key absent                    -> the file's value
  - key empty or only whitespace  -> the file's value
  - key with a real value         -> that value; the file never overrides it
  - the file leaves the key empty -> never overwrites a non-empty variable
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts"
LOADER_MODULES = ["ai_video", "ai_image", "ai_music", "voice_clone"]
KEY = "VOICE_PROVIDER"


def _load(module_name: str, environ: dict[str, str], settings_text: str,
          tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Run one loader against a scratch settings file and a fully controlled environment."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    module = importlib.import_module(module_name)
    env_file = tmp_path / ".env"
    env_file.write_text(settings_text, encoding="utf-8")
    monkeypatch.setattr(os, "environ", dict(environ))
    module.load_env_file(env_file)
    return os.environ  # type: ignore[return-value]


@pytest.mark.parametrize("module_name", LOADER_MODULES)
def test_absent_variable_takes_the_file_value(module_name, tmp_path, monkeypatch):
    result = _load(module_name, {}, f"{KEY}=from-file\n", tmp_path, monkeypatch)
    assert result.get(KEY) == "from-file"


@pytest.mark.parametrize("module_name", LOADER_MODULES)
def test_empty_variable_takes_the_file_value(module_name, tmp_path, monkeypatch):
    result = _load(module_name, {KEY: ""}, f"{KEY}=from-file\n", tmp_path, monkeypatch)
    assert result.get(KEY) == "from-file"


@pytest.mark.parametrize("module_name", LOADER_MODULES)
def test_whitespace_only_variable_takes_the_file_value(module_name, tmp_path, monkeypatch):
    result = _load(module_name, {KEY: "   "}, f"{KEY}=from-file\n", tmp_path, monkeypatch)
    assert result.get(KEY) == "from-file"


@pytest.mark.parametrize("module_name", LOADER_MODULES)
def test_non_empty_variable_beats_the_file(module_name, tmp_path, monkeypatch):
    result = _load(module_name, {KEY: "from-env"}, f"{KEY}=from-file\n", tmp_path, monkeypatch)
    assert result.get(KEY) == "from-env"


@pytest.mark.parametrize("module_name", LOADER_MODULES)
def test_empty_file_value_does_not_overwrite_a_non_empty_variable(module_name, tmp_path, monkeypatch):
    result = _load(module_name, {KEY: "from-env"}, f"{KEY}=\n", tmp_path, monkeypatch)
    assert result.get(KEY) == "from-env"


@pytest.mark.parametrize("module_name", LOADER_MODULES)
def test_both_empty_still_reads_as_unset(module_name, tmp_path, monkeypatch):
    result = _load(module_name, {KEY: ""}, f"{KEY}=\n", tmp_path, monkeypatch)
    assert result.get(KEY, "").strip() == ""


@pytest.mark.parametrize("module_name", LOADER_MODULES)
def test_export_prefix_comments_and_quotes_still_parse_over_an_empty_variable(
        module_name, tmp_path, monkeypatch):
    settings = f"# a comment\nexport {KEY}=\"quoted-value\"\n"
    result = _load(module_name, {KEY: ""}, settings, tmp_path, monkeypatch)
    assert result.get(KEY) == "quoted-value"


def test_voiceover_entry_uses_the_settings_file_provider_when_the_variable_is_empty(
        tmp_path, monkeypatch):
    """The reported symptom, through the voice-over script's real entry point."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    tts = importlib.import_module("tts")
    (tmp_path / ".env").write_text(f"{KEY}=chatgpt\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, "environ", {KEY: ""})

    assert tts.main(["voices"]) == 0
    assert os.environ.get(KEY) == "chatgpt"
