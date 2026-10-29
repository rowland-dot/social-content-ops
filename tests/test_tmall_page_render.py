"""Stage 7 pages drawn in headless Chromium: phone width, accessibility and Chinese text (checklist P4.1-P4.3, P5.1-P5.4).
Stand-in data only. The static page tests in test_tmall_page.py read the markup; these read what the browser lays out."""
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import pytest
from PIL import Image
import tmall_page as pg
import tmall_layers as ly
import tmall_checks
import tmall_common as common

# Stand-in builders, the same shapes test_tmall_page.py uses (pytest's importlib mode cannot import one test file from another).
def ok(folder, image):
    results = {c: {"check": c, "verdict": "pass", "method": "measured", "evidence": "crop.png" if c in tmall_checks.LOOKED else None} for c in tmall_checks.CHECKS}
    return {"complete": True, "passed": True, "image_sha256": common.sha256(folder / image), "results": results, "missing": [], "failed": []}

def product(tmp_path, n_main=2, n_detail=2):
    for i in range(1, n_main + 1): Image.new("RGB", (800, 800), "white").save(tmp_path / f"m{i}.png")
    for i in range(1, n_detail + 1): Image.new("RGB", (790, 600), "white").save(tmp_path / f"d{i}.png")
    items = [{"id": f"M{i}", "kind": "main", "image": f"m{i}.png", "copy": f"文案{i}", "sources": [f"fact {i}: website"]} for i in range(1, n_main + 1)]
    return items + [{"id": f"D{i}", "kind": "detail", "image": f"d{i}.png", "copy": f"详情{i}", "sources": [f"fact {i}: price list"]} for i in range(1, n_detail + 1)]

def passed(tmp_path, items): return {i["id"]: ok(tmp_path, i["image"]) for i in items}

def versions(tmp_path):
    out = {}
    for i, (k, d) in enumerate(zip("ABC", ("close-up", "flat lay", "in use")), 1):
        Image.new("RGB", (800, 800), "white").save(tmp_path / f"{k}.png")
        out[k] = {"image": f"{k}.png", "direction": d, "listing_id": f"L{i}", "headline": f"标题{k}", "report": ok(tmp_path, f"{k}.png")}
    return out

LONG_ZH = "燕麦蛋白肽粉，每日一勺，随餐或空腹冲服，口感清爽，便携独立包装，适合日常补充。" * 4       # 144 characters, no spaces to break on
WIDTHS = (360, 375)

def _open(tmp_path, html_text, width, name="page.html"):
    from playwright.sync_api import sync_playwright
    (tmp_path / name).write_text(html_text, encoding="utf-8")
    p = sync_playwright().start()
    b = p.chromium.launch(args=["--no-sandbox"]); page = b.new_page(viewport={"width": width, "height": 800})
    page.goto((tmp_path / name).as_uri())
    return p, b, page

def _close(p, b):
    b.close(); p.stop()

def _approval(tmp_path, copy=None, sources=None):
    items = product(tmp_path)
    if copy: items[0]["copy"] = copy
    if sources: items[0]["sources"] = sources
    return items, pg.build_approval(tmp_path, items, passed(tmp_path, items))

@pytest.mark.parametrize("width", WIDTHS)
def test_approval_page_images_fill_the_phone_width_and_nothing_scrolls_sideways(tmp_path, chromium, width):          # P4.1
    _, text = _approval(tmp_path)
    p, b, page = _open(tmp_path, text, width)
    try:
        imgs = page.eval_on_selector_all("section.phone > img", "els => els.map(e => [Math.round(e.getBoundingClientRect().width), Math.round(e.parentElement.getBoundingClientRect().width)])")
        scroll = page.evaluate("document.documentElement.scrollWidth")
    finally:
        _close(p, b)
    assert len(imgs) == 4 and all(img == section and img <= width for img, section in imgs) and scroll <= width

@pytest.mark.parametrize("width", WIDTHS)
def test_long_chinese_copy_and_a_long_source_wrap_inside_the_phone_and_are_not_cut_off(tmp_path, chromium, width):   # P4.2, i18n
    items, text = _approval(tmp_path, copy=LONG_ZH, sources=["价格表 2026年7月：" + "纯燕麦麸蛋白肽粉500克零售价" * 3])
    p, b, page = _open(tmp_path, text, width)
    try:
        scroll = page.evaluate("document.documentElement.scrollWidth")
        clipped = page.evaluate("""() => [...document.querySelectorAll('.copy, .source')]
            .filter(e => e.scrollWidth > e.clientWidth + 1 || e.getBoundingClientRect().right > innerWidth + 1).map(e => e.textContent.slice(0, 20))""")
        shown = page.inner_text("section[data-image='M1'] .copy")
    finally:
        _close(p, b)
    assert scroll <= width and clipped == [] and shown.replace("\n", "") == LONG_ZH      # every character is on the page, none trimmed

@pytest.mark.parametrize("width", WIDTHS)
def test_a_source_line_with_one_long_unbroken_word_does_not_push_the_page_sideways(tmp_path, chromium, width):      # P4.1, i18n edge
    _, text = _approval(tmp_path, sources=["price list: " + "ZhenNiuGuJiaoYuanDanBaiTaiFen2026" * 4])
    p, b, page = _open(tmp_path, text, width)
    try:
        scroll = page.evaluate("document.documentElement.scrollWidth")
    finally:
        _close(p, b)
    assert scroll <= width

@pytest.mark.parametrize("width", WIDTHS)
def test_long_unbroken_text_on_the_headline_and_check_report_pages_does_not_push_them_sideways(tmp_path, chromium, width):   # same bug class as the source line
    long = "https://example.com/" + "ZhenNiuGuJiaoYuanDanBaiTaiFen2026" * 4
    vs = versions(tmp_path)
    for v in vs.values(): v["headline"] = v["direction"] = long
    vs["A"]["listing_id"] = long
    report = pg.build_check_report({long: {"complete": False, "passed": False, "failed": ["layers_contrast"], "missing": [],
                                           "results": {"layers_contrast": {"note": long}}}}, not_confirmed=[long])
    for name, text in (("h.html", pg.build_headline(tmp_path, vs)), ("r.html", report)):
        p, b, page = _open(tmp_path, text, width, name)
        try:
            scroll = page.evaluate("document.documentElement.scrollWidth")
        finally:
            _close(p, b)
        assert scroll <= width, name

@pytest.mark.parametrize("width", WIDTHS)
def test_check_report_and_headline_pages_do_not_scroll_sideways_and_headline_versions_stack(tmp_path, chromium, width):    # P4.3
    report = pg.build_check_report({"M1": {"complete": False, "passed": False, "failed": ["layers_contrast"], "missing": ["compliance_quality_gate"],
                                           "results": {"layers_contrast": {"note": "标题：对比度 2.1 比 1，低于 4.5"}}}}, not_confirmed=["main_image.max_kb"])
    p, b, page = _open(tmp_path, report, width, "r.html")
    try:
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert "对比度 2.1" in page.inner_text("body")
    finally:
        _close(p, b)
    p, b, page = _open(tmp_path, pg.build_headline(tmp_path, versions(tmp_path)), width, "h.html")
    try:
        tops = page.eval_on_selector_all("figure.version", "els => els.map(e => [Math.round(e.getBoundingClientRect().top), Math.round(e.getBoundingClientRect().left)])")
        scroll = page.evaluate("document.documentElement.scrollWidth")
    finally:
        _close(p, b)
    assert scroll <= width and [left for _, left in tops] == [0, 0, 0] and tops == sorted(tops) and len({t for t, _ in tops}) == 3

def test_every_text_line_on_the_approval_page_meets_the_4_5_contrast_floor(tmp_path, chromium):                       # P5.3
    _, text = _approval(tmp_path)
    p, b, page = _open(tmp_path, text, 375)
    try:
        pairs = page.evaluate("""() => [...document.querySelectorAll('.copy, .source, .label, .summary')].map(e => {
            const parse = c => (c.match(/[\\d.]+/g) || []).map(Number);
            let bg = null, n = e;
            while (n && !bg) { const c = parse(getComputedStyle(n).backgroundColor); if (c.length >= 3 && (c.length === 3 || c[3] > 0)) bg = c; n = n.parentElement; }
            return [e.className, parse(getComputedStyle(e).color).slice(0, 3), (bg || [255, 255, 255]).slice(0, 3)]; })""")
    finally:
        _close(p, b)
    assert pairs
    low = [(cls, round(ly.contrast_ratio(fg, bg), 2)) for cls, fg, bg in pairs if ly.contrast_ratio(fg, bg) < 4.5]
    assert low == []

@pytest.mark.parametrize("builder", ("approval", "headline", "report"))
def test_every_page_is_marked_chinese_has_a_title_and_every_picture_has_a_text_alternative(tmp_path, chromium, builder):      # P5.1, P5.2
    items = product(tmp_path)
    text = {"approval": lambda: pg.build_approval(tmp_path, items, passed(tmp_path, items)),
            "headline": lambda: pg.build_headline(tmp_path, versions(tmp_path)),
            "report": lambda: pg.build_check_report({"M1": {"passed": False, "failed": ["pack"], "missing": []}})}[builder]()
    p, b, page = _open(tmp_path, text, 375)
    try:
        lang = page.evaluate("document.documentElement.lang"); title = page.title()
        alts = page.eval_on_selector_all("img", "els => els.map(e => e.getAttribute('alt'))")
    finally:
        _close(p, b)
    assert lang.lower().startswith("zh") and title.strip()
    assert all(a and a.strip() for a in alts)
    if builder == "approval":
        assert alts == ["文案1", "文案2", "详情1", "详情2"]               # the picture's Chinese words are its text alternative

def test_a_long_chinese_copy_text_alternative_keeps_its_start_and_the_full_words_stay_on_the_page(tmp_path):         # P5.1: the alt is cut, the page text is not
    items, text = _approval(tmp_path, copy=LONG_ZH)
    alt = re.search(r"alt='([^']*)'", text).group(1)
    assert LONG_ZH.startswith(alt) and len(alt) >= 100 and LONG_ZH in text

def test_reading_order_is_the_image_order_with_a_heading_for_each_and_nothing_to_trap_the_tab_key(tmp_path, chromium):   # P5.4
    items, text = _approval(tmp_path)
    p, b, page = _open(tmp_path, text, 375)
    try:
        headings = page.eval_on_selector_all("section.phone > h2", "els => els.map(e => e.textContent)")
        order = page.eval_on_selector_all("section.phone", "els => els.map(e => e.getAttribute('data-image') || e.getAttribute('data-screen'))")
        focusable = page.eval_on_selector_all("a[href], button, input, select, textarea, [tabindex]", "els => els.map(e => e.tagName + ':' + e.getAttribute('tabindex'))")
    finally:
        _close(p, b)
    assert headings == ["主图1", "主图2", "详情第1屏", "详情第2屏"] and order == [i["id"] for i in items]
    assert not any(f.split(":")[1] not in ("None", "0", "-1") for f in focusable)             # no positive tab index that would reorder the tabbing
