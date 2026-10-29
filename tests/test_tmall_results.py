import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import datetime as dt
import pytest
import tmall_results as rs

D = dt.date
def test_windows_are_four_weeks_each_and_clear_of_double_11():
    w = rs.windows(go_live=D(2026, 11, 20), warmup_start=D(2026, 10, 20), double11_end=D(2026, 11, 12))
    assert w["before"] == (D(2026, 9, 22), D(2026, 10, 19)) and w["after"] == (D(2026, 11, 20), D(2026, 12, 17))

def test_go_live_inside_double_11_is_refused():
    with pytest.raises(ValueError, match="Double 11"):
        rs.windows(go_live=D(2026, 11, 10), warmup_start=D(2026, 10, 20), double11_end=D(2026, 11, 12))
    with pytest.raises(ValueError, match="Double 11"):                      # the last day of the sale is still the sale
        rs.windows(go_live=D(2026, 11, 12), warmup_start=D(2026, 10, 20), double11_end=D(2026, 11, 12))
    assert rs.windows(go_live=D(2026, 11, 13), warmup_start=D(2026, 10, 20), double11_end=D(2026, 11, 12))["after"][0] == D(2026, 11, 13)

def test_conversion_cart_rate_and_time_for_a_window():
    days = [{"date": D(2026, 9, 22), "visitors": 100, "cart": 10, "payers": 2, "minutes": 1.5},
            {"date": D(2026, 9, 23), "visitors": 300, "cart": 20, "payers": 10, "minutes": 2.5}]
    out = rs.summarise(days, (D(2026, 9, 22), D(2026, 9, 28)))
    assert out == {"visitors": 400, "conversion": 0.03, "cart_rate": 0.075, "minutes": 2.0, "days": 2, "measure": rs.MEASURE}
    assert "生意参谋" in out["measure"]                                     # the report says which conversion figure it is

def test_price_and_promotion_notes_inside_either_window_are_listed_beside_the_result():
    events = [{"date": D(2026, 10, 1), "note": "price cut"}, {"date": D(2026, 11, 1), "note": "ignored"}]
    assert rs.notes_in(events, (D(2026, 9, 22), D(2026, 10, 19))) == ["2026-10-01: price cut"]

def test_a_missing_sheet_or_an_empty_window_is_reported_and_never_filled_in(tmp_path):      # checklist P3.23
    with pytest.raises(rs.NoDataError, match="missing"):
        rs.read_sheet(tmp_path / "none.xlsx", "demo")
    with pytest.raises(rs.NoDataError, match="no days"):
        rs.summarise([], (D(2026, 9, 22), D(2026, 9, 28)))
    with pytest.raises(rs.NoDataError, match="no days"):                    # days that exist but carry no visitors would otherwise divide by zero
        rs.summarise([{"date": D(2026, 9, 22), "visitors": 0, "cart": 0, "payers": 0, "minutes": 0}], (D(2026, 9, 22), D(2026, 9, 28)))

def test_stand_in_sheet_reader(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")        # not declared in pyproject.toml; skip where CI lacks it
    p = tmp_path / "s.xlsx"; wb = openpyxl.Workbook(); ws = wb.active; ws.title = "demo"
    ws.append(["日期", "访客", "加购", "付款人数", "停留分钟"]); ws.append([dt.datetime(2026, 9, 22), 100, 10, 2, 1.5])
    ws.append(["2026-09-23", 50, 5, 1, 1.0]); ws.append([None, None, None, None, None])           # a date typed as text, then a blank row
    wb.save(p)
    days = rs.read_sheet(p, "demo")
    assert days[0] == {"date": D(2026, 9, 22), "visitors": 100, "cart": 10, "payers": 2, "minutes": 1.5}
    assert len(days) == 2 and days[1]["date"] == D(2026, 9, 23)
    with pytest.raises(ValueError, match=r"\['停留时长'\] not found; columns found: .*停留分钟"):   # a real sheet whose headers differ says which ones it has
        rs.read_sheet(p, "demo", columns=("日期", "访客", "加购", "付款人数", "停留时长"))

def test_tmall_s_own_sales_in_the_after_window_are_listed_beside_the_result():
    # Spec stage 8: promotions in either window are noted. Double 12 falls inside a four-week window that starts after Double 11.
    after = rs.windows(go_live=D(2026, 11, 20), warmup_start=D(2026, 10, 20), double11_end=D(2026, 11, 12))["after"]
    assert rs.notes_in(rs.sale_days(2026), after) == ["2026-12-12: Double 12 (双12) sale day"]
