"""`audio_ops.py normalize` and `denoise --tier 3` keep the input's sample rate.

Both commands end their filter chain in `loudnorm`. On its own that filter works at 192 kHz, so
WAV, FLAC and OGG output came out at 192 kHz and M4A/AAC and a video's audio track at 96 kHz,
whatever the input rate. These tests drive the real command line through ffmpeg and read the
output's sample rate back with ffprobe.

Two cases are here because the obvious fix (forcing the output rate to the input's with -ar)
breaks them: MP3 from a 96 kHz input and Opus from a 44.1 kHz input must still succeed, at the
format's nearest supported rate (48 kHz).

Needs ffmpeg and ffprobe on PATH (WSL on this machine) and, for the tier 3 cases, the RNNoise
model at skills/shared/scripts/models/sh.rnnn; skipped otherwise.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/shared/scripts/audio_ops.py"
MODEL = ROOT / "skills/shared/scripts/models/sh.rnnn"

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)
needs_model = pytest.mark.skipif(not MODEL.is_file(), reason="RNNoise model sh.rnnn not present")

RATES = [48000, 44100, 16000]
KEPT_FORMATS = ["wav", "flac", "ogg", "m4a"]
# normalize, and denoise at level 3, are the two commands that end in loudnorm.
COMMANDS = [
    pytest.param(["normalize"], id="normalize"),
    pytest.param(["denoise", "--tier", "3"], id="denoise-tier3", marks=needs_model),
]


# ---- helpers -------------------------------------------------------------------

def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def _rate(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out)


def _video_md5(path: Path) -> str:
    """Hash of the video packets as stored: equal hashes mean the picture was copied, not re-encoded."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-c", "copy", "-f", "md5", "-"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out.startswith("MD5="), out
    return out


def _run(command: list[str], src: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(SCRIPT), command[0], str(src), "-o", str(out), *command[1:], *extra]
    return subprocess.run(argv, capture_output=True, text=True)


# ---- fixtures ------------------------------------------------------------------

@pytest.fixture(scope="module")
def media(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("audio_rate")
    paths: dict = {"dir": d}
    for r in [*RATES, 96000]:
        path = d / f"in{r}.wav"
        _ff("-f", "lavfi", "-i", f"sine=frequency=440:duration=2:sample_rate={r}",
            "-f", "lavfi", "-i", f"anoisesrc=d=2:c=pink:r={r}:a=0.05",
            "-filter_complex", "amix=inputs=2", "-ac", "1", str(path))
        paths[r] = path
    video = d / "vid48.mp4"
    _ff("-f", "lavfi", "-i", "testsrc=d=2:s=160x120:r=25", "-i", str(paths[48000]),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video))
    paths["video"] = video
    return paths


# ---- 1. every format that can hold the input's rate keeps it -------------------------------

@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("fmt", KEPT_FORMATS)
@pytest.mark.parametrize("rate", RATES)
def test_output_keeps_the_input_sample_rate(media, command, fmt, rate):
    out = media["dir"] / f"keep_{'_'.join(command)}_{rate}.{fmt}"
    proc = _run(command, media[rate], out)
    assert proc.returncode == 0, proc.stderr
    assert _rate(out) == rate


# ---- 2. MP3 and Opus: keep the rate where the format can, succeed at 48 kHz where it cannot ----

@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("rate", [44100, 16000])
def test_mp3_keeps_an_input_rate_it_supports(media, command, rate):
    out = media["dir"] / f"mp3_{'_'.join(command)}_{rate}.mp3"
    proc = _run(command, media[rate], out)
    assert proc.returncode == 0, proc.stderr
    assert _rate(out) == rate


@pytest.mark.parametrize("command", COMMANDS)
def test_mp3_from_a_96khz_input_succeeds_at_48khz(media, command):
    out = media["dir"] / f"mp3_{'_'.join(command)}_96000.mp3"
    proc = _run(command, media[96000], out)
    assert proc.returncode == 0, proc.stderr
    assert _rate(out) == 48000


@pytest.mark.parametrize("command", COMMANDS)
def test_opus_from_a_44khz_input_succeeds_at_48khz(media, command):
    out = media["dir"] / f"opus_{'_'.join(command)}_44100.opus"
    proc = _run(command, media[44100], out)
    assert proc.returncode == 0, proc.stderr
    assert _rate(out) == 48000


# ---- 3. a video keeps its picture untouched and its audio at the input's rate --------------

@needs_model
def test_tier3_on_a_video_copies_the_picture_and_keeps_48khz_audio(media):
    out = media["dir"] / "tier3_video.mp4"
    proc = _run(["denoise", "--tier", "3"], media["video"], out)
    assert proc.returncode == 0, proc.stderr
    assert _video_md5(out) == _video_md5(media["video"])
    assert _rate(out) == 48000


# ---- 4. nothing else moved: levels 1 and 2, and level 3 with no model ----------------------

# Measured on the script before the change: these chains do not end in loudnorm and already
# kept the input's rate (44.1 kHz in, 44.1 kHz out, for WAV and MP3 alike).
@pytest.mark.parametrize("fmt", ["wav", "mp3"])
@pytest.mark.parametrize(
    "extra",
    [["--tier", "1"], ["--tier", "2"], ["--tier", "3", "--model", "/nonexistent/sh.rnnn"]],
    ids=["tier1", "tier2", "tier3-no-model-fallback"],
)
def test_other_denoise_paths_still_keep_the_rate(media, extra, fmt):
    out = media["dir"] / f"other_{'_'.join(extra).replace('/', '')}.{fmt}"
    proc = _run(["denoise"], media[44100], out, *extra)
    assert proc.returncode == 0, proc.stderr
    assert _rate(out) == 44100


# ---- 5. tier 3 with no model argument still runs the model chain --------------------------

@needs_model
def test_tier3_default_prints_the_neural_chain_and_no_fallback_warning(media):
    out = media["dir"] / "tier3_chain.wav"
    proc = _run(["denoise", "--tier", "3"], media[48000], out)
    assert proc.returncode == 0, proc.stderr
    assert "arnndn" in proc.stderr and "loudnorm" in proc.stderr, proc.stderr
    assert "WARN" not in proc.stderr, proc.stderr


# ---- 6. the script's own self-test still passes (it cannot see this defect) ---------------

def test_selftest_still_passes():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--selftest"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
