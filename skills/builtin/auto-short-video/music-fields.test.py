"""Check that SKILL.md tells an agent about the assembler's music behaviour (issue 45).

The assembler now lowers the music under the voice by itself, does not loop music that is shorter than
the video unless the storyboard says `bgm_loop`, and fades the music only when the storyboard gives
`bgm_fade_out`. An agent that reads only SKILL.md has to learn all of that here, including that it
must not pre-mix the music into the voice track any more. Run: python music-fields.test.py
"""
import sys
from pathlib import Path

SKILL_MD = Path(__file__).resolve().parent / "SKILL.md"

MUST_SAY = {
    "names the loop field": '"bgm_loop"',
    "names the fade field": '"bgm_fade_out"',
    "says looping is off by default": "默认不循环",
    "says the music comes back up once the voice stops": "说完恢复",
    "says not to pre-mix the music into the voice": "不要另外先混好",
}


def main() -> int:
    text = SKILL_MD.read_text(encoding="utf-8")
    problems = [f"SKILL.md never {what} (looking for {needle})" for what, needle in MUST_SAY.items()
                if needle not in text]
    for p in problems:
        print("FAIL:", p)
    if not problems:
        print("ok: SKILL.md describes the music fields and defaults")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
