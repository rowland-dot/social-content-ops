import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import json, pytest, re
import tmall_rules as rules

def test_the_shipped_file_loads_and_every_rule_has_a_source_and_status():
    r = rules.load()
    for path, rule in rules.walk(r):
        assert rule["status"] in {"confirmed", "unconfirmed", "from-spec", "proposal"}, path
        assert rule["source"], path

READ_BY_THE_CHECKS = ["main_image.sizes", "main_image.max_kb", "detail.width", "detail.max_kb", "layers.contrast_min", "text.min_px_main",
                      "text.min_px_detail", "thumbnail.px", "thumbnail.min_headline_px", "diagnosis.product_height_min",
                      "diagnosis.glare_max_share", "rounds.max", "words.banned", "words.after_state", "bonded.must_not"]

def test_the_shipped_file_carries_every_rule_the_checks_read():           # the stage 6 tests use stand-in rules; a gap here would crash the first real run
    r = rules.load()
    for path in READ_BY_THE_CHECKS:
        rules.value(r, path)

def test_values_the_spec_fixes_are_present():
    r = rules.load()
    assert rules.value(r, "detail.width") == 790
    assert [800, 800] in rules.value(r, "main_image.sizes")
    assert rules.value(r, "layers.contrast_min") == 4.5
    assert rules.value(r, "diagnosis.product_height_min") == 0.6
    assert rules.value(r, "rounds.max") == 3

# ---- issue 09: the platform's published standards are read first (The owner, 2026-10-29: "the reading will be served as a fallback ONLY") ----

READ_ON = "2026-10-29"
# The 12 rules the recheck brief (decision 4) counted as not confirmed, by the plain name that brief uses.
TWELVE = {"main-image file weight": "main_image.max_kb", "formats": "main_image.formats",
          "white background": "main_image.white_background", "3:4 ratio": "main_image.ratio_3x4",
          "text share": "main_image.text_share_max", "detail file weight": "detail.max_kb",
          "thumbnail headline size": "thumbnail.min_headline_px", "glare share": "diagnosis.glare_max_share",
          "round limit": "rounds.max", "banned words": "words.banned", "after-state words": "words.after_state",
          "bonded-warehouse wording": "bonded.must_not"}

def _rule(r, path):
    node = r
    for part in path.split("."):
        node = node[part]
    return node

def test_main_image_sizes_are_every_size_the_published_guides_allow():
    r = rules.load()
    sizes = _rule(r, "main_image.sizes")
    assert sizes["status"] == "confirmed" and READ_ON in sizes["source"] and "https://" in sizes["source"]
    assert sizes["value"] == [[800, 800], [1440, 1440]]            # 800 x 800: ordinary food and dietary supplements; 1440 x 1440: health food and tonic pages
    by_category = _rule(r, "main_image.min_by_category")["value"]
    assert [800, 800] in by_category.values() and [1440, 1440] in by_category.values()
    assert [800, 1200] in by_category.values()                      # the clothing guide's vertical image: published, but not a size a food product uses

def test_every_rule_has_a_source_address_and_the_date_it_was_read():
    r = rules.load()
    for path, rule in rules.walk(r):
        assert re.search(r"\d{4}-\d{2}-\d{2}", rule["source"]), f"{path}: no read date in the source"
        assert re.search(r"https?://|\.(md|py)\b", rule["source"]), f"{path}: no address in the source"
        if rule["status"] == "confirmed":                            # never confirmed without a page that was actually read
            assert "https://" in rule["source"] and f"read {READ_ON}" in rule["source"], f"{path}: confirmed without a page and its read date"

def test_each_of_the_twelve_rules_is_settled_or_says_why_it_is_not():
    r = rules.load()
    for name, path in TWELVE.items():
        rule = _rule(r, path)
        if rule["status"] != "confirmed":
            assert "not confirmed because" in rule["source"], f"{name} ({path}) is neither settled nor given a reason"
    assert _rule(r, "main_image.white_background")["status"] == "confirmed"       # settled from the dietary-supplement and general food pages
    assert _rule(r, "words.banned")["status"] == "confirmed" and _rule(r, "bonded.must_not")["status"] == "confirmed"
    assert _rule(r, "main_image.ratio_3x4")["status"] == "unconfirmed"            # no page read allows or requires 3:4 for food or supplements

def test_words_the_platform_pages_name_are_checked_and_the_old_leads_still_are():
    r = rules.load()
    assert rules.banned_hits("极品燕麦", r) == ["极品"]                              # named on the platform's wrong-description reading, not in the old list
    assert "销量第一" in rules.banned_hits("全网销量第一", r)
    assert "最好" in rules.banned_hits("最好的燕麦", r)                              # an old lead no page names: still stops images, still reported as not confirmed
    assert rules.bonded_hits("海关监管 报关单", r) == ["海关监管", "报关单"]
    assert "国内现货" in rules.bonded_hits("国内现货秒发", r) and "全球同售" in rules.bonded_hits("全球同售", r)
    assert rules.after_state_hits("肌肤焕发光泽", r) == ["焕发光泽"]

def test_what_is_still_not_confirmed_is_reported_and_what_was_settled_is_not():
    nc = rules.not_confirmed(rules.load())
    for path in ("main_image.max_kb", "main_image.formats", "main_image.ratio_3x4", "main_image.text_share_max", "detail.max_kb",
                 "thumbnail.min_headline_px", "diagnosis.glare_max_share", "rounds.max", "words.after_state",
                 "words.banned_unlisted", "bonded.must_not_unlisted"):
        assert path in nc, path
    for path in ("main_image.sizes", "main_image.white_background", "words.banned", "bonded.must_not"):
        assert path not in nc, path

def test_text_minimums_are_worked_out_for_each_allowed_main_width():
    r = rules.load()
    minimum = _rule(r, "text.min_px_main")["value"]
    assert minimum == {"800": 21, "1440": 38}                       # 28 px body on a 1080 card, scaled to the width and rounded up
    assert rules.for_width(r, "text.min_px_main", 800) == 21 and rules.for_width(r, "text.min_px_main", 1440) == 38
    assert rules.for_width(r, "text.min_px_main", 1000) == 38       # a width with no worked-out minimum gets the strictest one
    assert rules.for_width(r, "text.min_px_detail", 790) == 21      # a single number is used as it is
    assert rules.for_width({"t": {"m": {"value": 9, "status": "proposal", "source": "s"}}}, "t.m", 1440) == 9

def test_a_rule_without_a_source_is_refused(tmp_path):
    f = tmp_path / "r.md"
    f.write_text('# x\n```json\n{"a": {"b": {"value": 1, "status": "confirmed", "source": ""}}}\n```\n', encoding="utf-8")
    with pytest.raises(ValueError, match="a.b"):
        rules.load(f)

def test_unconfirmed_rules_are_listed_for_the_report():
    r = {"a": {"x": {"value": 1, "status": "unconfirmed", "source": "none found"}, "y": {"value": 2, "status": "confirmed", "source": "u"},
               "z": {"value": 3, "status": "proposal", "source": "s"}, "w": {"value": 4, "status": "from-spec", "source": "spec"}}}
    assert rules.not_confirmed(r) == ["a.x", "a.z"]          # a proposal is not confirmed against Tmall guidance either; a from-spec value is
    with pytest.raises(KeyError, match="a.q"):
        rules.value(r, "a.q")

def test_banned_and_after_state_words_are_found():
    r = {"words": {"banned": {"value": ["最好", "第一"], "status": "proposal", "source": "s"},
                   "after_state": {"value": ["焕发光泽"], "status": "proposal", "source": "s"}},
         "bonded": {"must_not": {"value": ["国内现货"], "status": "proposal", "source": "s"}}}
    assert rules.banned_hits("全网第一", r) == ["第一"]
    assert rules.after_state_hits("肌肤焕发光泽", r) == ["焕发光泽"]
    assert rules.bonded_hits("国内现货秒发", r) == ["国内现货"]
