import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import json
from PIL import Image, ImageDraw
import pytest
import tmall_compose as comp

@pytest.fixture
def parts(tmp_path):
    scene = Image.linear_gradient("L").resize((800, 800)).convert("RGB"); scene.save(tmp_path / "scene.png")
    pack = Image.new("RGBA", (200, 400), (0, 0, 0, 0))
    ImageDraw.Draw(pack).rounded_rectangle((10, 10, 190, 390), 20, fill=(30, 80, 160, 255)); pack.save(tmp_path / "pack.png")
    return tmp_path

TEXT = [{"id": "headline", "text": "早上喝一勺", "tier": "headline", "x": 40, "y": 40, "w": 720, "px": 64,
         "color": "#ffffff", "font": "Noto Sans CJK SC", "weight": 700}]

def test_main_image_is_800_by_800_with_named_layers_and_the_pack_only_scaled(parts, chromium):
    m = comp.compose(parts / "out", "m1", scene=parts / "scene.png", size=(800, 800), texts=TEXT,
                     pack={"file": parts / "pack.png", "height": 480, "cx": 400, "bottom": 720})
    assert Image.open(parts / "out" / "m1.png").size == (800, 800)
    assert (parts / "out" / "m1.layout.json").is_file() and (parts / "out" / "m1.base.png").is_file()
    assert set(m["layer_names"]) == {"scene", "pack_shadow", "pack", "text_headline"}
    assert m["pack"]["box"][3] == 720 and m["pack"]["box"][1] == 240        # bottom and top are where we put them (height 480)
    assert m["pack"]["rotation"] == 0 and m["pack"]["source_sha256"]
    w = m["pack"]["box"][2] - m["pack"]["box"][0]
    assert abs(w / 480 - 200 / 400) < 0.005                                   # aspect ratio unchanged
    assert json.loads((parts / "out" / "m1.manifest.json").read_text(encoding="utf-8"))["name"] == "m1"
    assert m["texts"][0]["box"][2] > m["texts"][0]["box"][0]                   # measured box of the text layer

def test_a_pack_photo_with_a_solid_background_is_refused(parts, chromium):
    Image.new("RGB", (200, 400), "white").save(parts / "solid.png")
    with pytest.raises(comp.PackNeedsCutout):
        comp.compose(parts / "o2", "m", scene=parts / "scene.png", size=(800, 800), texts=[],
                     pack={"file": parts / "solid.png", "height": 480, "cx": 400, "bottom": 720})

def test_an_unlicensed_font_is_refused_before_rendering(parts):
    import tmall_fonts
    bad = [dict(TEXT[0], font="Comic Sans")]
    with pytest.raises(tmall_fonts.FontNotLicensed, match="Comic Sans"):
        comp.compose(parts / "o3", "m", scene=parts / "scene.png", size=(800, 800), texts=bad)
    # weight 900 renders from NotoSansCJK-Black.ttc, a file whose licence nobody read (reviewed-plan audit pass 1: `fc-match` in WSL)
    with pytest.raises(tmall_fonts.FontNotLicensed, match="weight 900"):
        comp.compose(parts / "o3", "m", scene=parts / "scene.png", size=(800, 800), texts=[dict(TEXT[0], weight=900)])

def test_detail_slice_is_790_wide(parts, chromium):
    comp.compose(parts / "o4", "d1", scene=parts / "scene.png", size=(790, 1200), texts=TEXT)
    assert Image.open(parts / "o4" / "d1.png").size == (790, 1200)

def test_a_scene_of_another_shape_is_cropped_to_cover_never_stretched(parts, chromium):
    wide = Image.new("RGB", (1600, 800), (0, 0, 255)); ImageDraw.Draw(wide).rectangle((0, 0, 399, 799), fill=(255, 0, 0)); wide.save(parts / "wide.png")
    comp.compose(parts / "o5", "m", scene=parts / "wide.png", size=(800, 800), texts=[])
    assert Image.open(parts / "o5" / "m.layers" / "scene.png").getpixel((50, 400)) == (0, 0, 255)   # stretching would show the red band here

def test_text_running_off_the_frame_is_measured_unclipped_and_a_chinese_id_is_refused(parts, chromium):
    long = [dict(TEXT[0], text="早上喝一勺" * 4, x=600, w=900)]
    m = comp.compose(parts / "o6", "m", scene=parts / "scene.png", size=(800, 800), texts=long, style_lock_version=2)
    assert m["texts"][0]["full_box"][2] > 800 and m["texts"][0]["box"][2] <= 800 and m["style_lock_version"] == 2
    with pytest.raises(ValueError, match="ASCII"):
        comp.compose(parts / "o7", "m", scene=parts / "scene.png", size=(800, 800), texts=[dict(TEXT[0], id="标题")])

def test_the_text_is_drawn_at_the_size_colour_and_weight_asked_for_not_the_browser_default(parts, chromium):
    # QA 2026-10-28: the page wrote style='...font:700 64px/1.25 'Noto Sans CJK SC',...;color:#fff' with the font name in single quotes inside a
    # single-quoted attribute, so the attribute ended at the font name: every text block was drawn 16 px black in the default face while the
    # manifest, and so every check (size, contrast, thumbnail), still said 64 px white.
    from PIL import Image
    import numpy as np
    dark = Image.new("RGB", (800, 800), (20, 20, 20)); dark.save(parts / "dark.png")
    m = comp.compose(parts / "o8", "m", scene=parts / "dark.png", size=(800, 800), texts=TEXT)
    box = m["texts"][0]["box"]
    assert box[3] - box[1] >= 55                                              # 64 px type is about 60 px tall; the 16 px default is under 20
    layer = np.asarray(Image.open(parts / "o8" / "m.layers" / "text_headline.png").convert("RGBA"))
    solid = layer[..., 3] > 200
    assert solid.any() and layer[..., :3][solid].min() >= 240                  # white (#ffffff), not black
    final = np.asarray(Image.open(parts / "o8" / "m.png").convert("RGB"))[box[1]:box[3], box[0]:box[2]]
    assert final.max() >= 240                                                 # and the finished image shows it
