import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

from decimal import Decimal as D
import pytest
import tmall_prices as prices

def _book(path):
    openpyxl = pytest.importorskip("openpyxl")        # not declared in pyproject.toml; the tests that build a workbook skip where CI lacks it
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "2026"
    ws.append(["SKU", "名称", "售价", "成本", "毛利率"])
    ws.append(["A1", "demo-powder 500g", 300, 90, 0.7])
    ws.append(["A2", "demo-powder 250g", 160, 50, 0.68])
    wb.save(path)

def test_only_the_mapped_selling_columns_come_back(tmp_path):
    p = tmp_path / "list.xlsx"; _book(p)
    rows = prices.read_selling_prices(p, "2026", {"sku": "SKU", "name": "名称", "selling_price": "售价"})
    assert rows == [{"sku": "A1", "name": "demo-powder 500g", "selling_price": D("300.00")},
                    {"sku": "A2", "name": "demo-powder 250g", "selling_price": D("160.00")}]

def test_a_missing_sheet_or_column_names_what_the_workbook_does_hold(tmp_path):
    p = tmp_path / "list.xlsx"; _book(p)
    with pytest.raises(ValueError, match=r"sheets found: \['2026'\]"):
        prices.read_selling_prices(p, "2025", {"sku": "SKU", "selling_price": "售价"})
    with pytest.raises(ValueError, match=r"'零售价'.*columns found: \['SKU', '名称', '售价', '成本', '毛利率'\]"):
        prices.read_selling_prices(p, "2026", {"sku": "SKU", "selling_price": "零售价"})

def test_a_blank_selling_price_is_refused_never_read_as_zero(tmp_path):              # reviewed-plan audit pass 1: a mutant reading it as 0 survived
    openpyxl = pytest.importorskip("openpyxl")
    p = tmp_path / "blank.xlsx"; wb = openpyxl.Workbook(); ws = wb.active; ws.title = "2026"
    ws.append(["SKU", "售价"]); ws.append(["A1", None]); wb.save(p)
    with pytest.raises(ValueError, match="A1 has no selling price"):
        prices.read_selling_prices(p, "2026", {"sku": "SKU", "selling_price": "售价"})

@pytest.mark.parametrize("column", ["成本", "毛利率"])
def test_a_cost_or_margin_column_cannot_be_mapped(tmp_path, column):
    p = tmp_path / "list.xlsx"; _book(p)
    with pytest.raises(ValueError, match="cost"):
        prices.read_selling_prices(p, "2026", {"sku": "SKU", "selling_price": column})

def test_two_copies_that_differ_or_miss_a_product_wait_on_ro():
    feb = {"A1": D("300"), "A2": D("160"), "A3": D("99")}
    jul = {"A1": D("300"), "A2": D("170")}
    settled, waiting = prices.reconcile(feb, jul)
    assert settled == {"A1": D("300.00")} and waiting == ["A2", "A3"]

def test_worked_out_prices_with_their_basis():
    assert prices.per_day(300, 500, 10) == D("6.00")         # 500 g / 10 g = 50 days; 300 / 50
    assert prices.per_day(199, 500, 10) == D("3.98")
    assert prices.per_serve(300, 50) == D("6.00")
    line = prices.per_day_line(199, 500, 10)
    assert line == {"kind": "per_day", "value": "3.98", "basis": "¥199.00 ÷ (500 g ÷ 10 g per day)"}

def test_a_spend_threshold_is_never_a_price():
    assert prices.extract_prices("满299减30，满500元") == []
    assert prices.extract_prices("¥199，每天约3.98元") == [D("199.00"), D("3.98")]

def test_printed_prices_not_in_the_allowed_set_are_reported():
    allowed = {D("199.00"), D("3.98")}
    assert prices.check_printed("¥199 每天约3.98元", allowed) == []
    assert prices.check_printed("¥199 每天约4.00元", allowed) == [D("4.00")]

def test_a_bundle_offer_needs_a_bundle_row_in_the_price_list():
    assert prices.bundle_problem("买2送1套装", bundle_rows=[]) != ""
    assert prices.bundle_problem("买2送1套装", bundle_rows=[{"sku": "B1"}]) == ""
    assert prices.bundle_problem("每天一勺", bundle_rows=[]) == ""

def test_a_price_printed_after_the_word_for_price_with_no_yuan_sign_is_still_read():
    # QA 2026-10-28 (review MEDIUM): "到手价199" has no ¥ and no 元, so it was never extracted and the price check passed it unchecked.
    assert prices.extract_prices("到手价199") == [D("199.00")]
    assert prices.extract_prices("售价：299.5") == [D("299.50")]
    assert prices.check_printed("到手价198", {D("199.00")}) == [D("198.00")]
    assert prices.check_printed("到手价199", {D("199.00")}) == []
    assert prices.extract_prices("满299减30 到手价199") == [D("199.00")]            # the spend threshold is still not a price
    assert prices.extract_prices("价格实惠，每天一勺") == []                         # the word alone, no number, is not a price
