"""Test world for the LibTV update gate (issue 37): a stand-in for LibTV's two servers and a fixture repo root.

The gate is driven only through its command line (ops/libtv-update-gate/libtv_gate.py). Everything LibTV
answers comes from a stand-in HTTP server on a loopback port; the repo it reads its pins from is a small
fixture folder, not this checkout. No `libtv` program is ever involved: a stand-in on PATH records any call.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "ops" / "libtv-update-gate" / "libtv_gate.py"
EVIDENCE = REPO / "work" / ".scratch" / "easel-setup-gaps" / "evidence" / "32-libtv-probe" / "reopen-2026-10-14"

LAST_MODIFIED = "Sun, 09 Aug 2026 06:20:00 GMT"

# the answer LibTV's old skill gave when it was retired (issue 32's evidence, get-session-nokey.json): HTTP 200,
# code 0, no data, a message telling the caller to install the new CLI
RETIREMENT_ANSWER = {
    "code": 0,
    "message": "LibTV Skill 已升级为 LibTV CLI。\n\n请删除本地旧版 LibTV Skill，并安装新版 LibTV CLI Skill。",
    "trace_id": "381e942640ab18501d0bc23de27c01f1",
}
CANARY_BASELINE = {"code": 401, "msg": "未登录", "data": None}

CLAUDE_MD = """# project

## Paid generation needs the owner's yes, every run

Never start a generation that spends the owner's money without his explicit yes.

LibTV credits are prepaid per use and count as paid media here. Every command that starts a LibTV run needs the owner's yes first: `libtv node <n> --run`, `libtv node create <n> --run`, `libtv group --run`, `libtv script storyboard`, `libtv image shortcut <scene> -n <node>` (it starts a generation with no `--run` flag) and any `count` above 1 on an image or video node. Uploads, queries, `libtv account info` and `libtv model search` are free.

## Agent skills

other text
"""

BASE_COMMANDS = {
    "node": {"": [], "create": ["--run", "--type"], "list": []},
    "login": {"": [], "web": []},
    "image": {"": [], "shortcut": []},
}

BASE_DOCS = {
    "SKILL.md": "# libtv\n\nUse the commands.\n",
    "commands/node.md": "# node\n\n`libtv node <n>`\n",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def program_source(version: str, commands: dict[str, dict[str, list[str]]]) -> str:
    """Text shaped like the program's embedded source: a package record, a decoy bundled-library command that
    the real tree does not contain, and the registration functions reached from the root function."""
    lines = [
        'program.command("serve").description("a bundled library, not LibTV");',
        "var package_default = {",
        '  name: "@liblib-apps/libtv-cli",',
        f'  version: "{version}",',
        "  private: true",
        "};",
    ]
    root_body = []
    for group, subs in commands.items():
        fn = "register" + group.capitalize() + "Commands"
        body = []
        for sub, options in subs.items():
            if sub == "":
                continue
            opt_text = "".join(f'.option("{o}", "an option")' for o in options)
            body.append(f'  parent.command("{sub}").description("{sub}"){opt_text}.action(async () => {{}});')
        lines += [f"function {fn}(parent) {{", *body, "}", f'__name({fn}, "{fn}");']
        top_options = "".join(f'.option("{o}", "an option")' for o in subs.get("", []))
        root_body.append(f'  const {group} = program2.command("{group}").description("{group}"){top_options};')
        root_body.append(f"  {fn}({group});")
    lines += [
        "function registerLibtvCommandsForProgram(program2) {",
        *root_body,
        "}",
        '__name(registerLibtvCommandsForProgram, "registerLibtvCommandsForProgram");',
    ]
    return "\n".join(lines) + "\n"


def make_zip(members: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def program_zip(version: str = "1.1.3", commands=None, filler: bytes = b"") -> bytes:
    src = program_source(version, commands if commands is not None else BASE_COMMANDS)
    program = b"\x7fELF" + b"\x00" * 64 + src.encode("utf-8") + filler
    return make_zip({"libtv-linux-x64/libtv": program})


def program_inside(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        return z.read("libtv-linux-x64/libtv")


def channel_envelope(payload: object) -> bytes:
    link = payload if isinstance(payload, str) else json.dumps(payload, indent=2, ensure_ascii=False)
    body = {"code": 0, "msg": None, "data": {"linkUrl": link, "id": 0}}
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0
    head_length: int | None = None   # the Content-Length a HEAD answers with, when it differs from the body
    drop: bool = False               # close the connection without answering
    sequence: list[bytes] | None = None   # successive GET bodies, one per request (the last repeats)


class StandIn(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.routes: dict[str, Reply] = {}
        self.log: list[tuple[str, str]] = []
        self.header_log: list[tuple[str, dict[str, str]]] = []
        self.stopping = threading.Event()   # set at teardown: a delayed reply ends without writing
        self.handlers: list[threading.Thread] = []
        self.errors: list[str] = []         # handler exceptions, reported by the fixture as the test's failure

    def process_request(self, request, client_address):
        # ThreadingMixIn only tracks non-daemon handler threads, and teardown must wait for every one
        t = threading.Thread(
            target=self.process_request_thread, args=(request, client_address), name="stand-in-handler", daemon=True
        )
        self.handlers.append(t)
        t.start()

    def handle_error(self, request, client_address):
        # the default prints the traceback to whatever sys.stderr is then, which may be another test's
        if not self.stopping.is_set():
            self.errors.append(f"request from {client_address}: {sys.exc_info()[1]!r}")

    def stop(self, serve_thread: threading.Thread) -> list[str]:
        """tear down; return what the owning test must fail on (handler errors, handlers that would not end)"""
        self.stopping.set()
        self.shutdown()
        serve_thread.join(5)
        self.server_close()
        deadline = time.time() + 5
        for t in self.handlers:
            t.join(max(0.0, deadline - time.time()))
        problems = list(self.errors)
        alive = [t for t in self.handlers if t.is_alive()]
        if alive:
            problems.append(f"{len(alive)} handler thread(s) still running 5 s after teardown began")
        return problems

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence
        pass

    def _serve(self, send_body: bool):
        try:
            self._answer(send_body)
        except Exception as exc:
            self.close_connection = True
            if not self.server.stopping.is_set():  # type: ignore[attr-defined]
                self.server.errors.append(f"{self.command} {self.path}: {type(exc).__name__}: {exc}")  # type: ignore[attr-defined]

    def _answer(self, send_body: bool):
        server: StandIn = self.server  # type: ignore[assignment]
        server.log.append((self.command, self.path))
        server.header_log.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
        reply = server.routes.get(self.path)
        if reply is None:
            reply = Reply(404, b"not found")
        if reply.delay and server.stopping.wait(reply.delay):
            self.close_connection = True   # teardown cancelled the delayed reply; nobody is waiting for it
            return
        if reply.drop:
            self.close_connection = True
            return
        body = reply.body
        if send_body and reply.sequence:
            body = reply.sequence.pop(0) if len(reply.sequence) > 1 else reply.sequence[0]
        length = len(body)
        if not send_body and reply.head_length is not None:
            length = reply.head_length
        self.send_response(reply.status)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Last-Modified", reply.headers.get("Last-Modified", LAST_MODIFIED))
        for k, v in reply.headers.items():
            if k != "Last-Modified":
                self.send_header(k, v)
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def do_GET(self):
        self._serve(True)

    def do_HEAD(self):
        self._serve(False)


@dataclass
class Result:
    code: int
    out: str
    err: str
    seconds: float

    def json(self) -> dict:
        return json.loads(self.out)

    def kinds(self) -> list[str]:
        return [f["kind"] for f in self.json()["findings"]]

    def detectors(self, kind: str) -> set[str]:
        """the detector of every finding of KIND; the gate promises no order among findings"""
        return {f["detector"] for f in self.json()["findings"] if f["kind"] == kind}

    def finding(self, kind: str) -> dict:
        found = [f for f in self.json()["findings"] if f["kind"] == kind]
        assert found, f"no finding of kind {kind}: {self.out}"
        return found[0]


class World:
    def __init__(self, tmp_path: Path, server: StandIn):
        self.tmp = tmp_path
        self.server = server
        self.root = tmp_path / "repo"
        self.store = tmp_path / "store"
        self.version = "1.1.3"
        self.pinned_program_zip = program_zip(self.version)
        self.pinned_docs = dict(BASE_DOCS)
        self.stand_in_bin = tmp_path / "bin"
        self.libtv_log = tmp_path / "libtv-calls.log"
        self._build_root()
        self._build_libtv_stand_in()
        self.published: dict[str, dict[str, bytes]] = {}
        self.reset_service()

    # ---- the fixture repo ------------------------------------------------------------------------
    def _build_root(self):
        r = self.root
        (r / "ops" / "wsl-setup").mkdir(parents=True)
        url = f"{self.server.base}/cli/{self.version}/libtv-linux-x64.zip"
        (r / "ops" / "wsl-setup" / "setup.sh").write_text(
            f'#!/usr/bin/env bash\nHERE=x\n. "$HERE/checks.sh"\nLIBTV_URL={url}\nSTEPS="a libtv b"\n', encoding="utf-8"
        )
        program = program_inside(self.pinned_program_zip)
        (r / "ops" / "wsl-setup" / "checks.sh").write_text(
            f"LIBTV_ZIP_SHA256=${{LIBTV_ZIP_SHA256:-{sha256(self.pinned_program_zip)}}}\n"
            f"LIBTV_SHA256=${{LIBTV_SHA256:-{sha256(program)}}}\n",
            encoding="utf-8",
        )
        (r / "work").mkdir()
        (r / "work" / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        self.write_vendor(self.pinned_docs)
        issues = r / "work" / ".scratch" / "easel-setup-gaps" / "issues"
        issues.mkdir(parents=True)
        for name in ("01-fonts.md", "37-libtv-update-gate.md", "38-banned-words.md"):
            (issues / name).write_text("Status: closed\n", encoding="utf-8")

    def write_vendor(self, docs: dict[str, bytes | str]):
        vendor = self.root / "skills" / "builtin" / "libtv-cli" / "references" / "vendor"
        if vendor.exists():
            import shutil

            shutil.rmtree(vendor)
        for name, data in docs.items():
            p = vendor / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def pin_hashes(self) -> dict[str, str]:
        """sha256 of every file the gate must never change"""
        out = {}
        for rel in ("ops/wsl-setup/setup.sh", "ops/wsl-setup/checks.sh"):
            out[rel] = sha256((self.root / rel).read_bytes())
        for p in sorted((self.root / "skills").rglob("*")):
            if p.is_file():
                out[p.relative_to(self.root).as_posix()] = sha256(p.read_bytes())
        return out

    # ---- a stand-in `libtv` on PATH that writes down every call ----------------------------------
    def _build_libtv_stand_in(self):
        self.stand_in_bin.mkdir()
        if os.name == "nt":
            (self.stand_in_bin / "libtv.cmd").write_text(f'@echo called %* >> "{self.libtv_log}"\r\n', encoding="utf-8")
        else:
            p = self.stand_in_bin / "libtv"
            p.write_text(f'#!/bin/sh\necho "called $*" >> "{self.libtv_log}"\n', encoding="utf-8")
            p.chmod(0o755)

    # ---- what LibTV answers ----------------------------------------------------------------------
    def reset_service(self):
        self.server.routes.clear()
        self.set_channel(self.version)
        self.set_notice(False, "")
        self.set_canary(CANARY_BASELINE)
        self.server.routes["/cli/latest/manifest.json"] = Reply(200, b'{"version": "1.0.2"}')
        self.publish(self.version, program_zip_bytes=self.pinned_program_zip, skill_docs=self.pinned_docs)
        self.set_settings("182", {"video": [{"modelKey": "m-one", "modelName": "One", "vip": False}]})
        self.set_settings("188", {"slashImage": [{"scene": "s-one", "label": "One"}]})
        self.set_settings("186", {"presets": [{"key": "pan"}]})
        self.set_settings("190", [{"voice_id": "v-one", "name": "One"}])   # as LibTV serves it: a JSON list, not an object

    def set_channel(self, version: str):
        payload = {
            "version": version,
            "install": {"shell": f"{self.server.base}/cli/{version}/install-libtv-cli.sh"},
            "skill": f"{self.server.base}/cli/{version}/libtv-cli-skill.zip",
        }
        self.server.routes["/api/www/landing-activities/getById?id=240"] = Reply(200, channel_envelope(payload))

    def set_notice(self, enable: bool, message: str):
        self.server.routes["/api/www/landing-activities/getById?id=217"] = Reply(
            200, channel_envelope({"message": message, "enable": enable})
        )

    def set_canary(self, body: dict | bytes, status: int = 200):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.server.routes["/api/www/account/list"] = Reply(status, raw)

    def set_settings(self, channel_id: str, payload: object):
        self.server.routes[f"/api/www/landing-activities/getById?id={channel_id}"] = Reply(200, channel_envelope(payload))

    def publish(self, version, program_zip_bytes=None, skill_docs=None, skill_zip_bytes=None, last_modified=None):
        headers = {"Last-Modified": last_modified or LAST_MODIFIED}
        base = f"/cli/{version}"
        if program_zip_bytes is not None:
            self.server.routes[f"{base}/libtv-linux-x64.zip"] = Reply(200, program_zip_bytes, dict(headers))
        if skill_zip_bytes is None and skill_docs is not None:
            skill_zip_bytes = make_zip(skill_docs)
        if skill_zip_bytes is not None:
            self.server.routes[f"{base}/libtv-cli-skill.zip"] = Reply(200, skill_zip_bytes, dict(headers))

    # builders and constants the tests use (conftest cannot be imported under pytest's importlib mode)
    program_zip = staticmethod(program_zip)
    program_inside = staticmethod(program_inside)
    make_zip = staticmethod(make_zip)
    sha256 = staticmethod(sha256)
    BASE_DOCS = BASE_DOCS
    BASE_COMMANDS = BASE_COMMANDS
    RETIREMENT_ANSWER = RETIREMENT_ANSWER
    CANARY_BASELINE = CANARY_BASELINE
    EVIDENCE = EVIDENCE
    REPO = REPO
    GATE = GATE

    def publish_candidate(self, version: str, commands=None, docs=None, program_version=None, channel=True, last_modified=None):
        """a newer version on LibTV's file server (and, by default, named by its version channel)"""
        self.publish(
            version,
            program_zip_bytes=program_zip(program_version or version, commands if commands is not None else BASE_COMMANDS),
            skill_docs=docs if docs is not None else BASE_DOCS,
            last_modified=last_modified,
        )
        if channel:
            self.set_channel(version)

    def route(self, path: str, body: bytes | str = b"", status: int = 200, **kw):
        """answer PATH with BODY; keyword arguments are Reply's (delay, drop, headers, head_length)"""
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.server.routes[path] = Reply(status, data, **kw)

    def closed_base(self) -> str:
        """an address nothing listens on: LibTV is unreachable"""
        import socket

        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return f"http://127.0.0.1:{port}"

    def point_files_at(self, base: str):
        """the pinned download address (setup.sh) now names another server"""
        p = self.root / "ops" / "wsl-setup" / "setup.sh"
        text = p.read_text(encoding="utf-8").replace(self.server.base, base)
        p.write_text(text, encoding="utf-8")

    # ---- running the gate ------------------------------------------------------------------------
    def run(self, *args: str, api_base: str | None = None, env: dict | None = None, timeout: float = 120,
            root: Path | None = None, default_store: bool = False) -> Result:
        full_env = {k: v for k, v in os.environ.items() if not k.startswith("LIBTV")}
        full_env.update(
            {
                "LIBTV_GATE_API_BASE": api_base if api_base is not None else self.server.base,
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.stand_in_bin) + os.pathsep + os.environ.get("PATH", ""),
                "HOME": str(self.tmp / "home"),
                "USERPROFILE": str(self.tmp / "home"),
            }
        )
        full_env.update(env or {})
        started = time.time()
        store_args = [] if default_store else ["--store", str(self.store)]
        proc = subprocess.run(
            [sys.executable, "-I", str(GATE), "--root", str(root or self.root), *store_args, *args],
            capture_output=True,
            timeout=timeout,
            env=full_env,
            cwd=str(self.tmp),
        )
        return Result(
            proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"),
            time.time() - started,
        )

    def requests(self, method: str | None = None) -> list[str]:
        return [p for m, p in self.server.log if method is None or m == method]

    def libtv_calls(self) -> str:
        return self.libtv_log.read_text(encoding="utf-8") if self.libtv_log.exists() else ""

    def state(self) -> dict:
        p = self.store / "state.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@pytest.fixture
def lt(tmp_path):
    server = StandIn()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield World(tmp_path, server)
    finally:
        problems = server.stop(thread)
    if problems:
        pytest.fail("the stand-in LibTV server reported:\n" + "\n".join(problems), pytrace=False)
