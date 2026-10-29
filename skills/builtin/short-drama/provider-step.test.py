"""Issue 53: short-drama step 16 no longer reads the video provider from the shell.

The step used to run `dubbing.py prepare ... --provider "$VIDEO_PROVIDER"`. That shell variable is whatever the
agent gateway copied from the settings file when it started, so after a change in the settings panel the step
locked the OLD provider into the episode's shots file. The step now passes the provider chosen from the model
registry's configured list one line above, and `prepare` itself still falls back to the settings file.

Seams: the text the agent reads (step 16 of SKILL.md), and the real `dubbing.py prepare` command run in a scratch
folder. Run: .venv/bin/python -m pytest skills/builtin/short-drama/provider-step.test.py
CI runs it through tests/test_short_drama_provider_step.py, because pytest does not collect *.test.py by name.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent
DUBBING = SKILL / "scripts" / "dubbing.py"
PROVIDER_KEYS = ("VIDEO_PROVIDER", "ARK_MODEL", "VIDEO_CAPABILITIES_JSON")


def _step16_prepare_command() -> str:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    step16 = text.split("16. **生成音频契约和 prompt", 1)[1].split("17. **逐镜生视频", 1)[0]
    return next(line for line in step16.splitlines() if "dubbing.py prepare" in line)


def _prepare(provider_args: list[str], settings: str, inherited: dict[str, str]) -> dict:
    """Run the real `prepare` in a scratch project: a settings file, a one-shot episode, a controlled environment."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env").write_text(settings, encoding="utf-8")
        episode = root / "outputs" / "drama" / "episodes" / "ep01"
        episode.mkdir(parents=True)
        (episode / "shots.json").write_text(json.dumps({"shots": [{"idx": 1, "desc": "a door opens"}]}), encoding="utf-8")
        (episode / "lines.json").write_text(json.dumps({"lines": []}), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k not in PROVIDER_KEYS}
        env.update(inherited)
        done = subprocess.run(
            [sys.executable, str(DUBBING), "prepare", "--series", "drama", "--episode", "1", "--language", "zh-CN",
             "--root", str(root / "outputs"), *provider_args],
            cwd=root, env=env, capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stdout + done.stderr
        return json.loads((episode / "shots.json").read_text(encoding="utf-8"))["video_generation"]


def test_step16_does_not_pass_the_raw_shell_variable_as_the_provider():
    command = _step16_prepare_command()
    assert "VIDEO_PROVIDER" not in command, command
    assert "--provider" in command, command  # still locks one provider for the episode, now the chosen one


def test_prepare_locks_the_provider_the_step_passes_even_when_the_shell_holds_a_stale_one():
    locked = _prepare(["--provider", "ark"], "VIDEO_PROVIDER=ark\n", {"VIDEO_PROVIDER": "openai-compatible"})
    assert locked["provider"] == "ark"


def test_prepare_with_no_shell_variable_locks_the_provider_the_settings_file_names():
    locked = _prepare(["--provider", ""], "VIDEO_PROVIDER=ark\n", {})
    assert locked["provider"] == "ark"
