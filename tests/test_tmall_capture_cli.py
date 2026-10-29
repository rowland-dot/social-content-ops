import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import json
import output_paths
import tmall_capture as cap

# The command line is what the owner's agent actually types in the live steps, so each command is driven here through main(), with the
# browser run and the knowledge-base call replaced by recorders (the run itself is proved against the stand-in site elsewhere).

def test_run_prints_a_summary_and_exits_with_the_code_of_the_kind_of_stop(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(output_paths, "validate_output_path", lambda p, **k: Path(p))
    seen = {}
    def fake_run(**kw):
        seen.update(kw)
        return {"items": [{}], "stopped": "item 1: captcha on page", "stop_kind": "wall", "incomplete": []}
    monkeypatch.setattr(cap, "run_capture", fake_run)
    code = cap.main(["run", "--query", "q", "--trial", "--top", "10", "--out", str(tmp_path / "out"), "--exclude", "9"])
    assert code == cap.NEXT_STEP["wall"][0]
    assert seen["top_n"] == 3 and seen["exclude"] == ["9"]                       # --trial is always the top three, whatever --top says
    assert json.loads(capsys.readouterr().out)["stopped"] == "item 1: captcha on page"

def test_run_exits_zero_when_nothing_stopped_it_and_names_incomplete_listings_otherwise(tmp_path, monkeypatch):
    monkeypatch.setattr(output_paths, "validate_output_path", lambda p, **k: Path(p))
    monkeypatch.setattr(cap, "run_capture", lambda **kw: {"items": [], "stopped": None, "stop_kind": None, "incomplete": []})
    assert cap.main(["run", "--query", "q", "--out", str(tmp_path)]) == 0
    monkeypatch.setattr(cap, "run_capture", lambda **kw: {"items": [], "stopped": None, "stop_kind": None, "incomplete": ["1"]})
    assert cap.main(["run", "--query", "q", "--out", str(tmp_path)]) == cap.NEXT_STEP["incomplete"][0]

def test_trial_sheet_command_writes_the_page_from_the_capture_report(tmp_path, capsys):
    (tmp_path / "capture-report.json").write_text(json.dumps({"items": [{"rank": 1, "id": "1", "main_saved": 0, "detail_saved": 0}], "stopped": None}), encoding="utf-8")
    assert cap.main(["trial-sheet", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "trial-sheet.html").is_file() and "trial-sheet.html" in capsys.readouterr().out

def test_deposit_command_hands_the_note_and_brand_through_and_lists_what_was_filed(tmp_path, monkeypatch, capsys):
    got = {}
    monkeypatch.setattr(cap, "deposit", lambda out, **kw: (got.update(kw), ["111_main_00.jpg"])[1])
    assert cap.main(["deposit", "--out", str(tmp_path), "--brand", "acme", "--cat", "05", "--note", "n.md"]) == 0
    assert got == {"brand": "acme", "cat": "05", "by": "easel-tmall", "note": "n.md"} and "111_main_00.jpg" in capsys.readouterr().out

def test_a_search_that_throws_is_recorded_as_an_error_stop(tmp_path):
    class Page:
        def goto(self, *a, **k): raise TimeoutError("slow")
    class Ctx:
        def new_page(self): return Page()
        def close(self): pass
    report = cap.run_capture(out_dir=tmp_path, query="q", top_n=1, pacer=None, open_context=lambda p: Ctx())
    assert report["stop_kind"] == "error" and "slow" in report["stopped"]
