"""sound_check.py check: the automatic sound check on a finished video (issue 49).

Seam: the `check` command line of skills/shared/scripts/sound_check.py, run on real files. The synthetic videos are
built from tones so every expected level is known by construction: the voice is a 300 Hz tone and the music a 1000 Hz
tone, each at a fixed volume. Needs ffmpeg and ffprobe; skipped when absent. The last section runs the real video 01
files and is skipped when the folder named by EASEL_SOUND_CHECK_VIDEO01_DIR is not set or is missing files.

Rules under test (the issue's acceptance criteria, with the owner's rulings of 2026-10-16):
- the report gives the music's level and the finished video's level for every second;
- fails when the music does not reach the end, when it fades earlier than the allowed last N seconds, when the last
  spoken line is more than 1 dB under the median of the other lines, when there is silence at the end of the video,
  and when the music is not at full level from the first frame;
- with no fade length given the check reports the measured fade and does not judge it;
- the fade length can come from the storyboard;
- (issue 31) fails a video whose integrated loudness is more than 1 LU away from -16 LUFS, or whose true peak is
  above -1 dBTP. The synthetic videos are brought to -16 LUFS by plain gain before they are checked, so the other
  tests judge one fault at a time.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "shared" / "scripts" / "sound_check.py"

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

DURATION = 12.0
LINES = [(0.0, 2.8), (3.0, 5.8), (6.0, 8.8), (9.0, 11.9)]  # where each spoken line starts and ends, in seconds
VOICE_HZ, MUSIC_HZ = 300, 1000
# ffmpeg's sine source reads -21 dB on its own, so these gains give a voice at -15 dB and music at -23 dB
VOICE_DB, MUSIC_DB = 6.0, -2.0
VOICE_LEVEL, MUSIC_LEVEL = -15.0, -23.0
TARGET_LUFS = -16.0  # the owner, 2026-10-23 (issue 31): every finished video lands here, plus or minus 1 LU, peak at most -1 dBTP


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _music(path: Path, *, fade_from: float | None = None, length: float = DURATION, delay: float = 0.0,
           cut_at: float | None = None) -> Path:
    """The music file as the mixer is given it: a tone, optionally faded out from `fade_from` to its end,
    cut off at `cut_at`, or started after `delay` seconds of silence."""
    chain = [f"volume={MUSIC_DB}dB"]
    if delay:
        chain.append(f"adelay={int(delay * 1000)}|{int(delay * 1000)}")
    if fade_from is not None:
        chain.append(f"afade=t=out:st={fade_from}:d={length - fade_from}")
    if cut_at is not None:
        chain.append(f"atrim=end={cut_at}")
    _ffmpeg("-f", "lavfi", "-i", f"sine=frequency={MUSIC_HZ}:duration={length}", "-af", ",".join(chain), str(path))
    return path


def _voice_and_subtitle(tmp: Path, *, last_line_gain: float = 0.0, stop_at: float | None = None) -> tuple[Path, Path]:
    inputs, chains = [], []
    for i, (start, end) in enumerate(LINES):
        gain = VOICE_DB + (last_line_gain if i == len(LINES) - 1 else 0.0)
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={VOICE_HZ}:duration={end - start}"]
        chains.append(f"[{i}]volume={gain}dB,adelay={int(start * 1000)}|{int(start * 1000)}[v{i}]")
    mix = "".join(f"[v{i}]" for i in range(len(LINES))) + f"amix=inputs={len(LINES)}:normalize=0:duration=longest"
    voice = tmp / "voice.wav"
    _ffmpeg(*inputs, "-filter_complex", ";".join(chains + [mix]), str(voice))
    srt = tmp / "voice.srt"
    srt.write_text("".join(f"{i + 1}\n{_ts(s)} --> {_ts(e)}\nline {i + 1}\n\n" for i, (s, e) in enumerate(LINES)),
                   encoding="utf-8")
    return voice, srt


def _ts(seconds: float) -> str:
    whole, millis = divmod(round(seconds * 1000), 1000)
    return f"00:00:{whole:02d},{millis:03d}"


def _measure(path: Path) -> tuple[float, float]:
    """(integrated loudness in LUFS, true peak in dBTP) of `path`'s sound, from ffmpeg's own ebur128 meter."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    return (float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1]), float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)[-1]))


def build(tmp: Path, *, music: Path | None = None, last_line_gain: float = 0.0, audio_stops_at: float | None = None,
          lufs: float = TARGET_LUFS, peak_pulse: bool = False):
    """A finished video: black picture for DURATION seconds, with the voice and the music file mixed as its sound,
    brought to `lufs` (the target, unless a test wants a video that misses it). `peak_pulse` adds one 50 ms
    full-scale burst at 5 s: it barely moves the loudness and puts the true peak above -1 dBTP."""
    music = music or _music(tmp / "music.wav", fade_from=DURATION - 2)
    voice, srt = _voice_and_subtitle(tmp, last_line_gain=last_line_gain)
    mixed = tmp / "mixed.wav"
    stop = ["-t", str(audio_stops_at)] if audio_stops_at else []
    pulse = (["-f", "lavfi", "-i", "sine=frequency=2000:duration=0.05", "-filter_complex",
              "[2]volume=18dB,adelay=5000|5000[p];[0][1][p]amix=inputs=3:normalize=0:duration=longest"]
             if peak_pulse else ["-filter_complex", "amix=inputs=2:normalize=0:duration=longest"])
    _ffmpeg("-i", str(voice), "-i", str(music), *pulse, *stop, str(mixed))
    sound = tmp / "sound.wav"
    _ffmpeg("-i", str(mixed), "-af", f"volume={lufs - _measure(mixed)[0]}dB", str(sound))  # plain gain: tones, no limiting
    video = tmp / "final.mp4"
    _ffmpeg("-f", "lavfi", "-i", f"color=c=black:s=64x64:r=10:d={DURATION}", "-i", str(sound),
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video))
    return video, music, srt


def check(video: Path, music: Path, srt: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--video", str(video), "--music", str(music), "--subtitle", str(srt),
         *extra],
        cwd=ROOT, capture_output=True, text=True,
    )


def verdicts(result: subprocess.CompletedProcess) -> dict[str, str]:
    """{check name: PASS or FAIL} read from the lines the command prints."""
    return dict((m.group(2), m.group(1)) for m in re.finditer(r"^(PASS|FAIL|SKIP) (\w+):", result.stdout, re.M))


# --- the report ------------------------------------------------------------------------------

def test_a_good_mix_passes_and_reports_both_levels_for_every_second(tmp_path):
    video, music, srt = build(tmp_path)
    result = check(video, music, srt, "--fade-seconds", "2")
    assert result.returncode == 0, result.stdout + result.stderr
    rows = re.findall(r"^\s*(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*$", result.stdout, re.M)
    assert [int(r[0]) for r in rows] == list(range(int(DURATION)))
    # second 4 is all voice (-15 dB) over music (-23 dB): the two add up to about -14.4 dB
    second_four = next(r for r in rows if r[0] == "4")
    assert abs(float(second_four[1]) - MUSIC_LEVEL) <= 1.5  # the music column: the music file alone
    assert abs(float(second_four[2]) - -14.4) <= 1.5  # the video column


# --- the music reaches the end ---------------------------------------------------------------

def test_a_good_mix_passes_music_reaches_the_end(tmp_path):
    video, music, srt = build(tmp_path)
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["music_reaches_end"] == "PASS"


@pytest.mark.parametrize("cut_at", [11.4, 9.0])  # half a second short, three seconds short
def test_music_that_stops_before_the_end_fails(cut_at, tmp_path):
    video, music, srt = build(tmp_path, music=_music(tmp_path / "music.wav", cut_at=cut_at))
    result = check(video, music, srt, "--fade-seconds", "2")
    assert result.returncode == 1, result.stdout
    assert verdicts(result)["music_reaches_end"] == "FAIL", result.stdout


# --- the fade ----------------------------------------------------------------------------------

def test_a_good_mix_passes_music_fade(tmp_path):
    video, music, srt = build(tmp_path)  # the music fades over its last 2 seconds
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["music_fade"] == "PASS"


def test_music_that_fades_earlier_than_the_allowed_last_seconds_fails(tmp_path):
    early = _music(tmp_path / "music.wav", fade_from=7.0)  # a 5 s fade, 2 s allowed
    video, music, srt = build(tmp_path, music=early)
    result = check(video, music, srt, "--fade-seconds", "2")
    assert result.returncode == 1, result.stdout
    assert verdicts(result)["music_fade"] == "FAIL", result.stdout


def test_with_no_fade_length_given_the_measured_fade_is_reported_and_not_judged(tmp_path):
    early = _music(tmp_path / "music.wav", fade_from=7.0)
    video, music, srt = build(tmp_path, music=early)
    result = check(video, music, srt)
    assert verdicts(result)["music_fade"] == "SKIP", result.stdout
    fade_start = float(re.search(r"fade, if any, starts at ([\d.]+) s", result.stdout).group(1))
    assert 8.0 <= fade_start <= 10.0  # the music is 6 dB down about half way through the 5 s fade, at 9.5 s
    assert result.returncode == 0, result.stdout


# --- the music is at full level from the first frame --------------------------------------------

def test_a_good_mix_passes_music_start(tmp_path):
    video, music, srt = build(tmp_path)
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["music_start"] == "PASS"


def test_music_that_starts_after_a_second_of_silence_fails(tmp_path):
    video, music, srt = build(tmp_path, music=_music(tmp_path / "music.wav", fade_from=10.0, delay=1.0))
    result = check(video, music, srt, "--fade-seconds", "2")
    assert result.returncode == 1, result.stdout
    assert verdicts(result)["music_start"] == "FAIL", result.stdout


def test_music_that_fades_in_fails(tmp_path):
    faded_in = tmp_path / "music.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=1000:duration=12", "-af",
            f"volume={MUSIC_DB}dB,afade=t=in:d=3,afade=t=out:st=10:d=2", str(faded_in))
    video, music, srt = build(tmp_path, music=faded_in)
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["music_start"] == "FAIL"


# --- the last spoken line is as loud as the rest -------------------------------------------------

def test_a_good_mix_passes_last_line(tmp_path):
    video, music, srt = build(tmp_path)
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["last_line"] == "PASS"


def test_a_last_line_half_a_decibel_under_the_others_still_passes(tmp_path):
    video, music, srt = build(tmp_path, last_line_gain=-0.5)
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["last_line"] == "PASS"


def test_a_last_line_three_decibels_under_the_others_fails(tmp_path):
    video, music, srt = build(tmp_path, last_line_gain=-3.0)
    result = check(video, music, srt, "--fade-seconds", "2")
    assert result.returncode == 1, result.stdout
    assert verdicts(result)["last_line"] == "FAIL", result.stdout


# --- no silence at the end of the video ------------------------------------------------------------

def test_a_good_mix_passes_end_silence(tmp_path):
    video, music, srt = build(tmp_path)  # the last line ends 0.1 s before the video does and the music is fading to nothing
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["end_silence"] == "PASS"


@pytest.mark.parametrize("sound_stops_at", [11.6, 9.0])  # 0.4 s and 3 s of silence at the end of the video
def test_sound_that_stops_before_the_video_ends_fails(sound_stops_at, tmp_path):
    video, music, srt = build(tmp_path, audio_stops_at=sound_stops_at)
    result = check(video, music, srt, "--fade-seconds", "2")
    assert result.returncode == 1, result.stdout
    assert verdicts(result)["end_silence"] == "FAIL", result.stdout


# --- the finished loudness (issue 31) ---------------------------------------------------------------

def test_a_good_mix_passes_loudness(tmp_path):
    video, music, srt = build(tmp_path)  # -16 LUFS
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["loudness"] == "PASS"


@pytest.mark.parametrize("lufs", [-15.2, -16.8])  # inside the allowed 1 LU either side
def test_a_video_within_one_lu_of_the_target_passes_loudness(lufs, tmp_path):
    video, music, srt = build(tmp_path, lufs=lufs)
    assert verdicts(check(video, music, srt, "--fade-seconds", "2"))["loudness"] == "PASS"


@pytest.mark.parametrize("lufs", [-24.0, -17.5, -14.5])  # the approved video 01 was about -24; the others are 1.5 LU off
def test_a_video_more_than_one_lu_off_the_target_fails_loudness_and_the_exit_code_is_1(lufs, tmp_path):
    video, music, srt = build(tmp_path, lufs=lufs)
    result = check(video, music, srt, "--fade-seconds", "2")
    assert verdicts(result)["loudness"] == "FAIL", result.stdout
    assert result.returncode == 1, result.stdout


def test_a_true_peak_above_minus_1_dbtp_fails_loudness_even_at_the_right_loudness(tmp_path):
    video, music, srt = build(tmp_path, peak_pulse=True)
    measured_lufs, measured_peak = _measure(video)
    assert abs(measured_lufs - TARGET_LUFS) <= 1.0 and measured_peak > -1.0, (measured_lufs, measured_peak)  # the fixture
    result = check(video, music, srt, "--fade-seconds", "2")
    assert verdicts(result)["loudness"] == "FAIL", result.stdout
    assert result.returncode == 1, result.stdout


# --- the storyboard supplies what it holds ---------------------------------------------------------

def _storyboard(tmp: Path, music: Path, subtitle: Path, **fields) -> Path:
    path = tmp / "storyboard.json"
    path.write_text(json.dumps({"bgm": str(music), "subtitle": str(subtitle), **fields}), encoding="utf-8")
    return path


def test_the_fade_length_the_music_and_the_subtitle_come_from_the_storyboard(tmp_path):
    video, music, srt = build(tmp_path, music=_music(tmp_path / "music.wav", fade_from=7.0))
    storyboard = _storyboard(tmp_path, music, srt, bgm_fade_out=2.0)
    result = subprocess.run([sys.executable, str(SCRIPT), "check", "--video", str(video), "--storyboard",
                             str(storyboard)], cwd=ROOT, capture_output=True, text=True)
    assert verdicts(result)["music_fade"] == "FAIL", result.stdout  # 2 s allowed, read from the storyboard
    assert verdicts(result)["last_line"] == "PASS", result.stdout  # the line timings came from its subtitle


def test_a_fade_length_on_the_command_line_wins_over_the_storyboard(tmp_path):
    video, music, srt = build(tmp_path, music=_music(tmp_path / "music.wav", fade_from=7.0))
    storyboard = _storyboard(tmp_path, music, srt, bgm_fade_out=2.0)
    result = subprocess.run([sys.executable, str(SCRIPT), "check", "--video", str(video), "--storyboard",
                             str(storyboard), "--fade-seconds", "6"], cwd=ROOT, capture_output=True, text=True)
    assert verdicts(result)["music_fade"] == "PASS", result.stdout


def test_a_storyboard_with_no_fade_length_reports_the_fade_without_judging_it(tmp_path):
    video, music, srt = build(tmp_path)
    storyboard = _storyboard(tmp_path, music, srt)
    result = subprocess.run([sys.executable, str(SCRIPT), "check", "--video", str(video), "--storyboard",
                             str(storyboard)], cwd=ROOT, capture_output=True, text=True)
    assert verdicts(result)["music_fade"] == "SKIP", result.stdout


def test_an_ass_subtitle_file_gives_the_line_timings_too(tmp_path):
    video, music, srt = build(tmp_path, last_line_gain=-3.0)
    ass = tmp_path / "voice.ass"
    ass.write_text("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" +
                   "".join(f"Dialogue: 0,0:00:{s:05.2f},0:00:{e:05.2f},Default,,0,0,0,,line {i}\n"
                           for i, (s, e) in enumerate(LINES)), encoding="utf-8")
    assert verdicts(check(video, music, ass, "--fade-seconds", "2"))["last_line"] == "FAIL"


def test_no_music_file_skips_the_music_checks_and_still_checks_the_voice(tmp_path):
    video, _music_file, srt = build(tmp_path, last_line_gain=-3.0)
    result = subprocess.run([sys.executable, str(SCRIPT), "check", "--video", str(video), "--subtitle", str(srt)],
                            cwd=ROOT, capture_output=True, text=True)
    found = verdicts(result)
    assert {found[k] for k in ("music_reaches_end", "music_start", "music_fade")} == {"SKIP"}, result.stdout
    assert found["last_line"] == "FAIL" and result.returncode == 1, result.stdout


def test_a_good_mix_passes_every_check(tmp_path):
    video, music, srt = build(tmp_path)
    result = check(video, music, srt, "--fade-seconds", "2")
    assert result.returncode == 0, result.stdout
    assert verdicts(result) == dict.fromkeys(
        ["music_reaches_end", "music_start", "music_fade", "last_line", "end_silence", "loudness"], "PASS")


# --- video 01, measured by hand on 2026-10-16 (the thresholds were set from these files) ----------------

# the folder of the real files comes from this setting, so no client folder name is written here; unset means skipped
VIDEO01 = Path(os.environ.get("EASEL_SOUND_CHECK_VIDEO01_DIR", "/nonexistent-video01-folder"))
APPROVED_VIDEO = VIDEO01 / "final.mp4"
EXTENDED_MUSIC = VIDEO01 / "assets" / "bgm-elevenmusic-延长到30秒-尾2秒淡出.mp3"  # held to 28 s, fades in the last 2 s
RAW_MUSIC = VIDEO01 / "assets" / "bgm-elevenmusic.mp3"  # 1 s of silence first, its own fade from about 27 s
VOICE = VIDEO01 / "assets" / "voice.mp3"
VOICE_SUBTITLE = VIDEO01 / "assets" / "voice.srt"
MIXER_BEFORE_ISSUE_42 = ROOT / "archive" / "skill-backups" / "audio-mix" / "2026-10-16" / "audio_mix.py"
real_files = pytest.mark.skipif(
    not all(p.is_file() for p in (APPROVED_VIDEO, EXTENDED_MUSIC, RAW_MUSIC, VOICE, VOICE_SUBTITLE,
                                  MIXER_BEFORE_ISSUE_42)),
    reason="EASEL_SOUND_CHECK_VIDEO01_DIR is not set to the video 01 folder, or skill backups are kept only on the owner's PC")


@real_files
def test_the_approved_video_01_passes_every_check_except_loudness():
    # issue 31: the approved video was measured at -24.5 LUFS on 2026-10-23, about 8.5 LU under the owner's -16 target
    result = check(APPROVED_VIDEO, EXTENDED_MUSIC, VOICE_SUBTITLE, "--fade-seconds", "2")
    found = verdicts(result)
    assert found.pop("loudness") == "FAIL", result.stdout
    assert set(found.values()) == {"PASS"}, result.stdout
    assert result.returncode == 1, result.stdout


@real_files
def test_the_raw_eleven_music_file_fails_on_its_early_fade_and_its_silent_start():
    result = check(APPROVED_VIDEO, RAW_MUSIC, VOICE_SUBTITLE, "--fade-seconds", "2")
    found = verdicts(result)
    assert result.returncode == 1, result.stdout
    assert found["music_fade"] == "FAIL" and found["music_start"] == "FAIL", result.stdout


@real_files
def test_the_mixer_as_it_was_before_issue_42_fails_on_the_last_line_and_on_silence_at_the_end(tmp_path):
    # the voice and the extended music, mixed by the old script as video 01 was (0.175 music, 30 s asked for), under a
    # 30 s picture: the old mixer faded the last line and stopped the sound where the voice stopped
    sound = tmp_path / "old-mix.wav"
    subprocess.run([sys.executable, str(MIXER_BEFORE_ISSUE_42), "mix", "--voice", str(VOICE), "--bgm",
                    str(EXTENDED_MUSIC), "--bgm-volume", "0.175", "--duration", "30", "-o", str(sound)],
                   cwd=ROOT, check=True, capture_output=True, env={**os.environ, "PYTHONUTF8": "1"})  # file names are Chinese
    video = tmp_path / "old-mix.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=30", "-i", str(sound), "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video))
    result = check(video, EXTENDED_MUSIC, VOICE_SUBTITLE, "--fade-seconds", "2")
    found = verdicts(result)
    assert result.returncode == 1, result.stdout
    assert found["last_line"] == "FAIL" and found["end_silence"] == "FAIL", result.stdout
