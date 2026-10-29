import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import json
import pytest
import tmall_capture as cap

@pytest.mark.parametrize("text,expect", [("1.5万+人付款", 15000), ("7000+人付款", 7000), ("300人付款", 300), ("无销量", 0), ("2万人付款", 20000)])
def test_payer_counts_are_read(text, expect):
    assert cap.parse_payers(text) == expect

def test_excluded_items_are_skipped_and_the_next_ones_take_their_place():
    tiles = [{"id": "11", "payers": 300}, {"id": "22", "payers": 9000}, {"id": "44", "payers": 5000}]
    assert [t["id"] for t in cap.rank_tiles(tiles, top_n=2, exclude=("22",))] == ["44", "11"]

def test_top_listings_are_chosen_by_payers_and_the_counts_are_not_kept():
    tiles = [{"id": "11", "payers": 300, "title": "a"}, {"id": "22", "payers": 9000, "title": "b"},
             {"id": "22", "payers": 9000, "title": "b"}, {"id": "33", "payers": 0, "title": "c"}, {"id": "44", "payers": 5000, "title": "d"}]
    top = cap.rank_tiles(tiles, top_n=2)
    assert [t["id"] for t in top] == ["22", "44"] and [t["rank"] for t in top] == [1, 2]
    assert all("payers" not in t for t in top)

def test_item_ids_and_full_size_urls():
    assert cap.item_id("https://detail.example/item.htm?spm=x&id=1234567&a=1") == "1234567"      # invented short id
    assert cap.full_size("//img.example/imgextra/i1/O1CNabc.jpg_110x10000.jpg_.webp") == "https://img.example/imgextra/i1/O1CNabc.jpg"
    assert cap.full_size("https://img.example/p/q.png") == "https://img.example/p/q.png"

@pytest.mark.parametrize("path,w,expect", [("div.desc > div.detail-body", 790, "detail"), ("div.rate-list > div.photo", 790, "review"),
                                          ("div.guess-you-like > li", 790, "recommendation"), ("div.detail-body", 300, "other"),
                                          ("div.buyer-show", 790, "review"), ("div.similar-items", 790, "recommendation")])
def test_detail_images_are_told_apart_from_review_photos_and_recommendations(path, w, expect):
    assert cap.classify_image({"path": path, "w": w, "h": 900, "src": "x"}) == expect

def test_walls_are_recognised_by_address_or_by_a_page_marker():
    assert cap.block_reason("https://detail.example/item.htm?id=1", 0) is None
    assert "redirected" in cap.block_reason("https://login.example/member/login.jhtml", 0, markers=("login.example",))
    assert cap.block_reason("https://detail.example/item.htm?id=1", 2) == "captcha on page"

def test_pacer_spaces_visits_and_stops_at_the_daily_cap(tmp_path):
    t = [1000.0]; slept = []
    p = cap.Pacer(tmp_path / "v.json", gap=(20, 35), daily_cap=2, clock=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)), rng=lambda a, b: 25)
    p.wait_turn(); p.record_visit()
    p.wait_turn(); p.record_visit()
    assert slept == [25]                                   # the first needs no wait, the second waits the gap
    with pytest.raises(cap.DailyCapReached):
        p.wait_turn()
    t[0] += 86400 * 1.5                                    # next day
    p2 = cap.Pacer(tmp_path / "v.json", gap=(20, 35), daily_cap=2, clock=lambda: t[0], sleep=lambda s: None, rng=lambda a, b: 25)
    p2.wait_turn()

def test_the_daily_cap_counts_beijing_days_not_the_machine_s(tmp_path):
    # reviewed-plan audit pass 1: a mutant counting UTC days survived. 2026-10-27 15:30 UTC is 23:30 in Beijing; an hour later is the next Beijing day.
    t = [1793115000.0]                                     # 2026-10-27 15:30 UTC, worked by hand from the calendar date
    p = cap.Pacer(tmp_path / "v.json", gap=(0, 0), daily_cap=1, clock=lambda: t[0], sleep=lambda s: None, rng=lambda a, b: 0)
    p.wait_turn(); p.record_visit()
    t[0] += 3600
    p.wait_turn()                                          # same UTC day, new Beijing day: allowed
