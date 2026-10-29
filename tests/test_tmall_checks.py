import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import pytest
import tmall_checks as ck

def res(name, verdict="pass", method="measured", evidence=None): return {"check": name, "verdict": verdict, "method": method, "evidence": evidence}

def full(**over):
    r = {n: res(n) for n in ck.CHECKS}
    for n in ck.LOOKED: r[n] = res(n, method="looked", evidence="crop.png")
    r.update(over); return r

def test_all_named_checks_must_be_present():
    report = ck.build_report("m1", {"claims": res("claims")})
    assert report["complete"] is False and "prices" in report["missing"]

def test_a_full_set_of_passes_is_a_pass():
    report = ck.build_report("m1", full())
    assert report["complete"] and report["passed"] and report["failed"] == []

def test_one_fail_fails_the_image_and_is_named():
    report = ck.build_report("m1", full(layers_contrast=res("layers_contrast", "fail")))
    assert report["passed"] is False and report["failed"] == ["layers_contrast"]

def test_a_looked_check_without_evidence_does_not_count():
    r = full(); r["scene_surface_looked"] = res("scene_surface_looked", method="looked", evidence=None)
    report = ck.build_report("m1", r)
    assert report["passed"] is False and "scene_surface_looked" in report["missing"]

def test_the_quality_check_result_is_missing_while_the_tool_is_held():
    r = full(); r.pop("compliance_quality_gate")
    assert "compliance_quality_gate" in ck.build_report("m1", r)["missing"]

def test_gather_refuses_a_quality_check_result_while_the_quality_check_is_held(tmp_path):
    # review 2026-10-28: a result handed in while the tool is held (never really run) would complete the report and open the approval page
    import tmall_held
    with pytest.raises(tmall_held.HeldError, match="skill-quality-gate"):
        ck.gather(tmp_path, manifest={"name": "M1"}, rules={}, sheet={}, selling_points={}, plan_problems=[], allowed_prices=set(),
                  bundle_rows=[], competitor_strings=[], style_lock={}, quality_gate=res("compliance_quality_gate"))

def test_rounds_stop_after_the_limit_and_report_the_reason():
    calls = []
    def make(round_no): calls.append(round_no); return {"layers_contrast": res("layers_contrast", "fail")}
    out = ck.run_rounds(make, fix=lambda failed: None, max_rounds=3, evaluate=lambda results: ck.build_report("m1", full(**results)))
    assert calls == [1, 2, 3] and out["status"] == "reported" and out["failed"] == ["layers_contrast"]

def test_a_missing_result_waits_instead_of_spending_re_makes():                           # the held quality check leaves every report incomplete
    calls, fixes = [], []
    def make(n): calls.append(n); return {}
    def evaluate(results):
        r = full(); r.pop("compliance_quality_gate"); return ck.build_report("m1", r)
    out = ck.run_rounds(make, fix=fixes.append, max_rounds=3, evaluate=evaluate)
    assert out["status"] == "waiting" and calls == [1] and fixes == [] and "compliance_quality_gate" in out["missing"]

def test_a_failure_no_new_scene_can_cure_stops_at_once():
    calls = []
    def make(n): calls.append(n); return {"pack": res("pack", "fail")}
    out = ck.run_rounds(make, fix=lambda f: None, max_rounds=3, evaluate=lambda results: ck.build_report("m1", full(**results)))
    assert calls == [1] and out["status"] == "reported" and out["failed"] == ["pack"]

def test_a_looked_result_needs_its_evidence_file_to_exist(tmp_path):
    r = full()
    assert "scene_surface_looked" in ck.build_report("m1", r, folder=tmp_path)["missing"]          # "crop.png" is only a name
    (tmp_path / "crop.png").write_bytes(b"x")
    assert ck.build_report("m1", r, folder=tmp_path)["missing"] == []

def test_rounds_end_early_on_a_pass():
    out = ck.run_rounds(lambda n: {}, fix=lambda f: None, max_rounds=3, evaluate=lambda results: ck.build_report("m1", full()))
    assert out["status"] == "passed" and out["rounds"] == 1

def test_competitor_strings_in_our_copy_fail_the_no_copying_check():
    assert ck.copying_hits("买家秀同款 BrandX 的第一名", ["BrandX"]) == ["BrandX"]
    assert ck.copying_hits("我们的配方", ["BrandX"]) == []

def test_a_mapped_claim_must_be_set_as_text_inside_the_frame_of_its_image():                 # spec stage 6, "Selling points visible"
    m = {"M1": {"size": [800, 800], "texts": [{"id": "h", "claims": ["C1"], "box": [10, 10, 200, 60]}]}}
    assert ck.selling_points_problems({"C1": "M1"}, m) == []
    assert any("C2" in p for p in ck.selling_points_problems({"C2": "M1"}, m))               # no text block carries it
    assert any("M2" in p for p in ck.selling_points_problems({"C3": "M2"}, m))               # its image was never made
    m["M1"]["texts"][0]["box"] = None
    assert any("C1" in p for p in ck.selling_points_problems({"C1": "M1"}, m))               # written in the plan, never laid out
    m["M1"]["texts"][0]["box"] = [10, 10, 900, 60]
    assert any("C1" in p for p in ck.selling_points_problems({"C1": "M1"}, m))               # runs off the frame

def test_the_report_lists_rules_not_confirmed_against_current_tmall_guidance():              # checklist P3.22
    assert ck.build_report("m1", full(), not_confirmed=["main_image.max_kb"])["not_confirmed"] == ["main_image.max_kb"]
    assert ck.build_report("m1", full())["not_confirmed"] == []

R = lambda v: {"value": v, "status": "proposal", "source": "stand-in"}
STAND_IN_RULES = {"layers": {"contrast_min": R(4.5)}, "text": {"min_px_main": R(21), "min_px_detail": R(21)},
                  "thumbnail": {"px": R(256), "min_headline_px": R(12)}, "diagnosis": {"product_height_min": R(0.6), "glare_max_share": R(0.02)},
                  "main_image": {"sizes": R([[800, 800]]), "max_kb": R(500)}, "detail": {"max_kb": R(500), "width": R(790)},
                  "words": {"banned": R(["第一"]), "after_state": R(["焕发光泽"])}, "bonded": {"must_not": R(["国内现货"])}}
LOCK = {"palette": ["#FFFFFF", "#1E3A5F"], "font": "Noto Sans CJK SC", "layout": "grid"}

def test_text_off_the_style_lock_is_named():                                                  # spec stage 5: later images inherit palette and type
    t = [{"id": "h", "font": "Noto Sans CJK SC", "color": "#ffffff"}]
    assert ck.style_problems(t, LOCK) == []
    assert any("colour #C9A227" in p for p in ck.style_problems([dict(t[0], color="#C9A227")], LOCK))
    assert any("Noto Serif CJK SC" in p for p in ck.style_problems([dict(t[0], font="Noto Serif CJK SC")], LOCK))

def test_gather_runs_every_measured_check_on_a_composed_stand_in_image(tmp_path, chromium):
    import tmall_compose as comp
    from PIL import Image, ImageDraw
    Image.linear_gradient("L").resize((800, 800)).convert("RGB").save(tmp_path / "scene.png")
    pack = Image.new("RGBA", (200, 400), (0, 0, 0, 0)); ImageDraw.Draw(pack).rounded_rectangle((10, 10, 190, 390), 20, fill=(30, 80, 160, 255)); pack.save(tmp_path / "pack.png")
    text = [{"id": "headline", "text": "每天一勺", "tier": "headline", "x": 40, "y": 40, "w": 720, "px": 64, "color": "#ffffff",
             "font": "Noto Sans CJK SC", "weight": 700, "claims": ["C1"]}]
    m = comp.compose(tmp_path / "out", "M1", scene=tmp_path / "scene.png", size=(800, 800), texts=text,
                     pack={"file": tmp_path / "pack.png", "height": 480, "cx": 400, "bottom": 720})
    sheet = {"claims": [{"id": "C1", "text": "每天一勺"}], "forbidden": [{"text": "治疗", "source": "s"}],
             "inventory": [{"file": "pack.png", "angle": "front", "use": "use as is"}]}
    report = ck.gather(tmp_path / "out", manifest=m, rules=STAND_IN_RULES, sheet=sheet, selling_points={"C1": "M1"}, plan_problems=[],
                       allowed_prices=set(), bundle_rows=[], competitor_strings=["BrandX"], style_lock=LOCK)
    assert set(report["results"]) == set(ck.CHECKS) - set(ck.LOOKED) - {"compliance_quality_gate"}
    assert report["complete"] is False and set(ck.LOOKED) <= set(report["missing"])           # looked verdicts and the held quality check are never made up here
    for name in ("claims", "prices", "selling_points_visible", "layers_overlap", "layers_contrast", "pack",
                 "font_licence", "text_size", "no_copying", "size_weight", "compliance_tmall_rules", "style_lock"):
        assert report["results"][name]["verdict"] == "pass", report["results"][name]
    assert "layout" not in report["results"] and report["not_confirmed"]                      # no text-card layout verdict (see the card_audit test below); every stand-in rule is a proposal
    # reviewed-plan audit pass 1: two mutants survived here, a report with no fingerprint (every page would then refuse every image)
    # and an unreadable layout answer passing on exit 0
    import tmall_common as common
    assert report["image_sha256"] == common.sha256(tmp_path / "out" / "M1.png")

def test_the_smallest_readable_type_is_worked_out_for_the_width_of_the_main_image(tmp_path, chromium):
    # issue 09: Tmall's published guides allow a 1440-wide main image as well as an 800-wide one. 30 px type is fine on 800 wide
    # (minimum 21) and too small on 1440 wide (minimum 38); the shipped rules file carries both minimums.
    import tmall_compose as comp, tmall_rules
    from PIL import Image
    shipped = tmall_rules.load()
    sheet = {"claims": [{"id": "C1", "text": "每天一勺"}], "forbidden": [], "inventory": []}
    verdicts = {}
    for width in (800, 1440):
        Image.linear_gradient("L").resize((width, width)).convert("RGB").save(tmp_path / f"scene{width}.png")
        text = [{"id": "headline", "text": "每天一勺", "tier": "headline", "x": width // 20, "y": width // 20, "w": width * 9 // 10, "px": 30,
                 "color": "#ffffff", "font": "Noto Sans CJK SC", "weight": 700, "claims": ["C1"]}]
        m = comp.compose(tmp_path / f"out{width}", "M1", scene=tmp_path / f"scene{width}.png", size=(width, width), texts=text)
        report = ck.gather(tmp_path / f"out{width}", manifest=m, rules=shipped, sheet=sheet, selling_points={"C1": "M1"}, plan_problems=[],
                           allowed_prices=set(), bundle_rows=[], competitor_strings=[], style_lock=LOCK)
        verdicts[width] = report["results"]["text_size"]
    assert verdicts[800]["verdict"] == "pass", verdicts[800]
    assert verdicts[1440]["verdict"] == "fail" and "minimum 38 px" in verdicts[1440]["note"], verdicts[1440]

def test_gather_names_each_failing_check_when_the_stand_in_image_breaks_the_rules(tmp_path, chromium):
    # The pass test above cannot tell a wired check from a dead one (audit pass 2: three mutants that made `_result` always pass,
    # dropped the no-copying call and dropped the bonded-wording call all survived it), so the failing path is run too.
    import tmall_compose as comp
    from PIL import Image, ImageDraw
    Image.linear_gradient("L").resize((800, 800)).convert("RGB").save(tmp_path / "scene.png")
    pack = Image.new("RGBA", (200, 400), (0, 0, 0, 0)); ImageDraw.Draw(pack).rounded_rectangle((10, 10, 190, 390), 20, fill=(30, 80, 160, 255)); pack.save(tmp_path / "pack.png")
    text = [{"id": "headline", "text": "第一 国内现货 BrandX 能治疗", "tier": "headline", "x": 40, "y": 40, "w": 720, "px": 12, "color": "#ffffff",
             "font": "Noto Sans CJK SC", "weight": 700, "claims": ["C9"]}]
    m = comp.compose(tmp_path / "bad", "M1", scene=tmp_path / "scene.png", size=(800, 800), texts=text,
                     pack={"file": tmp_path / "pack.png", "height": 480, "cx": 400, "bottom": 720})
    sheet = {"claims": [{"id": "C1", "text": "每天一勺"}], "forbidden": [{"text": "治疗", "source": "s"}],
             "inventory": [{"file": "other.png", "angle": "front", "use": "use as is"}]}           # the pack laid on this image is not in the inventory
    report = ck.gather(tmp_path / "bad", manifest=m, rules=STAND_IN_RULES, sheet=sheet, selling_points={"C1": "M1"}, plan_problems=[],
                       allowed_prices=set(), bundle_rows=[], competitor_strings=["BrandX"], style_lock=LOCK)
    assert report["passed"] is False
    for name in ("claims", "selling_points_visible", "compliance_tmall_rules", "no_copying", "text_size", "thumbnail", "pack"):
        assert report["results"][name]["verdict"] == "fail", (name, report["results"][name])
    assert "第一" in report["results"]["compliance_tmall_rules"]["note"] and "国内现货" in report["results"]["compliance_tmall_rules"]["note"]
    assert "BrandX" in report["results"]["no_copying"]["note"] and "inventory" in report["results"]["pack"]["note"]

def test_gather_fails_the_layer_price_size_font_and_plan_checks_the_first_bad_image_does_not_reach(tmp_path, chromium):
    # Audit pass 3: with `gather` as first tested, 13 of its 18 checks could each be forced to pass (prices, scenes, comparison, layers_overlap,
    # layers_contrast, layers_light, layers_shadow_surface, thumbnail, diagnosis_frame, pack, layout, size_weight, font_licence) and every test stayed green.
    import copy, tmall_compose as comp
    from decimal import Decimal as D
    from PIL import Image, ImageDraw
    Image.linear_gradient("L").rotate(90).resize((800, 800)).convert("RGB").save(tmp_path / "scene.png")        # dark on the left, bright on the right
    pack = Image.new("RGBA", (200, 400), (0, 0, 0, 0)); draw = ImageDraw.Draw(pack)
    draw.rounded_rectangle((10, 10, 100, 390), 20, fill=(250, 250, 250, 255)); draw.rectangle((100, 10, 190, 390), fill=(20, 20, 20, 255))  # lit from the left
    pack.save(tmp_path / "pack.png")
    text = [{"id": "headline", "text": "每天约3.99元", "tier": "headline", "x": 360, "y": 600, "w": 400, "px": 64, "color": "#ffffff",
             "font": "Noto Sans CJK SC", "weight": 700, "claims": ["C1"]}]                       # white on a light backdrop, over a small pack
    m = comp.compose(tmp_path / "bad", "M1", scene=tmp_path / "scene.png", size=(800, 800), texts=text,
                     pack={"file": tmp_path / "pack.png", "height": 200, "cx": 400, "bottom": 720})
    sheet = {"claims": [{"id": "C1", "text": "每天一勺"}], "forbidden": [], "inventory": [{"file": "pack.png", "angle": "front", "use": "use as is"}]}
    rules = copy.deepcopy(STAND_IN_RULES); rules["main_image"]["max_kb"] = R(0.001)
    plan = ["M1: scene implies a result (焕发光泽)", "M1: names a competitor without verified facts"]
    kw = dict(sheet=sheet, selling_points={"C1": "M1"}, plan_problems=plan, allowed_prices={D("3.98")}, bundle_rows=[], competitor_strings=[], style_lock=LOCK)
    report = ck.gather(tmp_path / "bad", manifest=m, rules=rules, **kw)
    for name in ("prices", "scenes", "comparison", "layers_overlap", "layers_contrast", "layers_light", "layers_shadow_surface",
                 "diagnosis_frame", "size_weight"):
        assert report["results"][name]["verdict"] == "fail", (name, report["results"][name])
    assert "3.99" in report["results"]["prices"]["note"]
    m2 = copy.deepcopy(m); m2["texts"][0]["font"] = "Comic Sans"
    assert ck.gather(tmp_path / "bad", manifest=m2, rules=rules, **kw)["results"]["font_licence"]["verdict"] == "fail"
    off_lock = dict(kw, style_lock=dict(LOCK, palette=["#1E3A5F"]))                                        # white text, lock without white
    assert ck.gather(tmp_path / "bad", manifest=m, rules=rules, **off_lock)["results"]["style_lock"]["verdict"] == "fail"
    # behaviour 9: after a ruling bumps the lock to version 2, an image made under an older lock fails (reviewed-plan audit pass 1:
    # a mutant that dropped this check survived every test, though the Test Plan Artifact named it)
    stale = dict(kw, style_lock=dict(LOCK, version=2))
    assert "version" in ck.gather(tmp_path / "bad", manifest=m, rules=rules, **stale)["results"]["style_lock"]["note"]
    m3 = copy.deepcopy(m); m3["style_lock_version"] = 2
    assert ck.gather(tmp_path / "bad", manifest=m3, rules=rules, **stale)["results"]["style_lock"]["verdict"] == "pass"
    # a detail slice is held to the 790 width in stage 6, not only at handover
    d = comp.compose(tmp_path / "wide", "D1", scene=tmp_path / "scene.png", size=(700, 1200), texts=[])
    wide = ck.gather(tmp_path / "wide", manifest=d, rules=STAND_IN_RULES, sheet=sheet, selling_points={}, plan_problems=[],
                     allowed_prices=set(), bundle_rows=[], competitor_strings=[], style_lock=LOCK)
    assert wide["results"]["size_weight"]["verdict"] == "fail" and "790" in wide["results"]["size_weight"]["note"]

def test_gather_never_consults_the_text_card_layout_check(tmp_path, chromium, monkeypatch):
    # The owner, 2026-10-28, asked whether Easel's card layout check (card_audit.py) applies to Tmall pack-and-scene images:
    # "Leave it out for Tmall (Recommended)". It is neither a named check nor run, and its verdict is not passed through.
    import subprocess, tmall_compose as comp
    from PIL import Image, ImageDraw
    assert "layout" not in ck.CHECKS and not hasattr(ck.ly, "card_audit")
    Image.linear_gradient("L").resize((800, 800)).convert("RGB").save(tmp_path / "scene.png")
    pack = Image.new("RGBA", (200, 400), (0, 0, 0, 0)); ImageDraw.Draw(pack).rounded_rectangle((10, 10, 190, 390), 20, fill=(30, 80, 160, 255)); pack.save(tmp_path / "pack.png")
    text = [{"id": "headline", "text": "每天一勺", "tier": "headline", "x": 40, "y": 40, "w": 720, "px": 64, "color": "#ffffff",
             "font": "Noto Sans CJK SC", "weight": 700, "claims": ["C1"]}]
    m = comp.compose(tmp_path / "out", "M1", scene=tmp_path / "scene.png", size=(800, 800), texts=text,
                     pack={"file": tmp_path / "pack.png", "height": 480, "cx": 400, "bottom": 720})
    real_run = subprocess.run
    def guard(args, *a, **k):
        assert "card_audit" not in " ".join(map(str, args)), args       # a call to the text-card check fails the test
        return real_run(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", guard)
    sheet = {"claims": [{"id": "C1", "text": "每天一勺"}], "forbidden": [], "inventory": [{"file": "pack.png", "angle": "front", "use": "use as is"}]}
    report = ck.gather(tmp_path / "out", manifest=m, rules=STAND_IN_RULES, sheet=sheet, selling_points={"C1": "M1"}, plan_problems=[],
                       allowed_prices=set(), bundle_rows=[], competitor_strings=[], style_lock=LOCK)
    assert "layout" not in report["results"]
