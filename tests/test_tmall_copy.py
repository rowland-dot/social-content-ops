import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

from decimal import Decimal as D
import tmall_copy as cp

def blk(i, tier, text, **kw): return {"id": i, "tier": tier, "text": text, **kw}

def test_extras_go_first_then_needed_facts_move_to_the_next_screen():
    blocks = [blk("h", "headline", "每天一勺"), blk("n1", "needed", "x" * 10), blk("n2", "needed", "y" * 10),
              blk("e1", "extra", "z" * 10), blk("e2", "extra", "w" * 10)]
    out = cp.fit_screen(blocks, capacity=32)
    assert [b["id"] for b in out["kept"]] == ["h", "n1", "n2"]
    assert [b["id"] for b in out["dropped_extras"]] == ["e1", "e2"] and out["moved"] == []
    out = cp.fit_screen(blocks, capacity=18)
    assert [b["id"] for b in out["kept"]] == ["h", "n1"] and [b["id"] for b in out["moved"]] == ["n2"]

def test_the_headline_is_never_moved_or_cut():
    out = cp.fit_screen([blk("h", "headline", "x" * 40)], capacity=10)
    assert [b["id"] for b in out["kept"]] == ["h"] and out["overflow"] is True

def test_a_closing_screen_cannot_be_left_half_empty():
    assert cp.closing_problem([blk("h", "headline", "x" * 5)], capacity=40, min_fill=0.6) != ""
    assert cp.closing_problem([blk("h", "headline", "x" * 30)], capacity=40, min_fill=0.6) == ""

SHEET = {"claims": [{"id": "C1", "text": "每天一勺"}], "forbidden": [{"text": "治疗", "source": "s"}]}

def test_unknown_claims_forbidden_phrases_and_wrong_prices_are_each_named():
    ok = [blk("a", "headline", "每天一勺，约¥3.98", claims=["C1"])]
    assert cp.trace(ok, SHEET, {D("3.98")}, bundle_rows=[]) == []
    bad = [blk("a", "headline", "能治疗", claims=["C9"]), blk("b", "needed", "只要¥4.00", claims=[])]
    found = cp.trace(bad, SHEET, {D("3.98")}, bundle_rows=[])
    assert any("C9" in x for x in found) and any("治疗" in x for x in found) and any("4.00" in x for x in found)

def test_a_block_with_no_claim_and_no_price_is_a_claim_without_a_source():
    assert any("no claim" in x for x in cp.trace([blk("a", "needed", "天然萃取", claims=[])], SHEET, set(), bundle_rows=[]))

def test_a_bundle_offer_needs_a_price_list_row_and_a_wrong_price_shows_its_basis():          # checklist P3.4 and P3.5
    offer = [blk("a", "headline", "买2送1套装", claims=["C1"])]
    assert any("bundle" in x for x in cp.trace(offer, SHEET, set(), bundle_rows=[]))
    assert cp.trace(offer, SHEET, set(), bundle_rows=[{"sku": "B1"}]) == []
    basis = {D("3.98"): "¥199.00 ÷ (500 g ÷ 10 g per day)"}
    found = cp.trace([blk("a", "headline", "每天约3.99元", claims=["C1"])], SHEET, basis, bundle_rows=[])
    assert any("3.99" in x and "¥199.00 ÷ (500 g ÷ 10 g per day)" in x for x in found), found
