"""Claude Code adapter: print mode with streamed JSON in and out; credentials remain in Claude Code."""
from __future__ import annotations

import asyncio
import json
import os
import signal

from easel.persona import external_profile_dirs

from .base import Descriptor, HarnessError, RunRequest
from .commands import base_command
from .permissions import _inside_workspace
from .workspace import harness_instructions

WRITE_TOOLS = ("Edit", "MultiEdit", "NotebookEdit", "Write")
# Pay-per-call credentials: Claude Code must only ever use the owner's subscription login.
PAID_CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
ALLOW, DENY = "允许本次", "拒绝"
UNSUPPORTED = "Claude Code 请求了当前操作不支持的交互或工具，请使用流式对话确认权限"


def _allow(tool_input: dict) -> dict:
    return {"behavior": "allow", "updatedInput": tool_input}


def _deny(message: str) -> dict:
    return {"behavior": "deny", "message": message}


async def _drain(stream):
    while await stream.read(8192):
        pass


async def _terminate(process):
    def kill_group(sent):
        try:
            os.killpg(process.pid, sent)
        except (ProcessLookupError, PermissionError):
            pass

    if os.name == "nt":
        if process.returncode is None:
            process.kill()
    else:
        kill_group(signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), 3)
    except asyncio.TimeoutError:
        if os.name == "nt":
            process.kill()
        else:
            kill_group(signal.SIGKILL)
        await process.wait()
    if os.name != "nt":
        kill_group(signal.SIGKILL)


class ClaudeAdapter:
    descriptor = Descriptor("claude", "Claude Code", "stream-json", "安装 Claude Code（claude 命令）；claude 登录订阅账号")

    async def run(self, request: RunRequest, emit, ask, bind):
        if request.sandbox not in ("read-only", "workspace-write"):
            raise HarnessError("Claude Code 只允许只读或工作区写入权限")
        mapped = [folder for folder in external_profile_dirs(request.env).values() if folder.is_dir()]
        command = (list(request.command) if request.command else base_command("claude")) + [
            "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--permission-prompt-tool", "stdio",
            # Skips the user's own CLAUDE.md, rules, hooks and plugins; sign-in and tools stay.
            "--safe-mode", "--append-system-prompt", harness_instructions(request)]
        if request.model:
            command += ["--model", request.model]
        if request.native_id:
            command += ["--resume", request.native_id]
        if mapped:
            command += ["--add-dir", *(str(folder) for folder in mapped)]
        env = {key: value for key, value in request.env.items() if key not in PAID_CREDENTIALS}
        env.update({"EASEL_ROOT": str(request.cwd.resolve()), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        try:
            process = await asyncio.create_subprocess_exec(
                *command, cwd=str(request.cwd), env=env, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                limit=4 * 1024 * 1024, start_new_session=os.name != "nt")
        except OSError as error:
            raise HarnessError("无法启动 Claude Code，请检查安装与 PATH") from error
        drain = asyncio.create_task(_drain(process.stderr))
        try:
            await self._turn(request, process, mapped, emit, ask, bind)
        finally:
            drain.cancel()
            await _terminate(process)
            await asyncio.gather(drain, return_exceptions=True)

    async def _turn(self, request, process, mapped, emit, ask, bind):
        session = ""
        streamed: set[tuple[str, str]] = set()
        message_id = ""

        async def send(message):
            try:
                process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as error:
                raise HarnessError("Claude Code 进程已退出，请检查 CLI 登录与模型配置") from error

        def accept(session_id):
            nonlocal session
            if not session_id or session:
                return
            if request.native_id and session_id != request.native_id:
                raise HarnessError("Claude Code 返回了不同的原生会话 ID，不会替换已有历史")
            session = session_id
            bind(session)

        async def put(questions):
            try:
                return await ask(questions)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                raise HarnessError(UNSUPPORTED) from error

        async def decide(body):
            name, tool_input = body.get("tool_name"), body.get("input") or {}
            if name == "AskUserQuestion":
                questions = tool_input.get("questions") or []
                if any(question.get("isSecret") for question in questions):
                    raise HarnessError("请在终端完成敏感凭证输入")
                answers = await put([{**question, "questionId": f"q{index}"}
                                     for index, question in enumerate(questions)])
                return _allow({**tool_input, "answers": {
                    question.get("question", ""): ", ".join(answers.get(f"q{index}", []))
                    for index, question in enumerate(questions)}})
            if name in WRITE_TOOLS:
                if request.sandbox == "read-only":
                    return _deny("只读权限不允许写入文件")
                path = tool_input.get("file_path") or tool_input.get("notebook_path")
                if isinstance(path, str) and any(
                        _inside_workspace(path, folder) for folder in (request.cwd, *mapped)):
                    return _allow(tool_input)
            detail = tool_input.get("command") or tool_input.get("file_path") or json.dumps(
                tool_input, ensure_ascii=False)
            answers = await put([{
                "questionId": "permission", "header": "执行授权",
                "question": f"Claude Code 请求使用工具 {name}（仅本次）：{str(detail)[:3000]}",
                "options": [{"label": ALLOW}, {"label": DENY}]}])
            return _allow(tool_input) if answers.get("permission") == [ALLOW] else _deny("用户拒绝了此操作")

        await send({"type": "user", "message": {
            "role": "user", "content": [{"type": "text", "text": request.prompt}]}})
        while True:
            try:
                line = await process.stdout.readline()
                item = json.loads(line) if line else None
            except ValueError:
                raise HarnessError("Claude Code 返回了无效数据") from None
            if item is None:
                raise HarnessError("Claude Code 在本轮完成前退出，请检查 CLI 登录与模型配置")
            if not isinstance(item, dict):
                raise HarnessError("Claude Code 返回了无效数据")
            kind = item.get("type")
            if kind == "system" and item.get("subtype") == "init":
                accept(item.get("session_id"))
            elif kind == "stream_event":
                event = item.get("event") or {}
                delta = event.get("delta") or {}
                if event.get("type") == "message_start":
                    message_id = (event.get("message") or {}).get("id", "")
                elif delta.get("type") == "text_delta":
                    streamed.add((message_id, "text"))
                    emit("token", delta.get("text", ""))
                elif delta.get("type") == "thinking_delta":
                    streamed.add((message_id, "thinking"))
                    emit("thinking", delta.get("thinking", ""))
            elif kind == "assistant":
                message = item.get("message") or {}
                for block in message.get("content") or []:
                    if block.get("type") == "text" and (message.get("id", ""), "text") not in streamed:
                        emit("token", block.get("text", ""))
                    elif block.get("type") == "thinking" and (message.get("id", ""), "thinking") not in streamed:
                        emit("thinking", block.get("thinking", ""))
                    elif block.get("type") == "tool_use":
                        emit("activity", f"工具：{block.get('name', 'tool')}")
            elif kind == "control_request":
                body = item.get("request") or {}
                if body.get("subtype") != "can_use_tool":
                    raise HarnessError("不支持的 Claude Code 客户端请求")
                await send({"type": "control_response", "response": {
                    "subtype": "success", "request_id": item.get("request_id"),
                    "response": await decide(body)}})
            elif kind == "result":
                if item.get("is_error") or item.get("subtype") != "success":
                    raise HarnessError(
                        f"Claude Code 本轮未完成：{item.get('subtype', 'error')}，请检查原生登录与模型配置")
                accept(item.get("session_id"))
                if not session:
                    raise HarnessError("Claude Code 未返回原生会话 ID")
                return
