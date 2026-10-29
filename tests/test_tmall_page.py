import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

from html.parser import HTMLParser
from PIL import Image
import pytest
import tmall_page as pg

class Collect(HTMLParser):
    def __init__(self): super().__init__(); self.tags = []
    def handle_starttag(self, tag, attrs): self.tags.append((tag, dict(attrs)))

def parse(text): c = Collect(); c.feed(text); return c.tags

import tmall_common as common

def ok(folder, image):
    """A passed report for these exact image bytes, as tmall_checks.gather writes it."""
    import tmall_checks
    results = {c: {"check": c, "verdict": "pass", "method": "measured", "evidence": "crop.png" if c in tmall_checks.LOOKED else None} for c in tmall_checks.CHECKS}
    return {"complete": True, "passed": True, "image_sha256": common.sha256(folder / image), "results": results, "missing": [], "failed": []}

def product(tmp_path, n_main=2, n_detail=2):
    for i in range(1, n_main + 1): Image.new("RGB", (800, 800), "white").save(tmp_path / f"m{i}.png")
    for i in range(1, n_detail + 1): Image.new("RGB", (790, 600), "white").save(tmp_path / f"d{i}.png")
    items = [{"id": f"M{i}", "kind": "main", "image": f"m{i}.png", "copy": f"文案{i}", "sources": [f"fact {i}: website"]} for i in range(1, n_main + 1)]
    items += [{"id": f"D{i}", "kind": "detail", "image": f"d{i}.png", "copy": f"详情{i}", "sources": [f"fact {i}: price list"]} for i in range(1, n_detail + 1)]
    return items

def passed(tmp_path, items):
    return {i["id"]: ok(tmp_path, i["image"]) for i in items}

def test_page_shows_every_image_with_its_copy_and_its_sources_at_phone_width(tmp_path):
    items = product(tmp_path)
    html_text = pg.build_approval(tmp_path, items, passed(tmp_path, items))
    tags = parse(html_text)
    assert sum(1 for t, a in tags if "main-image" in a.get("class", "")) == 2
    assert sum(1 for t, a in tags if "detail-screen" in a.get("class", "")) == 2
    assert "文案1" in html_text and "fact 2: price list" in html_text and "width:375px" in html_text.replace(" ", "")
    for t, a in tags:
        if t == "img":
            assert not a["src"].startswith(("/", "http")) and (tmp_path / a["src"]).is_file()
            assert a["alt"]                                       # the image's words are its text alternative
    assert "lang='zh'" in html_text and "max-width:420px" in html_text
    assert ".phone{width:375px;max-width:100%" in html_text          # a 360 px phone must not scroll sideways (audit pass 3: the page was 375 px wide at a 360 px screen)

def test_copy_and_sources_are_escaped_not_run_as_markup(tmp_path):
    items = product(tmp_path); items[0]["sources"] = ["fact 1: <b>site</b> & list"]; items[0]["copy"] = "<i>文案</i>"
    text = pg.build_approval(tmp_path, items, passed(tmp_path, items))
    assert "<b>site</b>" not in text and "<i>文案</i>" not in text and "&lt;b&gt;site&lt;/b&gt; &amp; list" in text

def test_a_page_with_an_unchecked_image_is_refused_and_says_what_is_wrong(tmp_path):
    items = product(tmp_path)
    reports = passed(tmp_path, items); reports["M2"] = {"complete": True, "passed": False, "failed": ["layers_contrast"], "missing": []}
    del reports["D1"]
    with pytest.raises(pg.NotCheckedError, match=r"M2: failed layers_contrast.*D1: no check report"):
        pg.build_approval(tmp_path, items, reports)

def test_a_passed_report_for_another_version_of_the_image_or_a_hand_written_pass_is_refused(tmp_path):
    # Autoplan review: the gate used to trust any "passed" written into the file, so a round-1 report passed a round-2 image.
    items = product(tmp_path); reports = passed(tmp_path, items)
    Image.new("RGB", (800, 800), "black").save(tmp_path / "m1.png")                   # remade after its report was written
    with pytest.raises(pg.NotCheckedError, match="M1.*another version"):
        pg.build_approval(tmp_path, items, reports)
    with pytest.raises(pg.NotCheckedError, match="M1"):
        pg.build_approval(tmp_path, items, {**reports, "M1": {"complete": True, "passed": True}})
    with pytest.raises(pg.NotCheckedError, match="M1"):                                # a hand-written report missing keys is refused, not a KeyError
        pg.build_approval(tmp_path, items, {**reports, "M1": {"passed": True}})

def test_images_carry_the_names_ro_uses_and_unconfirmed_rules_are_shown(tmp_path):
    items = product(tmp_path)
    text = pg.build_approval(tmp_path, items, passed(tmp_path, items), not_confirmed=["main_image.max_kb"])
    assert text.index("主图1") < text.index("主图2") < text.index("详情第1屏") < text.index("详情第2屏")
    assert "main_image.max_kb" in text and "尚未" in text

def versions(tmp_path):
    out = {}
    for i, (k, d) in enumerate(zip("ABC", ("close-up", "flat lay", "in use")), 1):
        Image.new("RGB", (800, 800), "white").save(tmp_path / f"{k}.png")
        out[k] = {"image": f"{k}.png", "direction": d, "listing_id": f"L{i}", "headline": f"标题{k}", "report": ok(tmp_path, f"{k}.png")}
    return out

def test_headline_page_puts_a_b_c_side_by_side_with_their_words_direction_and_listing(tmp_path):
    text = pg.build_headline(tmp_path, versions(tmp_path))
    assert [a["data-version"] for t, a in parse(text) if a.get("class") == "version"] == ["A", "B", "C"]
    assert "close-up" in text and "flat lay" in text and "in use" in text and "标题B" in text and "L3" in text
    assert sum(1 for t, a in parse(text) if a.get("class") == "thumb") == 3        # each also at search-result size
    assert "flex-direction:column" in text            # stacks on a phone-width screen

def test_headline_page_is_refused_unless_all_three_passed_their_checks(tmp_path):
    v = versions(tmp_path)
    with pytest.raises(pg.NotCheckedError, match="B"):
        pg.build_headline(tmp_path, {**v, "B": dict(v["B"], report={"complete": True, "passed": False})})
    with pytest.raises(pg.NotCheckedError, match="C"):
        pg.build_headline(tmp_path, {**v, "C": dict(v["C"], report=None)})

def test_check_report_page_says_in_words_what_failed_and_what_has_not_run(tmp_path):
    reports = {"M1": {"complete": False, "passed": False, "failed": ["layers_contrast"], "missing": ["compliance_quality_gate"],
                      "results": {"layers_contrast": {"note": "headline: contrast 2.1 to 1 is below 4.5"}}}}
    text = pg.build_check_report(reports, not_confirmed=["detail.max_kb"])
    assert "M1：未通过" in text and "contrast 2.1 to 1" in text and "compliance_quality_gate" in text and "detail.max_kb" in text
    assert "还没有检查结果" in pg.build_check_report({})
    # reviewed-plan audit pass 2: a hand-written report without "complete" or "results" crashed the report command with a KeyError
    assert "M1：未完成" in pg.build_check_report({"M1": {"passed": False}})
    assert "M1：未通过" in pg.build_check_report({"M1": {"complete": False, "passed": False, "failed": ["pack"], "missing": []}})

def test_command_line_writes_the_pages_and_refuses_an_unchecked_set(tmp_path):
    import json, subprocess, sys
    items = product(tmp_path)
    write = lambda reports: (tmp_path / "approval-items.json").write_text(json.dumps({"items": items, "reports": reports}), encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPTS / "tmall_page.py"), *a], capture_output=True, text=True)
    write(passed(tmp_path, items))
    assert run("approval", str(tmp_path)).returncode == 0 and (tmp_path / "approval.html").is_file()
    (tmp_path / "approval.html").unlink()
    write({**passed(tmp_path, items), "M2": {"complete": True, "passed": False}})
    r = run("approval", str(tmp_path))
    assert r.returncode == 2 and "M2" in r.stderr and not (tmp_path / "approval.html").exists()
    (tmp_path / "headline-versions.json").write_text(json.dumps(versions(tmp_path)), encoding="utf-8")
    assert run("headline", str(tmp_path)).returncode == 0 and (tmp_path / "headline-versions.html").is_file()
    r = run("report", str(tmp_path)); assert r.returncode == 2 and "check-reports.json" in r.stderr     # missing input is named, not a crash
    (tmp_path / "check-reports.json").write_text("{}", encoding="utf-8")                                # reviewed-plan audit pass 3: a KeyError traceback before
    r = run("report", str(tmp_path)); assert r.returncode == 2 and "'reports'" in r.stderr
    (tmp_path / "check-reports.json").write_text(json.dumps({"reports": {}, "not_confirmed": []}), encoding="utf-8")
    assert run("report", str(tmp_path)).returncode == 0 and (tmp_path / "check-report.html").is_file()


def test_a_hand_written_report_without_every_named_check_passing_is_refused(tmp_path):
    # QA 2026-10-28 (review MEDIUM): a report carrying complete/passed true and the right fingerprint opened the page even with no results at all.
    items = product(tmp_path); reports = passed(tmp_path, items)
    bare = {"complete": True, "passed": True, "image_sha256": common.sha256(tmp_path / "m1.png"), "results": {}}
    with pytest.raises(pg.NotCheckedError, match="M1"):
        pg.build_approval(tmp_path, items, {**reports, "M1": bare})
    lying = dict(reports["M2"], results=dict(reports["M2"]["results"], pack={"check": "pack", "verdict": "fail"}))      # flags say passed, the results say the pack failed
    with pytest.raises(pg.NotCheckedError, match="M2"):
        pg.build_approval(tmp_path, items, {**reports, "M2": lying})
    missing_gate = dict(reports["M2"], results={k: v for k, v in reports["M2"]["results"].items() if k != "compliance_quality_gate"})
    with pytest.raises(pg.NotCheckedError, match="M2"):
        pg.build_approval(tmp_path, items, {**reports, "M2": missing_gate})
    v = versions(tmp_path)
    with pytest.raises(pg.NotCheckedError, match="A"):
        pg.build_headline(tmp_path, {**v, "A": dict(v["A"], report=bare)})

def test_headline_versions_are_full_phone_width_one_under_another(tmp_path, chromium):
    # QA 2026-10-28 (checklist P4.3): the browser's default figure margin (40 px each side) left each version 295 px wide on a 375 px screen.
    from playwright.sync_api import sync_playwright
    (tmp_path / "h.html").write_text(pg.build_headline(tmp_path, versions(tmp_path)), encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"]); page = b.new_page(viewport={"width": 375, "height": 800})
        page.goto((tmp_path / "h.html").as_uri())
        widths = page.eval_on_selector_all("figure.version > img:not(.thumb)", "els => els.map(e => Math.round(e.getBoundingClientRect().width))")
        scroll = page.evaluate("document.documentElement.scrollWidth"); b.close()
    assert widths == [375, 375, 375] and scroll <= 375
