"""Text check for tmall-product-content's SKILL.md and its worked example.

Run: python skills/builtin/tmall-product-content/skill-text.test.py   (exit 0 = pass). The same checks, plus the
skill validator and the web skill list, are in tests/test_tmall_skill.py, which CI collects; this copy sits beside
the skill because the edit guard for skill folders wants a check file here.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
failures = []

skill = HERE / "SKILL.md"
if not skill.is_file():
    failures.append("SKILL.md does not exist")
    text = ""
else:
    text = skill.read_text(encoding="utf-8")
    if not re.search(r"(?m)^name: tmall-product-content\s*$", text):
        failures.append("the header has no 'name: tmall-product-content'")
    if not re.search(r"(?m)^layer: produce\s*$", text):
        failures.append("the header has no 'layer: produce'")
    if len(text.splitlines()) > 200:
        failures.append("SKILL.md is over 200 lines")
    desc = re.search(r"(?m)^description:\s*(.+)$", text)
    d = desc.group(1) if desc else ""
    if not ("天猫" in d and "主图" in d and "商详页" in d and "ecom-details-image" in d):
        failures.append("the description does not lead with 天猫 / 主图 / 商详页 and name ecom-details-image")
    elif d.index("天猫") > d.index("ecom-details-image"):
        failures.append("the description names ecom-details-image before 天猫")

    for s in re.findall(r"`(scripts/tmall_[a-z_]+\.py)`", text):
        if not (HERE / s).is_file():
            failures.append(f"the page names {s}, which does not exist")
    for n in range(1, 9):
        if f"references/stage-{n}-" not in text:
            failures.append(f"the page does not point at the stage {n} file")
        if not list((HERE / "references").glob(f"stage-{n}-*.md")):
            failures.append(f"references/stage-{n}-*.md does not exist")
    if "python3 " in text:
        failures.append("the page says python3; other builtin skills say python (the browser steps need the venv's Python)")
    for name in ("NEXT_STEP", "HeldError", "PaidRouteRefused", "PackNeedsCutout", "FontNotLicensed"):
        if name not in text:
            failures.append(f"the error table does not name {name}")
    for needle in ("HELD", "references/held.json", "issue 94", "issue 95", "never"):
        if needle not in text and needle not in text.lower():
            failures.append(f"the page does not say: {needle}")
    for needle in ("包装上印的字不检查", "不付费", "知识库", "先看三个封面", "只通过 Easel 改"):
        if needle not in text:
            failures.append(f"the page does not state the rule: {needle}")
    # the owner's ruling of 2026-10-28: the text-card layout check is not a Tmall check
    if "card_audit" in text or "不用于天猫" not in text:
        failures.append("the page must say the card layout check is not used for Tmall, and must not list it as a check")

example = HERE / "references" / "stage-5-images.md"
if not example.is_file():
    failures.append("references/stage-5-images.md does not exist")
else:
    e = example.read_text(encoding="utf-8")
    for needle in ("gather(", "load_state", "save_state", "tmall_page.py report"):
        if needle not in e:
            failures.append(f"the worked example does not contain {needle}")
    if e.count("style_lock_version") < 2:
        failures.append("the worked example must pass style_lock_version to compose and to gather's style lock")
    if "headline/A/M1.png" not in text + e or "promote_pick" not in text + e:
        failures.append("the headline version folders and promote_pick are not explained")

# Issue 09 (the owner, 2026-10-29): the Tmall platform standards are read first, but only as a fallback; a competitor case wins.
for label, page in (("SKILL.md", skill), ("the stage 2 notes", HERE / "references" / "stage-2-competitor-read.md"),
                    ("the stage 3 notes", HERE / "references" / "stage-3-page-design.md"),
                    ("the Tmall rules file introduction", HERE / "references" / "tmall-rules.md")):
    body = page.read_text(encoding="utf-8") if page.is_file() else ""
    if label.startswith("the Tmall rules"):
        body = body.split("\n## ", 1)[0]
    if not ("fallback" in body.lower() or "后备" in body) or not ("case always wins" in body or "案例永远优先" in body):
        failures.append(f"{label} does not state the precedence rule (the reading is a fallback only; the case always wins)")

pin = re.compile(r"800\s*(?:[×xX*]|by)\s*800|\(800,\s*800\)|\[800,\s*800\]|800x800")
for path in sorted(HERE.rglob("*")):
    if path.is_file() and path.suffix in {".md", ".py", ".json"} and path.name not in {"tmall-rules.md", "skill-text.test.py"}:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pin.search(line):
                failures.append(f"{path.relative_to(HERE).as_posix()}:{n} still pins main images to one fixed size (the sizes live in references/tmall-rules.md)")

meta = HERE / "EASEL-META.md"
if not meta.is_file() or "tmall-product-content" not in meta.read_text(encoding="utf-8"):
    failures.append("EASEL-META.md is missing or does not name the skill")

for line in failures:
    print("FAIL", line)
print("PASS" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
