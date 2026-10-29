"""auto-short-video assembler: background music under a voice, looping, end fade, clip sound (issue 45).

Seam: the `assemble` command line of skills/builtin/auto-short-video/scripts/assemble.py, run on a
storyboard of real tone files. Voice, music and clip sound are tones at different pitches, so each
track's level is read in its own narrow band. Needs ffmpeg and ffprobe; skipped when absent.

Rules under test (The owner's rulings in the issue, 2026-10-16):
- the music is lowered while the voice speaks and comes back up after it;
- music shorter than the video is not looped unless the storyboard asks (`bgm_loop`); without that
  the assembler stops before rendering and says how many seconds short the music is;
- the music fades out over the storyboard's `bgm_fade_out` seconds; nothing else is faded, and with
  no such field the music is not faded (as before);
- clip sound of native-audio shots keeps playing after the last spoken line.

Expected levels are literals read off the issue's own probes (music lowered by about 7.6 dB while the
voice speaks), never recomputed from the assembler's filter settings.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "builtin" / "auto-short-video" / "scripts" / "assemble.py"

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

VOICE_HZ, MUSIC_HZ, CLIP_HZ = 1000, 200, 440
VIDEO_SECONDS = 6.0
VOICE_SECONDS = 3.0
SILENCE_DB = -50.0  # anything quieter than this counts as no sound
LOWERED_BY_DB = 5.0  # the issue's probe measured about 7.6 dB with the mixing tool's settings
SIZE = "320x568"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _tone(path: Path, hz: int, seconds: float) -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds}", str(path))
    return path


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(out.strip())


def _level_db(path: Path, hz: int, start: float, length: float | None = None) -> float:
    """Mean level (dB) of the audio in a narrow band around `hz`, from `start` for `length` seconds.
    Minus infinity when there is no audio in that stretch."""
    cmd = ["ffmpeg", "-hide_banner", "-ss", str(start)]
    if length is not None:
        cmd += ["-t", str(length)]
    cmd += ["-i", str(path), "-af", f"bandpass=f={hz}:width_type=h:w=20,volumedetect", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    match = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", result.stderr)
    if not match or match.group(1) == "-inf":
        return float("-inf")
    return float(match.group(1))


@pytest.fixture
def media(tmp_path):
    image = tmp_path / "still.png"
    _ffmpeg("-f", "lavfi", "-i", f"color=c=red:s={SIZE}:d=1", "-frames:v", "1", str(image))
    clip = tmp_path / "clip.mp4"  # a 6 s clip with its own sound
    _ffmpeg("-f", "lavfi", "-i", f"color=c=yellow:s={SIZE}:d={VIDEO_SECONDS}",
            "-f", "lavfi", "-i", f"sine=frequency={CLIP_HZ}:duration={VIDEO_SECONDS}",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip))
    return {
        "image": image,
        "clip": clip,
        "voice": _tone(tmp_path / "voice.wav", VOICE_HZ, VOICE_SECONDS),
        "voice_full": _tone(tmp_path / "voice_full.wav", VOICE_HZ, VIDEO_SECONDS),
        "music": _tone(tmp_path / "music.wav", MUSIC_HZ, 8.0),  # longer than the video
        "music_short": _tone(tmp_path / "music_short.wav", MUSIC_HZ, 2.0),  # shorter than the video
    }


def _assemble(tmp_path: Path, shots: list[dict], **fields) -> tuple[subprocess.CompletedProcess, Path]:
    storyboard = {"size": SIZE, "image_motion": "static", "pad_mode": "trim", "shots": shots}
    storyboard.update({k: str(v) if isinstance(v, Path) else v for k, v in fields.items()})
    sb_file = tmp_path / "sb.json"
    sb_file.write_text(json.dumps(storyboard), encoding="utf-8")
    out = tmp_path / "final.mp4"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "assemble", "--storyboard", str(sb_file), "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True,
    )
    return result, out


def _still_shot(media) -> list[dict]:
    return [{"image": str(media["image"]), "duration": VIDEO_SECONDS}]


def _native_shot(media) -> list[dict]:
    return [{"video": str(media["clip"]), "duration": VIDEO_SECONDS, "audio_mode": "native"}]


# --- the music is lowered while the voice speaks --------------------------------------------

def test_music_is_lowered_while_the_voice_speaks_and_comes_back_after(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["voice"], bgm=media["music"])
    assert result.returncode == 0, result.stderr[-600:]
    while_speaking = _level_db(out, MUSIC_HZ, start=0.5, length=1.0)
    after_voice = _level_db(out, MUSIC_HZ, start=4.0, length=1.0)
    assert while_speaking > SILENCE_DB  # the music really is playing under the voice
    assert after_voice - while_speaking >= LOWERED_BY_DB, (
        f"music: {while_speaking} dB while speaking, {after_voice} dB after the voice stopped"
    )


def test_music_keeps_playing_after_the_voice_ends(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["voice"], bgm=media["music"])
    assert result.returncode == 0, result.stderr[-600:]
    assert _level_db(out, MUSIC_HZ, start=4.0, length=1.0) > SILENCE_DB


# --- music shorter than the video ------------------------------------------------------------

def test_short_music_without_a_loop_request_stops_before_rendering_and_says_how_short(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["voice"], bgm=media["music_short"])
    assert result.returncode != 0, "the assembler rendered a video with music 4 s shorter than the video"
    assert not out.exists()
    assert "合成分镜" not in result.stderr, "it started rendering shots before refusing"
    assert "4.0" in result.stderr, f"the refusal does not say the music is 4.0 s short: {result.stderr[-300:]}"


def test_short_music_loops_when_the_storyboard_asks_for_it(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["voice"],
                            bgm=media["music_short"], bgm_loop=True)
    assert result.returncode == 0, result.stderr[-600:]
    assert _level_db(out, MUSIC_HZ, start=4.5, length=1.0) > SILENCE_DB  # past the music's own 2 s end


def test_bgm_loop_must_be_true_or_false(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), bgm=media["music"], bgm_loop="yes")
    assert result.returncode != 0
    assert "bgm_loop" in result.stderr
    assert not out.exists()


# --- the end fade, music only ----------------------------------------------------------------

def test_music_fades_out_over_the_storyboards_fade_length(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["voice_full"],
                            bgm=media["music"], bgm_fade_out=2.0)
    assert result.returncode == 0, result.stderr[-600:]
    before_fade = _level_db(out, MUSIC_HZ, start=2.0, length=0.5)
    at_the_end = _level_db(out, MUSIC_HZ, start=VIDEO_SECONDS - 0.5)
    assert before_fade > SILENCE_DB
    assert at_the_end < before_fade - 6, f"music: {before_fade} dB before the fade, {at_the_end} dB at the end"


def test_the_fade_leaves_the_voice_alone(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["voice_full"],
                            bgm=media["music"], bgm_fade_out=2.0)
    assert result.returncode == 0, result.stderr[-600:]
    # The mixer turns the mono voice into stereo, which lowers its level by a fixed amount, so the
    # voice is compared with itself earlier in the same video: a steady tone must stay steady.
    earlier = _level_db(out, VOICE_HZ, start=2.0, length=1.0)
    last_second = _level_db(out, VOICE_HZ, start=VIDEO_SECONDS - 1.0)
    assert earlier > SILENCE_DB
    assert abs(last_second - earlier) <= 1.0, f"voice: {earlier} dB earlier, {last_second} dB in the last second"


def test_the_fade_leaves_the_clip_sound_alone(media, tmp_path):
    result, out = _assemble(tmp_path, _native_shot(media), narration=media["voice"],
                            bgm=media["music"], bgm_fade_out=2.0)
    assert result.returncode == 0, result.stderr[-600:]
    after_voice = _level_db(out, CLIP_HZ, start=4.0, length=1.0)
    last_second = _level_db(out, CLIP_HZ, start=VIDEO_SECONDS - 1.0)
    assert after_voice > SILENCE_DB  # the clip sound is really there to be faded
    assert abs(last_second - after_voice) <= 1.0, f"clip sound: {after_voice} dB, {last_second} dB in the last second"


def test_without_a_fade_field_the_music_is_not_faded(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["voice"], bgm=media["music"])
    assert result.returncode == 0, result.stderr[-600:]
    earlier = _level_db(out, MUSIC_HZ, start=4.0, length=0.5)
    at_the_end = _level_db(out, MUSIC_HZ, start=VIDEO_SECONDS - 0.5)
    assert earlier > SILENCE_DB
    assert abs(at_the_end - earlier) <= 1.0, f"music: {earlier} dB earlier, {at_the_end} dB at the end"


def test_a_fade_longer_than_the_video_is_refused(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), bgm=media["music"], bgm_fade_out=VIDEO_SECONDS + 1)
    assert result.returncode != 0
    assert "bgm_fade_out" in result.stderr
    assert not out.exists()


# --- clip sound keeps playing after the last spoken line ------------------------------------------

def test_clip_sound_keeps_playing_after_the_voice_ends(media, tmp_path):
    result, out = _assemble(tmp_path, _native_shot(media), narration=media["voice"])
    assert result.returncode == 0, result.stderr[-600:]
    after_voice = _level_db(out, CLIP_HZ, start=4.0, length=1.0)
    last_second = _level_db(out, CLIP_HZ, start=VIDEO_SECONDS - 1.0)
    assert after_voice > SILENCE_DB, f"clip sound after the voice ended: {after_voice} dB"
    assert abs(last_second - after_voice) <= 1.0, f"clip sound: {after_voice} dB, {last_second} dB in the last second"


def test_clip_sound_is_still_lowered_while_the_voice_speaks(media, tmp_path):
    result, out = _assemble(tmp_path, _native_shot(media), narration=media["voice"])
    assert result.returncode == 0, result.stderr[-600:]
    while_speaking = _level_db(out, CLIP_HZ, start=0.5, length=1.0)
    after_voice = _level_db(out, CLIP_HZ, start=4.0, length=1.0)
    assert after_voice - while_speaking >= LOWERED_BY_DB, (
        f"clip sound: {while_speaking} dB while speaking, {after_voice} dB after"
    )


def test_clip_sound_and_music_both_play_after_the_voice_ends(media, tmp_path):
    result, out = _assemble(tmp_path, _native_shot(media), narration=media["voice"], bgm=media["music"])
    assert result.returncode == 0, result.stderr[-600:]
    assert _level_db(out, CLIP_HZ, start=4.0, length=1.0) > SILENCE_DB
    assert _level_db(out, MUSIC_HZ, start=4.0, length=1.0) > SILENCE_DB
    assert abs(_duration(out) - VIDEO_SECONDS) <= 0.2


# --- the assembler's own self-check ---------------------------------------------------------------

def test_the_assemblers_own_selftest_passes():
    result = subprocess.run([sys.executable, str(SCRIPT), "selftest"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, (result.stdout + result.stderr)[-600:]
