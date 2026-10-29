import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

from PIL import Image
import tmall_capture as cap, tmall_note as note

def test_deposit_uses_only_the_knowledge_base_tool_under_windows_python_and_keeps_the_item_number(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "to_windows", lambda p: "WIN:" + str(p))      # the test folder is not under /mnt/c, so mark the conversion to see it used
    out = tmp_path / "out"; (out / "111").mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(out / "111" / "main_00.jpg")
    note_file = tmp_path / "note.md"; note_file.write_text("# n", encoding="utf-8")
    calls = []
    names = cap.deposit(out, brand="acme", cat="05", by="easel-tmall", note=note_file, runner=lambda cmd, **k: calls.append((cmd, k.get("cwd"))))
    assert names == ["111_main_00.jpg", "note.md"]                     # the item number travels in the file name; the note goes with the images
    cmd, cwd = calls[0]
    assert cmd[0] == cap.CLIENTKB_PYTHON and cmd[1:4] == ["-m", "clientkb", "add"] and cmd[4].startswith("WIN:") and Path(cmd[4]).name == "111_main_00.jpg"
    assert cmd[cmd.index("--brand") + 1] == "acme" and cmd[cmd.index("--cat") + 1] == "05" and "--by" in cmd
    assert str(cwd).endswith("clientkb")
    assert (out / "111" / "main_00.jpg").is_file()                     # the capture itself is left where it was

def test_a_failed_filing_says_how_far_it_got_and_that_a_rerun_is_safe(tmp_path):
    import subprocess, pytest
    out = tmp_path / "out"; (out / "111").mkdir(parents=True)
    for n in ("main_00.jpg", "main_01.jpg"): Image.new("RGB", (10, 10)).save(out / "111" / n)
    def runner(cmd, **k):
        if cmd[4].endswith("main_01.jpg"): raise subprocess.CalledProcessError(1, cmd)
    with pytest.raises(RuntimeError, match=r"after 1 of 2 files.*running deposit again is safe"):
        cap.deposit(out, brand="acme", cat="05", by="x", runner=runner)

def test_a_missing_windows_python_stops_before_anything_is_filed(tmp_path, monkeypatch):     # reviewed-plan audit pass 1: a mutant without this check survived
    out = tmp_path / "out"; (out / "111").mkdir(parents=True); Image.new("RGB", (10, 10)).save(out / "111" / "main_00.jpg")
    monkeypatch.setattr(cap, "CLIENTKB_PYTHON", str(tmp_path / "no-python.exe"))
    import pytest
    with pytest.raises(FileNotFoundError, match="TMALL_CLIENTKB_PYTHON"):
        cap.deposit(out, brand="acme", cat="05", by="x")              # the real runner: the check stops it before any call

def test_wsl_paths_become_windows_paths_for_the_windows_only_tool():
    assert cap.to_windows("/mnt/c/Users/x/a b/c.jpg") == "C:\\Users\\x\\a b\\c.jpg"
    assert cap.to_windows("C:\\Users\\x\\c.jpg") == "C:\\Users\\x\\c.jpg"

def test_the_commands_the_live_steps_name_exist(tmp_path):
    import subprocess, sys
    for args in (["run", "--help"], ["deposit", "--help"], ["trial-sheet", "--help"]):
        r = subprocess.run([sys.executable, str(SCRIPTS / "tmall_capture.py"), *args], capture_output=True, text=True)
        assert r.returncode == 0, (args, r.stderr)
    f = tmp_path / "n.md"; f.write_text(NOTE, encoding="utf-8")
    ok = subprocess.run([sys.executable, str(SCRIPTS / "tmall_note.py"), "check", str(f), "111", "222"], capture_output=True, text=True)
    assert ok.returncode == 0 and "OK" in ok.stdout
    bad = subprocess.run([sys.executable, str(SCRIPTS / "tmall_note.py"), "check", str(f), "333"], capture_output=True, text=True)
    assert bad.returncode == 1 and "333" in bad.stdout

def test_trial_sheet_is_a_page_listing_each_listing_with_its_images(tmp_path):
    out = tmp_path / "out"
    for i in ("111", "222"):
        (out / i).mkdir(parents=True); Image.new("RGB", (10, 10)).save(out / i / "main_00.jpg")
    Image.new("RGB", (10, 10)).save(out / "111" / "detail_00.jpg")
    page = cap.trial_sheet(out, {"items": [{"rank": 1, "id": "111", "main_saved": 1, "detail_saved": 1},
                                           {"rank": 2, "id": "222", "main_saved": 1, "detail_saved": 0},
                                           {"rank": 3, "id": "333", "blocked": "captcha on page"}], "stopped": "item 333: captcha on page"})
    text = page.read_text(encoding="utf-8")
    assert page.name == "trial-sheet.html" and "111/main_00.jpg" in text and "111/detail_00.jpg" in text
    assert "Stopped here: captcha on page" in text and "Detail page: 0 saved" in text

NOTE = """# Pattern note
## Listing 111
### 主图分工 Main-image jobs
x
### 详情页屏序 Screen order
x
### 主打卖点 Headline claims
x
### 证明方式 Proof style
x
## Listing 222
### 主图分工 Main-image jobs
x
### 详情页屏序 Screen order
x
### 主打卖点 Headline claims
x
### 证明方式 Proof style
x
"""
def test_strings_our_copy_must_not_repeat_come_from_headline_claims_and_names_and_badges():
    text = "## Listing 1\n### 主打卖点 Headline claims\n- 第一品牌\n- 三倍吸收\n### 品牌名与徽标 Names and badges\n- BrandX\n### 证明方式 Proof style\nx\n"
    assert note.competitor_strings(text) == ["第一品牌", "三倍吸收", "BrandX"]

def test_pattern_note_must_cover_every_captured_listing_with_the_four_parts():
    assert note.check(NOTE, ["111", "222"]) == []
    assert any("333" in p for p in note.check(NOTE, ["111", "222", "333"]))
    assert any("Proof style" in p for p in note.check(NOTE.replace("### 证明方式 Proof style\nx\n## Listing 222", "## Listing 222"), ["111", "222"]))
