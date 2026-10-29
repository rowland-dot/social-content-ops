"""Issue 61: a question the gateway has closed is "expired", never "unsupported".

The stand-in below replaces only the websocket the client talks through (the
system boundary); everything else is the real GatewayClient.
"""
import json

import pytest

from easel import gateway_questions as gq


class StandInSocket:
    """Answers each request with the next canned reply, echoing the request id."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self._last_id = None

    def send(self, raw):
        req = json.loads(raw)
        self.sent.append(req)
        self._last_id = req["id"]

    def recv(self):
        reply = dict(self.replies.pop(0))
        reply["id"] = self._last_id
        return json.dumps(reply)

    def close(self):
        pass


def client_with(*replies):
    client = gq.GatewayClient()
    client.ws = StandInSocket(replies)
    return client


def refusal(reason, message="refused"):
    error = {"code": "INVALID_REQUEST", "message": message}
    if reason:
        error["details"] = {"reason": reason}
    return {"ok": False, "error": error}


def test_resolving_a_question_the_gateway_no_longer_has_is_reported_as_expired():
    client = client_with(refusal("QUESTION_NOT_FOUND", "question 'ask_1:0' was not found"))
    with pytest.raises(gq.GatewayQuestionExpiredError) as caught:
        client.resolve("ask_1:0", {"q": ["B"]})
    assert not isinstance(caught.value, gq.GatewayUnsupportedError)
    assert "not supported" not in str(caught.value)


def test_a_cancelled_question_is_reported_as_expired():
    client = client_with(refusal("QUESTION_CANCELLED", "question was cancelled"))
    with pytest.raises(gq.GatewayQuestionExpiredError):
        client.resolve("ask_1:0", {"q": ["B"]})


def test_an_unknown_method_still_counts_as_unsupported():
    client = client_with(refusal(None, "unknown method: question.list"))
    with pytest.raises(gq.GatewayUnsupportedError) as caught:
        client.list_questions()
    assert "question.list not supported by this gateway" in str(caught.value)


def test_a_bad_answer_is_neither_expired_nor_unsupported():
    client = client_with(refusal("QUESTION_INVALID_ANSWER", "question 'x' requires an answer"))
    with pytest.raises(gq.GatewayQuestionError) as caught:
        client.resolve("ask_1:0", {})
    assert not isinstance(caught.value, (gq.GatewayQuestionExpiredError, gq.GatewayUnsupportedError))


# --- the answer endpoint ----------------------------------------------------

from fastapi.testclient import TestClient

import web.app as web


class StandInGateway:
    """Stands in for the gateway connection the web process opens per answer."""

    outcome = None

    def connect(self):
        pass

    def resolve(self, question_id, answers, resolved_by=None):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return {"status": "answered"}

    def close(self):
        pass


@pytest.fixture
def page_api(monkeypatch):
    monkeypatch.setattr(web, "GatewayClient", StandInGateway)
    monkeypatch.setattr(web, "_direct_api_enabled", lambda: False)
    monkeypatch.setattr(web, "_harness_settings", lambda: {"runtime": "openclaw"})
    local = "http://127.0.0.1:7860"
    return TestClient(web.app, base_url=local, headers={"Origin": local})


def answer(page_api):
    return page_api.post("/api/chat/question/answer",
                         json={"questionId": "ask_1:0", "answers": {"q": ["B"]}}).json()


def test_answer_endpoint_says_expired_when_the_question_is_closed(page_api):
    StandInGateway.outcome = gq.GatewayQuestionExpiredError("question.resolve: question closed")
    body = answer(page_api)
    assert body["ok"] is False
    assert body["expired"] is True
    assert "not supported" not in json.dumps(body)


def test_answer_endpoint_still_resolves_a_live_question(page_api):
    StandInGateway.outcome = None
    body = answer(page_api)
    assert body["ok"] is True
    assert not body.get("expired")


def test_other_answer_failures_are_not_called_expired(page_api):
    StandInGateway.outcome = gq.GatewayQuestionError("question.resolve failed: bad answer")
    body = answer(page_api)
    assert body["ok"] is False
    assert not body.get("expired")


# --- the bridge's poll step -------------------------------------------------

HOOK_LIMIT_MS = 600_000
TWO_HOURS_MS = 7_200_000


class StandInQuestionList:
    """Stands in for the gateway's list of pending questions."""

    def __init__(self, pending):
        self.pending = pending

    def list_questions(self, session_key=None, status=None):
        assert status == "pending"
        return list(self.pending)


def hook_question(created=1_000_000):
    return {"id": "toolu_01ABC:0", "createdAtMs": created, "expiresAtMs": created + TWO_HOURS_MS,
            "questions": [{"questionId": "q", "question": "上图文字", "options": []}]}


def test_a_new_hook_question_is_pushed_with_the_hooks_deadline_not_the_gateways():
    pushed = set()
    events = gq.question_events(StandInQuestionList([hook_question()]), "agent:main:web", pushed)
    assert [e["kind"] for e in events] == ["question"]
    assert events[0]["payload"]["id"] == "toolu_01ABC:0"
    # the hook cancels 10 minutes after the question appears, long before the gateway's 2 hours
    assert events[0]["payload"]["expiresAtMs"] == 1_000_000 + HOOK_LIMIT_MS


def test_an_ask_user_question_keeps_the_gateways_own_deadline():
    q = hook_question()
    q["id"] = "ask_77"
    events = gq.question_events(StandInQuestionList([q]), "agent:main:web", set())
    assert events[0]["payload"]["expiresAtMs"] == 1_000_000 + TWO_HOURS_MS


def test_a_question_is_pushed_once():
    pushed = set()
    source = StandInQuestionList([hook_question()])
    gq.question_events(source, "agent:main:web", pushed)
    assert gq.question_events(source, "agent:main:web", pushed) == []


def test_a_pushed_question_that_leaves_the_pending_list_is_reported_closed():
    pushed = set()
    source = StandInQuestionList([hook_question()])
    gq.question_events(source, "agent:main:web", pushed)
    source.pending = []
    events = gq.question_events(source, "agent:main:web", pushed)
    assert events == [{"kind": "question_closed", "payload": {"id": "toolu_01ABC:0"}}]
    assert gq.question_events(source, "agent:main:web", pushed) == []
