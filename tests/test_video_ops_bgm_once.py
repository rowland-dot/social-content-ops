"""`video_ops.py bgm --music-loop-off`: a voice-over laid onto a longer video plays once.

The bgm subcommand loops its --music input to the video's length, which is right for a music
bed and wrong for a voice-over (a 6 s voice-over on a 10 s clip replayed from 6 s). These tests
drive the real command line with ffmpeg tones on separate frequencies so each source can be
measured alone, on both branches of the command: a clip with its own sound, and a silent clip.

The voice-over case runs the tts-voiceover skill's step 3 command exactly as the skill text
reads (file names substituted), so the skill and the script cannot drift apart.

Needs ffmpeg and ffprobe on PATH (WSL on this machine); skipped otherwise.
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
SCRIPT = ROOT / "skills/shared/scripts/video_ops.py"
SKILL = ROOT / "skills/builtin/tts-voiceover/SKILL.md"

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)

CLIP_OWN_HZ, VOICE_HZ, MUSIC_HZ = 1000, 300, 700
CLIPS = ["with_sound", "silent"]


# ---- media helpers -------------------------------------------------------------

def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def _tone(path: Path, hz: int, seconds: float) -> None:
    _ff("-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds}", str(path))


def _clip(path: Path, *, with_sound: bool) -> None:
    video = ["-f", "lavfi", "-i", "testsrc=size=160x120:rate=25:duration=10"]
    if with_sound:
        _ff(*video, "-f", "lavfi", "-i", f"sine=frequency={CLIP_OWN_HZ}:duration=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path))
    else:
        _ff(*video, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(path))


def _band_db(path: Path, hz: int, start: float) -> float:
    """Mean level in dB of a narrow band around `hz` over the second starting at `start`."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-ss", str(start), "-t", "1", "-i", str(path), "-vn",
         "-af", f"bandpass=f={hz}:width_type=h:w=40,volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", proc.stderr)
    assert m, f"no mean_volume in ffmpeg output:\n{proc.stderr}"
    return -120.0 if m.group(1) == "-inf" else float(m.group(1))


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def _durations(path: Path) -> tuple[float, float]:
    """(container seconds, video stream seconds)."""
    info = _probe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    return float(info["format"]["duration"]), float(video["duration"])


def _layout(path: Path) -> list[str]:
    return [f'{s["codec_type"]}:{s["codec_name"]}' for s in _probe(path)["streams"]]


# ---- the skill's step 3 command, read from the skill text ---------------------------

def _skill_step3() -> tuple[list[str], str]:
    """(argv tail after 'video_ops.py', comment text) of step 3 in the tts-voiceover skill."""
    lines = SKILL.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("# ③"))
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("```"))
    block = lines[start:end]
    comment = "\n".join(ln for ln in block if ln.startswith("#"))
    command = " ".join(ln.rstrip("\\").strip() for ln in block if not ln.startswith("#"))
    words = shlex.split(command)
    assert words[:3] == ["python", "skills/shared/scripts/video_ops.py", "bgm"], command
    return words[2:], comment


def _run_skill_step3(workdir: Path, clip: Path, voiceover: Path, out: Path) -> subprocess.CompletedProcess:
    """Run step 3 as written, with only the file names substituted."""
    args, _ = _skill_step3()
    subst = {"clip.mp4": str(clip), "clip_vo.mp4": str(out), "vo.mp3": str(voiceover)}
    argv = [sys.executable, str(SCRIPT), *[subst.get(a, a) for a in args]]
    return subprocess.run(argv, cwd=workdir, capture_output=True, text=True)


def _run_bgm(clip: Path, music: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "bgm", "-i", str(clip), "-o", str(out), "--music", str(music),
         "--voice-volume", "0.4", "--music-volume", "1.0", *extra],
        capture_output=True, text=True,
    )


# ---- fixtures ------------------------------------------------------------------

@pytest.fixture(scope="module")
def media(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("bgm_once")
    paths = {
        "with_sound": d / "clip_sound.mp4",
        "silent": d / "clip_silent.mp4",
        "vo6": d / "vo6.mp3",
        "vo14": d / "vo14.mp3",
        "bed": d / "bed.mp3",
    }
    _clip(paths["with_sound"], with_sound=True)
    _clip(paths["silent"], with_sound=False)
    _tone(paths["vo6"], VOICE_HZ, 6)
    _tone(paths["vo14"], VOICE_HZ, 14)
    _tone(paths["bed"], MUSIC_HZ, 2.5)
    paths["dir"] = d
    return paths


# ---- 1. the skill's voice-over step plays the voice-over once ----------------------------

@pytest.mark.parametrize("kind", CLIPS)
def test_skill_step3_plays_a_6s_voiceover_once_on_a_10s_clip(media, kind):
    out = media["dir"] / f"vo_once_{kind}.mp4"
    proc = _run_skill_step3(media["dir"], media[kind], media["vo6"], out)
    assert proc.returncode == 0, proc.stderr
    container, video = _durations(out)
    assert container == pytest.approx(10, abs=0.1)
    assert video == pytest.approx(10, abs=0.1)
    early = _band_db(out, VOICE_HZ, 2)
    late = _band_db(out, VOICE_HZ, 7)
    assert early > -45, f"voice-over missing at 2-3 s ({early} dB)"
    assert early - late >= 30, f"voice-over still audible at 7-8 s: {early} dB at 2-3 s, {late} dB at 7-8 s"


def test_skill_step3_leaves_the_clips_own_sound_level_when_the_voiceover_ends(media):
    out = media["dir"] / "vo_once_level.mp4"
    proc = _run_skill_step3(media["dir"], media["with_sound"], media["vo6"], out)
    assert proc.returncode == 0, proc.stderr
    during = _band_db(out, CLIP_OWN_HZ, 2)
    after = _band_db(out, CLIP_OWN_HZ, 7)
    assert abs(after - during) <= 1, f"clip's own sound moved from {during} to {after} dB"


def test_skill_step3_comment_says_the_voiceover_is_played_once(media):
    _, comment = _skill_step3()
    assert "一次" in comment and "循环" in comment, comment


# ---- 2. a voice-over longer than the video is still cut to the video -----------------------

@pytest.mark.parametrize("kind", CLIPS)
def test_14s_voiceover_with_the_option_gives_a_10s_output(media, kind):
    out = media["dir"] / f"vo14_{kind}.mp4"
    proc = _run_bgm(media[kind], media["vo14"], out, "--music-loop-off")
    assert proc.returncode == 0, proc.stderr
    container, video = _durations(out)
    assert container == pytest.approx(10, abs=0.1)
    assert video == pytest.approx(10, abs=0.1)


# ---- 3. without the option, music still loops and the output is what it was before --------

# Measured on the script as it stood before --music-loop-off was added (2.5 s 700 Hz bed,
# volumes 0.4 / 1.0, 10 s clip). Independent literals, not recomputed from the code.
BEFORE_FIX = {
    "with_sound": {"layout": ["video:h264", "audio:aac"], "bed_1s": -27.6, "bed_8s": -27.6, "own_2s": -35.1},
    "silent": {"layout": ["video:h264", "audio:aac"], "bed_1s": -21.6, "bed_8s": -21.6, "own_2s": None},
}


@pytest.mark.parametrize("kind", CLIPS)
def test_music_bed_without_the_option_still_loops_to_the_video_length(media, kind):
    out = media["dir"] / f"bed_default_{kind}.mp4"
    proc = _run_bgm(media[kind], media["bed"], out)
    assert proc.returncode == 0, proc.stderr
    container, video = _durations(out)
    assert container == pytest.approx(10, abs=0.1)
    assert video == pytest.approx(10, abs=0.1)
    early = _band_db(out, MUSIC_HZ, 1)
    late = _band_db(out, MUSIC_HZ, 8)
    assert early > -50, f"music missing at 1-2 s ({early} dB)"
    assert abs(early - late) <= 1, f"music bed {early} dB at 1-2 s but {late} dB at 8-9 s"


@pytest.mark.parametrize("kind", CLIPS)
def test_default_output_matches_the_measurements_taken_before_the_fix(media, kind):
    base = BEFORE_FIX[kind]
    out = media["dir"] / f"bed_baseline_{kind}.mp4"
    proc = _run_bgm(media[kind], media["bed"], out)
    assert proc.returncode == 0, proc.stderr
    assert _layout(out) == base["layout"]
    assert _band_db(out, MUSIC_HZ, 1) == pytest.approx(base["bed_1s"], abs=0.5)
    assert _band_db(out, MUSIC_HZ, 8) == pytest.approx(base["bed_8s"], abs=0.5)
    if kind == "with_sound":
        assert _band_db(out, CLIP_OWN_HZ, 2) == pytest.approx(base["own_2s"], abs=0.5)
