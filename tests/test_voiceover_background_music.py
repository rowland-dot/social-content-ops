"""tts-voiceover step 1 (voiceover + background music) must work on an audio file.

Seam: the command written in tts-voiceover/SKILL.md post-processing step 1,
run as written (only file names, and the interpreter, substituted) on real
voiceover audio. Plus the two rule lines that tell the agent which script mixes.
Needs ffmpeg and ffprobe; skipped when they are absent.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TTS_TEXT = (ROOT / "skills" / "builtin" / "tts-voiceover" / "SKILL.md").read_text(encoding="utf-8")
MUSIC_TEXT = (ROOT / "skills" / "builtin" / "ai-music" / "SKILL.md").read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

VOICE_HZ, MUSIC_HZ = 300, 1000
VOICE_SECONDS, MUSIC_SECONDS = 6.0, 2.5  # music bed shorter than the voiceover: it must loop


def _step1_command() -> list[str]:
    """The command under the '① ' comment in step 2 of the skill, as an argv list."""
    section = TTS_TEXT.split("### 2. 后处理", 1)[1]
    block = section.split("# ① ", 1)[1].split("\n# ②", 1)[0]
    lines = [line.strip() for line in block.split("\n")[1:]]  # drop the rest of the first comment line
    command = " ".join(line.rstrip("\\") for line in lines if line and not line.startswith("#"))
    return shlex.split(command)


def _value_after(argv: list[str], *flags: str) -> int:
    for flag in flags:
        if flag in argv:
            return argv.index(flag) + 1
    raise AssertionError(f"none of {flags} in step 1 command: {argv}")


def _tone(path: Path, hz: int, seconds: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds}", str(path)],
        check=True,
    )


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)


def _band_db(path: Path, hz: int, start: float = 0.0) -> float:
    """Mean level (dB) of the audio around `hz`, from `start` seconds on."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", str(start), "-i", str(path), "-af",
         f"bandpass=f={hz}:width_type=h:w=20,volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", result.stderr)
    assert match, result.stderr[-500:]
    return float("-inf") if match.group(1) == "-inf" else float(match.group(1))


@pytest.fixture(params=["mp3", "wav", "m4a"])
def mixed(request, tmp_path):
    ext = request.param
    voice, music, out = tmp_path / f"vo.{ext}", tmp_path / "bgm.mp3", tmp_path / f"vo_bgm.{ext}"
    _tone(voice, VOICE_HZ, VOICE_SECONDS)
    _tone(music, MUSIC_HZ, MUSIC_SECONDS)
    argv = _step1_command()
    argv[_value_after(argv, "--voice", "-i")] = str(voice)
    argv[_value_after(argv, "--bgm", "--music")] = str(music)
    argv[_value_after(argv, "-o", "--output")] = str(out)
    if argv[0] == "python":
        argv[0] = sys.executable
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    return result, voice, out


def test_step1_command_succeeds_on_a_voiceover_audio_file(mixed):
    result, _voice, out = mixed
    assert result.returncode == 0, result.stderr[-600:]
    assert out.is_file() and out.stat().st_size > 0


def test_output_is_audio_only_and_as_long_as_the_voiceover(mixed):
    result, _voice, out = mixed
    assert result.returncode == 0, result.stderr[-600:]
    info = _probe(out)
    kinds = {s["codec_type"] for s in info["streams"]}
    assert kinds == {"audio"}
    assert abs(float(info["format"]["duration"]) - VOICE_SECONDS) <= 0.2


def test_music_is_audible_under_the_voiceover_including_the_last_two_seconds(mixed):
    result, voice, out = mixed
    assert result.returncode == 0, result.stderr[-600:]
    alone = _band_db(voice, MUSIC_HZ)
    assert _band_db(out, MUSIC_HZ) > alone + 6
    # the 2.5 s bed must loop to the end of the 6 s voiceover
    assert _band_db(out, MUSIC_HZ, start=VOICE_SECONDS - 2) > _band_db(voice, MUSIC_HZ, start=VOICE_SECONDS - 2) + 6


def test_step1_names_the_mixer_not_concat_and_mentions_ducking():
    block = TTS_TEXT.split("# ① ", 1)[1].split("\n# ②", 1)[0]
    assert "audio_mix.py mix" in block
    assert "concat" not in block
    assert "--no-duck" in block and "闪避" in block


def _rule(text: str, number: int) -> str:
    match = re.search(rf"^{number}\. \*\*.*?(?=^\d+\. \*\*|\Z)", text.split("## 规则", 1)[1], re.M | re.S)
    assert match, f"rule {number} not found"
    return match.group(0)


def test_tts_voiceover_rule_sends_mixing_to_the_audio_mixer():
    rule = _rule(TTS_TEXT, 4)
    assert "audio_mix.py" in rule
    assert "video_ops.py" in rule  # still the tool for putting audio onto a video


def test_ai_music_rule_sends_voiceover_plus_music_mixing_to_the_audio_mixer():
    rule = _rule(MUSIC_TEXT, 5)
    assert "audio_mix.py" in rule
    assert "video_ops.py bgm" not in rule
