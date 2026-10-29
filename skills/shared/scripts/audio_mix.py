#!/usr/bin/env python3
"""audio_mix.py — 多轨音频混合（旁白 + BGM + 音效）的确定性封装。

"音频混合"类 SKILL（audio-mix）共用此脚本。把旁白/口播、背景音乐、音效混成一轨，
BGM 自动循环补足并可"闪避"（ducking：旁白说话时自动压低 BGM，保证人声清晰）。

与 audio_ops.py 的边界：audio_ops `concat` 是**顺序拼接**（前后接起来）；本脚本是
**同时叠加混音**（多轨同时播放）。与 video_ops.py `bgm` 的边界：那个给视频配乐，本脚本
只处理纯音频输出。

依赖：ffmpeg + ffprobe。

子命令：
    mix       多轨混音（--voice / --bgm / --sfx）
    selftest  自检

用法举例：
    audio_mix.py mix --voice narration.mp3 --bgm music.mp3 -o out.mp3
    audio_mix.py mix --voice v.mp3 --bgm m.mp3 --bgm-volume 0.2 --no-duck -o out.mp3
    audio_mix.py mix --voice v.mp3 --sfx ding.wav --sfx-at 3.5 --sfx whoosh.wav --sfx-at 8 -o out.mp3
    audio_mix.py selftest
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _check_ffmpeg() -> None:
    for t in ("ffmpeg", "ffprobe"):
        if shutil.which(t) is None:
            _die(f"未找到 {t}，请先安装 ffmpeg（含 ffprobe）。", 3)


def _require(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_file():
        _die(f"输入文件不存在: {p}", 2)
    return p


def _prep_out(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-18:])
        _die(f"ffmpeg 执行失败（exit {proc.returncode}）:\n{tail}", proc.returncode or 1)


def _dur(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float((proc.stdout or "0").strip())
    except ValueError:
        return 0.0


def _band_db(path: Path, hz: int, start: float, length: float | None = None) -> float:
    """`hz` 附近窄带内、从 start 秒起（取 length 秒）的平均电平 dB；该段没有声音则为 -inf。"""
    cmd = ["ffmpeg", "-hide_banner", "-ss", str(start)]
    if length:
        cmd += ["-t", str(length)]
    cmd += ["-i", str(path), "-af", f"bandpass=f={hz}:width_type=h:w=20,volumedetect",
            "-f", "null", "-"]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", proc.stderr or "")
    return float(m.group(1)) if m else float("-inf")


def _done(out: Path, extra: str = "") -> None:
    kb = out.stat().st_size / 1024 if out.is_file() else 0
    print(f"✅ {out} ({kb:.0f} KB){(' ' + extra) if extra else ''}")


def duck_filters(src: str, key: str, out: str) -> list[str]:
    """把 `src` 轨在 `key` 轨（旁白）说话时压低，输出到 `out`。三个参数都是不带方括号的标签名。

    音频混合（本脚本）和视频合成器（auto-short-video 的 assemble.py）共用这一步，压低的力度只此一处。
    key 先补静音到无限长：sidechaincompress 在较短的输入结束时就结束，不补的话被压低的轨会在旁白结束处被截断。
    """
    return [f"[{key}]apad[{key}_pad]",
            f"[{src}][{key}_pad]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[{out}]"]


def cmd_mix(a) -> int:
    _check_ffmpeg()
    sfx = a.sfx or []
    sfx_at = a.sfx_at or []
    if sfx and len(sfx_at) not in (0, len(sfx)):
        _die(f"--sfx-at 数量（{len(sfx_at)}）须为 0 或与 --sfx 数量（{len(sfx)}）一致。", 2)
    if not a.voice and not a.bgm and not sfx:
        _die("至少给 --voice / --bgm / --sfx 之一。", 2)

    # ── 目标时长：有旁白按旁白；否则取各输入有效结束的最大值 ──
    voice_dur = _dur(_require(a.voice)) if a.voice else 0.0
    ends = []
    if voice_dur:
        ends.append(voice_dur)
    for i, s in enumerate(sfx):
        at = float(sfx_at[i]) if sfx_at else 0.0
        ends.append(at + _dur(_require(s)))
    if a.bgm and not a.bgm_loop_off and not ends:
        ends.append(_dur(_require(a.bgm)))  # 仅 bgm 且不循环时按 bgm 长
    if a.bgm and not ends:
        ends.append(_dur(_require(a.bgm)))
    target = a.duration if a.duration else (max(ends) if ends else 0.0)
    if target <= 0:
        _die("无法确定输出时长，请用 --duration 指定。", 2)

    inputs: list[str] = []
    filt: list[str] = []
    mix_labels: list[str] = []
    idx = 0

    voice_label = None
    if a.voice:
        inputs += ["-i", str(_require(a.voice))]
        filt.append(f"[{idx}:a]volume={a.voice_volume},aresample=44100[voice]")
        voice_label = "[voice]"
        idx += 1

    if a.bgm:
        # 循环补足 + 音量；如需 ducking，用旁白做 sidechain 压 BGM
        loop_args = [] if a.bgm_loop_off else ["-stream_loop", "-1"]
        inputs += [*loop_args, "-i", str(_require(a.bgm))]
        filt.append(f"[{idx}:a]volume={a.bgm_volume},aresample=44100[bgm0]")
        idx += 1
        if voice_label and not a.no_duck:
            # 复制旁白作 sidechain 控制信号（补静音等细节见 duck_filters）
            filt.append(f"{voice_label}asplit=2[voice_m][voice_sc]")
            voice_label = "[voice_m]"
            filt += duck_filters("bgm0", "voice_sc", "bgm")
        else:
            filt.append("[bgm0]anull[bgm]")
        mix_labels.append("[bgm]")

    for i, s in enumerate(sfx):
        at = float(sfx_at[i]) if sfx_at else 0.0
        ms = int(at * 1000)
        inputs += ["-i", str(_require(s))]
        filt.append(f"[{idx}:a]volume={a.sfx_volume},adelay={ms}|{ms},"
                    f"aresample=44100[sfx{i}]")
        mix_labels.append(f"[sfx{i}]")
        idx += 1

    if not mix_labels and not voice_label:
        _die("没有可混合的音轨。", 2)
    # 末尾淡出，避免 BGM 硬切：只作用在旁白以外的音轨（BGM/音效）上，旁白永不被淡出
    if mix_labels:
        if len(mix_labels) == 1:
            filt.append(f"{mix_labels[0]}anull[bed]")
        else:
            filt.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:"
                        f"duration=longest:normalize=0:dropout_transition=0[bed]")
        fade = min(1.5, target / 4)
        filt.append(f"[bed]afade=t=out:st={max(0.0, target - fade):.3f}:d={fade:.3f}[bedout]")
        if voice_label:
            filt.append(f"{voice_label}[bedout]amix=inputs=2:"
                        f"duration=longest:normalize=0:dropout_transition=0[out]")
        else:
            filt.append("[bedout]anull[out]")
    else:
        filt.append(f"{voice_label}anull[out]")
    tracks = len(mix_labels) + (1 if voice_label else 0)

    out = _prep_out(a.output)
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filt),
          "-map", "[out]", "-t", f"{target:.3f}", str(out)])
    duck = "闪避" if (a.voice and a.bgm and not a.no_duck) else "无闪避"
    _done(out, f"({tracks} 轨 / {_dur(out):.1f}s / {duck})")  # 报实际写出的文件时长
    return 0


def cmd_selftest(_a) -> int:
    _check_ffmpeg()
    print("audio_mix 自检 ...", file=sys.stderr)
    import tempfile
    with tempfile.TemporaryDirectory() as td_:
        d = Path(td_)
        voice = d / "voice.wav"
        bgm = d / "bgm.wav"
        sfx = d / "sfx.wav"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:d=4", str(voice)])
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=600:d=10", str(bgm)])
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1200:d=0.3", str(sfx)])

        # 旁白 + BGM + 闪避：输出≈旁白长 4s，BGM 循环被裁
        out1 = d / "duck.mp3"
        cmd_mix(argparse.Namespace(voice=str(voice), voice_volume=1.0, bgm=str(bgm),
                                   bgm_volume=0.25, bgm_loop_off=False, no_duck=False,
                                   sfx=None, sfx_at=None, sfx_volume=0.8,
                                   duration=None, output=str(out1)))
        d1 = _dur(out1)
        assert 3.6 < d1 < 4.4, f"混音时长应≈4s，实得 {d1:.2f}s"

        # 旁白 + 两个音效（定时）
        out2 = d / "sfx.mp3"
        cmd_mix(argparse.Namespace(voice=str(voice), voice_volume=1.0, bgm=None,
                                   bgm_volume=0.25, bgm_loop_off=False, no_duck=False,
                                   sfx=[str(sfx), str(sfx)], sfx_at=[1.0, 3.0],
                                   sfx_volume=0.9, duration=None, output=str(out2)))
        assert out2.is_file() and _dur(out2) > 3.0, "音效混音异常"

        # 仅 BGM（不循环）
        out3 = d / "bgmonly.mp3"
        cmd_mix(argparse.Namespace(voice=None, voice_volume=1.0, bgm=str(bgm),
                                   bgm_volume=0.5, bgm_loop_off=True, no_duck=False,
                                   sfx=None, sfx_at=None, sfx_volume=0.8,
                                   duration=None, output=str(out3)))
        assert 9.0 < _dur(out3) < 11.0, "仅 BGM 时长应≈10s"

        # 旁白一直说到最后：混音末尾 1 秒的旁白电平须与输入一致（旁白不被淡出）
        voice_in = _band_db(voice, 300, 3.0)
        voice_out = _band_db(out1, 300, _dur(out1) - 1.0)
        assert abs(voice_out - voice_in) <= 1.0, \
            f"旁白末尾 1 秒被改动：输入 {voice_in:.1f} dB，输出 {voice_out:.1f} dB"

        # 闪避 + 要求时长比旁白长 2s：须补满时长，旁白结束后 BGM 继续播
        out4 = d / "duck_long.wav"
        cmd_mix(argparse.Namespace(voice=str(voice), voice_volume=1.0, bgm=str(bgm),
                                   bgm_volume=0.25, bgm_loop_off=False, no_duck=False,
                                   sfx=None, sfx_at=None, sfx_volume=0.8,
                                   duration=6.0, output=str(out4)))
        d4 = _dur(out4)
        assert 5.9 < d4 < 6.1, f"闪避混音应补满 6s，实得 {d4:.2f}s"
        after_voice = _band_db(out4, 600, 4.1, 0.3)
        assert after_voice > -50, f"旁白结束后 BGM 应继续播，实得 {after_voice:.1f} dB"

    print("✅ selftest 全部通过（旁白+BGM闪避 / 定时音效 / 仅BGM / 旁白末尾不淡出 / 闪避补满时长）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="多轨音频混合（旁白+BGM+音效，含 BGM 闪避 ducking）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("mix", help="多轨混音")
    p.add_argument("--voice", help="旁白/口播主轨（决定输出时长）")
    p.add_argument("--voice-volume", type=float, default=1.0, help="旁白音量（默认 1.0）")
    p.add_argument("--bgm", help="背景音乐（自动循环补足）")
    p.add_argument("--bgm-volume", type=float, default=0.25, help="BGM 音量（默认 0.25）")
    p.add_argument("--bgm-loop-off", action="store_true", help="BGM 不循环（用原长）")
    p.add_argument("--no-duck", action="store_true", help="关闭闪避（默认旁白+BGM 时自动闪避）")
    p.add_argument("--sfx", action="append", help="音效（可多次）")
    p.add_argument("--sfx-at", action="append", help="音效起始秒（与 --sfx 同数量，可多次）")
    p.add_argument("--sfx-volume", type=float, default=0.9, help="音效音量（默认 0.9）")
    p.add_argument("--duration", type=float, help="强制输出时长秒")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_mix)

    sub.add_parser("selftest", help="自检").set_defaults(func=cmd_selftest)

    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 1
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
