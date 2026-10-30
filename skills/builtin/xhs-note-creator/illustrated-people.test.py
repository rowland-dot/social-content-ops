"""Issue 139: people on illustrated cards are drawn as stylised illustration, never semi-photoreal.

Run: python skills/builtin/xhs-note-creator/illustrated-people.test.py   (exit 0 = pass).
Reads SKILL.md and references/illustrated-people.md. No live request.
"""
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
skill = (here / "SKILL.md").read_text(encoding="utf-8")
ref_path = here / "references" / "illustrated-people.md"
ref = ref_path.read_text(encoding="utf-8") if ref_path.is_file() else ""

REF_NEEDS = [
    "issue 139", "风格化的插画", "扁平", "线稿", "五官简化", "从不画成半写实", "插画就是插画",
    "成熟、精细刻画", "【二级】", "并排", "照片场景帖", "不受本页影响", "不读、不列、不报商品包装上印的字",
]
SKILL_NEEDS = ["illustrated-people.md", "issue 139", "从不半写实", "照片场景帖不受它影响"]
# Rules only, no brand or person names, no quoted rulings (project rule for tracked skill text).
BANNED = ["Ro ", "Ro,", "CollagenX", "卢思琳", "@easel"]

fails = []
if not ref:
    fails.append("references/illustrated-people.md does not exist")
for need in REF_NEEDS:
    if ref and need not in ref:
        fails.append(f"the reference does not say: {need}")
for need in SKILL_NEEDS:
    if need not in skill:
        fails.append(f"SKILL.md does not say: {need}")
for text, name in ((ref, "the reference"), (skill, "SKILL.md")):
    for bad in BANNED:
        if bad in text:
            fails.append(f"{name} contains a name or quote it must not: {bad}")
# Scope: the reference must keep photo-scene people out of it.
if ref and not re.search(r"照片场景帖.*不受本页影响", ref):
    fails.append("the reference does not exempt photo-scene posts")

if fails:
    print("\n".join("FAIL " + f for f in fails))
    sys.exit(1)
print("PASS illustrated-people")
