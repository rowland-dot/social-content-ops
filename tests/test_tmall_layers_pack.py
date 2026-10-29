import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import numpy as np
from PIL import Image, ImageDraw
import tmall_layers as ly

def _pack(path, size=(200, 400)):
    im = Image.new("RGBA", size, (0, 0, 0, 0)); ImageDraw.Draw(im).rounded_rectangle((10, 10, size[0] - 10, size[1] - 10), 20, fill=(30, 80, 160, 255)); im.save(path)

def test_pack_is_unchanged_when_it_is_the_source_scaled_and_not_turned(tmp_path):
    src = tmp_path / "src.png"; _pack(src)
    layer = Image.open(src).resize((120, 240), Image.LANCZOS); layer.save(tmp_path / "pack.png")
    m = {"pack": {"source": str(src), "source_sha256": ly.sha(src), "rotation": 0, "box": [0, 0, 120, 240], "layer": "pack.png"}}
    assert ly.pack_problem(tmp_path, m) == ""
    m["pack"]["rotation"] = 3; assert "rotated" in ly.pack_problem(tmp_path, m)
    m["pack"]["rotation"] = 0; m["pack"]["source_sha256"] = "0" * 64; assert "source" in ly.pack_problem(tmp_path, m)

def test_a_stretched_or_recoloured_pack_layer_fails(tmp_path):
    src = tmp_path / "src.png"; _pack(src)
    Image.open(src).resize((200, 240)).save(tmp_path / "pack.png")                       # squashed
    m = {"pack": {"source": str(src), "source_sha256": ly.sha(src), "rotation": 0, "box": [0, 0, 200, 240], "layer": "pack.png"}}
    assert "aspect" in ly.pack_problem(tmp_path, m)
    Image.open(src).resize((100, 200)).point(lambda v: min(255, v + 60)).save(tmp_path / "pack.png")   # brightened
    m["pack"]["box"] = [0, 0, 100, 200]
    assert "pixels" in ly.pack_problem(tmp_path, m)

def test_light_side_from_a_picture_that_is_brighter_on_one_side():
    left = Image.linear_gradient("L").rotate(-90).resize((200, 100)).convert("RGB")        # white on the left, black on the right
    assert ly.light_side(left) == "left"
    assert ly.light_side(Image.new("RGB", (100, 100), (128, 128, 128))) == "flat"

def test_scene_light_must_match_the_pack_unless_the_pack_has_no_clear_side():
    assert ly.light_problem("left", "right") != ""
    assert ly.light_problem("left", "left") == ""
    assert ly.light_problem("flat", "right") == ""

def test_contact_shadow_must_touch_the_pack_foot():
    m = {"pack": {"box": [100, 100, 300, 500]}, "shadow": {"box": [90, 480, 310, 520]}}
    assert ly.shadow_problem(m) == ""
    m["shadow"]["box"] = [90, 600, 310, 640]; assert ly.shadow_problem(m) != ""
    assert ly.shadow_problem({"pack": {"box": [0, 0, 1, 1]}}) != ""

def test_pack_needs_a_surface_edge_under_its_foot():
    scene = Image.new("RGB", (400, 600), (230, 230, 225)); scene.paste((120, 90, 70), (0, 520, 400, 600))   # table from y=520
    assert ly.surface_problem(scene, [100, 100, 300, 515]) == ""
    assert ly.surface_problem(Image.new("RGB", (400, 600), (230, 230, 225)), [100, 100, 300, 515]) != ""

def test_pack_must_fill_the_frame_height_and_stand_upright():
    m = {"size": [800, 800], "pack": {"box": [100, 100, 300, 740], "rotation": 0}}
    assert ly.frame_problem(m, minimum=0.6) == ""                                          # 640 / 800 = 0.8
    m["pack"]["box"] = [100, 400, 200, 700]; assert ly.frame_problem(m, minimum=0.6) != ""  # 0.375

def test_blown_out_glare_and_gold_text_on_light_are_flagged():
    glare = Image.new("RGB", (100, 100), (255, 255, 255))
    assert ly.glare_problem(glare, [0, 0, 100, 100], max_share=0.02) != ""
    assert ly.glare_problem(Image.new("RGB", (100, 100), (90, 90, 90)), [0, 0, 100, 100], max_share=0.02) == ""
    white_pack = Image.new("RGBA", (50, 50), (255, 255, 255, 255))                               # a white pack's own colour is not glare
    assert ly.glare_problem(glare, [0, 0, 100, 100], max_share=0.02, pack_layer=white_pack) == ""
    assert ly.glare_problem(glare, [0, 0, 100, 100], max_share=0.02, pack_layer=Image.new("RGBA", (50, 50), (90, 90, 90, 255))) != ""
    light = Image.new("RGB", (200, 100), (245, 242, 235))
    assert ly.gold_on_light_problem({"id": "h", "color": "#C9A227", "box": [0, 0, 100, 50]}, light) != ""
    assert ly.gold_on_light_problem({"id": "h", "color": "#C9A227", "box": [0, 0, 100, 50]}, Image.new("RGB", (200, 100), (20, 20, 30))) == ""
