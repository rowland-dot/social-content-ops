"""auto-short-video assembler: the finished video's loudness (issue 31).

Seam: the `assemble` command line of skills/builtin/auto-short-video/scripts/assemble.py, run on a storyboard of
real tone files, and the finished file measured afterwards with ffmpeg's own loudness meter (ebur128). Needs
ffmpeg and ffprobe; skipped when absent.

Rules under test (The owner's rulings in the issue, 2026-10-23):
- every finished video that has sound lands at -16 LUFS integrated (plus or minus 1 LU) with a true peak no
  higher than -1 dBTP, measured on the finished file;
- that holds when the sound is a voice-over, and when it is the clips' own sound with no voice-over at all;
- the audio stays at 48 kHz;
- a video with no sound still has none;
- the balance of the mix is left alone: the voice-over stays above the music by the same amount.

The quiet voice is a tone about 15 dB under the target, so "too quiet" is true before the fix. Expected values
are the ruling's literals, never read back from the assembler's filter settings.
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

TARGET_LUFS = -16.0
TOLERANCE_LU = 1.0
PEAK_CEILING_DBTP = -1.0
SIZE = "320x568"
VIDEO_SECONDS = 6.0
VOICE_HZ, MUSIC_HZ, CLIP_HZ = 1000, 200, 440
QUIET_DB = -9.0  # ffmpeg's sine source reads about -22 LUFS alone, so this tone is about -31 LUFS: far too quiet


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _tone(path: Path, hz: int, seconds: float, gain_db: float = 0.0) -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds}", "-af", f"volume={gain_db}dB", str(path))
    return path


def _loudness(path: Path) -> tuple[float, float]:
    """(integrated loudness in LUFS, true peak in dBTP) of the sound in `path`, from ffmpeg's ebur128 meter."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    integrated = re.findall(r"I:\s+(-?[\d.]+) LUFS", result.stderr)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", result.stderr)
    assert integrated and peak, f"no loudness summary in: {result.stderr[-400:]}"
    return float(integrated[-1]), float(peak[-1])


@pytest.fixture
def media(tmp_path):
    image = tmp_path / "still.png"
    _ffmpeg("-f", "lavfi", "-i", f"color=c=red:s={SIZE}:d=1", "-frames:v", "1", str(image))
    clip = tmp_path / "clip.mp4"  # a 6 s clip with its own, quiet, sound
    _ffmpeg("-f", "lavfi", "-i", f"color=c=yellow:s={SIZE}:d={VIDEO_SECONDS}",
            "-f", "lavfi", "-i", f"sine=frequency={CLIP_HZ}:duration={VIDEO_SECONDS}",
            "-af", f"volume={QUIET_DB}dB", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(clip))
    return {
        "image": image,
        "clip": clip,
        "quiet_voice": _tone(tmp_path / "voice.wav", VOICE_HZ, VIDEO_SECONDS, QUIET_DB),
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


def _assert_on_target(out: Path) -> None:
    lufs, peak = _loudness(out)
    assert abs(lufs - TARGET_LUFS) <= TOLERANCE_LU, f"finished video is {lufs} LUFS, target {TARGET_LUFS} +/- 1"
    assert peak <= PEAK_CEILING_DBTP, f"true peak {peak} dBTP is above {PEAK_CEILING_DBTP}"


# --- the voice-over case ---------------------------------------------------------------------

def test_a_quiet_voice_over_comes_out_at_minus_16_lufs_with_the_peak_under_minus_1(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["quiet_voice"])
    assert result.returncode == 0, result.stderr[-600:]
    _assert_on_target(out)


def test_a_quiet_voice_with_music_also_comes_out_on_target(media, tmp_path):
    music = _tone(tmp_path / "music.wav", MUSIC_HZ, 8.0, QUIET_DB)
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["quiet_voice"], bgm=music)
    assert result.returncode == 0, result.stderr[-600:]
    _assert_on_target(out)


# --- the clips' own sound, with no voice-over, music or effects (a short drama can be all of this) -----------

def test_clip_sound_alone_comes_out_on_target_too(media, tmp_path):
    shots = [{"video": str(media["clip"]), "duration": VIDEO_SECONDS, "audio_mode": "native"}]
    result, out = _assemble(tmp_path, shots)
    assert result.returncode == 0, result.stderr[-600:]
    _assert_on_target(out)


# --- the other sound cases are not disturbed -------------------------------------------------------

def test_a_video_with_no_sound_track_still_has_none(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media))
    assert result.returncode == 0, result.stderr[-600:]
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True)
    assert probe.stdout.strip() == "", f"a sound track appeared: {probe.stdout!r}"


def test_the_finished_audio_is_48_khz(media, tmp_path):
    result, out = _assemble(tmp_path, _still_shot(media), narration=media["quiet_voice"])
    assert result.returncode == 0, result.stderr[-600:]
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True)
    assert probe.stdout.strip() == "48000", f"sample rate {probe.stdout!r}"


# --- the balance of the mix is left alone ---------------------------------------------------------------

def _band_db(path: Path, hz: int, start: float, length: float) -> float:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(length), "-i", str(path), "-af",
         f"bandpass=f={hz}:width_type=h:w=20,volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    return float(re.search(r"mean_volume: (-?[\d.]+) dB", result.stderr).group(1))


def test_the_voice_stays_above_the_music_by_the_same_amount(media, tmp_path):
    # Before the loudness step this mix (3 s of 1000 Hz voice at -9 dB over 200 Hz music at 0.175) measured the voice
    # 7.0 dB above the music while the voice speaks; read off the assembler as it was before issue 31.
    voice = _tone(tmp_path / "short_voice.wav", VOICE_HZ, 3.0, QUIET_DB)
    music = _tone(tmp_path / "music.wav", MUSIC_HZ, 8.0)
    result, out = _assemble(tmp_path, _still_shot(media), narration=voice, bgm=music, bgm_volume=0.175)
    assert result.returncode == 0, result.stderr[-600:]
    gap = _band_db(out, VOICE_HZ, 0.5, 1.0) - _band_db(out, MUSIC_HZ, 0.5, 1.0)
    assert abs(gap - 7.0) <= 1.0, f"voice is {gap} dB above the music while speaking, it was 7.0 before the step"
