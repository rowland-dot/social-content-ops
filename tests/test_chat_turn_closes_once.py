"""Easel web chat: a finished turn's reply is saved once and whole (issue 62).

Seam: the chat page's own code, built from web/frontend and run in a real headless Chromium against a stand-in
for Easel's backend. The stand-in speaks the two streams the page uses (the live send stream and the catch-up
stream that replays a turn's event log) and keeps the events of each turn, like the backend's per-turn event log.
The chat is read back from the page's own browser storage, which is where the page keeps conversations.

A tab in the background is modelled the way Chrome treats it: timers stop running and the page reports itself as
hidden. The page's network handling keeps working, so the whole reply reaches it while its typing effect is stalled.

Expected texts are literals made here from the pieces the stand-in sends, never read back from the page.

Skipped when this machine cannot start Chromium, cannot build the page, or has no Playwright.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web" / "frontend"
REAL_EVENT_LOG = ROOT / "outputs" / "_sessions" / "jobs" / "1792670512974-iqp25qdbwb.jsonl"

FIRST = [f"第一轮{i:03d}段。" for i in range(200)]
SECOND = [f"第二轮{i:03d}段。" for i in range(200)]
FIRST_TEXT, SECOND_TEXT = "".join(FIRST), "".join(SECOND)

# What Chrome does to a hidden tab: its timers do not run, and the page can tell it is hidden. `__setStalled(true)`
# stops the timers alone (a tab in front whose timers are not keeping up); `__wake()` is the timers' occasional
# turn to run, once each; leaving the hidden or stalled state lets them all run.
BACKGROUND = """
(() => {
  const nativeTimeout = window.setTimeout.bind(window), nativeClear = window.clearTimeout.bind(window);
  const live = new Map(); let next = 0, hidden = false, stalled = false;
  Object.defineProperty(document, 'hidden', { get: () => hidden });
  Object.defineProperty(document, 'visibilityState', { get: () => (hidden ? 'hidden' : 'visible') });
  const schedule = (repeat, fn, delay, args) => {
    const id = ++next, rec = { native: 0, waiting: false };
    const run = () => { rec.waiting = false; if (!repeat) live.delete(id); fn(...args); if (repeat && live.has(id)) arm(); };
    const arm = () => { rec.native = nativeTimeout(() => { if (hidden || stalled) rec.waiting = true; else run(); }, delay); };
    rec.run = run; live.set(id, rec); arm(); return id;
  };
  window.setTimeout = (fn, delay = 0, ...args) => schedule(false, fn, delay, args);
  window.setInterval = (fn, delay = 0, ...args) => schedule(true, fn, delay, args);
  window.clearTimeout = window.clearInterval = (id) => { const rec = live.get(id); if (rec) { nativeClear(rec.native); live.delete(id); } };
  window.__wake = () => { for (const rec of [...live.values()]) if (rec.waiting) rec.run(); };
  window.__setStalled = (value) => { stalled = value; if (!hidden && !stalled) window.__wake(); };
  window.__setHidden = (value) => {
    hidden = value;
    document.dispatchEvent(new Event('visibilitychange'));
    if (!hidden && !stalled) window.__wake();
  };
})();
"""


# --- the page, built once -----------------------------------------------------------------------------------

def _build(out: Path) -> bool:
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite.is_file():
        return False
    attempts = []
    if shutil.which("node"):
        attempts.append(["node", str(vite), "build", "--outDir", str(out), "--emptyOutDir"])
    if shutil.which("wsl.exe"):  # this PC installed the page's packages under Linux (Easel runs in WSL)
        def linux(path: Path) -> str:
            return subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace").stdout.strip()
        attempts.append(["wsl.exe", "-e", "bash", "-ic",
                         f"cd '{linux(FRONTEND)}' && node node_modules/vite/bin/vite.js build "
                         f"--outDir '{linux(out)}' --emptyOutDir"])
    for command in attempts:
        done = subprocess.run(command, cwd=FRONTEND, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300)
        if done.returncode == 0 and (out / "index.html").is_file():
            return True
    return False


@pytest.fixture(scope="module")
def built_page(tmp_path_factory):
    out = tmp_path_factory.mktemp("easel-page")
    if not _build(out):
        pytest.skip("the chat page cannot be built here (needs its packages installed and a working node)")
    return out


# --- stand-in backend ---------------------------------------------------------------------------------------

class Turn:
    def __init__(self):
        self.events, self.finished, self.lock = [], False, threading.Lock()

    def add(self, event, data):
        with self.lock:
            self.events.append((len(self.events) + 1, event, json.dumps(data, ensure_ascii=False)))
            self.finished = self.finished or event == "done"

    def after(self, cursor):
        with self.lock:
            return [e for e in self.events if e[0] > cursor]


class Backend:
    """Serves the built page and the few interfaces the chat page calls."""

    def __init__(self, page_dir: Path):
        self.page_dir, self.turns, self.script, self.posts = page_dir, {}, None, []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def send_json(self, payload, code=200):
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def stream(self, turn, cursor):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    while True:
                        for number, event, data in turn.after(cursor):
                            self.wfile.write(f"id: {number}\nevent: {event}\ndata: {data}\n\n".encode())
                            self.wfile.flush()
                            cursor = number
                            if event in ("done", "error"):
                                return
                        time.sleep(0.05)
                except OSError:
                    return

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/api/status":
                    return self.send_json({"gateway": True, "runtime": "openclaw", "skills": [],
                                           "personas": [{"name": "t", "description": ""}]})
                if path == "/api/settings/bootstrap":
                    return self.send_json({"modelConfigured": True})
                if path == "/api/upload/limits":
                    return self.send_json({"max_mb": 50})
                if path == "/api/trends":
                    return self.send_json({"trends": [], "updated": 0})
                if path.startswith("/api/chat/jobs/") and path.endswith("/stream"):
                    turn = backend.turns.get(path.split("/")[4])
                    if turn is None:
                        return self.send_json({"detail": "gone"}, 404)
                    cursor = int(self.path.split("after=")[1].split("&")[0]) if "after=" in self.path else 0
                    return self.stream(turn, cursor)
                if path.startswith("/api/"):
                    return self.send_json([])
                file = backend.page_dir / ("index.html" if path == "/" else path.lstrip("/"))
                if not file.is_file():
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    return self.end_headers()
                body = file.read_bytes()
                kind = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}.get(file.suffix, "image/svg+xml")
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if self.path.split("?")[0] == "/api/chat/stream":
                    backend.posts.append(body)
                    turn = backend.turns[body["turnId"]] = Turn()
                    threading.Thread(target=backend.script, args=(turn, body["message"]), daemon=True).start()
                    return self.stream(turn, 0)
                return self.send_json({"stopped": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()


def two_turn_script(turn, message):
    """Like the real backend: two status lines at once, the whole text in one burst, then the end event."""
    pieces, thinking = (FIRST, 0.0) if message == "first" else (SECOND, 1.0)
    turn.add("activity", "⏳ 已收到，正在唤醒 agent…")
    turn.add("activity", "🧠 正在思考…")
    time.sleep(thinking)
    for piece in pieces:
        turn.add("token", piece)
    turn.add("done", {"sessionKey": "web:test"})


@pytest.fixture
def backend(built_page):
    backend = Backend(built_page)
    backend.script = two_turn_script
    yield backend
    backend.close()


@pytest.fixture
def open_page(chromium, backend):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()

        def open_chat(hidden=False, stalled=False, seed=None):
            context = browser.new_context()
            context.add_init_script(BACKGROUND)
            if seed:  # a stored conversation, written once, that a reload keeps
                context.add_init_script(
                    "if (!localStorage.getItem('seeded')) { localStorage.setItem('seeded', '1');"
                    f" for (const [k, v] of Object.entries({json.dumps(seed)})) localStorage.setItem(k, v); }}")
            page = context.new_page()
            page.goto(backend.url + "/")
            page.get_by_text("对话", exact=True).first.click()
            page.wait_for_selector("textarea.chat-input")
            if hidden:  # the tab goes to the background once the page is up
                page.evaluate("window.__setHidden(true)")
            if stalled:
                page.evaluate("window.__setStalled(true)")
            return page

        yield open_chat
        browser.close()


# --- helpers ------------------------------------------------------------------------------------------------

def messages(page):
    """The conversation the page has stored, as [(role, text, status lines)]."""
    chats = json.loads(page.evaluate("localStorage.getItem('easel_sessions')") or "[]")
    chat = next((c for c in chats if c["messages"]), {"messages": []})
    return [(m["role"], m["content"], (m.get("activity") or "").splitlines()) for m in chat["messages"]]


def send(page, text):
    page.fill("textarea.chat-input", text)
    page.press("textarea.chat-input", "Enter")


def until(check, seconds=8):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.1)
    return check()


def reply_arrived(backend, page, count=1):
    """The backend finished `count` turns and the page has had time to take in the end event."""
    assert until(lambda: len(backend.posts) >= count and backend.turns[backend.posts[count - 1]["turnId"]].finished)
    page.wait_for_timeout(700)


# --- the double close -----------------------------------------------------------------------------------------

def test_pressing_stop_while_the_arrived_reply_is_still_being_typed_saves_it_once_and_whole(backend, open_page):
    page = open_page(stalled=True)
    send(page, "first")
    reply_arrived(backend, page)
    page.locator(".send-btn").click()          # the page still says it is generating, so this button is Stop
    page.evaluate("window.__wake()")           # the timers' next turn to run
    page.wait_for_timeout(500)
    assert [(role, text) for role, text, _ in messages(page)] == [("user", "first"), ("assistant", FIRST_TEXT)]


def test_a_leftover_closer_from_one_turn_cannot_close_the_next_turn(backend, open_page):
    page = open_page(stalled=True)
    send(page, "first")
    reply_arrived(backend, page)
    page.locator(".send-btn").click()
    send(page, "second")
    page.wait_for_selector(".live-activity")   # the second turn is under way
    page.evaluate("window.__wake()")           # the first turn's leftover timers run now
    page.evaluate("window.__setStalled(false)")
    until(lambda: len(messages(page)) >= 4 and messages(page)[-1][1] == SECOND_TEXT, 20)
    assert [(role, text) for role, text, _ in messages(page)] == [
        ("user", "first"), ("assistant", FIRST_TEXT), ("user", "second"), ("assistant", SECOND_TEXT)]


def test_the_reply_is_saved_while_the_tab_is_still_in_the_background(backend, open_page):
    page = open_page(hidden=True)
    send(page, "first")
    reply_arrived(backend, page)
    assert until(lambda: len(messages(page)) == 2, 3), messages(page)
    assert [(role, text) for role, text, _ in messages(page)] == [("user", "first"), ("assistant", FIRST_TEXT)]
    assert messages(page)[1][2] == ["⏳ 已收到，正在唤醒 agent…", "🧠 正在思考…"]


def test_a_reply_still_being_typed_is_saved_when_the_tab_goes_to_the_background(backend, open_page):
    page = open_page(stalled=True)
    send(page, "first")
    reply_arrived(backend, page)
    assert [role for role, _, _ in messages(page)] == ["user"]     # still being typed: nothing saved yet
    page.evaluate("window.__setHidden(true)")
    assert until(lambda: len(messages(page)) == 2, 3), messages(page)
    assert [(role, text) for role, text, _ in messages(page)] == [("user", "first"), ("assistant", FIRST_TEXT)]


# --- catching up on a turn that finished while the page was away --------------------------------------------

def stored_waiting_turn(turn_id):
    chat = {"id": "c1", "title": "first", "created": 1, "pendingTurnId": turn_id,
            "messages": [{"role": "user", "content": "first"}]}
    return {"easel_sessions": json.dumps([chat]), "easel_active_session": "c1"}


def catch_up(backend, open_page, hidden, turn_id, events):
    """The page comes back to a stored conversation whose turn is still running, and the turn then finishes."""
    turn = backend.turns[turn_id] = Turn()
    turn.add("activity", "⏳ 已收到，正在唤醒 agent…")
    page = open_page(hidden=hidden, seed=stored_waiting_turn(turn_id))
    page.wait_for_timeout(600)  # the page is attached to the turn's stream
    for event, data in events:
        turn.add(event, data)
    return page


@pytest.mark.parametrize("hidden", [False, True], ids=["tab in front", "tab in background"])
def test_catching_up_on_a_finished_turn_gives_the_whole_reply_once(backend, open_page, hidden):
    events = [("activity", "🧠 正在思考…")] + [("token", piece) for piece in FIRST] + [("done", {"sessionKey": "web:test"})]
    page = catch_up(backend, open_page, hidden, "t-first", events)
    assert until(lambda: len(messages(page)) >= 2, 20), messages(page)
    page.wait_for_timeout(500)
    assert [(role, text) for role, text, _ in messages(page)] == [("user", "first"), ("assistant", FIRST_TEXT)]


@pytest.mark.skipif(not REAL_EVENT_LOG.is_file(), reason="the real event log from 2026-10-22 is not on this machine")
@pytest.mark.parametrize("hidden", [False, True], ids=["tab in front", "tab in background"])
def test_catching_up_on_the_lost_turn_from_2026_10_22_gives_its_whole_reply(backend, open_page, hidden):
    logged = [json.loads(line) for line in REAL_EVENT_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = "".join(e["data"] for e in logged if e["event"] == "token")
    page = catch_up(backend, open_page, hidden, "t-real", [(e["event"], e["data"]) for e in logged])
    assert until(lambda: len(messages(page)) >= 2, 30), messages(page)
    page.wait_for_timeout(500)
    assert [(role, text) for role, text, _ in messages(page)] == [("user", "first"), ("assistant", expected)]
