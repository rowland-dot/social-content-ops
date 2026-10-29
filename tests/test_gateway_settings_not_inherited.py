"""Issue 53: a value saved in Easel's settings panel reaches the next agent run without a gateway restart.

Cause: OpenClaw loads the `.env` of the folder its gateway runs in into its own environment, and only fills keys
that are not set yet, so the start-up copy never changes. Every agent shell inherits that copy. Easel's shared
settings loaders let a non-empty inherited value win (issue 46), so they act on the stale copy.

Seam: `scripts/gateway.sh start`, run for real in a scratch project root. `openclaw` is a stub that runs
OpenClaw's own installed settings-file loader the way the gateway does (at start, and again on a config reload)
and then plays the agent shell: a child process that inherits the stub's environment and runs a real shared
loader on the settings file. Catches: the gateway start script handing the settings file to agent shells.
Does not catch: OpenClaw changing how it loads the file (the stub reads the installed copy, so an upgrade that
renames it makes these tests skip rather than pass).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SHARED = REPO / "skills" / "shared" / "scripts"
LOADER_MODULES = ["ai_video", "ai_image", "ai_music", "voice_clone"]


def _nvm(pattern: str) -> list[str]:
    return sorted(glob.glob(os.path.expanduser(f"~/.nvm/versions/node/*/{pattern}")))


def _find_openclaw_loader() -> tuple[str, str, str] | None:
    """(node binary, loader module path, export name of loadDotEnv), or None when OpenClaw is not installed."""
    node = shutil.which("node") or next(iter(_nvm("bin/node")), None)
    dists = [Path(p) / "dist" for p in _nvm("lib/node_modules/openclaw")]
    oc = shutil.which("openclaw")
    if oc:
        dists.insert(0, Path(oc).resolve().parent / "dist")
    for dist in dists:
        for module in sorted(dist.glob("dotenv-*.mjs")) if dist.is_dir() else []:
            m = re.search(r"loadDotEnv as (\w+)", module.read_text(encoding="utf-8"))
            if node and m:
                return node, module.as_posix(), m.group(1)
    return None


LOADER = _find_openclaw_loader()
pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or LOADER is None or not shutil.which("curl"),
    reason="needs Linux (WSL), curl, and OpenClaw's installed settings-file loader",
)

STUB = """#!/usr/bin/env node
import { createServer } from "node:http";
import { execFileSync } from "node:child_process";
const args = process.argv.slice(2);
if (args.includes("--version")) { console.log("OpenClaw 2026.10.1"); process.exit(0); }
const { %(export)s: loadDotEnv } = await import(%(module)s);
loadDotEnv({ quiet: true });   // what the gateway does at start
const AGENT_SHELL = `
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1]); module = __import__(sys.argv[2])
module.load_env_file(Path(sys.argv[3]))
print(json.dumps({k: os.environ.get(k) for k in sys.argv[4].split(",")}))
`;
createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  const keys = (u.searchParams.get("keys") || "").split(",").filter(Boolean);
  let body = "ok";
  if (u.pathname === "/reload") loadDotEnv({ quiet: true });   // OpenClaw re-runs this on every config load
  else if (u.pathname === "/pid") body = String(process.pid);
  else if (u.pathname === "/env") body = JSON.stringify(Object.fromEntries(keys.map((k) => [k, process.env[k] ?? null])));
  else if (u.pathname === "/shell") body = execFileSync(%(python)s, ["-c", AGENT_SHELL, %(shared)s,
      u.searchParams.get("module"), u.searchParams.get("env"), keys.join(",")], { env: process.env }).toString();
  res.end(body);
}).listen(Number(process.env.OPENCLAW_GATEWAY_PORT), "127.0.0.1");
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Gateway:
    def __init__(self, root: Path, port: int):
        self.root, self.port, self.env_file = root, port, root / ".env"

    def get(self, path: str, **query) -> str:
        url = f"http://127.0.0.1:{self.port}{path}?{urllib.parse.urlencode(query)}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(url, timeout=20).read().decode()

    def save_settings(self, text: str) -> None:
        """What the settings panel does (writes the file), then OpenClaw's config reload."""
        self.env_file.write_text(text, encoding="utf-8")
        self.get("/reload")

    def agent_shell(self, module: str, *keys: str) -> dict:
        return json.loads(self.get("/shell", module=module, env=str(self.env_file), keys=",".join(keys)))

    def gateway_env(self, *keys: str) -> dict:
        return json.loads(self.get("/env", keys=",".join(keys)))


@pytest.fixture
def start_gateway(tmp_path):
    started: list[Gateway] = []

    def start(settings: str, launch_env: dict | None = None) -> Gateway:
        root = tmp_path / "project"
        (root / "scripts").mkdir(parents=True)
        shutil.copy(REPO / "scripts" / "gateway.sh", root / "scripts" / "gateway.sh")
        (root / "easel").symlink_to(REPO / "easel", target_is_directory=True)
        (root / ".env").write_text(settings, encoding="utf-8")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        node, module, export = LOADER
        stub = bin_dir / "openclaw"
        stub.write_text(STUB % {"export": export, "module": json.dumps(module), "python": json.dumps(sys.executable),
                                "shared": json.dumps(str(SHARED))}, encoding="utf-8")
        stub.chmod(0o755)
        (tmp_path / "home").mkdir()
        port = _free_port()
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("OPENCLAW_", "EASEL_")) and k not in LAUNCH_KEYS and not k.lower().endswith("_proxy")}
        env.update({
            "HOME": str(tmp_path / "home"),
            "PATH": f"{bin_dir}:{Path(node).parent}:{env.get('PATH', '')}",
            "EASEL_GATEWAY_PORT": str(port),
            "EASEL_GATEWAY_LOG": str(tmp_path / "gateway.log"),
            "EASEL_RAW_STREAM_PATH": str(tmp_path / "raw-stream.jsonl"),
            **(launch_env or {}),
        })
        done = subprocess.run(["bash", str(root / "scripts" / "gateway.sh"), "start"], env=env, cwd=root,
                              capture_output=True, text=True, timeout=120)
        gateway = Gateway(root, port)
        started.append(gateway)
        assert "Gateway started" in done.stdout, done.stdout + done.stderr
        return gateway

    yield start
    for gateway in started:
        try:
            os.kill(int(gateway.get("/pid")), signal.SIGTERM)
        except OSError:
            pass
    time.sleep(0.2)


LAUNCH_KEYS = {"VIDEO_PROVIDER", "VOICE_PROVIDER", "IMG_PROVIDER", "MUSIC_PROVIDER", "ARK_API_KEY", "ARK_MODEL",
               "CLAUDE_MODEL"}


def test_a_changed_and_a_cleared_setting_reach_the_next_agent_shell_without_a_restart(start_gateway):
    gateway = start_gateway("VOICE_PROVIDER=chatgpt\nMUSIC_PROVIDER=suno\n")
    for module in LOADER_MODULES:
        assert gateway.agent_shell(module, "VOICE_PROVIDER", "MUSIC_PROVIDER") == {
            "VOICE_PROVIDER": "chatgpt", "MUSIC_PROVIDER": "suno"}, module
    gateway.save_settings("VOICE_PROVIDER=edge\nMUSIC_PROVIDER=\n")
    for module in LOADER_MODULES:
        shell = gateway.agent_shell(module, "VOICE_PROVIDER", "MUSIC_PROVIDER")
        assert shell["VOICE_PROVIDER"] == "edge", f"{module}: changed value stayed {shell['VOICE_PROVIDER']!r}"
        assert not (shell["MUSIC_PROVIDER"] or "").strip(), f"{module}: cleared value stayed {shell['MUSIC_PROVIDER']!r}"


def test_a_value_set_in_the_gateways_launch_environment_still_wins_before_and_after_a_save(start_gateway):
    gateway = start_gateway("VOICE_PROVIDER=chatgpt\n", launch_env={"VOICE_PROVIDER": "deliberate"})
    for module in LOADER_MODULES:
        assert gateway.agent_shell(module, "VOICE_PROVIDER") == {"VOICE_PROVIDER": "deliberate"}, module
    gateway.save_settings("VOICE_PROVIDER=edge\n")
    for module in LOADER_MODULES:
        assert gateway.agent_shell(module, "VOICE_PROVIDER") == {"VOICE_PROVIDER": "deliberate"}, module


def test_every_variable_the_start_script_exports_still_reaches_the_gateway_process(start_gateway, tmp_path):
    gateway = start_gateway("VOICE_PROVIDER=chatgpt\n", launch_env={"EASEL_PROXY": "http://proxy.invalid:3128"})
    keys = ["EASEL_ROOT", "OPENCLAW_GATEWAY_PORT", "OPENCLAW_RAW_STREAM", "OPENCLAW_RAW_STREAM_PATH",
            "EASEL_ASKUSER_CARDS", "http_proxy", "https_proxy", "no_proxy"]
    env = gateway.gateway_env(*keys)
    assert env["EASEL_ROOT"] == str(gateway.root)
    assert env["OPENCLAW_GATEWAY_PORT"] == str(gateway.port)
    assert env["OPENCLAW_RAW_STREAM"] == "1"
    assert env["OPENCLAW_RAW_STREAM_PATH"] == str(tmp_path / "raw-stream.jsonl")
    assert env["EASEL_ASKUSER_CARDS"] in ("0", "1")
    assert env["http_proxy"] == env["https_proxy"] == "http://proxy.invalid:3128"
    assert "localhost" in env["no_proxy"]


def test_openclaws_other_settings_file_locations_hold_none_of_the_project_settings_keys():
    """Fix A holds only while OpenClaw has no other copy of the project's keys to load for the easel profile.

    OpenClaw also loads `<state folder>/.env` (the profile's, and the default profile's) and
    `~/.config/openclaw/gateway.env`. Any of them holding a key the project's settings file defines would put
    that key back into every agent shell at start-up.
    """
    home = Path.home()
    project_keys = {line.split("=", 1)[0].strip().removeprefix("export ").strip()
                    for line in (REPO / ".env.example").read_text(encoding="utf-8").splitlines()
                    if "=" in line and not line.lstrip().startswith("#")}
    leaks = {}
    for path in (home / ".openclaw-easel" / ".env", home / ".openclaw" / ".env",
                 home / ".config" / "openclaw" / "gateway.env"):
        if path.is_file():
            held = {line.split("=", 1)[0].strip().removeprefix("export ").strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if "=" in line and not line.lstrip().startswith("#")}
            if held & project_keys:
                leaks[str(path)] = sorted(held & project_keys)
    assert not leaks, f"OpenClaw would load these project settings keys into agent shells: {leaks}"
