import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import io, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
import pytest
import tmall_capture as cap

def _png(w, h):
    b = io.BytesIO(); Image.new("RGB", (w, h), "white").save(b, "PNG"); return b.getvalue()

class Site(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        path = self.path
        if path.startswith("/img/"):
            w, h = (int(x) for x in path.split("/")[2].split(".")[0].split("x")); body, ctype = _png(w, h), "image/png"
        elif path.startswith("/search"):
            tiles = "".join(f"<div class='tile'><a href='/item?id={i}00000000{i}'>t{i}</a><span>{n}人付款</span></div>" for i, n in ((1, "3000+"), (2, "2万+"), (3, "800+")))
            body, ctype = f"<html><body>{tiles}</body></html>".encode(), "text/html; charset=utf-8"
        elif path.startswith("/item?id=3"):
            self.send_response(302); self.send_header("Location", "/punish?x=1"); self.end_headers(); return
        elif path.startswith("/punish"):
            body, ctype = b"<html><body><div id='nocaptcha'>slide</div></body></html>", "text/html; charset=utf-8"
        else:
            g = "".join(f"<img src='/img/800x800.png?{i}'>" for i in range(4))
            d = "".join(f"<img src='/img/790x900.png?{i}'>" for i in range(3))
            r = "".join(f"<img src='/img/790x700.png?r{i}'>" for i in range(2))
            body = (f"<html><body><div class='gallery'>{g}</div><div class='detail-body'>{d}</div>"
                    f"<div class='rate-list'>{r}</div><div class='guess-you-like'><img src='/img/790x700.png?g'></div></body></html>").encode(); ctype = "text/html; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body)

@pytest.fixture
def site():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Site); threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"; srv.shutdown()

def plain_context(p):                       # tests use a plain headless browser, never the saved Tmall login
    return p.chromium.launch(args=["--no-sandbox"]).new_context()

def test_run_captures_main_and_detail_images_only_and_stops_at_a_wall_keeping_what_it_has(site, tmp_path, chromium):
    pacer = cap.Pacer(tmp_path / "v.json", gap=(0, 0), daily_cap=10, sleep=lambda s: None, rng=lambda a, b: 0)
    report = cap.run_capture(out_dir=tmp_path / "out", query="demo", top_n=3, pacer=pacer, open_context=plain_context,
                             search_url=site + "/search?q={q}", item_url=site + "/item?id={id}", scroll_steps=2)
    assert [i["rank"] for i in report["items"]] == [1, 2, 3]
    first = report["items"][0]
    assert first["main_saved"] == 4 and first["detail_saved"] == 3            # review photos and recommendations left out
    assert report["stopped"] and "punish" in report["stopped"] and report["stop_kind"] == "wall"     # the third listing hit the wall
    assert [r["rank"] for r in report["ranked"]] == [1, 2, 3] and "payers" not in json.dumps(report["ranked"])
    assert (tmp_path / "out" / "capture-report.json").is_file()
    assert "payers" not in json.dumps(report)

def test_a_second_run_skips_listings_already_captured(site, tmp_path, chromium):
    kw = dict(out_dir=tmp_path / "out", query="demo", top_n=2, open_context=plain_context,
              search_url=site + "/search?q={q}", item_url=site + "/item?id={id}", scroll_steps=1)
    p = lambda: cap.Pacer(tmp_path / "v.json", gap=(0, 0), daily_cap=10, sleep=lambda s: None, rng=lambda a, b: 0)
    cap.run_capture(pacer=p(), **kw)
    again = cap.run_capture(pacer=p(), **kw)
    assert all(i.get("skipped") for i in again["items"])

def test_a_listing_whose_downloads_all_fail_is_recorded_and_retried_next_time(site, tmp_path, chromium, monkeypatch):
    # Autoplan review: _save used to swallow every error, so a listing with zero pictures counted as finished and was skipped for good.
    kw = dict(out_dir=tmp_path / "out", query="demo", top_n=2, open_context=plain_context,
              search_url=site + "/search?q={q}", item_url=site + "/item?id={id}", scroll_steps=1)
    p = lambda: cap.Pacer(tmp_path / "v.json", gap=(0, 0), daily_cap=10, sleep=lambda s: None, rng=lambda a, b: 0)
    real = cap._save
    monkeypatch.setattr(cap, "_save", lambda ctx, url, path: f"{url}: HTTP 403")
    first = cap.run_capture(pacer=p(), **kw)
    assert len(first["incomplete"]) == 2 and all(i["main_saved"] == 0 and "HTTP 403" in i["failed_downloads"][0] for i in first["items"])
    monkeypatch.setattr(cap, "_save", real)
    again = cap.run_capture(pacer=p(), **kw)
    assert not any(i.get("skipped") for i in again["items"]) and again["incomplete"] == [] and again["items"][0]["main_saved"] == 4

def test_a_listing_that_crashes_is_recorded_and_the_report_still_written(site, tmp_path, chromium, monkeypatch):
    monkeypatch.setattr(cap, "_visit", lambda *a: (_ for _ in ()).throw(TimeoutError("page took too long")))
    report = cap.run_capture(out_dir=tmp_path / "out", query="demo", top_n=2, open_context=plain_context,
                             pacer=cap.Pacer(tmp_path / "v.json", gap=(0, 0), daily_cap=10, sleep=lambda s: None, rng=lambda a, b: 0),
                             search_url=site + "/search?q={q}", item_url=site + "/item?id={id}", scroll_steps=1)
    assert report["stop_kind"] == "error" and "page took too long" in report["items"][0]["error"]
    assert "page took too long" in (tmp_path / "out" / "capture-report.json").read_text(encoding="utf-8")

def test_an_early_stop_keeps_the_listings_finished_in_earlier_runs(site, tmp_path, chromium):
    kw = dict(out_dir=tmp_path / "out", query="demo", open_context=plain_context, item_url=site + "/item?id={id}", scroll_steps=1)
    p = lambda: cap.Pacer(tmp_path / "v.json", gap=(0, 0), daily_cap=10, sleep=lambda s: None, rng=lambda a, b: 0)
    cap.run_capture(pacer=p(), top_n=2, search_url=site + "/search?q={q}", **kw)
    stopped = cap.run_capture(pacer=p(), top_n=2, search_url=site + "/punish?q={q}", **kw)          # the search page itself is walled
    assert stopped["stop_kind"] == "wall"
    kept = json.loads((tmp_path / "out" / "capture-report.json").read_text(encoding="utf-8"))["items"]
    assert len(kept) == 2 and all(i["main_saved"] == 4 for i in kept)

def test_a_refused_download_is_named_and_nothing_is_written(tmp_path):
    # reviewed-plan audit pass 1: the test above replaces _save, so a _save that swallowed HTTP errors again survived every test
    class Refused: ok, status = False, 403
    class Ctx:
        class request:
            @staticmethod
            def get(url, timeout): return Refused()
    assert cap._save(Ctx(), "u", tmp_path / "x.jpg") == "u: HTTP 403" and not (tmp_path / "x.jpg").exists()

def test_each_kind_of_stop_has_its_own_exit_code_and_next_step():
    codes = {k: c for k, (c, _msg) in cap.NEXT_STEP.items()}
    assert len({codes["wall"], codes["login"], codes["daily_cap"], codes["error"]}) == 4 and 0 not in codes.values()
    assert "tmall_login.py login" in cap.NEXT_STEP["login"][1]
