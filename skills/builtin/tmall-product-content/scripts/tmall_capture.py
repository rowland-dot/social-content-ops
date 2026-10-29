"""Competitor read: pick the leading listings, capture main galleries and detail pages as images. Third-party material: it goes to the knowledge base, never the repo."""
from __future__ import annotations
import json, re, sys, time, random, datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))   # tmall_login lives with the other login scripts

GAP = (20, 35)          # seconds between listing visits; what the access test used for three visits. Replaced by the trial's measured value (Task 25).
DAILY_CAP = 12          # listing visits a day; a guess until the trial measures it (Task 25).
BLOCK_URL_PARTS = ("punish", "login.taobao.com", "login.tmall.com", "x5sec")
REVIEW_RE = re.compile(r"(?<![a-z])rate(?![a-z])|review|comment|buyer-show|评价|买家秀")
RECOMMEND_RE = re.compile(r"recommend|guess|similar|相似|推荐|猜你")
MIN_DETAIL_WIDTH = 600
BEIJING = dt.timezone(dt.timedelta(hours=8))

class DailyCapReached(RuntimeError):
    pass

def parse_payers(text: str) -> int:
    m = re.search(r"([\d.]+)\s*(万)?\s*\+?\s*人付款", text)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * 10000) if m.group(2) else int(n)

def rank_tiles(tiles: list[dict], top_n: int, exclude=()) -> list[dict]:
    """exclude: item ids to leave out (the real top ten holds drinks and sachets, which are not powders of the searched kind)."""
    seen, ranked = set(exclude), []
    for t in sorted((t for t in tiles if t["payers"] > 0), key=lambda t: -t["payers"]):
        if t["id"] not in seen:
            seen.add(t["id"]); ranked.append(t)
    return [{"id": t["id"], "title": t.get("title", ""), "rank": i} for i, t in enumerate(ranked[:top_n], 1)]

def item_id(href: str) -> str | None:
    m = re.search(r"[?&]id=(\d+)", href)
    return m.group(1) if m else None

def full_size(src: str) -> str:
    src = re.sub(r"_\.webp$", "", re.sub(r"\.(jpg|jpeg|png)_[^/]*$", r".\1", src))
    return "https:" + src if src.startswith("//") else src

def classify_image(rec: dict) -> str:
    path = rec["path"].lower()
    if REVIEW_RE.search(path): return "review"
    if RECOMMEND_RE.search(path): return "recommendation"
    return "detail" if rec["w"] >= MIN_DETAIL_WIDTH else "other"

def block_reason(url: str, dom_hits: int, markers=BLOCK_URL_PARTS) -> str | None:
    if any(m in url for m in markers):
        return f"redirected to {url.split('?')[0]}"
    return "captcha on page" if dom_hits else None

class Pacer:
    def __init__(self, state_file, gap=GAP, daily_cap=DAILY_CAP, clock=time.time, sleep=time.sleep, rng=random.uniform):
        self.file, self.gap, self.cap, self.clock, self.sleep, self.rng = Path(state_file), gap, daily_cap, clock, sleep, rng

    def _visits(self) -> list[float]:
        try: return json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError): return []

    def _today(self) -> list[float]:
        day = dt.datetime.fromtimestamp(self.clock(), BEIJING).date()     # Taobao's day, whatever the machine's clock zone is
        return [v for v in self._visits() if dt.datetime.fromtimestamp(v, BEIJING).date() == day]

    def wait_turn(self) -> None:
        today = self._today()
        if len(today) >= self.cap:
            raise DailyCapReached(f"{len(today)} listing visits today; the cap is {self.cap}")
        if today:
            wait = today[-1] + self.rng(*self.gap) - self.clock()
            if wait > 0: self.sleep(wait)

    def record_visit(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self._visits() + [self.clock()]), encoding="utf-8")

TILES_JS = """() => { const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href*="id="]')) {
    const m = a.href.match(/[?&]id=(\\d+)/); if (!m || seen.has(m[1])) continue; seen.add(m[1]);
    let el = a; for (let i = 0; i < 6 && el && !/人付款/.test(el.innerText || ''); i++) el = el.parentElement;
    out.push({id: m[1], title: (a.innerText || '').slice(0, 80), text: el ? el.innerText : ''}); }
  return out; }"""
GALLERY_SELECTOR = ".gallery img, [class*='thumbnailPic'], [class*='PicGallery'] img"
IMAGES_JS = """() => [...document.querySelectorAll('img')].map(i => {
  const path = []; for (let e = i.parentElement; e && path.length < 6; e = e.parentElement) path.push(e.tagName.toLowerCase() + '.' + (e.className || '') + '#' + (e.id || ''));
  return {src: i.currentSrc || i.src, w: i.naturalWidth || 0, h: i.naturalHeight || 0, path: path.join(' > ')}; })"""
BLOCK_DOM = "#baxia-dialog-content, .nc_wrapper, #nocaptcha, iframe[src*='punish']"
SEARCH_URL = "https://s.taobao.com/search?q={q}&tab=mall"
ITEM_URL = "https://detail.tmall.com/item.htm?id={id}"

def _save(context, url: str, path: Path) -> str | None:
    """None when saved; otherwise why not, so a refused download is recorded instead of silently counted out (autoplan review)."""
    try:
        r = context.request.get(url, timeout=20000)
        if r.ok:
            path.write_bytes(r.body()); return None
        return f"{url}: HTTP {r.status}"
    except Exception as e:
        return f"{url}: {type(e).__name__}: {e}"

def _stop(report: dict, kind: str, why: str) -> None:
    """kind: wall (block page or captcha), login (the saved login expired), daily_cap, error. Each has its own next step and exit code."""
    report["stopped"], report["stop_kind"] = why, kind

def _done(item: dict) -> bool:
    # a listing counts as captured only if it saved gallery and detail images; zero of either is retried on the next run
    return bool(item.get("main_saved")) and bool(item.get("detail_saved"))

def _visit(ctx, page, t: dict, entry: dict, out_dir: Path, item_url: str, scroll_steps: int) -> str | None:
    """One listing. Returns a wall reason, or None after saving what it found into entry."""
    page.goto(item_url.format(id=t["id"]), wait_until="domcontentloaded", timeout=30000); page.wait_for_timeout(500)
    wall = block_reason(page.url, page.locator(BLOCK_DOM).count())
    if wall:
        return wall
    for _ in range(scroll_steps):
        page.mouse.wheel(0, 900); page.wait_for_timeout(100)
    gallery = list(dict.fromkeys(full_size(s) for s in page.eval_on_selector_all(GALLERY_SELECTOR, "els => els.map(e => e.currentSrc || e.src)") if s))
    recs = [r for r in page.evaluate(IMAGES_JS) if classify_image(r) == "detail"]
    detail = [u for u in dict.fromkeys(full_size(r["src"]) for r in recs) if u not in gallery]   # the gallery is not the detail page
    folder = out_dir / t["id"]; folder.mkdir(exist_ok=True)
    failed = []
    for kind, urls in (("main", gallery), ("detail", detail)):
        errors = [_save(ctx, u, folder / f"{kind}_{i:02d}.jpg") for i, u in enumerate(urls)]
        entry[f"{kind}_saved"] = sum(e is None for e in errors); failed += [e for e in errors if e]
    if failed:
        entry["failed_downloads"] = failed
    return None

def run_capture(*, out_dir, query: str, top_n: int, pacer, search_url=SEARCH_URL, item_url=ITEM_URL,
                open_context=None, scroll_steps=45, profile_base=None, exclude=()) -> dict:
    """open_context(playwright) -> a browser context. Default: the saved Tmall login, headless (no window on the owner's screen)."""
    from urllib.parse import quote
    from playwright.sync_api import sync_playwright
    import tmall_login
    open_context = open_context or (lambda p: tmall_login._context(p, headless=True, base=profile_base))
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / "capture-report.json"
    previous = {i["id"]: i for i in json.loads(report_file.read_text(encoding="utf-8"))["items"]
                if _done(i)} if report_file.is_file() else {}
    report = {"query": query, "items": [], "stopped": None, "stop_kind": None, "incomplete": []}
    def save():
        # finished listings from earlier runs stay in the record even when this run stops early, so a resume never revisits them on the owner's account
        seen = {i["id"] for i in report["items"]}
        merged = report["items"] + [{**i, "skipped": True} for k, i in previous.items() if k not in seen]
        report_file.write_text(json.dumps({**report, "items": merged}, ensure_ascii=False, indent=1), encoding="utf-8")
    with sync_playwright() as p:
        ctx = open_context(p)
        try:
            page = ctx.new_page()
            try:
                page.goto(search_url.format(q=quote(query)), wait_until="domcontentloaded"); page.wait_for_timeout(500)
            except Exception as e:
                _stop(report, "error", f"search: {type(e).__name__}: {e}"); return report
            wall = block_reason(page.url, page.locator(BLOCK_DOM).count())
            if wall:
                _stop(report, "login" if "login" in page.url else "wall", f"search: {wall}")
            else:
                tiles = [dict(t, payers=parse_payers(t["text"])) for t in page.evaluate(TILES_JS)]
                report["ranked"] = rank_tiles(tiles, top_n + 6)             # rank, id and title only: what the owner is shown to drop non-powders
                for t in rank_tiles(tiles, top_n, exclude=exclude):
                    entry = {"rank": t["rank"], "id": t["id"], "title": t["title"]}
                    if t["id"] in previous:
                        report["items"].append({**previous[t["id"]], "rank": t["rank"], "skipped": True}); continue
                    try: pacer.wait_turn()
                    except DailyCapReached as e:
                        _stop(report, "daily_cap", str(e)); break
                    try:
                        wall = _visit(ctx, page, t, entry, out_dir, item_url, scroll_steps)
                    except Exception as e:             # a timeout or browser error on one listing is recorded, not lost
                        entry["error"] = f"{type(e).__name__}: {e}"; report["items"].append(entry)
                        _stop(report, "error", f"item {t['id']}: {entry['error']}"); break
                    finally:
                        pacer.record_visit()
                    if wall:
                        entry["blocked"] = wall; report["items"].append(entry)
                        _stop(report, "login" if "login" in page.url else "wall", f"item {t['id']}: {wall}"); break
                    report["items"].append(entry)
                    if not _done(entry):
                        report["incomplete"].append(t["id"])
                    save()
        finally:
            ctx.close()
            save()
    return report

NEXT_STEP = {"wall": (2, "a block page or captcha stopped the run; do not retry today, tell the owner"),
             "login": (3, "the saved Taobao login has expired; run tmall_login.py login and stop for the owner's scan, then run again"),
             "daily_cap": (4, "today's visit limit is reached; run again tomorrow, finished listings are skipped"),
             "error": (5, "a listing failed to load; run again, finished listings are skipped"),
             "incomplete": (5, "some listings saved no gallery or no detail images; run again to retry them, or tell the owner if it repeats")}

import os, subprocess, html, shutil
# The knowledge-base tool is Windows-only (its `add` calls ctypes.windll, which Linux Python lacks: probed 2026-10-28), so a capture made in
# WSL is handed to it under Windows Python, started from WSL, with Windows-form paths. Both locations can be overridden by setting.
def _first_in_windows_users(pattern: str, fallback: str) -> str:
    """The first match under the Windows user folders, so no user name is written here."""
    users = Path("/mnt/c/Users")
    found = sorted(users.glob(pattern)) if users.is_dir() else []
    return str(found[0]) if found else fallback


CLIENTKB_PYTHON = os.environ.get("TMALL_CLIENTKB_PYTHON") or _first_in_windows_users(
    "*/AppData/Local/Programs/Python/Python311/python.exe", "/mnt/c/Users/<user>/AppData/Local/Programs/Python/Python311/python.exe")
CLIENTKB = Path(os.environ.get("TMALL_CLIENTKB_DIR") or _first_in_windows_users("*/Projects/clientkb", "/mnt/c/Users/<user>/Projects/clientkb"))

def to_windows(path) -> str:
    m = re.match(r"^/mnt/([a-z])/(.*)$", str(path))
    return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\") if m else str(path)

def deposit(out_dir, *, brand: str, cat: str, by: str, note=None, runner=subprocess.run, clientkb=CLIENTKB) -> list[str]:
    """Hand every captured image, the capture report and the pattern note to the knowledge base through its tool (it keeps its own
    backups); nothing is copied by hand. Each image is staged under a name that starts with its item number, because the tool files
    everything of one category together and would otherwise lose which listing an image came from."""
    out_dir = Path(out_dir); stage = out_dir / "_deposit"; stage.mkdir(exist_ok=True)
    files = []
    for f in sorted(out_dir.glob("*/*.jpg")):
        if f.parent.name != "_deposit":
            s = stage / f"{f.parent.name}_{f.name}"; shutil.copy2(f, s); files.append(s)
    if (out_dir / "capture-report.json").is_file(): files.append(out_dir / "capture-report.json")
    if note: files.append(Path(note))
    if runner is subprocess.run and not Path(CLIENTKB_PYTHON).is_file():
        raise FileNotFoundError(f"the knowledge-base tool needs Windows Python at {CLIENTKB_PYTHON} (set TMALL_CLIENTKB_PYTHON); nothing was filed")
    for n, f in enumerate(files, 1):
        try:
            runner([CLIENTKB_PYTHON, "-m", "clientkb", "add", to_windows(f), "--brand", brand, "--cat", cat, "--by", by], cwd=str(clientkb), check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"filing {f.name} failed after {n - 1} of {len(files)} files were filed; running deposit again is safe "
                               f"(the tool skips files it already holds): {e}") from e
        print(f"filed {n}/{len(files)}: {f.name}", flush=True)          # a full set takes hours; this is the progress
    return [f.name for f in files]

def trial_sheet(out_dir, report: dict) -> Path:
    """What the owner judges the trial on (spec: the saved login reaches listings, how often walls appear, and that a full detail page
    comes out as images), so each listing shows its gallery and its detail images, and a stopped listing shows why (autoplan review)."""
    out_dir = Path(out_dir)
    def imgs(i, kind, style):
        return "".join(f"<img src='{i['id']}/{p.name}' style='{style}' alt='{kind}'>" for p in sorted((out_dir / i["id"]).glob(f"{kind}_*.jpg")))
    rows = []
    for i in report["items"]:
        head = f"<h2>Rank {i['rank']}: {html.escape(i.get('title', ''))} (item {i['id']})</h2>"
        if i.get("blocked") or i.get("error"):
            rows.append(f"<section class='stopped'>{head}<p>Stopped here: {html.escape(i.get('blocked') or i.get('error'))}</p></section>"); continue
        rows.append(f"<section>{head}<p>Gallery: {i.get('main_saved', 0)} saved. Detail page: {i.get('detail_saved', 0)} saved.</p>"
                    f"<div>{imgs(i, 'main', 'height:200px')}</div><div style='max-width:395px'>{imgs(i, 'detail', 'width:100%;display:block')}</div></section>")   # detail slices stacked as the page scrolls
    page = out_dir / "trial-sheet.html"
    page.write_text(f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Tmall trial</title>"
                    f"{''.join(rows)}<p>{html.escape(str(report.get('stopped') or 'Not stopped.'))}</p>", encoding="utf-8")
    return page

def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__); sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--query", required=True); r.add_argument("--top", type=int, default=10)
    r.add_argument("--out", required=True); r.add_argument("--trial", action="store_true", help="the 2 to 3 listing trial: always the top 3, whatever --top says")
    r.add_argument("--exclude", nargs="*", default=[], help="item ids to leave out (drinks, sachets)")
    d = sub.add_parser("deposit"); d.add_argument("--out", required=True); d.add_argument("--brand", required=True)
    d.add_argument("--cat", required=True); d.add_argument("--by", default="easel-tmall"); d.add_argument("--note")
    t = sub.add_parser("trial-sheet"); t.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    if a.cmd == "run":
        import output_paths
        out = output_paths.validate_output_path(a.out, allow_system=True)
        report = run_capture(out_dir=out, query=a.query, top_n=3 if a.trial else a.top, pacer=Pacer(out.parent / "visits.json"), exclude=a.exclude)
        print(json.dumps({"items": len(report["items"]), "stopped": report["stopped"], "incomplete": report["incomplete"]}, ensure_ascii=False))
        kind = report["stop_kind"] or ("incomplete" if report["incomplete"] else None)
        if kind:
            code, step = NEXT_STEP[kind]
            print(f"{kind}: {step}", file=sys.stderr); return code
        return 0
    if a.cmd == "deposit":
        print("\n".join(deposit(out, brand=a.brand, cat=a.cat, by=a.by, note=a.note)))
        return 0
    print(trial_sheet(out, json.loads((out / "capture-report.json").read_text(encoding="utf-8"))))
    return 0

if __name__ == "__main__":
    sys.exit(main())
