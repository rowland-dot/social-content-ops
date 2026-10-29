"""asr.py can be told how long it may spend transcribing, and says when it stopped early (issue 70).

faster-whisper hands its segments over one at a time as it decodes them, so stopping the loop stops the work and
keeps what was already recognised. The model is a stand-in: no model is loaded and no audio is decoded here.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest

ASR = Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts" / "asr.py"
spec = importlib.util.spec_from_file_location("asr_under_test", ASR)
asr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asr)


class Seg:
    def __init__(self, start, text):
        self.start, self.end, self.text = start, start + 2.0, text


def fake_faster_whisper(monkeypatch, texts):
    class WhisperModel:
        def __init__(self, ref, device=None, compute_type=None):
            pass

        def transcribe(self, audio, **kwargs):
            return (Seg(i * 2.0, t) for i, t in enumerate(texts)), types.SimpleNamespace(language="zh", duration=len(texts) * 2.0)

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)


def args(**over):
    base = dict(model="small", device="cpu", compute_type="int8", language="zh", beam_size=5, max_line_chars=18)
    return argparse.Namespace(**{**base, **over})


def clock_that_jumps(monkeypatch, seconds_per_look):
    now = [0.0]

    def monotonic():
        now[0] += seconds_per_look
        return now[0]

    monkeypatch.setattr(time, "monotonic", monotonic)


def test_it_stops_when_the_time_is_used_up_and_says_the_transcript_is_partial(monkeypatch):
    fake_faster_whisper(monkeypatch, ["第一句", "第二句", "第三句"])
    clock_that_jumps(monkeypatch, 400.0)
    cues, meta = asr._transcribe_audio(Path("x.wav"), args(max_seconds=600))
    assert [text for _, _, text in cues] == ["第一句"]
    assert meta["partial"] is True


def test_with_no_limit_it_reads_everything_and_is_not_partial(monkeypatch):
    fake_faster_whisper(monkeypatch, ["第一句", "第二句", "第三句"])
    clock_that_jumps(monkeypatch, 400.0)
    cues, meta = asr._transcribe_audio(Path("x.wav"), args(max_seconds=0))
    assert len(cues) == 3
    assert meta["partial"] is False


def test_a_limit_that_is_not_reached_leaves_the_transcript_whole(monkeypatch):
    fake_faster_whisper(monkeypatch, ["第一句", "第二句"])
    clock_that_jumps(monkeypatch, 1.0)
    cues, meta = asr._transcribe_audio(Path("x.wav"), args(max_seconds=600))
    assert len(cues) == 2 and meta["partial"] is False


def test_the_json_output_carries_the_partial_flag(monkeypatch):
    fake_faster_whisper(monkeypatch, ["第一句", "第二句", "第三句"])
    clock_that_jumps(monkeypatch, 400.0)
    cues, meta = asr._transcribe_audio(Path("x.wav"), args(max_seconds=600))
    assert '"partial": true' in asr._render_json(cues, meta)


def test_the_command_line_offers_the_limit():
    parsed = asr.build_parser().parse_args(["transcribe", "-i", "a.mp4", "--max-seconds", "600"])
    assert parsed.max_seconds == 600
    assert asr.build_parser().parse_args(["transcribe", "-i", "a.mp4"]).max_seconds == 0
