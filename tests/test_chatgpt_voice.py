"""Voices through the owner's ChatGPT subscription (issue 24): no API key, no per-call provider.

Seams (the issue's acceptance criteria and its triage notes' traps, written down before any test):
  1. the shared model registry: a provider that needs no key still shows up as configured
  2. `tts.py speak` with VOICE_PROVIDER=chatgpt: a whole script in, one mp3 (+ SRT) out
  3. `voice_clone.py clone --provider chatgpt` (the call the multi-voice engine makes per line)
  4. `multivoice.py` with VOICE_PROVIDER=chatgpt: its closed-source check passes without a key
  5. the browser helper, at its command line only: refuses a port that belongs to another browser

ChatGPT itself is not reachable from a test, so seams 2-4 run against a stand-in helper that obeys the
same command-line protocol as the real one (`ask` / `speak` / `status`, see chatgpt_voice.py). The real
helper is proved by the live run recorded on the issue, not here.
Needs ffmpeg and ffprobe; skipped when they are absent.
"""

from __future__ import annotations

import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from model_registry import configured_providers, provider_ids, provider_required_env  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed"
)

SECONDS_PER_CHAR = 0.25  # the stand-in speaks 4 characters a second, like ChatGPT's Read aloud did


# ── 1. registry ────────────────────────────────────────────────────────
def test_chatgpt_is_a_voice_provider_that_needs_no_key():
    assert "chatgpt" in provider_ids("voice")
    assert provider_required_env("voice")["chatgpt"] == ()


def test_chatgpt_counts_as_configured_only_when_it_is_the_chosen_voice_provider():
    chosen = [p["id"] for p in configured_providers("voice", {"VOICE_PROVIDER": "chatgpt"})]
    assert chosen == ["chatgpt"]
    assert configured_providers("voice", {}) == []
    other = [p["id"] for p in configured_providers("voice", {"VOICE_PROVIDER": "minimax"})]
    assert "chatgpt" not in other


def test_the_web_settings_page_does_not_call_the_voice_skill_configured_just_because_a_keyless_provider_exists():
    """A provider with nothing to fill in must not turn the missing-key warning off for everyone."""
    sys.path.insert(0, str(ROOT / "web"))
    import app as web  # noqa: E402  (heavy import, only needed here)
    assert web._skill_api_configured("voice-clone", {}) is False
    assert web._skill_api_configured("voice-clone", {"VOICE_PROVIDER": "chatgpt"}) is True
    assert web._skill_api_configured("voice-clone", {"MINIMAX_API_KEY": "k", "MINIMAX_GROUP_ID": "g"}) is True


# ── the stand-in for the browser helper ────────────────────────────────
# Same command line as chatgpt_voice.mjs:
#   ask                       script text on stdin -> one JSON line {conversation_id, message_id, reply}
#   speak --message-id M --conversation-id C --voice V   -> mp3 bytes on stdout
#   status                    -> exit 0 when signed in
# FAKE_MODE: ok | reword (the reply is not the script) | not-signed-in | wrong-browser
#            | empty-audio | short-audio (audio far too short for the text)
# FAKE_PLAN: designed audio for `speak`, a JSON object {message id: [[tone|gap, seconds], ...]} (issue 47)
FAKE_HELPER = r'''
import json, os, subprocess, sys
from pathlib import Path

log = Path(os.environ["FAKE_LOG"])
state = Path(os.environ["FAKE_LOG"] + ".texts")
mode = os.environ.get("FAKE_MODE", "ok")
spc = float(os.environ.get("FAKE_SECONDS_PER_CHAR", "0.25"))


def note(**kw):
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(kw, ensure_ascii=False) + "\n")


def arg(name):
    return sys.argv[sys.argv.index(name) + 1]


cmd = sys.argv[1]
if mode == "not-signed-in" and cmd in ("ask", "status"):
    note(cmd=cmd)
    sys.stderr.write("chatgpt_voice: the ChatGPT profile is not signed in\n")
    sys.exit(5)
if mode == "wrong-browser" and cmd in ("ask", "status"):
    note(cmd=cmd)
    sys.stderr.write("chatgpt_voice: the port belongs to a different browser\n")
    sys.exit(4)
if cmd == "status":
    note(cmd="status")
    print(json.dumps({"signed_in": True}))
elif cmd == "ask":
    text = sys.stdin.buffer.read().decode("utf-8")
    texts = json.loads(state.read_text("utf-8")) if state.exists() else {}
    mid = f"m{len(texts) + 1}"
    texts[mid] = text
    state.write_text(json.dumps(texts, ensure_ascii=False), "utf-8")
    note(cmd="ask", text=text)
    reply = ("好的，" + text) if mode == "reword" else text
    print(json.dumps({"conversation_id": "c1", "message_id": mid, "reply": reply}, ensure_ascii=False))
elif cmd == "speak":
    texts = json.loads(state.read_text("utf-8"))
    text = texts[arg("--message-id")]
    voice = arg("--voice")
    note(cmd="speak", voice=voice, message_id=arg("--message-id"))
    if os.environ.get("FAKE_PLAN"):
        # designed audio (issue 47): FAKE_PLAN = {"m1": [["tone", seconds], ["gap", seconds], ...], "m2": ...}
        import io, math, struct, wave
        tone = b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * i / 40))) for i in range(40))  # 400 Hz at 16 kHz
        pcm = b""
        for kind, secs in json.loads(os.environ["FAKE_PLAN"])[arg("--message-id")]:
            n = round(secs * 16000)
            pcm += (tone * (n // 40 + 1))[: 2 * n] if kind == "tone" else b"\0\0" * n
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm)
        sys.stdout.buffer.write(buf.getvalue())
        sys.exit(0)
    chars = len("".join(text.split()))
    seconds = chars * (0.01 if mode == "short-audio" else spc)
    if mode == "empty-audio":
        sys.exit(0)
    hz = 440 if voice == "cove" else 660
    audio = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds:.3f}",
         "-ar", "24000", "-ac", "1", "-f", "mp3", "-"],
        check=True, capture_output=True).stdout
    sys.stdout.buffer.write(audio)
else:
    sys.exit(2)
'''


@pytest.fixture
def fake(tmp_path):
    """The stand-in helper, its call log, and the environment that points the scripts at it."""
    helper = tmp_path / "fake_helper.py"
    helper.write_text(FAKE_HELPER, encoding="utf-8")
    log = tmp_path / "calls.jsonl"

    class Fake:
        def __init__(self):
            self.log = log

        def env(self, **extra):
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("VOICE_", "CHATGPT_", "FAKE_", "http_proxy", "https_proxy"))}
            env.update(PYTHONIOENCODING="utf-8", VOICE_PROVIDER="chatgpt", FAKE_LOG=str(log),
                       CHATGPT_VOICE_HELPER=f"{shlex.quote(sys.executable)} {shlex.quote(str(helper))}")
            env.update(extra)
            return env

        def calls(self, cmd=None):
            if not log.exists():
                return []
            rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
            return [r for r in rows if cmd is None or r["cmd"] == cmd]

    return Fake()


def run(script: str, args: list[str], cwd: Path, env: dict):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=cwd, env=env,
                          text=True, encoding="utf-8", capture_output=True, check=False)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=noprint_wrappers=1:nokey=1", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# ── 2. tts.py speak: a whole script in, one mp3 out ────────────────────
@needs_ffmpeg
def test_speak_makes_an_mp3_from_a_short_script_with_no_key(tmp_path, fake):
    out = tmp_path / "vo.mp3"
    script = "大家好，今天给大家介绍一款燕麦蛋白饮品。"
    r = run("tts.py", ["speak", "--text", script, "-o", str(out)], tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    assert out.is_file() and out.stat().st_size > 0
    spoken = len("".join(script.split())) * SECONDS_PER_CHAR
    assert abs(duration(out) - spoken) <= 0.5
    assert [c["cmd"] for c in fake.calls()] == ["ask", "speak"]
    assert fake.calls("ask")[0]["text"] == script


def _twenty_sentences() -> str:
    return "".join(f"第{n:02d}句是配音测试用的话。" for n in range(1, 21))


@needs_ffmpeg
def test_a_twenty_sentence_script_costs_a_few_requests_not_twenty_and_still_gets_a_cue_per_sentence(tmp_path, fake):
    out, srt = tmp_path / "vo.mp3", tmp_path / "vo.srt"
    script = _twenty_sentences()
    r = run("tts.py", ["speak", "--text", script, "-o", str(out), "--subtitle", str(srt)], tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    asks = fake.calls("ask")
    assert 1 < len(asks) <= math.ceil(len("".join(script.split())) / 160) + 1  # a handful of requests
    assert len(asks) < 20
    assert all(len(a["text"]) <= 160 for a in asks)  # each request stays short
    assert "".join(a["text"] for a in asks) == script  # nothing dropped, nothing reordered
    cues = re.findall(r"(\d+)\n(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})\n(.+)\n", srt.read_text("utf-8"))
    assert [c[3] for c in cues] == [f"第{n:02d}句是配音测试用的话。" for n in range(1, 21)]

    def secs(ts: str) -> float:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    starts = [secs(c[1]) for c in cues]
    assert starts == sorted(starts) and starts[0] == 0
    assert abs(secs(cues[-1][2]) - duration(out)) <= 0.5


@needs_ffmpeg
def test_speak_to_wav_and_the_chosen_voice_reaches_the_helper(tmp_path, fake):
    out = tmp_path / "vo.wav"
    r = run("tts.py", ["speak", "--text", "你好，这是测试。", "-o", str(out), "--voice", "juniper"], tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    assert out.read_bytes()[:4] == b"RIFF"
    assert [c["voice"] for c in fake.calls("speak")] == ["juniper"]


@needs_ffmpeg
def test_default_voice_is_cove(tmp_path, fake):
    out = tmp_path / "vo.mp3"
    assert run("tts.py", ["speak", "--text", "你好，这是测试。", "-o", str(out)], tmp_path, fake.env()).returncode == 0
    assert [c["voice"] for c in fake.calls("speak")] == ["cove"]


# ── a reply that is not the script, audio that is the wrong length, a profile that is not signed in ──
@needs_ffmpeg
def test_a_reply_that_is_not_the_script_saves_nothing_and_never_asks_for_audio(tmp_path, fake):
    out = tmp_path / "vo.mp3"
    r = run("tts.py", ["speak", "--text", "你好，这是测试。", "-o", str(out), "--engine", "closed"],
            tmp_path, fake.env(FAKE_MODE="reword"))
    assert r.returncode != 0
    assert "逐字" in r.stderr
    assert not out.exists()
    assert fake.calls("speak") == []


@needs_ffmpeg
@pytest.mark.parametrize("mode", ["short-audio", "empty-audio"])
def test_audio_that_does_not_fit_the_text_saves_nothing(tmp_path, fake, mode):
    out = tmp_path / "vo.mp3"
    r = run("tts.py", ["speak", "--text", "大家好，今天给大家介绍一款燕麦蛋白饮品，口感清爽。", "-o", str(out),
                       "--engine", "closed"], tmp_path, fake.env(FAKE_MODE=mode))
    assert r.returncode != 0
    assert not out.exists()


@needs_ffmpeg
def test_one_bad_chunk_in_a_long_script_saves_no_partial_audio(tmp_path, fake):
    out = tmp_path / "vo.mp3"
    r = run("tts.py", ["speak", "--text", _twenty_sentences(), "-o", str(out), "--engine", "closed"],
            tmp_path, fake.env(FAKE_MODE="short-audio"))
    assert r.returncode != 0 and not out.exists()


@needs_ffmpeg
@pytest.mark.parametrize("mode,words", [("not-signed-in", "登录"), ("wrong-browser", "别的浏览器")])
def test_an_unusable_browser_stops_with_a_plain_reason_instead_of_a_fake_voice(tmp_path, fake, mode, words):
    out = tmp_path / "vo.mp3"
    r = run("tts.py", ["speak", "--text", "你好。", "-o", str(out), "--engine", "closed"], tmp_path, fake.env(FAKE_MODE=mode))
    assert r.returncode != 0
    assert words in r.stderr
    assert not out.exists()


# ── 3. voice_clone.py clone, the call multivoice makes for every line ──
@needs_ffmpeg
def test_voice_clone_clone_speaks_a_line_with_the_named_read_aloud_voice(tmp_path, fake):
    out = tmp_path / "line.mp3"
    r = run("voice_clone.py", ["clone", "--provider", "chatgpt", "--voice-id", "juniper", "--text", "你输了。", "-o", str(out)],
            tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    assert out.stat().st_size > 0
    assert [c["voice"] for c in fake.calls("speak")] == ["juniper"]


def test_voice_clone_enroll_says_this_route_cannot_clone(tmp_path, fake):
    r = run("voice_clone.py", ["enroll", "--provider", "chatgpt", "--sample", "x.mp3"], tmp_path, fake.env())
    assert r.returncode != 0
    assert "克隆" in r.stderr


def test_voice_clone_selftest_still_passes_with_a_provider_that_has_no_key(tmp_path, fake):
    r = run("voice_clone.py", ["selftest"], tmp_path, fake.env())
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]


def test_voice_clone_check_asks_the_browser_instead_of_looking_for_a_key(tmp_path, fake):
    ok = run("voice_clone.py", ["check", "--provider", "chatgpt"], tmp_path, fake.env())
    assert ok.returncode == 0, ok.stderr
    assert [c["cmd"] for c in fake.calls()] == ["status"]
    out = run("voice_clone.py", ["check", "--provider", "chatgpt"], tmp_path, fake.env(FAKE_MODE="not-signed-in"))
    assert out.returncode == 3 and "登录" in out.stderr


# ── 5. the real browser helper, at its command line: it must only ever touch the dedicated browser ──
NODE_WIN = Path("/mnt/c/Program Files/nodejs/node.exe")
needs_windows_node = pytest.mark.skipif(not NODE_WIN.is_file(), reason="needs Windows Node (WSL interop)")


def real_helper_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("VOICE_", "CHATGPT_", "FAKE_"))}
    env.update(PYTHONIOENCODING="utf-8", **extra)
    return env


@needs_windows_node
def test_no_browser_on_the_port_stops_with_the_not_running_reason(tmp_path):
    r = run("chatgpt_voice.py", ["check"], tmp_path, real_helper_env(CHATGPT_CDP_PORT="9331"))
    assert r.returncode != 0
    assert "no browser is listening on port 9331" in r.stderr


@needs_windows_node
def test_a_port_held_by_some_other_program_is_refused_and_nothing_is_sent_to_it(tmp_path):
    """Obstacle from the issue: a port number does not say which browser answers on it."""
    served = ("var n=0;require('http').createServer(function(q,s){process.stdout.write(q.url+'\\n');"
              "s.setHeader('content-type','application/json');"
              "s.end(JSON.stringify({webSocketDebuggerUrl:'ws://127.0.0.1:9332/devtools/browser/x'}))})"
              ".listen(9332,'127.0.0.1');setTimeout(function(){process.exit(0)},60000)")
    server = subprocess.Popen([str(NODE_WIN), "-e", served], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # WSL cannot see Windows loopback, so ask Windows whether the stand-in is answering yet
        ping = "fetch('http://127.0.0.1:9332/json/version').then(function(){process.exit(0)},function(){process.exit(1)})"
        for _ in range(30):
            if subprocess.run([str(NODE_WIN), "-e", ping], capture_output=True).returncode == 0:
                break
        r = run("chatgpt_voice.py", ["check"], tmp_path, real_helper_env(CHATGPT_CDP_PORT="9332"))
    finally:
        server.terminate()  # the stand-in also exits by itself after a minute
    assert r.returncode != 0
    # had the helper trusted the port it would have tried the debugging socket, which this stand-in
    # does not serve, and said "websocket failed" instead
    assert "different browser" in r.stderr


# ── 4. multivoice: the closed-source check must pass for a provider that has no key ──
def mv(args: list[str], cwd: Path, env: dict):
    return run("multivoice.py", args, cwd, env)


def test_cast_init_gives_the_narrator_a_read_aloud_voice_not_edge(tmp_path, fake):
    cast = tmp_path / "cast.json"
    assert mv(["cast", "init", "--cast", str(cast)], tmp_path, fake.env()).returncode == 0
    narrator = json.loads(cast.read_text("utf-8"))["cast"][0]
    assert (narrator["engine"], narrator["provider"], narrator["voice_id"]) == ("clone", "chatgpt", "cove")


def test_a_cast_of_read_aloud_voices_passes_the_check_but_edge_voices_are_still_refused(tmp_path, fake):
    cast = tmp_path / "cast.json"
    assert mv(["cast", "init", "--cast", str(cast)], tmp_path, fake.env()).returncode == 0
    assert mv(["cast", "add", "--cast", str(cast), "--name", "林策", "--role", "male_lead",
               "--voice-id", "juniper", "--archetype", "冷峻男主"], tmp_path, fake.env()).returncode == 0
    ok = mv(["cast", "check", "--cast", str(cast)], tmp_path, fake.env())
    assert ok.returncode == 0, ok.stdout
    mv(["cast", "add", "--cast", str(cast), "--name", "苏晚", "--engine", "edge", "--voice", "zh-CN-XiaoxiaoNeural"],
       tmp_path, fake.env())
    bad = mv(["cast", "check", "--cast", str(cast)], tmp_path, fake.env())
    assert bad.returncode != 0 and "苏晚" in bad.stdout


@needs_ffmpeg
def test_dub_speaks_each_line_in_its_own_read_aloud_voice_with_no_key(tmp_path, fake):
    cast, lines = tmp_path / "cast.json", tmp_path / "lines.json"
    mv(["cast", "init", "--cast", str(cast)], tmp_path, fake.env())
    mv(["cast", "add", "--cast", str(cast), "--name", "林策", "--role", "male_lead", "--voice-id", "juniper",
        "--archetype", "冷峻男主"], tmp_path, fake.env())
    lines.write_text(json.dumps({"lines": [
        {"speaker": "旁白", "text": "三年后，雨夜。"}, {"speaker": "林策", "text": "你输了。"}]}, ensure_ascii=False),
        encoding="utf-8")
    out = tmp_path / "voice.mp3"
    r = mv(["dub", "--cast", str(cast), "--lines", str(lines), "-o", str(out)], tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    assert [c["voice"] for c in fake.calls("speak")] == ["cove", "juniper"]
    spoken = (len("三年后，雨夜。") + len("你输了。")) * SECONDS_PER_CHAR
    assert abs(duration(out) - (spoken + 0.35)) <= 0.8  # plus the pause multivoice puts between lines
    assert out.with_suffix(".srt").is_file()


# ── 6. every voice ChatGPT's own settings page lists, picked by the name shown there (issue 41) ──
# Name -> id pairs as ChatGPT's web app serves them (GET /backend-api/settings/voices, read from the live
# service on 2026-10-15; evidence in .scratch/easel-setup-gaps/evidence/41-chatgpt-voice-names/). Read aloud
# accepts the id, not the name: Sol is `glimmer`, Spruce is `orbit`, Arbor is `fathom`.
NINE_VOICES = {"Sol": "glimmer", "Cove": "cove", "Vale": "vale", "Spruce": "orbit", "Arbor": "fathom",
               "Juniper": "juniper", "Breeze": "breeze", "Ember": "ember", "Maple": "maple"}
LINE = "你好，这是测试。"


@needs_ffmpeg
@pytest.mark.parametrize("name,voice_id", list(NINE_VOICES.items()))
def test_voice_over_picks_each_of_the_nine_voices_by_its_settings_name(tmp_path, fake, name, voice_id):
    out = tmp_path / "vo.mp3"
    r = run("tts.py", ["speak", "--text", LINE, "-o", str(out), "--voice", name, "--engine", "closed"],
            tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    assert [c["voice"] for c in fake.calls("speak")] == [voice_id]


@needs_ffmpeg
@pytest.mark.parametrize("typed,voice_id", [("maple", "maple"), ("MAPLE", "maple"), ("sol", "glimmer"),
                                             ("glimmer", "glimmer"), ("Glimmer", "glimmer")])
def test_voice_over_takes_the_name_in_any_case_or_the_id_itself(tmp_path, fake, typed, voice_id):
    out = tmp_path / "vo.mp3"
    r = run("tts.py", ["speak", "--text", LINE, "-o", str(out), "--voice", typed], tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    assert [c["voice"] for c in fake.calls("speak")] == [voice_id]


@needs_ffmpeg
def test_the_default_narrator_setting_can_be_a_settings_name_too(tmp_path, fake):
    out = tmp_path / "vo.mp3"
    r = run("tts.py", ["speak", "--text", LINE, "-o", str(out)], tmp_path, fake.env(VOICE_NARRATOR_VOICE_ID="Vale"))
    assert r.returncode == 0, r.stderr[-800:]
    assert [c["voice"] for c in fake.calls("speak")] == ["vale"]


@needs_ffmpeg
@pytest.mark.parametrize("engine", [[], ["--engine", "closed"]], ids=["auto", "closed"])
@pytest.mark.parametrize("bad", ["marin", "zh-CN-XiaoxiaoNeural"])
def test_an_unknown_voice_stops_before_the_browser_and_names_the_nine(tmp_path, fake, bad, engine):
    """Used to be swapped for Cove with a success line; marin and edge voice names are not ChatGPT voices."""
    out = tmp_path / "vo.mp3"
    r = run("tts.py", ["speak", "--text", LINE, "-o", str(out), "--voice", bad, *engine], tmp_path, fake.env())
    assert r.returncode != 0
    assert fake.calls() == []  # not even a status check: nothing reached the browser helper
    assert not out.exists()
    assert bad in r.stderr
    assert all(name in r.stderr for name in NINE_VOICES)


@needs_ffmpeg
@pytest.mark.parametrize("name,voice_id", [("Sol", "glimmer"), ("Spruce", "orbit"), ("Arbor", "fathom"),
                                            ("Maple", "maple")])
def test_voice_clone_clone_takes_a_settings_name_and_sends_the_id(tmp_path, fake, name, voice_id):
    out = tmp_path / "line.mp3"
    r = run("voice_clone.py", ["clone", "--provider", "chatgpt", "--voice-id", name, "--text", LINE, "-o", str(out)],
            tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    assert [c["voice"] for c in fake.calls("speak")] == [voice_id]


def test_voice_clone_clone_refuses_an_unknown_voice_before_the_browser(tmp_path, fake):
    out = tmp_path / "line.mp3"
    r = run("voice_clone.py", ["clone", "--provider", "chatgpt", "--voice-id", "marin", "--text", LINE, "-o", str(out)],
            tmp_path, fake.env())
    assert r.returncode != 0
    assert fake.calls() == []
    assert "marin" in r.stderr and all(name in r.stderr for name in NINE_VOICES)


def test_voice_clone_enroll_no_longer_says_only_two_voices_exist(tmp_path, fake):
    r = run("voice_clone.py", ["enroll", "--provider", "chatgpt", "--sample", "x.mp3"], tmp_path, fake.env())
    assert r.returncode != 0 and "克隆" in r.stderr
    assert "cove、juniper" not in r.stderr  # the refusal now points at all nine
    assert all(name in r.stderr for name in NINE_VOICES)


def _cast(tmp_path, fake, members: dict[str, str]) -> Path:
    cast = tmp_path / "cast.json"
    assert mv(["cast", "init", "--cast", str(cast)], tmp_path, fake.env()).returncode == 0
    for who, voice in members.items():
        assert mv(["cast", "add", "--cast", str(cast), "--name", who, "--role", "male_lead", "--voice-id", voice,
                   "--archetype", "测试角色"], tmp_path, fake.env()).returncode == 0
    return cast


def test_cast_check_accepts_settings_names_and_refuses_an_unknown_voice(tmp_path, fake):
    good = _cast(tmp_path, fake, {"甲": "Sol", "乙": "Spruce", "丙": "Arbor"})
    assert mv(["cast", "check", "--cast", str(good)], tmp_path, fake.env()).returncode == 0
    bad = mv(["cast", "add", "--cast", str(good), "--name", "丁", "--role", "male_lead", "--voice-id", "marin",
              "--archetype", "测试角色"], tmp_path, fake.env())
    assert bad.returncode == 0
    checked = mv(["cast", "check", "--cast", str(good)], tmp_path, fake.env())
    assert checked.returncode != 0
    assert "丁" in checked.stdout and "marin" in checked.stdout
    assert fake.calls() == []  # checking a cast never touches the browser


def test_the_voice_over_skill_text_checks_run_here_because_ci_does_not_collect_dot_test_dot_py_files():
    """skills/builtin/tts-voiceover/chatgpt-route.test.py holds the checks on the skill text (the nine names, the two
    wrong claims gone); its name keeps pytest's default collection away, so run its tests from here."""
    import importlib.util
    path = ROOT / "skills" / "builtin" / "tts-voiceover" / "chatgpt-route.test.py"
    spec = importlib.util.spec_from_file_location("chatgpt_route_skill_text", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = [getattr(module, n) for n in dir(module) if n.startswith("test_")]
    assert len(checks) >= 6  # the file really has its checks, so an empty pass cannot happen
    for check in checks:
        check()


@needs_ffmpeg
def test_dub_sends_the_ids_for_settings_names(tmp_path, fake):
    cast = _cast(tmp_path, fake, {"甲": "Sol", "乙": "Spruce", "丙": "Arbor"})
    lines = tmp_path / "lines.json"
    lines.write_text(json.dumps({"lines": [{"speaker": s, "text": "你好。"} for s in ("甲", "乙", "丙")]},
                                ensure_ascii=False), encoding="utf-8")
    r = mv(["dub", "--cast", str(cast), "--lines", str(lines), "-o", str(tmp_path / "voice.mp3")], tmp_path, fake.env())
    assert r.returncode == 0, r.stderr[-800:]
    assert [c["voice"] for c in fake.calls("speak")] == ["glimmer", "orbit", "fathom"]


# ── 7. subtitle times follow the pauses in the audio itself (issue 47) ──
# Seam: `tts.py speak --subtitle` on the ChatGPT route (it writes the cues `synthesize` returns). The stand-in
# helper returns designed audio: speech as tone bursts, pauses as digital silence, so each test knows
# where every line really starts. Expected times below are the plans' own arithmetic (a plan's first
# tone, plus the gaps and tones before a line), written out as literals, not computed from the script.
ONSET_TOLERANCE = 0.15


def _tone(seconds: float):
    return ["tone", seconds]


def _gap(seconds: float):
    return ["gap", seconds]


def _seconds(stamp: str) -> float:
    h, m, rest = stamp.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _cues(srt: Path) -> list[tuple[str, float, float]]:
    found = re.findall(r"\d+\n(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})\n(.+)\n", srt.read_text("utf-8"))
    return [(text, _seconds(a), _seconds(b)) for a, b, text in found]


def _speak_with_plan(tmp_path, fake, script: str, plan: dict):
    out, srt = tmp_path / "vo.mp3", tmp_path / "vo.srt"
    r = run("tts.py", ["speak", "--text", script, "-o", str(out), "--subtitle", str(srt), "--engine", "closed"],
            tmp_path, fake.env(FAKE_PLAN=json.dumps(plan)))
    return r, out, srt


def _assert_each_line_starts_at(cues, onsets: list[float], out: Path):
    assert [round(c[1], 2) for c in cues][0] == 0  # the first line starts at 0
    for number, (cue, onset) in enumerate(zip(cues, onsets), 1):
        assert abs(cue[1] - onset) <= ONSET_TOLERANCE, f"line {number} starts at {cue[1]:.2f}s, speech starts at {onset}s"
    for before, after in zip(cues, cues[1:]):
        assert abs(before[2] - after[1]) <= 0.002  # each line ends where the next one starts
    assert abs(cues[-1][2] - duration(out)) <= ONSET_TOLERANCE  # the last line ends with the audio


@needs_ffmpeg
def test_lines_of_equal_length_but_different_spoken_length_start_when_their_speech_starts(tmp_path, fake):
    script = "第一句话在这里。第二句话在这里。第三句话在这里。"  # three lines of 8 characters each
    plan = {"m1": [_tone(1.0), _gap(0.5), _tone(3.0), _gap(0.5), _tone(2.0)]}  # speech starts at 0, 1.5, 5.0
    r, out, srt = _speak_with_plan(tmp_path, fake, script, plan)
    assert r.returncode == 0, r.stderr[-800:]
    cues = _cues(srt)
    assert [c[0] for c in cues] == ["第一句话在这里。", "第二句话在这里。", "第三句话在这里。"]
    _assert_each_line_starts_at(cues, [0.0, 1.5, 5.0], out)


@needs_ffmpeg
def test_a_pause_inside_a_line_that_is_longer_than_the_pauses_between_lines_is_not_taken_for_a_boundary(tmp_path, fake):
    script = "大家好呀。今天来聊聊，一款新饮品。快来试试。"  # 5, 12 and 5 characters; the comma is inside line 2
    plan = {"m1": [_tone(1.5), _gap(0.4), _tone(1.6), _gap(0.9), _tone(1.4), _gap(0.4), _tone(1.2)]}
    # line 2 starts at 1.9 and line 3 at 6.2; the 0.9 s pause at 3.5-4.4 is the longest one and is not a boundary
    r, out, srt = _speak_with_plan(tmp_path, fake, script, plan)
    assert r.returncode == 0, r.stderr[-800:]
    cues = _cues(srt)
    assert len(cues) == 3
    _assert_each_line_starts_at(cues, [0.0, 1.9, 6.2], out)


@needs_ffmpeg
def test_a_script_of_two_requests_times_its_first_line_of_the_second_by_speech_not_by_where_the_file_begins(tmp_path, fake):
    lines = ["甲" * 69 + "。", "乙" * 69 + "。", "丙" * 69 + "。"]  # 70 characters each: lines 1-2 fill one request, line 3 the next
    plan = {"m1": [_tone(10.0), _gap(0.5), _tone(10.5), _gap(0.8)],   # the first take ends with 0.8 s of silence
            "m2": [_gap(0.5), _tone(10.0), _gap(0.9)]}                 # the second begins with 0.5 s of silence
    # line 2 starts at 10.5; the first take is 21.8 s long, so line 3 starts at 21.8 + 0.5 = 22.3
    r, out, srt = _speak_with_plan(tmp_path, fake, "".join(lines), plan)
    assert r.returncode == 0, r.stderr[-800:]
    assert [c["cmd"] for c in fake.calls()] == ["ask", "speak", "ask", "speak"]
    cues = _cues(srt)
    assert [c[0] for c in cues] == lines
    _assert_each_line_starts_at(cues, [0.0, 10.5, 22.3], out)


@needs_ffmpeg
def test_a_boundary_with_no_pause_near_it_keeps_the_estimate_warns_about_that_line_and_still_succeeds(tmp_path, fake):
    script = "第一句话在这里。第二句话在这里。第三句话在这里。"
    plan = {"m1": [_tone(1.0), _gap(0.5), _tone(5.0)]}  # lines 2 and 3 are spoken straight through: no pause between them
    r, out, srt = _speak_with_plan(tmp_path, fake, script, plan)
    assert r.returncode == 0, r.stderr[-800:]
    cues = _cues(srt)
    assert abs(cues[1][1] - 1.5) <= ONSET_TOLERANCE  # the boundary that has a pause is still placed by it
    assert abs(cues[2][1] - 4.33) <= 0.05  # no pause: the share of the 6.5 s that 16 of 24 characters take
    assert abs(duration(out) - 6.5) <= ONSET_TOLERANCE  # the audio is untouched
    warned = [line for line in r.stderr.splitlines() if "第三句话在这里" in line]
    assert len(warned) == 1  # one warning line, and it names the line
    assert not [line for line in r.stderr.splitlines() if "第二句话在这里" in line]
