"""Document check for issue 58: the note skill offers "photo-scene post" and hands it to xhs-reference-visual.

Run: python skills/builtin/xhs-note-creator/photo-scene.test.py   (exit 0 = pass). The fuller checks
(strategy table rows, the text-check and visual-check split, the metadata document) are in
tests/test_xhs_reference_visual_skill.py, which CI collects.
"""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
skill = (here / "SKILL.md").read_text(encoding="utf-8")
schema = (here / "references" / "meta-schema.md").read_text(encoding="utf-8")

required = {
    "intake offers photo-scene post": "photo-scene post" in skill,
    "strategy table sends it to the new skill": "../xhs-reference-visual/SKILL.md" in skill,
    "html_card still goes to card-xiaohongshu": "../card-xiaohongshu/SKILL.md" in skill,
    "metadata document lists photo_scene": "html_card | text_on_photo | collage | photo_scene" in schema,
}
missing = [why for why, ok in required.items() if not ok]
if missing:
    print("missing:", "; ".join(missing))
    sys.exit(1)
print("ok")
