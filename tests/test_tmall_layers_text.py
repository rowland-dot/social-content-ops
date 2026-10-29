import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

from PIL import Image
import numpy as np
import tmall_layers as ly

def test_text_boxes_touching_the_pack_are_found():
    layout = {"boxes": [{"kind": "text", "text": "a", "box": [10, 10, 100, 60]},
                        {"kind": "note", "text": "b", "box": [300, 300, 400, 360]}]}
    assert [b["text"] for b in ly.text_over_pack(layout, [250, 250, 500, 700])] == ["b"]
    assert ly.text_over_pack(layout, [600, 600, 700, 700]) == []

def test_contrast_ratio_matches_wcag_for_black_on_white_and_grey():
    assert round(ly.contrast_ratio((0, 0, 0), (255, 255, 255)), 1) == 21.0
    assert round(ly.contrast_ratio((119, 119, 119), (255, 255, 255)), 1) == 4.5   # #777 on white is the textbook 4.5

def test_white_text_on_a_light_backdrop_fails_and_on_a_dark_one_passes(tmp_path):
    light = Image.new("RGB", (200, 200), (240, 240, 235)); dark = Image.new("RGB", (200, 200), (20, 30, 40))
    block = {"id": "h", "color": "#ffffff", "box": [10, 10, 150, 60]}
    assert ly.contrast_problem(block, light, 4.5) != ""
    assert ly.contrast_problem(block, dark, 4.5) == ""

def test_worst_case_is_used_when_part_of_the_backdrop_is_light(tmp_path):
    # 30% light and 70% dark: the median pixel is dark, so only the 95th-percentile pixel catches it (audit pass 3: a median-only mutant survived the old half-and-half image)
    part = Image.new("RGB", (200, 200), (10, 10, 10)); part.paste((250, 250, 250), (140, 0, 200, 200))
    assert ly.contrast_problem({"id": "h", "color": "#ffffff", "box": [0, 0, 200, 100]}, part, 4.5) != ""

def test_type_below_the_scaled_minimum_fails():
    assert ly.size_problem({"id": "h", "px": 18, "tier": "needed"}, minimum=21) != ""
    assert ly.size_problem({"id": "h", "px": 21, "tier": "needed"}, minimum=21) == ""

def test_headline_must_stay_readable_at_phone_thumbnail_size():
    m = {"size": [800, 800], "texts": [{"id": "h", "tier": "headline", "px": 64}]}
    assert ly.thumbnail_problem(m, thumb_px=256, min_headline_px=12) == ""            # 64 * 256/800 = 20.5
    m["texts"][0]["px"] = 30
    assert ly.thumbnail_problem(m, thumb_px=256, min_headline_px=12) != ""            # 9.6

def test_size_and_weight_follow_the_rules(tmp_path):
    p = tmp_path / "m.png"; Image.new("RGB", (800, 800), "white").save(p)
    assert ly.size_weight_problem(p, sizes=[[800, 800]], max_kb=500) == ""
    assert "size" in ly.size_weight_problem(p, sizes=[[750, 1000]], max_kb=500)
    assert "KB" in ly.size_weight_problem(p, sizes=[[800, 800]], max_kb=0.001)

def test_every_layout_box_must_sit_inside_the_frame():
    layout = {"width": 800, "height": 800, "boxes": [{"kind": "text", "text": "a", "box": [10, 10, 900, 60]}]}
    assert ly.outside_frame(layout) != []

def test_text_off_the_frame_and_text_on_text_are_found_from_the_unclipped_boxes():
    # render_card.py clips its layout boxes to the frame (`Math.min(W, ...)`, line 94), so only compose's unclipped full_box can show a run-off
    a = {"id": "a", "box": [10, 10, 800, 60], "full_box": [10, 10, 950, 60]}; b = {"id": "b", "box": [600, 40, 700, 90]}
    assert ly.off_frame([a], (800, 800)) == ["text 'a' runs off the frame"] and ly.off_frame([b], (800, 800)) == []
    assert ly.text_on_text([a, b]) == ["text 'a' overlaps text 'b'"] and ly.text_on_text([b]) == []

def test_three_digit_colours_are_read():
    assert ly._hex("#fff") == (255, 255, 255) and ly._hex("#1E3A5F") == (30, 58, 95)

def test_the_text_card_layout_check_is_left_out_of_the_tmall_checks():
    # The owner, 2026-10-28, on whether Easel's card layout check applies to Tmall pack-and-scene images: "Leave it out for Tmall (Recommended)"
    assert not hasattr(ly, "card_audit") and not hasattr(ly, "AUDIT")
    assert "card_audit" not in Path(ly.__file__).read_text(encoding="utf-8")
