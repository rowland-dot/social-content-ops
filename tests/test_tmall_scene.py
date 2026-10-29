import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import json
from PIL import Image
import pytest
import tmall_scene as sc, tmall_held as held

def test_command_uses_the_text_to_image_subcommand_with_no_key_or_api_flag(tmp_path):
    cmd = sc.build_command("clean counter, soft morning light, no text, no product", tmp_path / "s.png", size=(790, 1200))
    assert "text2img" in cmd and cmd[cmd.index("-o") + 1].endswith("s.png") and cmd[cmd.index("--size") + 1] == "790x1200"
    assert not any("key" in c.lower() or "api" in c.lower() for c in cmd if c.startswith("--"))

def test_a_scene_is_never_made_at_a_size_nobody_chose(tmp_path):
    # the size of a main image is chosen in stage 3 (from the competitor cases, the Tmall reading as the fallback); the scene maker has no default of its own
    with pytest.raises(TypeError, match="size"):
        sc.build_command("clean counter, no text, no product", tmp_path / "s.png")
    ran = []
    with pytest.raises(TypeError, match="size"):
        sc.generate_scene("p", tmp_path / "s.png", env={"IMG_PROVIDER": "codex"}, runner=lambda *a, **k: ran.append(1))
    assert ran == []

def test_reference_photos_are_refused_until_the_inputs_are_settled(tmp_path):
    # the image tool keeps its first --image as the product (ai_image.py, the --image help text, line 890 on 2026-10-28); a style reference alone would become "the product"
    with pytest.raises(sc.ReferencesNotSettled):
        sc.build_command("same light, empty space", tmp_path / "s.png", size=(800, 800), refs=["a.png"])

def test_while_held_nothing_runs(tmp_path):
    ran = []
    with pytest.raises(held.HeldError):
        sc.generate_scene("p", tmp_path / "s.png", size=(800, 800), env={"IMG_PROVIDER": "codex"}, runner=lambda *a, **k: ran.append(1))
    assert ran == []

def test_even_when_released_a_missing_codex_setting_stops_the_run(tmp_path):
    rel = tmp_path / "h.json"; rel.write_text(json.dumps({"ai-image-gen": {"held": False, "until": "x"}}), encoding="utf-8")
    ran = []
    with pytest.raises(sc.PaidRouteRefused):
        sc.generate_scene("p", tmp_path / "s.png", size=(800, 800), env={}, runner=lambda *a, **k: ran.append(1), held_file=rel)
    assert ran == []
    sc.generate_scene("p", tmp_path / "s.png", size=(800, 800), env={"IMG_PROVIDER": "codex"}, runner=lambda *a, **k: ran.append(a[0]), held_file=rel)
    assert len(ran) == 1

def test_stand_in_scene_writes_a_text_free_picture_of_the_requested_size(tmp_path):
    sc.stand_in_scene(tmp_path / "s.png", (800, 800)); assert Image.open(tmp_path / "s.png").size == (800, 800)
