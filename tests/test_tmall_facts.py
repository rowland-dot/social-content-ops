import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import copy, pytest
import tmall_facts as facts

GOOD = {"product": "demo-powder",
        "facts": [{"id": "F1", "kind": "dose", "text": "10 g a day", "source": "website", "status": "settled", "conflict": []}],
        "claims": [{"id": "C1", "text": "每天一勺", "fact_ids": ["F1"], "source": "website"}],
        "forbidden": [{"text": "治疗", "source": "compliance floor"}],
        "shipping": {"route": "bonded warehouse in China", "source": "The owner"},
        "inventory": [{"file": "front.png", "angle": "front", "use": "use as is"}]}

def test_a_complete_sheet_has_no_problems():
    assert facts.validate(GOOD) == []

@pytest.mark.parametrize("edit,expect", [
    (lambda s: s["facts"][0].update(source=""), "F1: no source"),
    (lambda s: s["claims"][0].update(source=""), "C1: no source"),
    (lambda s: s["claims"][0].update(fact_ids=["F9"]), "C1: unknown fact F9"),
    (lambda s: s["facts"][0].update(status="waiting_on_ro"), "C1: rests on F1, which is waiting on the owner"),
    (lambda s: s.update(forbidden=[]), "no forbidden claims listed"),
    (lambda s: s.pop("shipping"), "no shipping route"),
    (lambda s: s["inventory"][0].update(angle="diagonal"), "front.png: angle"),
    (lambda s: s["inventory"][0].update(use="redraw"), "front.png: use"),
])
def test_each_gap_is_named(edit, expect):
    s = copy.deepcopy(GOOD); edit(s)
    assert any(expect in p for p in facts.validate(s)), facts.validate(s)

def test_the_website_wins_and_the_other_source_is_kept_as_a_conflict():
    out = facts.settle("spec", [{"source_type": "website", "source": "site", "text": "500 g"},
                                {"source_type": "toolkit", "source": "kit", "text": "450 g"}])
    assert out["status"] == "settled" and out["text"] == "500 g"
    assert out["conflict"] == [{"source": "kit", "text": "450 g"}]

def test_without_the_website_disagreement_waits_on_ro():
    out = facts.settle("spec", [{"source_type": "toolkit", "source": "kit", "text": "450 g"},
                                {"source_type": "copy", "source": "cn", "text": "500 g"}])
    assert out["status"] == "waiting_on_ro"

def test_prices_ignore_the_website_and_need_both_list_copies_to_agree():
    two = [{"source_type": "price_list", "source": "Feb", "text": "300.00"},
           {"source_type": "price_list", "source": "Jul", "text": "300.00"}]
    assert facts.settle("price", two)["status"] == "settled"
    differ = two[:1] + [{"source_type": "price_list", "source": "Jul", "text": "310.00"}]
    waiting = facts.settle("price", differ + [{"source_type": "website", "source": "s", "text": "300.00"}])
    assert waiting["status"] == "waiting_on_ro" and waiting["text"] == "300.00 (Feb) or 310.00 (Jul)"   # each value beside the copy that gave it
    assert facts.settle("price", two[:1])["status"] == "waiting_on_ro"
    assert facts.settle("price", [dict(two[0], text="300"), two[1]])["status"] == "settled"          # the same money written two ways
    site = {"source_type": "website", "source": "s", "text": "300.00"}
    assert facts.settle("price", two[:1] + [site])["status"] == "waiting_on_ro"        # the website cannot stand in for the second list copy (The owner: prices come only from the price list)

def test_render_lists_waiting_items_first(tmp_path):
    s = copy.deepcopy(GOOD)
    s["facts"].append({"id": "F2", "kind": "price", "text": "300.00 or 310.00", "source": "price list", "status": "waiting_on_ro", "conflict": []})
    md = facts.render(s)
    assert md.index("Waiting on the owner") < md.index("F1")

def test_check_and_render_commands_read_the_product_folder(tmp_path):
    import json, subprocess
    run = lambda cmd: subprocess.run([sys.executable, str(SCRIPTS / "tmall_facts.py"), cmd, str(tmp_path)], capture_output=True, text=True)
    (tmp_path / "fact-sheet.json").write_text(json.dumps(GOOD), encoding="utf-8")
    r = run("check"); assert r.returncode == 0 and r.stdout.strip() == "OK"
    assert run("render").returncode == 0 and "## Allowed claims" in (tmp_path / "fact-sheet.md").read_text(encoding="utf-8")
    bad = copy.deepcopy(GOOD); bad["forbidden"] = []
    (tmp_path / "fact-sheet.json").write_text(json.dumps(bad), encoding="utf-8")
    r = run("check"); assert r.returncode == 1 and "no forbidden claims listed" in r.stdout
