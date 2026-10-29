#!/usr/bin/env python3
"""chatgpt_voice.py — 配音走负责人的 ChatGPT 订阅（网页「朗读」），没有 API key，不按次计费。

路线（2026-10-12 实测，证据见 .scratch/easel-setup-gaps/evidence/24-codex-realtime-voice-probe/）：
  1. 专用 Chrome（独立资料夹 ~/.easel-browser/chatgpt，调试端口 9230，登录由负责人做一次）里的 ChatGPT
     新开一个普通对话，发送「请逐字重复这段文字」；
  2. 取回回复文字，必须与发送的文字**逐字相同**（去掉首尾空白），否则整条作废、什么都不保存；
  3. 对这条回复调用 ChatGPT 自带的「朗读」，得到音频，存成 mp3。
ChatGPT 只能朗读它自己的回复，所以第 1 步无法省；发送一步要过人机验证，只能由真浏览器完成。

浏览器那一半是 Windows 上的 Node 脚本 chatgpt_voice.mjs（WSL 经互操作调用，与 xhs-cdp-cookies.mjs
同一做法），登录状态只留在专用资料夹里，不复制、不落盘。本文件是它的 Python 一侧：切句、分块、
核对回复、核对音频长度、拼接、出字幕。

助手程序的命令行（测试里的替身也遵守同一协议；环境变量 CHATGPT_VOICE_HELPER 可整体替换它）：
    ask                     stdin 给文案 → stdout 一行 JSON {conversation_id, message_id, reply}
    speak --message-id M --conversation-id C --voice V   → stdout 是 mp3 字节
    status                  已登录则退出码 0
退出码：4 专用浏览器没开 / 端口属于别的浏览器；5 专用浏览器里没登录 ChatGPT；其它为一般失败。

限制：没有声音克隆；只能用「朗读」自带的声线，即 ChatGPT 设置页列出的九个（见 VOICES），可按设置页上
的名字（任意大小写）或朗读用的 id 选；名字不在这九个里就在碰浏览器之前报错，不会悄悄换成别的声线；
没有情绪参数；每个请求是一次完整的浏览器往返，所以按块（见 MAX_CHUNK_CHARS）合并多句，不逐句调用。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_VOICE = "cove"
# ChatGPT 设置页上的名字 → 「朗读」接受的 id。名字和 id 不总是一样（Sol=glimmer、Spruce=orbit、Arbor=fathom），
# 用设置页的名字去问会得到 404「声音不存在」。来源：ChatGPT 网页自己读的 GET /backend-api/settings/voices，
# 2026-10-15 在负责人的账号上读到（九个 id 都实测出声，证据见 .scratch/easel-setup-gaps/evidence/41-chatgpt-voice-names/）。
VOICES = {"Sol": "glimmer", "Cove": "cove", "Vale": "vale", "Spruce": "orbit", "Arbor": "fathom",
          "Juniper": "juniper", "Breeze": "breeze", "Ember": "ember", "Maple": "maple"}

# 每个请求最多多少字。长回复是否会被截断没有定论，所以保持短，并在下面核对音频长度。
MAX_CHUNK_CHARS = 160
# 音频长度合理性：一般中文朗读约 3.5–5 字/秒。快于 MAX_CHARS_PER_SEC 说明被截断，
# 比每字 MAX_SECONDS_PER_CHAR 秒（再加 3 秒余量）还长说明混进了别的内容。
MAX_CHARS_PER_SEC = 8.0
MAX_SECONDS_PER_CHAR = 1.5

# 字幕时间轴：在拼好的音频里找停顿（静音检测），句界落在停顿结尾。估算的句界离最近的停顿超过
# PAUSE_WINDOW 秒就不认它。实测视频 01：估算偏差最大约 0.8 秒，最近的错误停顿至少隔 1.2 秒。
PAUSE_NOISE_DB = -35
PAUSE_MIN_SECONDS = 0.15
PAUSE_WINDOW = 1.0

ASK_TIMEOUT = 240
SPEAK_TIMEOUT = 180

NODE_WIN = "/mnt/c/Program Files/nodejs/node.exe"
HERE = Path(__file__).resolve().parent

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\n])")
_CLAUSE_END = re.compile(r"(?<=[，,、：:])")


class ChatGPTVoiceError(Exception):
    """配音失败；消息写明原因，调用方决定是否回退。"""


def resolve_voice(name: str | None) -> str:
    """设置页名字（任意大小写）或朗读 id → 朗读用的 id；没给就是默认 cove；不认识就报错、不替换。"""
    wanted = (name or "").strip()
    if not wanted:
        return DEFAULT_VOICE
    for shown, voice_id in VOICES.items():
        if wanted.lower() in (shown.lower(), voice_id):
            return voice_id
    raise ChatGPTVoiceError(f"ChatGPT 朗读没有「{wanted}」这个声线。可用的（ChatGPT 设置页上的名字）：{'、'.join(VOICES)}。")


# ── 切句、分块（纯函数）─────────────────────────────────────────────────
def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s and s.strip()]


def _pieces_within(sentence: str, limit: int) -> list[str]:
    """一句话本身超过 limit 时，先按逗号切，再硬切。"""
    if len(sentence) <= limit:
        return [sentence]
    out: list[str] = []
    current = ""
    for clause in (c for c in _CLAUSE_END.split(sentence) if c):
        while len(clause) > limit:
            if current:
                out.append(current)
                current = ""
            out.append(clause[:limit])
            clause = clause[limit:]
        if len(current) + len(clause) > limit:
            out.append(current)
            current = ""
        current += clause
    if current:
        out.append(current)
    return out


def _join(a: str, b: str) -> str:
    """中文句子直接相接；两边都是英文字母/数字时补一个空格。"""
    return a + b if (not a or not b or not (a[-1].isascii() and b[0].isascii())) else f"{a} {b}"


def chunk_script(text: str, limit: int = MAX_CHUNK_CHARS) -> list[list[str]]:
    """整篇文案 → 若干块，每块是相邻的若干句，合起来不超过 limit 字。"""
    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for sentence in (p for s in split_sentences(text) for p in _pieces_within(s, limit)):
        if current and size + len(sentence) > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(sentence)
        size += len(sentence)
    if current:
        chunks.append(current)
    return chunks


def chunk_text(sentences: list[str]) -> str:
    out = ""
    for s in sentences:
        out = _join(out, s)
    return out


def spoken_chars(text: str) -> int:
    return len("".join(text.split()))


def check_audio_length(chars: int, seconds: float) -> None:
    """音频时长与文字量对不上就报错：空的、被截断的、混进别的内容的都不要。"""
    if seconds <= 0.1:
        raise ChatGPTVoiceError("ChatGPT 朗读返回了空音频（这个声线可能不能用）。")
    if chars / seconds > MAX_CHARS_PER_SEC:
        raise ChatGPTVoiceError(
            f"音频只有 {seconds:.1f} 秒，却要读 {chars} 个字——朗读被截断了，这条作废。")
    if seconds > chars * MAX_SECONDS_PER_CHAR + 3:
        raise ChatGPTVoiceError(
            f"音频有 {seconds:.1f} 秒，对 {chars} 个字来说太长——混进了别的内容，这条作废。")


# ── 助手程序（浏览器那一半）──────────────────────────────────────────────
def helper_command() -> list[str]:
    override = os.environ.get("CHATGPT_VOICE_HELPER", "").strip()
    if override:
        return shlex.split(override)
    node = os.environ.get("CHATGPT_NODE", "").strip() or (NODE_WIN if Path(NODE_WIN).is_file() else "") \
        or shutil.which("node") or ""
    if not node:
        raise ChatGPTVoiceError("找不到 node（需要 Windows 上的 Node，路径 " + NODE_WIN + "）。")
    script = str(HERE / "chatgpt_voice.mjs")
    if node.lower().endswith(".exe") and shutil.which("wslpath"):
        script = subprocess.run(["wslpath", "-w", script], capture_output=True, text=True,
                                check=True).stdout.strip()
    return [node, script]


def _settings_flags() -> list[str]:
    """Environment variables do not cross into a Windows program started from WSL, so settings go as flags."""
    flags: list[str] = []
    for env_name, flag in (("CHATGPT_CDP_PORT", "--port"), ("CHATGPT_PROFILE_DIR", "--profile-dir")):
        if os.environ.get(env_name, "").strip():
            flags += [flag, os.environ[env_name].strip()]
    return flags


_EXIT_MESSAGES = {
    4: "ChatGPT 专用浏览器没有运行，或调试端口属于别的浏览器（只认专用资料夹里的那个）。",
    5: "专用浏览器里的 ChatGPT 还没登录——请在该窗口登录一次，然后重试。",
}


def _run_helper(args: list[str], stdin: bytes | None, timeout: int) -> bytes:
    flags = [] if os.environ.get("CHATGPT_VOICE_HELPER", "").strip() else _settings_flags()
    cmd = helper_command() + [args[0], *flags, *args[1:]]  # the subcommand comes first, then settings
    try:
        proc = subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ChatGPTVoiceError(f"ChatGPT 助手超过 {timeout} 秒没有回应。") from None
    except OSError as exc:
        raise ChatGPTVoiceError(f"无法启动 ChatGPT 助手：{exc}") from None
    if proc.returncode != 0:
        why = proc.stderr.decode("utf-8", "replace").strip()
        known = _EXIT_MESSAGES.get(proc.returncode)
        raise ChatGPTVoiceError(f"{known}\n  （助手说：{why[-200:]}）" if known else
                                f"ChatGPT 助手失败（退出码 {proc.returncode}）：{why[-300:]}")
    return proc.stdout


def check() -> dict:
    """专用浏览器是否在线并已登录 ChatGPT（不发消息）。"""
    return json.loads(_run_helper(["status"], None, 60).decode("utf-8").strip() or "{}")


def ask(text: str) -> dict:
    raw = _run_helper(["ask"], text.encode("utf-8"), ASK_TIMEOUT).decode("utf-8").strip()
    try:
        data = json.loads(raw.splitlines()[-1])
        return {"conversation_id": str(data["conversation_id"]), "message_id": str(data["message_id"]),
                "reply": str(data["reply"])}
    except (ValueError, KeyError, IndexError):
        raise ChatGPTVoiceError(f"ChatGPT 助手的回复格式不对：{raw[:200]}") from None


def speak(message_id: str, conversation_id: str, voice: str) -> bytes:
    return _run_helper(["speak", "--message-id", message_id, "--conversation-id", conversation_id,
                        "--voice", voice], None, SPEAK_TIMEOUT)


# ── 合成 ────────────────────────────────────────────────────────────────
def _probe_seconds(path: Path) -> float:
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                           "default=noprint_wrappers=1:nokey=1", str(path)],
                          capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def _to_mp3(raw: bytes, dst: Path) -> None:
    """朗读返回的音频统一转成 mp3；转不动（不是音频）就是失败。"""
    if not raw:
        raise ChatGPTVoiceError("ChatGPT 朗读返回了空音频（这个声线可能不能用）。")
    src = dst.with_suffix(".raw")
    src.write_bytes(raw)
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                           "-c:a", "libmp3lame", "-q:a", "4", str(dst)], capture_output=True, text=True)
    if proc.returncode != 0 or not dst.is_file():
        raise ChatGPTVoiceError(f"朗读返回的不是可用的音频：{proc.stderr.strip()[-200:]}")


def _concat(parts: list[Path], dst: Path) -> None:
    if len(parts) == 1:
        shutil.copyfile(parts[0], dst)
        return
    listing = dst.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                           "-i", str(listing), "-c:a", "libmp3lame", "-q:a", "4", str(dst)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not dst.is_file():
        raise ChatGPTVoiceError(f"拼接音频失败：{proc.stderr.strip()[-200:]}")


def _pauses(path: Path) -> list[tuple[float, float]]:
    """拼好的整段音频里的停顿 [(起, 止)]（ffmpeg 静音检测；解析沿用视频工具里已有的那个）。"""
    from video_ops import _parse_silences
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                           f"silencedetect=noise={PAUSE_NOISE_DB}dB:d={PAUSE_MIN_SECONDS}", "-f", "null", "-"],
                          capture_output=True, text=True)
    return _parse_silences(proc.stderr)


def _place_boundaries(estimates: list[float], lines: list[str], pauses: list[tuple[float, float]],
                      total: float) -> list[float]:
    """每条句界取与估算最近（落在其中算距离 0）的那段停顿的结尾，也就是下一句开口的时刻。
    不取「最长的 N−1 段停顿」：句内的逗号、冒号停顿可能比句间的还长。
    估算 PAUSE_WINDOW 秒内没有可用停顿 → 沿用估算，并在 stderr 打一行警告，指明是哪一句。"""
    free = list(pauses)
    placed: list[float] = []
    for i, guess in enumerate(estimates):
        def distance(p: tuple[float, float]) -> float:
            return 0.0 if p[0] <= guess <= p[1] else min(abs(guess - p[0]), abs(guess - p[1]))
        best = min(free, key=distance, default=None)
        if best is None or distance(best) > PAUSE_WINDOW:
            print(f"警告：第 {i + 2} 句字幕「{lines[i + 1][:20]}」附近没有找到停顿，沿用按字数估算的开始时间。",
                  file=sys.stderr)
            when = guess
        else:
            free.remove(best)
            when = best[1]
        placed.append(min(max(when, placed[-1] if placed else 0.0), total))
    return placed


def synthesize(text: str, out: Path, voice: str | None = None) -> list[tuple[str, float, float]]:
    """整篇文案 → out（mp3）。返回分句时间轴 [(句子, 起, 止)]：每句从它开口的时刻起，到下一句开口止；
    开口时刻取自拼好的整段音频里的停顿（见 _place_boundaries），找不到停顿的句界退回按字数分摊块时长的估算。
    任何一块失败（回复对不上、音频长度不对…）都整体失败，out 不会被写出。"""
    voice = resolve_voice(voice)  # 先认声线：不认识就在碰浏览器之前报错
    chunks = chunk_script(text)
    if not chunks:
        raise ChatGPTVoiceError("待合成文本为空。")
    lines: list[str] = []
    estimates: list[float] = []  # 估算的句末时刻（块内按字数分摊块的真实时长）
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        parts: list[Path] = []
        clock = 0.0
        for i, sentences in enumerate(chunks):
            sent = chunk_text(sentences)
            reply = ask(sent)
            if reply["reply"].strip() != sent.strip():
                raise ChatGPTVoiceError(
                    "ChatGPT 没有逐字重复文案（改写或回答了它），这条作废、什么都没保存。"
                    f"\n  发送：{sent[:80]}\n  回复：{reply['reply'][:80]}")
            part = work / f"part{i:03d}.mp3"
            _to_mp3(speak(reply["message_id"], reply["conversation_id"], voice), part)
            seconds = _probe_seconds(part)
            check_audio_length(spoken_chars(sent), seconds)
            total = sum(spoken_chars(s) for s in sentences) or 1
            for s in sentences:
                clock += seconds * spoken_chars(s) / total
                lines.append(s)
                estimates.append(clock)
            parts.append(part)
        out.parent.mkdir(parents=True, exist_ok=True)
        staged = work / "all.mp3"
        _concat(parts, staged)
        shutil.copyfile(staged, out)
        end = _probe_seconds(staged) or clock
        starts = [0.0, *_place_boundaries(estimates[:-1], lines, _pauses(staged), end)]
    return list(zip(lines, starts, [*starts[1:], end]))


# ── 命令行 ──────────────────────────────────────────────────────────────
def _cmd_speak(a) -> int:
    text = Path(a.file).read_text(encoding="utf-8") if a.file else (a.text or "")
    try:
        cues = synthesize(text, Path(a.output).expanduser().resolve(), a.voice)
    except ChatGPTVoiceError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 4
    print(f"✅ {a.output}  ({cues[-1][2]:.1f}s, ChatGPT 朗读 {a.voice or DEFAULT_VOICE})")
    return 0


def _cmd_check(_a) -> int:
    try:
        print(json.dumps(check(), ensure_ascii=False))
    except ChatGPTVoiceError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 4
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="配音走 ChatGPT 订阅的「朗读」（无 key）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("speak", help="文案 → mp3")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("-t", "--text")
    g.add_argument("-f", "--file")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("-v", "--voice", help=f"朗读声线，ChatGPT 设置页上的名字：{'、'.join(VOICES)}（默认 {DEFAULT_VOICE}）")
    p.set_defaults(func=_cmd_speak)
    sub.add_parser("check", help="专用浏览器在线且已登录吗").set_defaults(func=_cmd_check)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
