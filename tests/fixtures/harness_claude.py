"""Fake Claude Code process speaking its print-mode stream-json protocol.

Records its argv, pid, environment facts and everything it receives to FAKE_CLAUDE_AUDIT.
"""
import json
import os
import sys
import time

mode = os.environ.get("FAKE_CLAUDE_MODE", "normal")
audit = os.environ["FAKE_CLAUDE_AUDIT"]
argv = sys.argv[1:]


def record(entry):
    with open(audit, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send(message):
    print(json.dumps(message, ensure_ascii=False), flush=True)


def receive():
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    message = json.loads(line)
    record(message)
    return message


def option(name):
    return argv[argv.index(name) + 1] if name in argv else None


def ask_permission(tool_name, tool_input):
    send({"type": "control_request", "request_id": "permission-request",
          "request": {"subtype": "can_use_tool", "tool_name": tool_name,
                      "input": tool_input, "tool_use_id": "tool-1"}})
    while receive().get("type") != "control_response":
        pass


record({"argv": argv, "pid": os.getpid(), "has_api_key": "ANTHROPIC_API_KEY" in os.environ,
        "has_auth_token": "ANTHROPIC_AUTH_TOKEN" in os.environ, "cwd": os.getcwd()})
session = option("--resume") or "claude-session"
if mode == "wrong-session" and option("--resume"):
    session = "replacement-session"

receive()  # the user message
send({"type": "system", "subtype": "init", "session_id": session, "model": "fake-model"})

if mode == "hang":
    record({"started": True})
    time.sleep(60)
if mode == "exit":
    sys.exit(0)
if mode == "error":
    send({"type": "result", "subtype": "error_during_execution", "is_error": True,
          "session_id": session, "result": "invalid key secret-test-key"})
    sys.exit(1)
if mode == "permission":
    ask_permission("Bash", {"command": "read public file"})
if mode == "question":
    ask_permission("AskUserQuestion", {"questions": [{
        "question": "选哪个封面？", "header": "封面", "multiSelect": False,
        "options": [{"label": "A", "description": "圆形"}, {"label": "B", "description": "方形"}]}]})
if mode == "secret":
    ask_permission("AskUserQuestion", {"questions": [{
        "question": "请输入密码", "header": "密码", "isSecret": True, "options": []}]})
if mode == "write":
    ask_permission("Write", {"file_path": os.environ["FAKE_CLAUDE_PATH"], "content": "x"})

if mode == "no-stream":
    send({"type": "assistant", "message": {"id": "m1", "content": [{"type": "text", "text": "你好"}]}})
elif mode == "tool":
    send({"type": "assistant", "message": {"id": "m1", "content": [
        {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "a.md"}}]}})
else:
    send({"type": "stream_event", "event": {"type": "message_start", "message": {"id": "m1"}}})
    for delta in ({"type": "thinking_delta", "thinking": "思考"}, {"type": "text_delta", "text": "你好"}):
        send({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": delta}})
    send({"type": "assistant", "message": {"id": "m1", "content": [
        {"type": "thinking", "thinking": "思考"}, {"type": "text", "text": "你好"}]}})
send({"type": "result", "subtype": "success", "is_error": False, "session_id": session, "result": "你好"})
# Real Claude Code keeps reading its input after a result; wait for the adapter to end the process.
while True:
    receive()
