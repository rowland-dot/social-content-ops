"""Document check: SKILL.md step 3 lays the voice-over onto the video once, not looped.

Run: python skills/builtin/tts-voiceover/step3-voiceover-once.test.py
The behaviour itself (audio plays once, music still loops) is covered by
tests/test_video_ops_bgm_once.py, which runs this same step 3 text through ffmpeg.
"""
from pathlib import Path
import sys

text = (Path(__file__).parent / "SKILL.md").read_text(encoding="utf-8")
lines = text.splitlines()
start = next(i for i, ln in enumerate(lines) if ln.startswith("# ③"))
end = next(i for i in range(start, len(lines)) if lines[i].startswith("```"))
block = "\n".join(lines[start:end])

problems = []
if "--music-loop-off" not in block:
    problems.append("step 3 command lacks --music-loop-off")
if "不循环" not in block:
    problems.append("step 3 comment does not say the voice-over is played once, not looped")

if problems:
    sys.exit("FAIL: " + "; ".join(problems))
print("ok")
