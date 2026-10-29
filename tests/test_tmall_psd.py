import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

from PIL import Image, PsdImagePlugin
import tmall_psd as psd

def test_psd_has_each_layer_named_placed_and_a_flat_picture(tmp_path):
    bg = Image.new("RGBA", (40, 30), (200, 100, 50, 255)); pk = Image.new("RGBA", (10, 20), (10, 20, 200, 255))
    tx = Image.new("RGBA", (8, 8), (0, 0, 0, 255))
    psd.write_psd(tmp_path / "t.psd", (40, 30), [{"name": "scene", "image": bg}, {"name": "pack", "image": pk, "x": 5, "y": 4},
                                                  {"name": "text_01_headline", "image": tx, "x": 20, "y": 10}])
    im = PsdImagePlugin.PsdImageFile(tmp_path / "t.psd")
    assert im.size == (40, 30)
    assert [(n, b) for n, _m, b, *_ in im.layers] == [("scene", (0, 0, 40, 30)), ("pack", (5, 4, 15, 24)), ("text_01_headline", (20, 10, 28, 18))]
    flat = im.convert("RGB")
    assert flat.getpixel((7, 6)) == (10, 20, 200) and flat.getpixel((0, 0)) == (200, 100, 50)

def test_psd_from_a_composed_manifest_keeps_the_layers_separate(tmp_path):
    folder = tmp_path / "m.layers"; folder.mkdir()
    for n, c in (("scene", (9, 9, 9, 255)), ("pack", (1, 2, 3, 255)), ("pack_shadow", (0, 0, 0, 90)), ("text_h", (255, 255, 255, 255))):
        Image.new("RGBA", (10, 10), c).save(folder / f"{n}.png")
    manifest = {"name": "m", "size": [20, 20], "pack": {"box": [2, 2, 12, 12], "layer": "m.layers/pack.png"},
                "shadow": {"box": [2, 10, 12, 14], "layer": "m.layers/pack_shadow.png"},
                "texts": [{"id": "h", "box": [3, 3, 13, 13], "layer": "m.layers/text_h.png"}]}
    out = psd.psd_from_manifest(tmp_path, manifest)
    names = [n for n, *_ in PsdImagePlugin.PsdImageFile(out).layers]
    assert names == ["scene", "pack_shadow", "pack", "text_h"]

def test_a_layer_that_starts_outside_the_frame_still_writes(tmp_path):            # a shadow near the left edge used to crash at handover
    psd.write_psd(tmp_path / "e.psd", (20, 20), [{"name": "scene", "image": Image.new("RGBA", (20, 20), (9, 9, 9, 255))},
                                                 {"name": "pack_shadow", "image": Image.new("RGBA", (10, 4), (0, 0, 0, 90)), "x": -3, "y": 18}])
    assert [n for n, *_ in PsdImagePlugin.PsdImageFile(tmp_path / "e.psd").layers] == ["scene", "pack_shadow"]

def test_a_non_ascii_layer_name_is_refused_before_anything_is_written(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="ASCII"):
        psd.write_psd(tmp_path / "x.psd", (4, 4), [{"name": "text_标题", "image": Image.new("RGBA", (2, 2))}])
    assert not (tmp_path / "x.psd").exists()
