"""Issue 09: the Tmall platform standards are read first, and a competitor case that shows what sells always wins over that reading.

The owner, 2026-10-29, on the recheck of the Tmall plan choices (docs/reports/briefs/2026-10-29-tmall-product-content-recheck.md, choice 31)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "builtin" / "tmall-product-content"
SPEC = ROOT / "docs" / "specs" / "2026-10-25-tmall-product-content-spec.md"
BRIEF = ROOT / "docs" / "reports" / "briefs" / "2026-10-29-tmall-product-content-brief.md"

def read(p): return Path(p).read_text(encoding="utf-8")

def test_the_precedence_rule_is_in_every_page_the_following_work_sessions_read():
    pages = {"skill page": SKILL / "SKILL.md", "stage 2 notes (competitor read)": SKILL / "references" / "stage-2-competitor-read.md",
             "stage 3 notes (page plan)": SKILL / "references" / "stage-3-page-design.md",
             "Tmall rules file introduction": SKILL / "references" / "tmall-rules.md"}
    for name, page in pages.items():
        text = read(page)
        if page.name == "tmall-rules.md":
            text = text.split("\n## ", 1)[0]                                                   # the introduction: everything before the first section
        assert "fallback" in text.lower() or "后备" in text, f"{name}: does not say the reading is a fallback"
        assert "case always wins" in text or "案例永远优先" in text, f"{name}: does not say the case wins"

NO_FIXED_800 = re.compile(r"800\s*(?:[×xX*]|by)\s*800|\(800,\s*800\)|\[800,\s*800\]|800x800")



