"""Claude Code as an Easel engine: print mode with streamed JSON, no OpenClaw gateway."""
import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import web.app as web
from easel import harnesses
from easel.harnesses import store
from easel.harnesses.base import HarnessError, RunRequest
from easel.harnesses.workspace import harness_instructions

FAKE = Path(__file__).parent / "fixtures" / "harness_claude.py"


def claude_request(tmp_path, mode="normal", native_id="", sandbox="read-only", **env):
    environment = {**os.environ, "FAKE_CLAUDE_MODE": mode,
                   "FAKE_CLAUDE_AUDIT": str(tmp_path / "audit.jsonl"), **env}
    return RunRequest("hello", tmp_path, environment, native_id, "test-model", sandbox, 10,
                      (sys.executable, str(FAKE)))


def records(tmp_path):
    return [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]


def launch(tmp_path):
    return records(tmp_path)[0]


def control_response(tmp_path):
    return next(message for message in records(tmp_path)
                if message.get("type") == "control_response")["response"]["response"]


async def refuse(questions):
    raise AssertionError("no question expected")


def run_claude(request, answer=refuse):
    events, identifiers = [], []
    asyncio.run(harnesses.adapter("claude").run(
        request, lambda kind, text: events.append((kind, text)), answer, identifiers.append))
    return events, identifiers


def test_claude_code_is_a_registered_engine():
    descriptor = harnesses.adapter("claude").descriptor
    assert descriptor.id == "claude"
    assert descriptor.label == "Claude Code"
    assert "claude" in store.IDS
    assert harnesses.describe("claude")["label"] == "Claude Code"


def test_describe_reports_whether_the_claude_program_is_installed(monkeypatch):
    monkeypatch.setattr("easel.harnesses.commands.shutil.which", lambda command: None)
    assert harnesses.describe("claude")["installed"] is False
    monkeypatch.setattr("easel.harnesses.commands.shutil.which", lambda command: "/usr/local/bin/claude")
    assert harnesses.describe("claude")["installed"] is True


def test_settings_and_bindings_accept_claude(tmp_path):
    store.write_json(tmp_path / "_harness" / "config.json",
                     {"runtime": "claude", "models": {"claude": "opus"}})
    config = store.settings(tmp_path, {})
    assert config["runtime"] == "claude"
    assert config["models"] == {"claude": "opus"}
    store.bind(tmp_path, "web-session", "claude", "native-claude")
    assert store.binding(tmp_path, "web-session") == {"runtime": "claude", "native_id": "native-claude"}


def test_streamed_text_and_thinking_reach_emit_once(tmp_path):
    events, _ = run_claude(claude_request(tmp_path))
    assert events == [("thinking", "思考"), ("token", "你好")]


def test_text_that_was_not_streamed_comes_from_the_final_message(tmp_path):
    events, _ = run_claude(claude_request(tmp_path, "no-stream"))
    assert events == [("token", "你好")]


def test_tool_use_reaches_emit_as_activity(tmp_path):
    events, _ = run_claude(claude_request(tmp_path, "tool"))
    assert ("activity", "工具：Read") in events


def test_claude_is_started_in_print_mode_with_streamed_json_and_a_permission_pipe(tmp_path):
    request = claude_request(tmp_path)
    run_claude(request)
    argv = launch(tmp_path)["argv"]
    assert "--print" in argv or "-p" in argv
    assert argv[argv.index("--input-format") + 1] == "stream-json"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--permission-prompt-tool") + 1] == "stdio"
    assert argv[argv.index("--model") + 1] == "test-model"
    assert launch(tmp_path)["cwd"] == str(tmp_path)


def test_shared_workspace_instructions_are_appended_to_the_system_prompt(tmp_path):
    request = claude_request(tmp_path)
    run_claude(request)
    argv = launch(tmp_path)["argv"]
    assert argv[argv.index("--append-system-prompt") + 1] == harness_instructions(request)


def test_personal_and_operator_instructions_are_not_loaded(tmp_path):
    run_claude(claude_request(tmp_path))
    assert "--safe-mode" in launch(tmp_path)["argv"]


def test_no_api_key_reaches_claude(tmp_path):
    run_claude(claude_request(tmp_path, ANTHROPIC_API_KEY="secret-test-key",
                              ANTHROPIC_AUTH_TOKEN="secret-test-token"))
    assert launch(tmp_path)["has_api_key"] is False
    assert launch(tmp_path)["has_auth_token"] is False


def test_prompt_is_sent_as_a_streamed_user_message(tmp_path):
    run_claude(claude_request(tmp_path))
    message = next(item for item in records(tmp_path) if item.get("type") == "user")
    assert message["message"]["role"] == "user"
    assert message["message"]["content"] == [{"type": "text", "text": "hello"}]


def test_session_id_is_bound_on_the_first_turn_and_resumed_on_the_next(tmp_path):
    _, first = run_claude(claude_request(tmp_path))
    assert first == ["claude-session"]
    assert "--resume" not in launch(tmp_path)["argv"]
    (tmp_path / "audit.jsonl").unlink()
    _, second = run_claude(claude_request(tmp_path, native_id="claude-session"))
    argv = launch(tmp_path)["argv"]
    assert argv[argv.index("--resume") + 1] == "claude-session"
    assert second == ["claude-session"]


def test_changed_session_id_raises_instead_of_replacing_history(tmp_path):
    with pytest.raises(HarnessError, match="不同的原生会话 ID"):
        run_claude(claude_request(tmp_path, "wrong-session", native_id="old-native"))


@pytest.mark.parametrize("allow", [True, False])
def test_permission_request_reaches_ask_and_the_answer_is_passed_back(tmp_path, allow):
    asked = []

    async def answer(questions):
        asked.append(questions)
        options = questions[0]["options"]
        assert len(options) == 2
        assert "Always" not in str(options)
        return {questions[0]["questionId"]: [options[0 if allow else 1]["label"]]}

    run_claude(replace(claude_request(tmp_path, "permission"), claude_auto_approve=False), answer)
    assert "read public file" in asked[0][0]["question"]
    response = control_response(tmp_path)
    assert response["behavior"] == ("allow" if allow else "deny")
    if allow:
        assert response["updatedInput"] == {"command": "read public file"}
    else:
        assert response["message"]


def test_tool_use_is_allowed_without_a_question_box_by_default(tmp_path):
    run_claude(claude_request(tmp_path, "permission"))  # `refuse` fails the test if a box opens
    response = control_response(tmp_path)
    assert response["behavior"] == "allow"
    assert response["updatedInput"] == {"command": "read public file"}


def test_auto_approve_still_denies_writes_in_read_only(tmp_path):
    run_claude(claude_request(tmp_path, "write", FAKE_CLAUDE_PATH=str(tmp_path / "a.md")))
    assert control_response(tmp_path)["behavior"] == "deny"


def test_auto_approve_still_sends_user_questions_to_the_box(tmp_path):
    asked = []

    async def answer(questions):
        asked.append(questions)
        return {questions[0]["questionId"]: ["A"]}

    run_claude(claude_request(tmp_path, "question"), answer)
    assert asked


def test_claude_auto_approve_setting_defaults_on_and_must_be_a_switch(tmp_path):
    assert store.settings(tmp_path, {})["claude_auto_approve"] is True
    config = tmp_path / "_harness" / "config.json"
    store.write_json(config, {"claude_auto_approve": False})
    assert store.settings(tmp_path, {})["claude_auto_approve"] is False
    store.write_json(config, {"claude_auto_approve": "false"})
    with pytest.raises(HarnessError):
        store.settings(tmp_path, {})


def test_user_question_is_answered_through_the_question_box(tmp_path):
    asked = []

    async def answer(questions):
        asked.append(questions)
        return {questions[0]["questionId"]: ["B"]}

    run_claude(claude_request(tmp_path, "question"), answer)
    assert asked[0][0]["question"] == "选哪个封面？"
    assert [option["label"] for option in asked[0][0]["options"]] == ["A", "B"]
    response = control_response(tmp_path)
    assert response["behavior"] == "allow"
    assert response["updatedInput"]["answers"] == {"选哪个封面？": "B"}


def test_secret_question_is_refused_without_asking(tmp_path):
    with pytest.raises(HarnessError, match="敏感凭证"):
        run_claude(claude_request(tmp_path, "secret"))


def test_noninteractive_permission_is_an_error_not_success(tmp_path):
    async def unavailable(questions):
        raise HarnessError("requires interactive approval")

    with pytest.raises(HarnessError, match="流式对话"):
        run_claude(replace(claude_request(tmp_path, "permission"), claude_auto_approve=False), unavailable)


def test_read_only_never_writes_and_does_not_ask(tmp_path):
    run_claude(claude_request(tmp_path, "write", FAKE_CLAUDE_PATH=str(tmp_path / "a.md")))
    assert control_response(tmp_path)["behavior"] == "deny"


def test_workspace_write_allows_writes_inside_the_project_without_asking(tmp_path):
    run_claude(claude_request(tmp_path, "write", sandbox="workspace-write",
                              FAKE_CLAUDE_PATH=str(tmp_path / "outputs" / "a.md")))
    assert control_response(tmp_path)["behavior"] == "allow"


def test_workspace_write_allows_a_mapped_external_profile_folder(tmp_path):
    profile = tmp_path.parent / f"{tmp_path.name}-profile"
    profile.mkdir()
    run_claude(claude_request(tmp_path, "write", sandbox="workspace-write",
                              EASEL_PROFILE_DIRS=f"northwind={profile}",
                              FAKE_CLAUDE_PATH=str(profile / "memory.md")))
    assert control_response(tmp_path)["behavior"] == "allow"
    argv = launch(tmp_path)["argv"]
    assert str(profile) in argv[argv.index("--add-dir"):]


def test_workspace_write_asks_before_writing_outside_the_project(tmp_path):
    asked = []

    async def deny(questions):
        asked.append(questions)
        return {questions[0]["questionId"]: ["拒绝"]}

    run_claude(replace(claude_request(tmp_path, "write", sandbox="workspace-write",
                                      FAKE_CLAUDE_PATH=str(tmp_path.parent / "elsewhere.md")),
                       claude_auto_approve=False), deny)
    assert asked
    assert control_response(tmp_path)["behavior"] == "deny"


def test_unsupported_sandbox_is_refused(tmp_path):
    with pytest.raises(HarnessError, match="只读或工作区写入"):
        run_claude(claude_request(tmp_path, sandbox="danger-full-access"))


@pytest.mark.parametrize(("mode", "message"), [("error", "本轮未完成"), ("exit", "在本轮完成前退出")])
def test_failure_never_succeeds_or_leaks_keys(tmp_path, mode, message):
    with pytest.raises(HarnessError, match=message) as failure:
        run_claude(claude_request(tmp_path, mode, ANTHROPIC_API_KEY="secret-test-key"))
    assert "secret-test-key" not in str(failure.value)


def test_cancelling_a_turn_ends_the_claude_process(tmp_path):
    async def exercise():
        task = asyncio.create_task(harnesses.adapter("claude").run(
            claude_request(tmp_path, "hang"), lambda *args: None, refuse, lambda identifier: None))
        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
            path = tmp_path / "audit.jsonl"
            if path.exists() and any(item.get("started") for item in records(tmp_path)):
                break
        else:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            pytest.fail("fake Claude Code did not start its turn")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    pid = launch(tmp_path)["pid"]
    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        __import__("time").sleep(0.02)
    else:
        pytest.fail("Claude Code process survived cancellation")




def test_settings_picker_offers_claude_code_and_saves_its_model(tmp_path, monkeypatch):
    monkeypatch.delenv("EASEL_AGENT_RUNTIME", raising=False)
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(web, "ENV_FILE", env)
    monkeypatch.setattr(web, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(web, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(web, "OUTPUTS_DIR", tmp_path / "outputs")
    monkeypatch.setattr(web, "_HARNESS_TASKS", set())
    monkeypatch.setattr("easel.harnesses.commands.shutil.which", lambda command: "/usr/local/bin/" + command)
    local = "http://127.0.0.1:7860"
    with TestClient(web.app, base_url=local, headers={"Origin": local}) as client:
        agents = {agent["id"]: agent for agent in client.get("/api/settings/harness").json()["agents"]}
        assert agents["claude"]["label"] == "Claude Code"
        saved = client.post("/api/settings/harness", json={
            "runtime": "claude", "model": "opus", "sandbox": "read-only"})
        assert saved.status_code == 200
        assert saved.json()["runtime"] == "claude"
        assert saved.json()["models"]["claude"] == "opus"
        assert client.post("/api/settings/harness/models/claude").status_code == 400
