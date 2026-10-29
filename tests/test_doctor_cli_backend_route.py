"""doctor 必须认得「走本机 agent CLI 登录态、不填 API key」这条路线。

背景：Easel 自己的「接入 Claude Code」流程写出的配置是 primary = claude-cli/<模型>、
models.providers.anthropic 只有 baseUrl 没有 key、.env 里没有真 key。这条路线对话和
`easel ping` 都通，但 doctor 报两个假失败：
  * OpenClaw model routing —— 它拿 primary 斜杠前的 `claude-cli` 去找同名 provider 块，
    而 CLI 后端的配置块叫 `anthropic`（Gemini CLI 干脆没有块）；
  * .env (API Key) —— 它不知道这条路线本来就不需要 key。

哪些后端是 CLI 后端，只认 easel.local_agents.KNOWN_AGENT_CLIS 这一张表。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from easel.commands import doctor  # noqa: E402

# Easel 的「接入 Claude Code」写出的 anthropic 块：有地址、没有 key、模型表为空。
KEYLESS_ANTHROPIC = {"baseUrl": "https://api.anthropic.com", "models": []}


def _install(tmp_path, monkeypatch, primary, providers, on_path=()):
    """写一份 openclaw.json，并规定 PATH 上有哪些命令（只让 on_path 里的命令能被 which 找到）。"""
    cfg = {"agents": {"defaults": {"model": {"primary": primary}}},
           "models": {"providers": providers}}
    monkeypatch.setenv("EASEL_OPENCLAW_STATE_DIR", str(tmp_path))
    (tmp_path / "openclaw.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(
        doctor.shutil, "which",
        lambda cmd, *a, **k: f"/fake/bin/{cmd}" if cmd in on_path else None)


def test_claude_cli_primary_with_keyless_anthropic_block_is_routable(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "claude-cli/opus",
             {"anthropic": KEYLESS_ANTHROPIC}, on_path=("claude",))
    ok, detail = doctor._primary_model_routable()
    assert ok, f"Easel 自己写出的 claude-cli 配置被误判为不可路由：{detail}"


def test_gemini_cli_primary_with_no_provider_block_is_routable(tmp_path, monkeypatch):
    """Easel 的接入流程对 Gemini CLI 根本不写 provider 块。"""
    _install(tmp_path, monkeypatch, "google-gemini-cli/gemini-2.5-pro", {}, on_path=("gemini",))
    ok, detail = doctor._primary_model_routable()
    assert ok, f"google-gemini-cli 路线被误判为不可路由：{detail}"


def test_claude_cli_primary_without_claude_on_path_names_the_missing_cli(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "claude-cli/opus",
             {"anthropic": KEYLESS_ANTHROPIC}, on_path=())
    ok, detail = doctor._primary_model_routable()
    assert not ok
    assert "claude" in detail and "Claude Code" in detail, f"提示没说清缺哪个 CLI：{detail}"


def test_key_based_provider_verdicts_are_unchanged(tmp_path, monkeypatch):
    """CLI 分支不能放松 key 型 provider 的判定：openai 没有 openai 块照样不过，
    哪怕 PATH 上装着 claude。"""
    _install(tmp_path, monkeypatch, "openai/gpt-4o", {}, on_path=("claude", "gemini"))
    ok, detail = doctor._primary_model_routable()
    assert not ok and "models.providers.openai 不存在" in detail


# ── .env 里的 API key 检查：CLI 路线本来就不需要 key ─────────────────────────


def _env_file(tmp_path, monkeypatch, text):
    """.env 内容由 text 决定；text 为 None 表示根本没有 .env。"""
    monkeypatch.setattr(doctor, "PROJECT_ROOT", tmp_path)
    for name in ("EASEL_DIRECT_API_BASE_URL", "EASEL_DIRECT_API_MODEL", "EASEL_DIRECT_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    if text is not None:
        (tmp_path / ".env").write_text(text, encoding="utf-8")


@pytest.mark.parametrize("env_text", [
    "ANTHROPIC_API_KEY=sk-ant-REPLACE_ME\n",  # .env.example 带来的占位符
    "",                                       # 空文件
    None,                                     # 没有 .env
])
def test_key_check_passes_on_installed_cli_route_without_a_key(tmp_path, monkeypatch, env_text):
    state = tmp_path / "state"
    state.mkdir()
    _install(state, monkeypatch, "claude-cli/opus",
             {"anthropic": KEYLESS_ANTHROPIC}, on_path=("claude",))
    _env_file(tmp_path, monkeypatch, env_text)
    assert doctor._env_key_valid()


def test_key_check_still_fails_when_the_cli_is_not_installed(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    _install(state, monkeypatch, "claude-cli/opus",
             {"anthropic": KEYLESS_ANTHROPIC}, on_path=())
    _env_file(tmp_path, monkeypatch, "ANTHROPIC_API_KEY=sk-ant-REPLACE_ME\n")
    assert not doctor._env_key_valid()


def test_key_check_still_fails_for_key_based_primary_with_placeholder_env(tmp_path, monkeypatch):
    """claude 装着也不能替 openai 路线免 key。"""
    state = tmp_path / "state"
    state.mkdir()
    _install(state, monkeypatch, "openai/gpt-4o",
             {"openai": {"apiKey": "sk-x"}}, on_path=("claude",))
    _env_file(tmp_path, monkeypatch, "ANTHROPIC_API_KEY=sk-ant-REPLACE_ME\n")
    assert not doctor._env_key_valid()
