import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import re
from easel import persona

GUARD = Path(__file__).resolve()
# constraint 4: nothing from a Lovart file enters the repository; plus real shop addresses and item ids
ADDRESS_PATTERNS = [re.compile(p, re.I) for p in (r"lovart", r"(?:img|gw|gtd)\.alicdn\.com",
                                                  r"item\.htm\?id=\d{9,}", r"[?&]id=\d{9,}")]


def brand_patterns(settings=None):
    """One pattern per brand name this machine maps in EASEL_PROFILE_DIRS (git-ignored), so no brand name is written here."""
    return [re.compile(re.escape(name), re.I) for name in persona.external_profile_dirs(settings)]


def hits(files, patterns):
    return [(p.name, pat.pattern) for p in files
            for pat in patterns if pat.search(p.read_text(encoding="utf-8", errors="ignore"))]


def _files():
    for base in (SCRIPTS.parent, ):
        yield from (p for p in base.rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".json", ".html"})
    yield from SHARED.glob("tmall_*.py")
    yield from (p for p in (ROOT / "tests").glob("test_tmall_*.py") if p != GUARD)


def test_no_client_name_real_cdn_address_or_real_item_id_is_committed():
    assert hits(list(_files()), ADDRESS_PATTERNS + brand_patterns()) == []


def test_a_mapped_brand_name_planted_in_a_tmall_file_is_caught(tmp_path):
    planted = tmp_path / "page.md"
    planted.write_text("This page was made for Northwind Foods.", encoding="utf-8")
    patterns = brand_patterns({"EASEL_PROFILE_DIRS": "northwind=/somewhere/profile"})
    assert hits([planted], patterns) == [("page.md", "northwind")]
    assert hits([planted], brand_patterns({"EASEL_PROFILE_DIRS": ""})) == []
