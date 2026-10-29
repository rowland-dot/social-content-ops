"""Check: every free-voice `cast add` example in SKILL.md names the free engine.

`cast add` defaults to the cloud engine, so a free-voice example (`--voice <edge name>`)
without `--engine edge` stores a broken entry (engine=clone, no voice id) and the
`cast check` right after it fails. Run: python free-voice-examples.test.py
"""
import re
import sys
from pathlib import Path

text = (Path(__file__).parent / "SKILL.md").read_text(encoding="utf-8")
# join backslash-continued shell lines, drop the "> " quote prefix, then find cast add commands
flat = re.sub(r"\\\s*\n\s*(?:>\s*)?", " ", text)
adds = [m.group(0) for m in re.finditer(r"multivoice\.py cast add[^\n]*", flat)]

free = [c for c in adds if re.search(r"--voice\s", c)]
cloud = [c for c in adds if "--voice-id" in c]
problems = []
if len(free) < 2:
    problems.append(f"expected the two free-voice examples (林策, 苏晚), found {len(free)}")
for c in free:
    if not re.search(r"--engine\s+edge\b", c):
        name = re.search(r"--name\s+(\S+)", c)
        problems.append(f"free-voice example without --engine edge: {name.group(1) if name else c}")
if len(cloud) != 1 or "--engine clone" not in cloud[0]:
    problems.append("the cloud-voice example must stay as it is (--engine clone ... --voice-id)")

if problems:
    print("FAIL")
    print("\n".join(problems))
    sys.exit(1)
print(f"PASS: {len(free)} free-voice examples name --engine edge; cloud example intact")
