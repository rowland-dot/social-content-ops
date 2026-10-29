import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import copy
import pytest
import tmall_plan as pm

ROLES = ["headline", "ingredients_evidence", "scene_audience", "comparison_proof", "sizes_bundles"]
SHEET = {"facts": [{"id": f"F{i}", "status": "settled"} for i in range(1, 8)],
         "claims": [{"id": "C1"}, {"id": "C2"}],
         "inventory": [{"file": "f.png", "angle": "front", "use": "use as is"},
                       {"file": "b.png", "angle": "back", "use": "crop"},
                       {"file": "r.png", "angle": "top", "use": "reference only"}]}
RULES = {"words": {"after_state": {"value": ["焕发光泽"], "status": "proposal", "source": "s"}},
         "main_image": {"sizes": {"value": [[800, 800], [1440, 1440]], "status": "confirmed", "source": "s"}}}

def good():
    mains = [{"id": f"M{i+1}", "role": r, "question": f"q{i}", "fact_id": f"F{i+1}",
              "claim_ids": [], "pack_angle": "front" if i % 2 == 0 else "back", "scene": "clean kitchen counter, morning",
              "varies": "scale" if i in (2, 3, 4) else None} for i, r in enumerate(ROLES)]
    mains[0]["claim_ids"] = ["C1"]; mains[1]["claim_ids"] = ["C2"]
    mains[3]["comparison"] = {"competitor": None, "verified_fact_ids": [], "numbers": []}
    return {"style_lock": {"palette": ["#fff"], "font": "Noto Sans CJK SC", "layout": "grid"},
            "main_size": [800, 800],
            "main_images": mains,
            "detail_screens": [{"id": "D1", "question": "d1", "fact_id": "F6", "claim_ids": []}],
            "selling_point_map": {"C1": "M1", "C2": "M2"},
            "angle_note": "only front and back exist; images 3 and 5 vary scale"}

def problems(edit=None):
    p = copy.deepcopy(good())
    if edit: edit(p)
    return pm.validate(p, SHEET, RULES)

def test_good_plan_passes():
    assert problems() == []

@pytest.mark.parametrize("edit,expect", [
    (lambda p: p["main_images"].pop(), "five main images"),
    (lambda p: p["main_images"][1].update(question="q0"), "same buyer question"),
    (lambda p: p["detail_screens"][0].update(fact_id="F1"), "restates"),
    (lambda p: p["selling_point_map"].pop("C2"), "C2: not assigned"),
    (lambda p: p["main_images"][0].update(pack_angle="top"), "pack angle top"),
    (lambda p: p["main_images"][0].update(scene="皮肤焕发光泽的清晨"), "implies a result"),
    (lambda p: p["main_images"][3].update(comparison={"competitor": "BrandX", "verified_fact_ids": [], "numbers": []}), "names a competitor"),
    (lambda p: p["main_images"][3].update(comparison={"competitor": None, "verified_fact_ids": [], "numbers": [{"value": "3倍"}]}), "number without a fact"),
    (lambda p: p["main_images"][3].update(comparison={"competitor": None, "verified_fact_ids": [], "numbers": [{"value": "3倍", "fact_id": "F99"}]}), "not a settled fact"),
    (lambda p: p["main_images"][3].update(comparison={"competitor": "BrandX", "verified_fact_ids": ["F99"], "numbers": []}), "competitor fact F99"),
    (lambda p: p["main_images"][4].update(varies=None), "repeats an angle"),
    (lambda p: p.pop("main_size"), "main_size"),                           # stage 3 chooses the main-image size; nothing downstream has a default
    (lambda p: p.update(main_size=[750, 1000]), "750×1000 is not one of the sizes the Tmall rules file allows"),
])
def test_each_rule_is_enforced(edit, expect):
    assert any(expect in x for x in problems(edit)), problems(edit)

def test_either_allowed_main_size_passes():
    for size in ([800, 800], [1440, 1440]):
        assert problems(lambda p: p.update(main_size=size)) == []

def test_check_command_reads_the_product_folder(tmp_path):
    import json, subprocess, sys
    run = lambda: subprocess.run([sys.executable, str(SCRIPTS / "tmall_plan.py"), "check", str(tmp_path)], capture_output=True, text=True)
    r = run(); assert r.returncode == 2 and "plan.json" in r.stderr                     # nothing there yet: named, not a crash
    (tmp_path / "plan.json").write_text(json.dumps(good()), encoding="utf-8")
    (tmp_path / "fact-sheet.json").write_text(json.dumps(SHEET), encoding="utf-8")
    assert run().returncode == 0
    bad = good(); bad["main_images"].pop(); (tmp_path / "plan.json").write_text(json.dumps(bad), encoding="utf-8")
    r = run(); assert r.returncode == 1 and "five main images" in r.stdout
