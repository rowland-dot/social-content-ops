import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import pytest
import tmall_common as common
import output_paths

def test_product_dir_sits_under_outputs(tmp_path, monkeypatch):
    (tmp_path / "outputs").mkdir()
    monkeypatch.setattr(output_paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(output_paths, "OUTPUTS_DIR", tmp_path / "outputs")
    d = common.product_dir("Acme", "demo-powder", create=True)
    assert d == (tmp_path / "outputs" / "Acme" / "天猫商品内容" / "demo-powder").resolve()
    assert d.is_dir()

def test_generic_brand_folder_is_refused(tmp_path, monkeypatch):
    (tmp_path / "outputs").mkdir()
    monkeypatch.setattr(output_paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(output_paths, "OUTPUTS_DIR", tmp_path / "outputs")
    with pytest.raises(output_paths.OutputPathError):
        common.product_dir("test", "demo-powder")

def test_json_round_trip_keeps_chinese_and_is_atomic(tmp_path):
    p = tmp_path / "a" / "x.json"
    common.write_json(p, {"名": "燕麦"})
    assert common.read_json(p) == {"名": "燕麦"}
    assert "燕麦" in p.read_text(encoding="utf-8")
    assert not list(p.parent.glob("*.tmp"))

def test_sha256_of_known_bytes(tmp_path):
    p = tmp_path / "f"; p.write_bytes(b"abc")
    assert common.sha256(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
