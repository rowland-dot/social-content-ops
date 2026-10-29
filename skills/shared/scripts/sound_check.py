#!/usr/bin/env python3
"""sound_check.py — automatic sound check on a finished video, run before it is shown to anyone (issue 49).

A finished video carries one mixed sound track; the music is not a separate track inside it. So the check takes
three inputs: the finished video, the music file as it was fed to the mixer, and the subtitle file the assembler
burned (the line timings). It prints the music's level and the video's level for every second, then judges:

    music_reaches_end  the music keeps sounding to the end of the video
    music_start        the music is at full level from the first frame (no fade-in, no silent start)
    music_fade         the music starts fading no earlier than the last N seconds (N is passed in)
    last_line          the last spoken line is not quieter than the median of the other lines by more than 1 dB
    end_silence        the end of the video is not silent
    loudness           the whole video is -16 LUFS integrated (within 1 LU) with a true peak of at most -1 dBTP

Exit code 0 when every judged check passes, 1 when one fails, 2 for bad input.

Usage:
    sound_check.py check --video final.mp4 --music bgm.mp3 --subtitle voice.srt --fade-seconds 2
    sound_check.py check --video final.mp4 --storyboard outputs/<topic>/assets/storyboard.json

Needs ffmpeg and ffprobe.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

WINDOW = 0.1  # seconds per level reading; everything else is averaged from these
FLOOR_DB = -120.0  # what digital silence reads as
SILENCE_DB = -70.0  # quieter than this is no sound at all; the approved video 01 fades to -62 dB and must pass
FADE_DROP_DB = 6.0  # a fade has started once the music is this far under its own median, and stays there
START_SPAN = 0.5  # the music must be at full level over this many first seconds
LAST_LINE_MARGIN_DB = 1.0  # the last line may be this far under the median of the other lines
SILENT_END = 0.25  # this much silence at the very end of the video is a fault
END_TOLERANCE = 0.25  # the music may stop this long before the end (a fade to nothing ends inside it)
TARGET_LUFS = -16.0  # the owner, 2026-10-23: finished videos land at -16 LUFS integrated ...
LOUDNESS_TOLERANCE_LU = 1.0  # ... plus or minus this much ...
MAX_TRUE_PEAK_DBTP = -1.0  # ... with a true peak no higher than this


def _die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1",
                          str(path)], capture_output=True, text=True).stdout
    try:
        return float(out.strip())
    except ValueError:
        _die(f"cannot read the length of {path}")


def levels(path: Path, length: float) -> list[float]:
    """Mean level (dB) of each WINDOW of `path`'s sound, up to `length` seconds."""
    samples = int(44100 * WINDOW)
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn", "-af",
         f"aresample=44100,asetnsamples=n={samples}:p=0,astats=metadata=1:reset=1,"
         "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"],
        capture_output=True, text=True)
    out = [FLOOR_DB if v == "-inf" else max(float(v), FLOOR_DB)
           for v in re.findall(r"RMS_level=(\S+)", proc.stdout)]
    return out[: math.ceil(length / WINDOW - 1e-9)]


def mean_db(values: list[float]) -> float:
    """Average level of several readings, by power (not by dB)."""
    if not values:
        return FLOOR_DB
    return max(10 * math.log10(sum(10 ** (v / 10) for v in values) / len(values)), FLOOR_DB)


def per_second(readings: list[float], seconds: int) -> list[float]:
    step = round(1 / WINDOW)
    return [mean_db(readings[i * step:(i + 1) * step]) for i in range(seconds)]


def verdict(ok: bool, note: str) -> tuple[str, str]:
    return ("PASS" if ok else "FAIL"), note


def music_reaches_end(music_levels: list[float], length: float) -> tuple[str, str]:
    """The music is counted by where it actually sounds, not by the length of its file: a file can carry
    seconds of silence at either end."""
    sounding = [i for i, v in enumerate(music_levels) if v > SILENCE_DB]
    ends = (sounding[-1] + 1) * WINDOW if sounding else 0.0
    ok = ends >= length - END_TOLERANCE - 1e-9
    return verdict(ok, f"the music sounds until {ends:.2f} s of a {length:.2f} s video")


def fade_start(music_levels: list[float], seconds: int) -> float | None:
    """The first moment from which the music stays more than FADE_DROP_DB under its own median level until the
    end, or None when it never does. It is the moment the music is clearly down, so a fade that began a little
    earlier but was still gentle at that point is not caught (ponytail: finer rules need more than one video's
    measurements to calibrate)."""
    median = sorted(per_second(music_levels, seconds))[seconds // 2]
    start = len(music_levels)
    while start > 0 and music_levels[start - 1] < median - FADE_DROP_DB:
        start -= 1
    return None if start == len(music_levels) else start * WINDOW


def music_fade(music_levels: list[float], seconds: int, length: float, allowed: float | None) -> tuple[str, str]:
    start = fade_start(music_levels, seconds)
    where = "the music never fades" if start is None else f"the music's fade, if any, starts at {start:.2f} s"
    if allowed is None:
        return "SKIP", f"{where} (no fade length given, so not judged)"
    ok = start is None or start >= length - allowed - 1e-9
    return verdict(ok, f"{where}; allowed only in the last {allowed:g} s, from {length - allowed:.2f} s")


def music_start(music_levels: list[float], seconds: int) -> tuple[str, str]:
    """The owner's rule: full level from the first frame, no fade-in. 'Full' is within FADE_DROP_DB of the music's median."""
    median = sorted(per_second(music_levels, seconds))[seconds // 2]
    opening = mean_db(music_levels[: round(START_SPAN / WINDOW)])
    return verdict(opening >= median - FADE_DROP_DB,
                   f"the first {START_SPAN:g} s of music is {opening:.1f} dB, its median is {median:.1f} dB")


def line_spans(path: Path) -> list[tuple[float, float]]:
    """Where each subtitle line starts and ends, in seconds, from an .srt or an .ass file."""
    stamp = re.compile(r"(\d+):(\d\d):(\d\d)[.,](\d+)")
    spans = []
    for row in path.read_text(encoding="utf-8-sig").splitlines():
        if "-->" in row or row.startswith("Dialogue:"):
            times = [int(h) * 3600 + int(m) * 60 + int(sec) + float("0." + frac)
                     for h, m, sec, frac in stamp.findall(row)[:2]]
            if len(times) == 2:
                spans.append((times[0], times[1]))
    return sorted(spans)


def last_line(video_levels: list[float], spans: list[tuple[float, float]]) -> tuple[str, str]:
    """The last line against the median of the other lines, each measured over its own subtitle span. (Against the
    loudest line the approved video 01 would fail: its lines differ by 2.7 dB among themselves.)"""
    if len(spans) < 2:
        return "SKIP", "fewer than two subtitle lines, nothing to compare"
    line_db = [mean_db(video_levels[round(s / WINDOW):max(round(s / WINDOW) + 1, round(e / WINDOW))])
               for s, e in spans]
    others = statistics.median(line_db[:-1])
    return verdict(line_db[-1] >= others - LAST_LINE_MARGIN_DB,
                   f"the last line is {line_db[-1]:.1f} dB, the median of the {len(line_db) - 1} other lines is "
                   f"{others:.1f} dB (allowed {LAST_LINE_MARGIN_DB:g} dB under)")


def end_silence(video_levels: list[float], length: float) -> tuple[str, str]:
    """Silence is below SILENCE_DB. Sound that stops before the video does counts, because the missing sound is silence."""
    loud = [i for i, v in enumerate(video_levels) if v > SILENCE_DB]
    heard_until = min((loud[-1] + 1) * WINDOW, length) if loud else 0.0
    silent = length - heard_until
    return verdict(silent < SILENT_END - 1e-9,
                   f"the video has sound until {heard_until:.2f} s of {length:.2f} s ({silent:.2f} s of silence at the end)")


def loudness(video: Path) -> tuple[str, str]:
    """The whole finished sound against the owner's target (2026-10-23, issue 31): integrated loudness within
    LOUDNESS_TOLERANCE_LU of TARGET_LUFS and true peak no higher than MAX_TRUE_PEAK_DBTP, as ffmpeg's ebur128 meter
    reads them on the finished file."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    integrated = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    if not integrated or not peak:
        return "FAIL", "the loudness of the video could not be measured (no sound track?)"
    lufs, tp = float(integrated[-1]), float(peak[-1])
    ok = abs(lufs - TARGET_LUFS) <= LOUDNESS_TOLERANCE_LU + 1e-9 and tp <= MAX_TRUE_PEAK_DBTP + 1e-9
    return verdict(ok, f"the video is {lufs:.1f} LUFS with a true peak of {tp:.1f} dBTP; allowed "
                       f"{TARGET_LUFS:g} LUFS plus or minus {LOUDNESS_TOLERANCE_LU:g} and a peak of at most "
                       f"{MAX_TRUE_PEAK_DBTP:g} dBTP")


def existing(path: str, what: str) -> Path:
    if not Path(path).is_file():
        _die(f"{what} not found: {path}")
    return Path(path)


def cmd_check(a) -> int:
    board = json.loads(existing(a.storyboard, "storyboard").read_text(encoding="utf-8")) if a.storyboard else {}
    music_path = a.music or board.get("bgm")
    subtitle_path = a.subtitle or board.get("subtitle")
    allowed = a.fade_seconds if a.fade_seconds is not None else board.get("bgm_fade_out")
    video = existing(a.video, "video")
    length = duration(video)
    seconds = math.ceil(length - 1e-9)
    video_levels = levels(video, length)
    music_levels = levels(existing(music_path, "music file"), length) if music_path else None
    music_column = per_second(music_levels, seconds) if music_levels else [None] * seconds
    print(f"{'second':>6} {'music':>8} {'video':>8}   (dB, mean level over each second)")
    for s, (m, v) in enumerate(zip(music_column, per_second(video_levels, seconds))):
        print(f"{s:>6} {'-' if m is None else format(m, '.1f'):>8} {v:>8.1f}")
    no_music = ("SKIP", "no music file given")
    results = [
        ("music_reaches_end", *(music_reaches_end(music_levels, length) if music_levels else no_music)),
        ("music_start", *(music_start(music_levels, seconds) if music_levels else no_music)),
        ("music_fade", *(music_fade(music_levels, seconds, length, allowed) if music_levels else no_music)),
        ("last_line", *(last_line(video_levels, line_spans(existing(subtitle_path, "subtitle file")))
                        if subtitle_path else ("SKIP", "no subtitle file given, so the line timings are unknown"))),
        ("end_silence", *end_silence(video_levels, length)),
        ("loudness", *loudness(video)),
    ]
    for name, status, note in results:
        print(f"{status} {name}: {note}")
    return 1 if any(status == "FAIL" for _, status, _ in results) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Automatic sound check on a finished video")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("check", help="check one finished video")
    p.add_argument("--video", required=True, help="the finished video (or any file with the finished sound)")
    p.add_argument("--music", help="the music file as it was fed to the mixer")
    p.add_argument("--subtitle", help="the subtitle file (.srt or .ass) the assembler burned")
    p.add_argument("--fade-seconds", type=float, help="how many last seconds the music may fade over")
    p.add_argument("--storyboard", help="the storyboard: supplies the music (bgm), the subtitle and the fade length "
                   "(bgm_fade_out) that the flags above leave out")
    p.set_defaults(func=cmd_check)
    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
