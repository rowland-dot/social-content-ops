import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

from PIL import Image
import pytest
import tmall_handover as ho, tmall_psd, tmall_common as common

def make(tmp_path):
    src = tmp_path / "work"; src.mkdir()
    for n, size in (("m1", (800, 800)), ("d1", (790, 600))):
        folder = src / f"{n}.layers"; folder.mkdir()
        Image.new("RGB", size, "white").save(src / f"{n}.png"); Image.new("RGB", size, "white").save(folder / "scene.png")
        manifest = {"name": n, "size": list(size), "pack": None, "texts": []}
        common.write_json(src / f"{n}.manifest.json", manifest)
    return src

def test_handover_holds_sized_images_a_psd_for_each_and_the_copy_file(tmp_path):
    src = make(tmp_path); out = tmp_path / "handover"
    ho.hand_over(src, out, mains=["m1"], details=["d1"], copy_text="标题\n正文\n")
    assert sorted(p.name for p in out.iterdir()) == ["copy.md", "d1.png", "d1.psd", "m1.png", "m1.psd"]
    assert Image.open(out / "m1.png").size == (800, 800) and Image.open(out / "d1.png").width == 790
    assert (out / "copy.md").read_text(encoding="utf-8") == "标题\n正文\n"

def test_a_wrong_size_is_refused_and_nothing_is_half_written(tmp_path):
    src = make(tmp_path); Image.new("RGB", (700, 700), "white").save(src / "m1.png")
    with pytest.raises(ho.HandoverError, match="m1: is 700×700"):
        ho.hand_over(src, tmp_path / "out", mains=["m1"], details=["d1"], copy_text="x")
    assert not (tmp_path / "out").exists()

def _with_main(tmp_path, size):
    src = make(tmp_path); folder = src / "m1.layers"
    Image.new("RGB", size, "white").save(src / "m1.png"); Image.new("RGB", size, "white").save(folder / "scene.png")
    common.write_json(src / "m1.manifest.json", {"name": "m1", "size": list(size), "pack": None, "texts": []})
    return src

def test_a_main_image_of_every_size_the_rules_file_lists_is_accepted(tmp_path):
    import tmall_rules
    listed = tmall_rules.value(tmall_rules.load(), "main_image.sizes")
    assert len(listed) >= 2                                                              # the platform publishes more than one main-image size
    for i, size in enumerate(map(tuple, listed)):
        (tmp_path / f"s{i}").mkdir(); src = _with_main(tmp_path / f"s{i}", size); out = tmp_path / f"out{i}"
        ho.hand_over(src, out, mains=["m1"], details=["d1"], copy_text="x")
        assert Image.open(out / "m1.png").size == size

@pytest.mark.parametrize("size", [(700, 700), (750, 1000), (1000, 1000)])             # 750 x 1000 (3:4) is not confirmed by any page read, so it is not listed
def test_a_main_image_of_a_size_the_rules_file_does_not_list_is_refused(tmp_path, size):
    src = _with_main(tmp_path, size)
    with pytest.raises(ho.HandoverError, match=rf"m1: is {size[0]}×{size[1]}.*800×800.*1440×1440"):
        ho.hand_over(src, tmp_path / "out", mains=["m1"], details=["d1"], copy_text="x")
    assert not (tmp_path / "out").exists()

def test_the_allowed_main_sizes_can_be_handed_in_instead_of_read_from_the_rules_file(tmp_path):
    src = _with_main(tmp_path, (750, 1000))
    ho.hand_over(src, tmp_path / "out", mains=["m1"], details=["d1"], copy_text="x", main_sizes=[(750, 1000)])
    assert Image.open(tmp_path / "out" / "m1.png").size == (750, 1000)

def test_an_existing_handover_is_never_written_over(tmp_path):
    src = make(tmp_path); ho.hand_over(src, tmp_path / "out", mains=["m1"], details=["d1"], copy_text="x")
    with pytest.raises(ho.HandoverError, match="already exists"):
        ho.hand_over(src, tmp_path / "out", mains=["m1"], details=["d1"], copy_text="y")
    assert (tmp_path / "out" / "copy.md").read_text(encoding="utf-8") == "x"

def test_a_failure_while_writing_leaves_no_handover_folder(tmp_path, monkeypatch):
    src = make(tmp_path)
    monkeypatch.setattr(ho.tmall_psd, "psd_from_manifest", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        ho.hand_over(src, tmp_path / "out", mains=["m1"], details=["d1"], copy_text="x")
    assert not (tmp_path / "out").exists() and not (tmp_path / "out.partial").exists()

def test_a_detail_slice_that_is_not_790_wide_is_refused(tmp_path):
    src = make(tmp_path); Image.new("RGB", (700, 600), "white").save(src / "d1.png")
    with pytest.raises(ho.HandoverError, match="d1: is 700 wide"):
        ho.hand_over(src, tmp_path / "out", mains=["m1"], details=["d1"], copy_text="x")
    assert not (tmp_path / "out").exists()
