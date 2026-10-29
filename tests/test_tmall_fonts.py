import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

from pathlib import Path
import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
import tmall_fonts as fonts

def _font(path, licence):
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef"]); fb.setupCharacterMap({})
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph()}); fb.setupHorizontalMetrics({".notdef": (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    names = {"familyName": "TestFont", "styleName": "Regular"}
    if licence: names["licenseDescription"] = licence
    fb.setupNameTable(names); fb.setupOS2(); fb.setupPost(); fb.save(path)

def test_licence_text_is_read_from_the_font(tmp_path):
    _font(tmp_path / "a.ttf", "This font is licensed under the SIL Open Font License, Version 1.1.")
    assert "SIL Open Font License" in fonts.licence_text(tmp_path / "a.ttf", "TestFont")

def test_a_font_with_no_licence_text_is_not_licensed(tmp_path):
    _font(tmp_path / "b.ttf", None)
    assert fonts.is_commercially_licensed(tmp_path / "b.ttf", "TestFont") is False

def test_ofl_font_passes_and_an_unlisted_family_is_refused(tmp_path):
    _font(tmp_path / "a.ttf", "SIL Open Font License, Version 1.1")
    assert fonts.is_commercially_licensed(tmp_path / "a.ttf", "TestFont") is True
    with pytest.raises(fonts.FontNotLicensed, match="NotListed"):
        fonts.assert_allowed("NotListed")

def test_a_listed_font_whose_file_is_missing_is_refused(tmp_path):
    listed = [{"family": "TestFont", "file": str(tmp_path / "gone.ttf"), "licence": "SIL Open Font License"}]
    with pytest.raises(fonts.FontNotLicensed, match="gone.ttf"):
        fonts.assert_allowed("TestFont", listed)

def test_a_listed_bold_file_that_is_missing_is_refused_too(tmp_path):        # reviewed-plan audit pass 1: a mutant that skipped "also" survived
    _font(tmp_path / "a.ttf", "SIL Open Font License, Version 1.1")
    listed = [{"family": "TestFont", "file": str(tmp_path / "a.ttf"), "also": [str(tmp_path / "gone-bold.ttf")], "licence": "SIL Open Font License"}]
    with pytest.raises(fonts.FontNotLicensed, match="gone-bold.ttf"):
        fonts.assert_allowed("TestFont", listed)

def test_the_shipped_list_names_a_family_whose_file_really_carries_the_licence():
    listed = fonts.load_list()
    entry = next(e for e in listed if e["family"] == "Noto Sans CJK SC")
    if not Path(entry["file"]).exists():
        pytest.skip("font file not on this machine")
    assert fonts.is_commercially_licensed(entry["file"], entry["family"])
    fonts.assert_allowed("Noto Sans CJK SC")
