import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import pytest
import tmall_flow as fl

V = lambda lid, d, ok=True: {"listing_id": lid, "direction": d, "image": f"{lid}.png", "checks_passed": ok}
THREE = {"A": V("L1", "close-up"), "B": V("L2", "flat lay"), "C": V("L3", "in use")}

def test_only_the_headline_may_be_made_before_a_pick():
    s = fl.new_state(); fl.register_versions(s, THREE)
    assert fl.may_make(s, "M1") and not fl.may_make(s, "M2") and not fl.may_make(s, "D1")
    fl.pick(s, "B")
    assert fl.may_make(s, "M2") and s["headline"]["picked"] == "B"

def test_versions_must_differ_in_listing_and_direction_and_all_pass_the_checks():
    s = fl.new_state()
    with pytest.raises(fl.FlowError, match="listing"):
        fl.register_versions(s, {"A": V("L1", "x"), "B": V("L1", "y"), "C": V("L3", "z")})
    with pytest.raises(fl.FlowError, match="direction"):
        fl.register_versions(s, {"A": V("L1", "x"), "B": V("L2", "x"), "C": V("L3", "z")})
    with pytest.raises(fl.FlowError, match="checks"):
        fl.register_versions(s, {"A": V("L1", "x", False), "B": V("L2", "y"), "C": V("L3", "z")})
    with pytest.raises(fl.FlowError, match="A, B and C"):
        fl.register_versions(s, {"A": V("L1", "x")})

def test_a_ruling_on_the_versions_remakes_them_and_makes_nothing_else():
    s = fl.new_state(); fl.register_versions(s, THREE)
    fl.rule_on_versions(s, "make the pack larger")
    assert s["headline"]["versions"] is None and not fl.may_make(s, "M2")
    assert s["style_lock_version"] == 2 and s["headline"]["rulings"] == ["make the pack larger"]

def test_a_pick_is_impossible_before_versions_exist():
    with pytest.raises(fl.FlowError): fl.pick(fl.new_state(), "A")

def test_a_rejection_remakes_only_the_named_images_and_the_rest_stay_byte_identical():
    s = fl.new_state(); fl.register_versions(s, THREE); fl.pick(s, "A")
    todo = fl.reject(s, "image 3 is too dark", affected=["M3"])
    assert todo == ["M3"] and s["images"]["M3"]["status"] == "to_remake"
    before = {"M1": "h1", "M2": "h2", "M3": "h3"}
    assert fl.changed_outside(before, {"M1": "h1", "M2": "h2", "M3": "NEW"}, affected=["M3"]) == []
    assert fl.changed_outside(before, {"M1": "CHANGED", "M2": "h2", "M3": "NEW"}, affected=["M3"]) == ["M1"]

def test_the_approval_page_needs_every_report_complete_and_passed():
    ok = {"complete": True, "passed": True}
    assert fl.may_show_approval({"M1": ok, "M2": ok}, ["M1", "M2"]) is True
    assert fl.may_show_approval({"M1": ok, "M2": {"complete": True, "passed": False}}, ["M1", "M2"]) is False
    assert fl.may_show_approval({"M1": ok}, ["M1", "M2"]) is False

def test_status_command_creates_and_reports_the_flow_file(tmp_path):
    import json, subprocess, sys
    r = subprocess.run([sys.executable, str(SCRIPTS / "tmall_flow.py"), "status", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout) == {"style_lock_version": 1, "versions_ready": False, "picked": None}
    assert (tmp_path / "flow.json").is_file()

def test_state_saved_by_a_script_is_what_the_next_script_loads(tmp_path):
    s = fl.load_state(tmp_path); fl.register_versions(s, THREE); fl.pick(s, "C"); fl.save_state(tmp_path, s)
    assert fl.load_state(tmp_path)["headline"]["picked"] == "C" and not list(tmp_path.glob("*.tmp"))

def test_the_picked_version_is_copied_up_beside_the_other_images_byte_for_byte(tmp_path):
    # reviewed-plan audit pass 3: the three versions are composed as M1 in headline/A, B and C (Task 27), and the handover reads every
    # main image from one folder, so a picked M1 left in headline/B stopped it with "No such file ... M1.png" (probed)
    s = fl.new_state(); fl.register_versions(s, THREE)
    with pytest.raises(fl.FlowError, match="picked"):
        fl.promote_pick(tmp_path, s)
    b = tmp_path / "headline" / "B"; (b / "M1.layers").mkdir(parents=True)
    for n in ("M1.png", "M1.base.png", "M1.layout.json", "M1.manifest.json", "M1.layers/scene.png"): (b / n).write_bytes(n.encode())
    (tmp_path / "headline" / "A").mkdir(); (tmp_path / "headline" / "A" / "M1.png").write_bytes(b"A")
    fl.pick(s, "B")
    assert fl.promote_pick(tmp_path, s) == ["M1.base.png", "M1.layers", "M1.layout.json", "M1.manifest.json", "M1.png"]
    assert (tmp_path / "M1.png").read_bytes() == b"M1.png" and (tmp_path / "M1.layers" / "scene.png").read_bytes() == b"M1.layers/scene.png"
    fl.pick(s, "A"); fl.promote_pick(tmp_path, s)          # a later pick replaces the earlier copy, its layer folder included
    assert (tmp_path / "M1.png").read_bytes() == b"A" and not (tmp_path / "M1.layers").exists()
    fl.pick(s, "C")
    with pytest.raises(fl.FlowError, match="no M1.png"):    # a version never composed is named, not copied as nothing
        fl.promote_pick(tmp_path, s)
