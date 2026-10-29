"""Easel's question box shows its time left, marks itself expired and passes a late answer on (issue 61).

Seam: the chat page's own code, built from web/frontend and run in a real headless Chromium against a stand-in for
Easel's backend. The stand-in speaks the live send stream and the two question calls the box makes (answer and
status), and records every message the page sends. Nothing inside the page is replaced.

Expected texts are literals made here, never read back from the page.

Skipped when this machine cannot start Chromium, cannot build the page, or has no Playwright.
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.test_chat_turn_closes_once import Turn, _build

QUESTION_ID = "toolu_01TEST:0"
ASKED = "上图文字用哪个方案？"


def question(expires_in_s):
    payload = {"id": QUESTION_ID, "questions": [{
        "questionId": "q1", "header": "上图文字", "question": ASKED,
        "options": [{"label": "方案 A"}, {"label": "方案 B"}, {"label": "方案 C"}]}]}
    if expires_in_s is not None:
        payload["expiresAtMs"] = int((time.time() + expires_in_s) * 1000)
    return payload


@pytest.fixture(scope="module")
def built_page(tmp_path_factory):
    out = tmp_path_factory.mktemp("easel-page")
    if not _build(out):
        pytest.skip("the chat page cannot be built here (needs its packages installed and a working node)")
    return out


class Backend:
    """Serves the built page, the send stream and the question calls."""

    def __init__(self, page_dir: Path):
        self.page_dir, self.turns, self.posts, self.answers = page_dir, {}, [], []
        self.answer_reply = {"ok": True}
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

            def stream(self, turn):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                cursor = 0
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
                path = self.path.split("?")[0]
                if path == "/api/chat/stream":
                    backend.posts.append(body)
                    turn = backend.turns[body["turnId"]] = Turn()
                    threading.Thread(target=backend.script, args=(turn, len(backend.posts)), daemon=True).start()
                    return self.stream(turn)
                if path == "/api/chat/question/status":
                    return self.send_json({"ok": True, "questions": {q: {"status": "pending"} for q in body["questionIds"]}})
                if path == "/api/chat/question/answer":
                    backend.answers.append(body)
                    return self.send_json(backend.answer_reply)
                return self.send_json({"stopped": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def script(self, turn, number):
        """First message: the agent puts up a box and keeps working (the test ends the turn). Later ones: a reply."""
        turn.add("activity", "🧠 正在思考…")
        if number > 1:
            turn.add("token", "收到你的选择。")
            turn.add("done", {"sessionKey": "web:test"})

    def first_turn(self):
        return self.turns[self.posts[0]["turnId"]]

    def close(self):
        self.server.shutdown()


@pytest.fixture
def backend(built_page):
    backend = Backend(built_page)
    yield backend
    backend.close()


@pytest.fixture
def open_chat(chromium, backend):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()

        def open_page():
            page = browser.new_context().new_page()
            page.goto(backend.url + "/")
            page.get_by_text("对话", exact=True).first.click()
            page.wait_for_selector("textarea.chat-input")
            page.fill("textarea.chat-input", "做上图文字")
            page.press("textarea.chat-input", "Enter")
            deadline = time.time() + 8
            while not backend.posts and time.time() < deadline:
                time.sleep(0.05)
            assert backend.posts, "the page never sent the first message"
            return page

        yield open_page
        browser.close()


def box_text(page):
    return page.locator(".question-card").inner_text()


def pick_and_submit(page, label="方案 B"):
    page.locator(".question-card__option", has_text=label).click()
    page.locator(".question-card__submit").click()


def sent_messages(backend):
    return [post["message"] for post in backend.posts]


def until(check, seconds=8):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.1)
    return check()


def test_a_live_box_shows_how_much_time_is_left(backend, open_chat):
    page = open_chat()
    backend.first_turn().add("question", question(expires_in_s=300))
    page.wait_for_selector(".question-card")
    left = page.locator(".question-card__timer").inner_text()
    minutes, seconds = re.fullmatch(r"剩余 (\d):(\d\d)", left.strip()).groups()
    assert 4 * 60 <= int(minutes) * 60 + int(seconds) <= 5 * 60


def test_a_box_whose_time_runs_out_marks_itself_expired_and_a_pick_goes_out_as_a_chat_message(backend, open_chat):
    page = open_chat()
    backend.first_turn().add("question", question(expires_in_s=2))
    page.wait_for_selector(".question-card")
    page.wait_for_selector(".question-card__expired", timeout=6000)
    assert "已过期" in box_text(page)
    backend.first_turn().add("done", {"sessionKey": "web:test"})    # the agent's turn ends
    page.wait_for_timeout(900)
    assert page.locator(".question-card").count() == 1               # the box survives the turn's end
    pick_and_submit(page)
    assert until(lambda: len(backend.posts) == 2), sent_messages(backend)
    sent = backend.posts[1]["message"]
    assert ASKED in sent and "方案 B" in sent and "方案 A" not in sent
    assert backend.answers == []                                      # nothing went to the gateway for a dead box
    assert "not supported" not in page.content()
    assert until(lambda: page.locator(".question-card").count() == 0)


def test_a_pick_on_an_expired_box_waits_while_the_agent_is_still_working(backend, open_chat):
    page = open_chat()
    backend.first_turn().add("question", question(expires_in_s=1))
    page.wait_for_selector(".question-card__expired", timeout=6000)
    pick_and_submit(page)
    page.wait_for_timeout(1200)
    assert len(backend.posts) == 1                                    # nothing sent while the turn runs
    assert "等" in box_text(page)                                      # and the box says it is waiting
    backend.first_turn().add("done", {"sessionKey": "web:test"})
    assert until(lambda: len(backend.posts) == 2), sent_messages(backend)
    assert "方案 B" in backend.posts[1]["message"]


def test_the_gateway_closing_the_question_just_before_the_pick_falls_back_to_a_chat_message(backend, open_chat):
    backend.answer_reply = {"ok": False, "expired": True, "error": "这道题已过期，答案会作为普通消息发给 AI"}
    page = open_chat()
    backend.first_turn().add("question", question(expires_in_s=300))
    page.wait_for_selector(".question-card")
    backend.first_turn().add("done", {"sessionKey": "web:test"})
    page.wait_for_timeout(900)
    pick_and_submit(page)
    assert until(lambda: len(backend.posts) == 2), sent_messages(backend)
    assert ASKED in backend.posts[1]["message"] and "方案 B" in backend.posts[1]["message"]
    assert "not supported" not in page.content()


def test_the_bridge_telling_the_page_the_question_closed_marks_the_box_expired_at_once(backend, open_chat):
    page = open_chat()
    backend.first_turn().add("question", question(expires_in_s=300))
    page.wait_for_selector(".question-card")
    backend.first_turn().add("question_closed", {"id": QUESTION_ID})
    page.wait_for_selector(".question-card__expired", timeout=4000)


def test_a_box_answered_in_time_still_goes_to_the_gateway_and_leaves_the_chat_alone(backend, open_chat):
    page = open_chat()
    backend.first_turn().add("question", question(expires_in_s=300))
    page.wait_for_selector(".question-card")
    pick_and_submit(page)
    assert until(lambda: len(backend.answers) == 1)
    assert backend.answers[0] == {"questionId": QUESTION_ID, "answers": {"q1": ["方案 B"]}}
    assert until(lambda: page.locator(".question-card").count() == 0)
    page.wait_for_timeout(500)
    assert len(backend.posts) == 1
