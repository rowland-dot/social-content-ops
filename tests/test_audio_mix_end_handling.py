"""audio_mix.py mix: the closing fade and the length of a ducked mix (issue 42).

Seam: the `mix` command line of skills/shared/scripts/audio_mix.py, run on real
tone files. Voice and music are tones at different pitches, so each track's level
is read in its own narrow band. Needs ffmpeg and ffprobe; skipped when absent.

Rules under test:
- the voice is never faded or shortened by the mixer's end handling;
- music (and sound effects) still fade out at the end;
- with ducking on, the music runs to the full requested length after the voice ends;
- the success line prints the length of the file actually written;
- mixes with no voice come out as they did before the change. "Before" is the
  copy of the script saved in archive/skill-backups/audio-mix/2026-10-16/.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "shared" / "scripts" / "audio_mix.py"
BEFORE_CHANGE = ROOT / "archive" / "skill-backups" / "audio-mix" / "2026-10-16" / "audio_mix.py"

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

VOICE_HZ, MUSIC_HZ, SFX_HZ = 300, 1000, 1200
VOICE_SECONDS, MUSIC_SECONDS, SFX_SECONDS = 6.0, 2.5, 0.3  # music is shorter than the voice: it loops
LONGER_BY = 2.0  # how much longer than the voice a ducked mix is asked to be
SILENCE_DB = -50.0  # anything quieter than this counts as no music


def _tone(path: Path, hz: int, seconds: float) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds}", str(path)],
        check=True,
    )
    return path


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(out.strip())


def _level_db(path: Path, hz: int | None = None, start: float = 0.0, length: float | None = None) -> float:
    """Mean level (dB) of `path` from `start` for `length` seconds, in a narrow band around `hz` if given.
    Minus infinity when there is no audio in that stretch (for example past the end of the file)."""
    cmd = ["ffmpeg", "-hide_banner", "-ss", str(start)]
    if length is not None:
        cmd += ["-t", str(length)]
    band = f"bandpass=f={hz}:width_type=h:w=20," if hz else ""
    cmd += ["-i", str(path), "-af", f"{band}volumedetect", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    match = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", result.stderr)
    if not match or match.group(1) == "-inf":
        return float("-inf")
    return float(match.group(1))


def _mix(script: Path, out: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), "mix", *args, "-o", str(out)], cwd=ROOT, capture_output=True, text=True
    )


@pytest.fixture
def tones(tmp_path):
    return {
        "voice": _tone(tmp_path / "voice.wav", VOICE_HZ, VOICE_SECONDS),
        "music": _tone(tmp_path / "music.wav", MUSIC_HZ, MUSIC_SECONDS),
        "sfx": _tone(tmp_path / "sfx.wav", SFX_HZ, SFX_SECONDS),
    }


# --- the voice is never faded -------------------------------------------------------------

VOICE_CASES = {
    "music, ducking on": lambda t: ["--bgm", str(t["music"])],
    "music, ducking off": lambda t: ["--bgm", str(t["music"]), "--no-duck"],
    "no music at all": lambda t: [],
    "no music, one sound effect": lambda t: ["--sfx", str(t["sfx"]), "--sfx-at", "5.0"],
}


@pytest.mark.parametrize("case", list(VOICE_CASES))
def test_voice_keeps_its_input_level_in_the_last_second(case, tones, tmp_path):
    out = tmp_path / "out.wav"
    result = _mix(SCRIPT, out, "--voice", str(tones["voice"]), *VOICE_CASES[case](tones))
    assert result.returncode == 0, result.stderr[-600:]
    voice_in = _level_db(tones["voice"], VOICE_HZ, start=VOICE_SECONDS - 1.0)
    voice_out = _level_db(out, VOICE_HZ, start=_duration(out) - 1.0)
    assert voice_in > SILENCE_DB  # the input really has a voice in its last second
    assert abs(voice_out - voice_in) <= 1.0, f"voice last second: input {voice_in} dB, output {voice_out} dB"


# --- the music still fades ----------------------------------------------------------------

def test_music_still_fades_out_under_a_voice_at_the_default_length(tones, tmp_path):
    out = tmp_path / "out.wav"
    result = _mix(SCRIPT, out, "--voice", str(tones["voice"]), "--bgm", str(tones["music"]))
    assert result.returncode == 0, result.stderr[-600:]
    two_seconds_earlier = _level_db(out, MUSIC_HZ, start=VOICE_SECONDS - 2.5, length=0.5)
    final = _level_db(out, MUSIC_HZ, start=VOICE_SECONDS - 0.5)
    assert two_seconds_earlier > SILENCE_DB  # the music is really there to be faded
    assert final < two_seconds_earlier - 6, f"music: {two_seconds_earlier} dB earlier, {final} dB at the end"


# --- ducking on, mix asked to be longer than the voice -------------------------------------

LONG_TARGET = VOICE_SECONDS + LONGER_BY


@pytest.fixture
def long_ducked(tones, tmp_path):
    out = tmp_path / "long.wav"
    result = _mix(SCRIPT, out, "--voice", str(tones["voice"]), "--bgm", str(tones["music"]),
                  "--duration", str(LONG_TARGET))
    assert result.returncode == 0, result.stderr[-600:]
    return result, out


def test_ducked_mix_is_as_long_as_requested_when_the_voice_is_shorter(long_ducked):
    _result, out = long_ducked
    assert abs(_duration(out) - LONG_TARGET) <= 0.1


def test_music_plays_on_after_the_voice_has_ended(long_ducked):
    _result, out = long_ducked
    after_voice = _level_db(out, MUSIC_HZ, start=VOICE_SECONDS + 0.1, length=0.3)
    assert after_voice > SILENCE_DB, f"music right after the voice: {after_voice} dB"


def test_music_after_the_voice_fades_at_the_end_instead_of_cutting(long_ducked):
    _result, out = long_ducked
    just_before_fade = _level_db(out, MUSIC_HZ, start=VOICE_SECONDS + 0.1, length=0.3)
    final = _level_db(out, MUSIC_HZ, start=LONG_TARGET - 0.5)
    assert just_before_fade > SILENCE_DB  # music is really there to be faded
    assert final < just_before_fade - 6, f"music: {just_before_fade} dB before the fade, {final} dB at the end"


def test_success_line_reports_the_length_of_the_file_written(long_ducked):
    result, out = long_ducked
    printed = re.search(r"/ ([\d.]+)s /", result.stdout)
    assert printed, result.stdout
    assert abs(float(printed.group(1)) - _duration(out)) <= 0.1


# --- mixes with no voice are unchanged ------------------------------------------------------

NO_VOICE_CASES = {
    "music only, default length": lambda t: ["--bgm", str(t["music"])],
    "music only, 6 s": lambda t: ["--bgm", str(t["music"]), "--duration", "6"],
    "music and sound effect, 6 s": lambda t: ["--bgm", str(t["music"]), "--sfx", str(t["sfx"]),
                                                "--sfx-at", "1.0", "--duration", "6"],
}


@pytest.fixture(params=list(NO_VOICE_CASES))
def before_and_after(request, tones, tmp_path):
    if not BEFORE_CHANGE.is_file():
        pytest.skip("skill backups are kept only on the owner's PC")
    args = NO_VOICE_CASES[request.param](tones)
    old, new = tmp_path / "old.wav", tmp_path / "new.wav"
    for script, out in ((BEFORE_CHANGE, old), (SCRIPT, new)):
        result = _mix(script, out, *args)
        assert result.returncode == 0, result.stderr[-600:]
    return old, new


def test_no_voice_mix_has_the_same_length_as_before(before_and_after):
    old, new = before_and_after
    assert abs(_duration(new) - _duration(old)) <= 0.05


def test_no_voice_mix_has_the_same_end_level_as_before(before_and_after):
    old, new = before_and_after
    old_end = _level_db(old, start=_duration(old) - 0.5)
    new_end = _level_db(new, start=_duration(new) - 0.5)
    assert old_end > -80  # the end of the old mix is mid-fade, not digital silence
    assert abs(new_end - old_end) <= 1.0, f"end level: before {old_end} dB, now {new_end} dB"


# --- the script's own self-check ------------------------------------------------------------

def test_the_scripts_own_selftest_passes():
    result = subprocess.run([sys.executable, str(SCRIPT), "selftest"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, (result.stdout + result.stderr)[-600:]
