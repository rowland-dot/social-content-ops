import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import importlib.util, re
import pytest
import web.app as web

SKILL = SCRIPTS.parent / "SKILL.md"
def _validator():
    spec = importlib.util.spec_from_file_location("validate_skills", ROOT / "scripts" / "validate_skills.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def text(): return SKILL.read_text(encoding="utf-8")

def test_skill_passes_the_contract_check_and_is_listed_under_produce():
    assert _validator().validate(SKILL) == []
    assert _validator().validate_output_layout_references() == []
    listed = [s for s in web.get_skills() if s["name"] == "tmall-product-content"]
    assert len(listed) == 1 and listed[0]["layer"] == "produce"

def test_description_leads_with_tmall_triggers_and_refuses_the_old_skill():
    d = next(s for s in web.get_skills() if s["name"] == "tmall-product-content")["description"]
    assert "天猫" in d and "主图" in d and "商详页" in d and "ecom-details-image" in d

def test_every_script_the_page_names_exists_and_every_stage_is_covered():
    for s in re.findall(r"`(scripts/tmall_[a-z_]+\.py)`", text()):
        assert (SKILL.parent / s).is_file(), s
    for n in range(1, 9):
        assert f"references/stage-{n}-" in text()

def test_the_page_names_the_python_other_skills_use_and_carries_the_error_table_and_the_example():
    t = text()
    assert "python3 " not in t and f"python {SCRIPTS.relative_to(ROOT).as_posix()}/" in t
    for name in ("NEXT_STEP", "HeldError", "PaidRouteRefused", "PackNeedsCutout", "FontNotLicensed"):
        assert name in t, name
    example = (SKILL.parent / "references" / "stage-5-images.md").read_text(encoding="utf-8")
    assert "gather(" in example and "load_state" in example and "save_state" in example and "tmall_page.py report" in example
    assert example.count("style_lock_version") >= 2          # passed to compose and, as the lock's version, to gather
    assert "headline/A/M1.png" in t + example                # where the three headline versions go (reviewed-plan audit pass 2)
    assert "promote_pick" in t + example                     # and how the picked one joins the other images (reviewed-plan audit pass 3)

def test_the_live_steps_are_marked_held_until_the_hold_file_says_otherwise():
    t = text()
    assert "HELD" in t and "references/held.json" in t and "issue 94" in t and "issue 95" in t
    assert "ecom-details-image" in t and "never" in t.lower()

def test_the_page_states_the_rules_that_bind_it():
    t = text()
    for needle in ("包装上印的字不检查", "不付费", "知识库", "先看三个封面", "只通过 Easel 改"):
        assert needle in t, needle

def test_the_card_layout_check_is_not_listed_as_a_tmall_check():
    # The owner, 2026-10-28, through the question tool: "Leave it out for Tmall (Recommended)"
    t = text()
    assert "card_audit" not in t and "不用于天猫" in t

def test_the_worked_example_runs_against_stand_in_inputs_and_its_report_page_command_works(tmp_path, chromium):
    # The skill page promises "one complete, working example"; this runs it, so a renamed function or a changed argument breaks here.
    import json, subprocess
    from PIL import Image, ImageDraw
    code = re.search(r"```python\n(.*?)\n```", (SKILL.parent / "references" / "stage-5-images.md").read_text(encoding="utf-8"), re.S).group(1)
    packs = tmp_path / "packs"; packs.mkdir()
    pack = Image.new("RGBA", (200, 400), (0, 0, 0, 0)); ImageDraw.Draw(pack).rounded_rectangle((10, 10, 190, 390), 20, fill=(30, 80, 160, 255)); pack.save(packs / "pack.png")
    note = tmp_path / "note.md"; note.write_text("## Listing 1\n### 主打卖点 Headline claims\n- 第一品牌\n", encoding="utf-8")
    code = re.sub(r'(?m)^PACK_DIR = .*$', f"PACK_DIR = Path({str(packs)!r})", code)
    code = re.sub(r'(?m)^NOTE = .*$', f"NOTE = Path({str(note)!r})", code)
    script = tmp_path / "example.py"; script.write_text(code, encoding="utf-8")
    product = tmp_path / "product"; (product / "scenes").mkdir(parents=True)
    for k in "ABC":
        Image.linear_gradient("L").resize((800, 800)).convert("RGB").save(product / "scenes" / f"M1-{k}.png")
    (product / "fact-sheet.json").write_text(json.dumps({"facts": [], "claims": [{"id": "C1", "text": "每天一勺"}], "forbidden": [],
                                                          "inventory": [{"file": "pack.png", "angle": "front", "use": "use as is"}]}), encoding="utf-8")
    (product / "plan.json").write_text(json.dumps({"style_lock": {"palette": ["#ffffff"], "font": "Noto Sans CJK SC", "layout": "grid"},
                                                    "main_size": [800, 800], "selling_point_map": {"C1": "M1"}}), encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, *map(str, a)], cwd=ROOT, capture_output=True, text=True)
    r = run(script, product)
    assert r.returncode == 0, r.stderr
    reports = json.loads((product / "check-reports.json").read_text(encoding="utf-8"))["reports"]
    assert sorted(reports) == ["M1-A", "M1-B", "M1-C"] and all(r["image_sha256"] for r in reports.values())
    assert all((product / "headline" / k / "M1.png").is_file() for k in "ABC") and json.loads((product / "flow.json").read_text(encoding="utf-8"))["style_lock_version"] == 1
    page = run(SCRIPTS / "tmall_page.py", "report", product)
    assert page.returncode == 0, page.stderr
    assert (product / "check-report.html").is_file()
