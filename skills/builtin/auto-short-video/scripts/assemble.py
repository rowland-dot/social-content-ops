#!/usr/bin/env python3
"""auto-short-video 合成器：分镜素材（图/片段 + 配音 + BGM + 字幕）→ 成品短视频。

这是端到端"主题→成片"流程里【确定性合成】的一环（ffmpeg）。上游的文案/配图/配音/
字幕/BGM 由各自 SKILL 生成（video-script / ai-image-gen / tts-voiceover / auto-subtitle
/ ai-music），本脚本负责把它们**可靠地拼成一条竖版短视频**。

输入 storyboard JSON（--storyboard 文件 或 stdin）：
{
  "size": "1080x1920",              // 可选，默认 1080x1920（9:16）
  "image_motion": "ken-burns",      // 可选；static 为完全静止、等比适配
  "shots": [
    {"image": "shot1.png", "duration": 3.0, "caption": "第一句话", "motion": "static"},
    {"video": "clip2.mp4", "caption": "第二句"},   // image 或 video 二选一
    ...
  ],
  "narration": "voice.mp3",         // 可选，整条配音；给了则总时长跟随它
  "bgm": "bgm.mp3",                 // 可选，背景音乐；有配音时配音说话处自动压低，说完恢复
  "subtitle": "sub.srt",            // 可选，烧录字幕；没给则用各 shot 的 caption 自动生成
  "subtitle_keep_words": ["燕麦肽"],  // 可选，字幕断行时不许拆开的词（品牌词/产品名）；每条字幕最多 2 行
  "subtitle_size": 96,              // 可选，烧录字幕字号（像素，正整数）；顺序：--sub-size > 这里 > 默认(短边×0.05)；
                                    // 字幕是现成 .ass 文件时不能用（报错，改传 SRT）
  "bgm_volume": 0.25,                // 可选，BGM 相对音量（默认 0.25）
  "bgm_loop": false,                 // 可选，音乐比视频短时是否循环（默认 false：不循环，渲染前报错并点名差几秒）
  "bgm_fade_out": 2.0                // 可选，音乐在最后几秒淡出（只淡音乐，不动配音/原声/音效）；缺省不淡出
}

成片出完后会自动查一遍：字幕有没有盖住卡片镜头上的字或便签（读卡片图旁边 render_card.py 存的 <图片名>.layout.json），
结果打印在 ✅ 那行下面；只报告，不改任何文件，也不影响退出码。量不了的卡片会写「未检查」。

用法：
    assemble.py assemble --storyboard sb.json -o outputs/xxx/final.mp4
    assemble.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from itertools import groupby
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))   # audio_mix：压低音乐/原声共用


def fail(msg: str, code: int = 1):
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(code)


def _check_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            fail(f"未找到 {tool}，请先安装 ffmpeg。", 3)


def _run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tail = "\n".join((r.stderr or "").splitlines()[-12:])
        fail(f"ffmpeg 执行失败：\n{tail}", 4)


def _probe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _has_audio(path: str) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def _fmt_ts(sec: float) -> str:
    h = int(sec // 3600); m = int((sec % 3600) // 60)
    s = int(sec % 60); ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _auto_srt(shots: list[dict], durations: list[float], srt_path: Path):
    """用各 shot 的 caption + 时长自动生成 SRT。"""
    lines = []
    t = 0.0
    idx = 1
    for shot, dur in zip(shots, durations):
        cap = (shot.get("caption") or "").strip()
        if cap:
            lines.append(f"{idx}\n{_fmt_ts(t)} --> {_fmt_ts(t + dur)}\n{cap}\n")
            idx += 1
        t += dur
    srt_path.write_text("\n".join(lines), encoding="utf-8")


DEFAULT_SUB_FONT = "Noto Sans CJK SC"   # 环境已装 fonts-noto-cjk；缺则 libass 回退系统字体


def _ass_ts(srt_ts: str) -> str:
    """SRT 时间戳 HH:MM:SS,mmm → ASS H:MM:SS.cs（厘秒）。"""
    srt_ts = srt_ts.strip().replace(".", ",")
    hms, _, ms = srt_ts.partition(",")
    h, m, s = (hms.split(":") + ["0", "0", "0"])[:3]
    cs = int(round(int((ms or "0").ljust(3, "0")[:3]) / 10))
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs:02d}"


# libass 的字号是「行高」（Noto Sans CJK 的上下延伸合计约 1.448 em），不是 em：实测一个汉字或全角标点
# 宽 0.685 × 字号（54px→37.0、84px→57.6、96px→65.8，2026-10-16 在 WSL 里渲染量得）。拉丁字母约 0.49 em、
# 空格约 0.22 em（字体表量得）。字符宽度单位 = 字号的倍数，与 _srt_to_ass 的每行上限同一单位。
_EM = 0.685


def _char_units(ch: str) -> float:
    """单字符占的横向宽度（单位：字号）：汉字/全角 1 em，空格 0.22 em，其余（拉丁/数字/半角标点）0.5 em。"""
    if ch == " ":
        return 0.22 * _EM
    return (1.0 if ord(ch) > 0x2E80 else 0.5) * _EM


_NO_LINE_START = "，。、？！：；）」』”’》…,.?!:;)%"   # 避头：这些符号不放行首，并入上一个词
_CLAUSE_END = "，、；：。？！,;:.?!"                  # 有停顿的位置：优先在这里断行


@lru_cache(maxsize=8)
def _tokenizer(keep_words: tuple[str, ...]):
    """jieba 分词器；keep_words 里的词（品牌词、产品名）保证不被拆开。每组词只建一次。"""
    try:
        import logging
        import jieba
    except ImportError:
        fail("字幕按词断行需要 jieba（Easel 的依赖，pyproject 已声明），当前环境没有安装。", 3)
    jieba.setLogLevel(logging.WARNING)
    tk = jieba.Tokenizer()
    for word in keep_words:
        tk.add_word(word)
    return tk


def _atoms(flat: str, max_units: float, keep_words: tuple[str, ...]) -> list[list]:
    """把一行字幕切成不可拆的「词」：[文字, 前面是否有空格]。标点并入前一个词，保证不会落到行首。"""
    toks: list[tuple[str, bool]] = []   # (词, 前面是否有空格)
    spaced = False
    for is_cjk, chars in groupby(flat, lambda ch: ord(ch) > 0x2E80):   # 汉字段交给 jieba，其余按空格切
        run = "".join(chars)
        words = _tokenizer(keep_words).lcut(run) if is_cjk else re.findall(r"\s+|\S+", run)
        for word in words:
            if word.isspace():
                spaced = True
                continue
            toks.append((word, spaced))
            spaced = False
    atoms: list[list] = []
    for word, spaced in toks:
        if atoms and word[0] in _NO_LINE_START:
            atoms[-1][0] += word
        elif sum(map(_char_units, word)) > max_units:
            # 单个词比一整行还宽（超长英文串等）：只能逐字强制断开
            atoms += [[ch, spaced and i == 0] for i, ch in enumerate(word)]
        else:
            atoms.append([word, spaced])
    return atoms


def wrap_caption(text: str, max_units: float, keep_words=()) -> list[str]:
    """按显示宽度把一行字幕**确定性**折成多行，每行 ≤ max_units（单位：字号），**只在词与词之间断**。

    纯函数、可测。保证不超视频宽度、随宽度自适应；不依赖 libass 折行启发式。
    - 词边界来自 jieba；keep_words 里的词（来自 storyboard.subtitle_keep_words）不会被拆开。
    - 标点不放行首；英文词之间的空格在断行处去掉，词不会被粘在一起。
    - 能放一行就一行（原样）；要两行时优先在逗号/顿号/冒号等停顿处断，并选两行最均衡的断点，没有停顿就取最均衡的词边界。
    - 需要三行以上时按最少行数顺排返回，由调用方决定是否拒绝（最多 2 行是规定，见 _srt_to_ass）。
    先并掉原有的软换行（统一按当前视频宽度重排）。
    """
    flat = " ".join(seg.strip() for seg in str(text).replace("\\N", "\n").split("\n") if seg.strip())
    if not flat:
        return []
    atoms = _atoms(flat, max_units, tuple(keep_words))
    widths = [sum(map(_char_units, a[0])) for a in atoms]
    gaps = [_char_units(" ") if a[1] else 0.0 for a in atoms]

    def span(i: int, j: int) -> float:   # atoms[i:j] 排成一行的宽度
        return sum(widths[i:j]) + sum(gaps[i + 1:j])

    def text_of(i: int, j: int) -> str:
        return "".join((" " if a[1] and k > i else "") + a[0] for k, a in enumerate(atoms[i:j], i))

    limit = max_units + 1e-9
    cuts = [0]                           # 最少行数的顺排：每行尽量装满
    for k in range(1, len(atoms)):
        if span(cuts[-1], k + 1) > limit:
            cuts.append(k)
    cuts.append(len(atoms))
    if len(cuts) == 3:                   # 恰好两行：重新挑断点
        fits = [s for s in range(1, len(atoms)) if span(0, s) <= limit and span(s, len(atoms)) <= limit]
        pauses = [s for s in fits if atoms[s - 1][0][-1] in _CLAUSE_END]
        cuts = [0, min(pauses or fits, key=lambda s: round(max(span(0, s), span(s, len(atoms))), 6)), len(atoms)]
    return [text_of(i, j) for i, j in zip(cuts, cuts[1:])]


def _srt_to_ass(srt_path: Path, ass_path: Path, w: int, h: int,
                font: str = DEFAULT_SUB_FONT, font_size: int | None = None,
                margin_v: int | None = None, keep_words: list[str] | None = None) -> Path:
    """把 SRT 转成带完整样式的 ASS，尺寸/位置/折行**确定可控**（治「字幕过大 / 超出边界 / 挤成一行」）。

    关键：显式 PlayResX/Y = 视频尺寸，字号就是像素级别、不再被 libass 按默认 288 放大。
    默认字号 ≈ **短边***0.05（min(w,h)：竖屏 1080×1920→54、横屏 1920×1080→54，横竖屏都合适、
    不再横屏字号翻倍过大），Alignment=2 底部居中，MarginV≈高*0.07，MarginL/R≈宽*0.06。
    **长行按可用宽度确定性折行**（wrap_caption：只在词与词之间断、标点不放行首、两行时均衡），保证不超边界、
    自适应视频宽度。**每条字幕最多 2 行**：放不进 2 行的字幕直接报错并点名（不拆条、不缩字号）。
    keep_words（storyboard.subtitle_keep_words）里的词不会被拆开。
    白字黑描边（Outline=2, Shadow=0）竖/横屏可读。
    """
    fs = int(font_size if font_size else round(min(w, h) * 0.05))
    mv = int(margin_v if margin_v is not None else round(h * 0.07))
    mh = int(round(w * 0.06))
    # 每行最大宽度单位 = 可用像素宽 / 字号；留 6% 安全余量防描边/字距溢出。
    max_units = max(6.0, (w - 2 * mh) / fs * 0.94)
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"0,0,0,0,100,100,0,0,1,2,0,2,{mh},{mh},{mv},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    # 解析 SRT 块
    events: list[str] = []
    too_long: list[str] = []
    blocks = [b for b in srt_path.read_text(encoding="utf-8").replace("\r", "").split("\n\n") if b.strip()]
    for b in blocks:
        rows = [r for r in b.split("\n") if r.strip() != ""]
        ts_line = next((r for r in rows if "-->" in r), None)
        if not ts_line:
            continue
        start, _, end = ts_line.partition("-->")
        txt_rows = rows[rows.index(ts_line) + 1:]
        raw = " ".join(t.strip() for t in txt_rows) if txt_rows else ""
        wrapped = wrap_caption(raw, max_units, keep_words or ())
        if not wrapped:
            continue
        if len(wrapped) > 2:
            too_long.append(f"「{raw}」需要 {len(wrapped)} 行")
        text = "\\N".join(wrapped)
        events.append(f"Dialogue: 0,{_ass_ts(start)},{_ass_ts(end)},Default,,0,0,0,,{text}")
    if too_long:
        # 规定：每条字幕最多 2 行。放不下就停下并点名，不偷偷缩字号、不折成三行、不估时间拆条。
        fail(f"字幕在 {fs}px 下放不进 2 行（每行约 {int(max_units / _char_units('汉'))} 个汉字）：\n  "
             + "\n  ".join(too_long) + "\n请把这几句缩短，或拆成两条字幕（各自对应配音的一句），再重新合成。")
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return ass_path


def _ass_seconds(ts: str) -> float:
    """ASS 时间戳 H:MM:SS.cs → 秒。"""
    h, m, s = ts.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _read_ass_cues(ass_path: Path, w: int, h: int) -> list[dict]:
    """读出**实际烧录**的 ASS 里每条字幕的起止时间和它占的方框（视频像素：[x0, y0, x1, y1]）。

    不自己估字号：合成器生成的 ASS 和现成的 ASS（如视频 01 的 96px 手动断行稿）都从文件里读，所以
    字号来源怎么变（命令行 / storyboard / 默认），这里都跟着烧进去的那份走。
    方框 = 左右到 MarginL/MarginR，底边在 高−MarginV，高 = 行数 ×（字号 + 2×描边）；行数按 \\N 数。
    只认底部对齐（Alignment 1–3）；别的对齐 box 为 None，由调用方说「没检查」。
    不模拟 libass 自己的折行：合成器生成的字幕已按宽度折好，现成 ASS 一般 WrapStyle 2。
    PlayRes 与视频尺寸不同时按比例换算（libass 也是这样缩放）。
    """
    section, style_fmt, event_fmt = "", [], []
    styles: dict[str, dict] = {}
    play = {"PlayResX": 384.0, "PlayResY": 288.0}   # libass 缺省
    cues = []
    for raw in ass_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line.lower()
            continue
        key, _, rest = line.partition(":")
        rest = rest.strip()
        if key in play:
            play[key] = float(rest)
        elif key == "Format":
            fmt = [f.strip() for f in rest.split(",")]
            if section == "[events]":
                event_fmt = fmt
            else:
                style_fmt = fmt
        elif key == "Style" and style_fmt:
            row = dict(zip(style_fmt, (v.strip() for v in rest.split(","))))
            styles[row["Name"]] = row
        elif key == "Dialogue" and event_fmt:
            ev = dict(zip(event_fmt, rest.split(",", len(event_fmt) - 1)))
            text = re.sub(r"\{[^}]*\}", "", ev["Text"])
            if not text.strip():
                continue
            st = styles.get(ev["Style"].strip()) or styles.get("Default")
            box = None
            if st and int(st["Alignment"]) in (1, 2, 3):
                sx, sy = w / play["PlayResX"], h / play["PlayResY"]
                ml = int(ev.get("MarginL", 0)) or int(st["MarginL"])
                mr = int(ev.get("MarginR", 0)) or int(st["MarginR"])
                mv = int(ev.get("MarginV", 0)) or int(st["MarginV"])
                bottom = h - mv * sy
                top = bottom - (text.count("\\N") + 1) * (float(st["Fontsize"]) + 2 * float(st["Outline"])) * sy
                box = [ml * sx, top, w - mr * sx, bottom]
            cues.append({"start": _ass_seconds(ev["Start"]), "end": _ass_seconds(ev["End"]),
                         "text": text.replace("\\N", " "), "box": box})
    return cues


def _subtitle_card_report(shots: list[dict], durations: list[float], ass_path: Path, w: int, h: int,
                          image_motion: str) -> list[str]:
    """字幕会不会盖住卡片镜头上的字或便签？**只报告，不改任何东西。**

    卡片的字和便签在哪，来自 render_card.py 存在卡片图旁边的 <图片名>.layout.json（图片像素）。
    对每个图片镜头：和它同屏过的每条字幕（哪怕只有一瞬）逐个和版面里的字、便签比；重叠就报镜头号、
    字幕时间、同屏秒数、盖住的是什么、y 范围。量不了的（没有版面文件、读不了、尺寸对不上、画面会缩放）
    如实写「未检查」，绝不当成「没问题」。
    """
    cues = _read_ass_cues(ass_path, w, h)
    lines: list[str] = []
    start = 0.0
    for n, (shot, dur) in enumerate(zip(shots, durations), 1):
        end = start + dur
        window, start = (start, end), end
        image = shot.get("image")
        if shot.get("video") or not image:
            continue
        head = f"  镜头 {n}（{Path(image).name}，{window[0]:.2f}–{window[1]:.2f}s）"
        layout_file = Path(image).with_suffix(".layout.json")
        motion = str(shot.get("motion") or image_motion)
        if motion != "static":
            lines.append(f"{head}未检查：画面会缩放（motion={motion}），卡片上的字会移动，位置对不上。"
                         "卡片镜头请写 \"motion\": \"static\"。")
            continue
        try:
            layout = json.loads(layout_file.read_text(encoding="utf-8"))
            boxes, size = layout["boxes"], (layout["width"], layout["height"])
        except FileNotFoundError:
            lines.append(f"{head}未检查：图片旁边没有版面文件 {layout_file.name}"
                         "（用 render_card.py 渲染卡片时会自动存）。")
            continue
        except (OSError, ValueError, KeyError, TypeError) as e:
            lines.append(f"{head}未检查：版面文件 {layout_file.name} 读不了（{type(e).__name__}: {e}）。")
            continue
        if size != (w, h):
            lines.append(f"{head}未检查：卡片图 {size[0]}x{size[1]}，视频 {w}x{h}，尺寸不同，版面对不上。")
            continue
        on_card = [c for c in cues if min(c["end"], window[1]) - max(c["start"], window[0]) > 1e-6]
        hits = skipped = 0
        for cue in on_card:
            secs = min(cue["end"], window[1]) - max(cue["start"], window[0])
            when = f"字幕 {cue['start']:.2f}–{cue['end']:.2f}s 与卡片同屏 {secs:.2f}s"
            if cue["box"] is None:
                skipped += 1
                lines.append(f"{head}：{when}，但它不是底部对齐的字幕，位置没检查。")
                continue
            sx0, sy0, sx1, sy1 = cue["box"]
            for b in boxes:
                bx0, by0, bx1, by1 = b["box"]
                if min(sx1, bx1) > max(sx0, bx0) and min(sy1, by1) > max(sy0, by0):
                    hits += 1
                    what = {"note": "便签", "text": "文字"}.get(b["kind"], b["kind"])
                    lines.append(f"  ⚠️ 镜头 {n}（{Path(image).name}）：{when}，盖住{what}「{b['text']}」 "
                                 f"y {round(max(sy0, by0))}–{round(min(sy1, by1))}")
        if not hits and not skipped:
            lines.append(f"{head}：没有重叠（{len(on_card)} 条字幕在这张卡上出现）。" if on_card
                         else f"{head}：没有重叠（这张卡上没有字幕）。")
    return ["字幕与卡片重叠检查（只报告，不改任何东西）："] + lines if lines else []


MAX_STRETCH = 2.0   # 慢放填满的最大倍数；超过则改用循环（避免过度慢动作）。仅 auto/stretch 模式用；trim 禁止填充。


def _image_filter(motion: str, w: int, h: int, frames: int) -> str:
    if motion == "static":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30")
    if motion == "ken-burns":
        return (f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
                f"crop={w*2}:{h*2},"
                f"zoompan=z='min(zoom+0.0008,1.08)':d={frames}:s={w}x{h}:fps=30,"
                f"setsar=1")
    fail(f"shot motion 不支持：{motion}（只能是 static / ken-burns）")


def _make_shot_clip(shot: dict, dur: float, w: int, h: int, out: Path, workdir: Path,
                    pad_mode: str = "auto", include_audio: bool = False,
                    preserve_audio: bool = False, image_motion: str = "ken-burns"):
    """把单个 shot（图或视频）做成 w×h、时长 dur 的片段。

    视频短于 dur 时如何补足（pad_mode）：
      trim（自然，短剧默认）= **绝不慢放/循环/冻结**。够长裁到 dur；片段比 dur 短 → **直接硬失败**
        （让上游按真实片段重跑 align 或用更大档重生成，而不是冻结凑台词长度、破坏流畅度）。
      auto = 差得不多就慢放拉伸(setpts，≤MAX_STRETCH 倍)、差很多就循环(loop)；
      stretch = 一律慢放填满；loop = 一律循环填满；freeze = 一律冻结末帧（仅显式要求时）。
    视频长于 dur → 裁到 dur。
    """
    base_vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")

    def audio_args(src: str | None) -> tuple[list[str], list[str]]:
        if not include_audio:
            return [], ["-an"]
        if preserve_audio:
            if not src or not _has_audio(src):
                fail(f"镜头声明 audio_mode=native，但源片段没有可用音轨：{src}")
            return [], ["-map", "0:v:0", "-map", "0:a:0", "-af",
                        "aresample=48000,aformat=channel_layouts=stereo,apad",
                        "-c:a", "aac", "-b:a", "192k"]
        return (["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"],
                ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"])

    if shot.get("video"):
        src = shot["video"]
        if not Path(src).is_file():
            fail(f"shot 视频不存在：{src}")
        src_dur = _probe_duration(src)
        extra_inputs, audio_out = audio_args(src)
        if src_dur >= dur - 0.05 or src_dur <= 0:
            # 够长（或探测不到）→ 裁到 dur
            _run(["ffmpeg", "-y", "-i", src, *extra_inputs, "-t", f"{dur:.3f}",
                  "-vf", f"{base_vf},fps=30", *audio_out,
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
            return
        factor = dur / src_dur
        mode = pad_mode
        if mode == "trim":
            # 自然模式：**绝不冻结/拉伸/循环**。片段比所需短 = 画面盖不住 → 直接硬失败，
            # 让上游按真实片段重跑 dubbing align（画面时长=真实片段长）或用更大档重生成该镜片段，
            # 而不是冻结末帧凑台词长度（那会让画面停住、割裂、不流畅）。
            fail(f"视频片段仅 {src_dur:.2f}s 但该镜要 {dur:.2f}s（差 {dur - src_dur:.2f}s）——"
                 f"trim(自然)模式禁止冻结/拉伸/循环。\n"
                 f"根因通常是：align 没在**真实视频片段都生成好之后**跑（用了台词长度当画面时长）。"
                 f"请先确保每镜 clip 已生成，重跑 `dubbing.py align`（按真实片段对齐），再合成；"
                 f"或用更大片段档重生成该镜。", 4)
        if mode == "auto":
            mode = "stretch" if factor <= MAX_STRETCH else "loop"
        if mode == "stretch":
            # 慢放：拉伸 PTS 到 dur，画面持续运动、无跳变、无停顿
            _run(["ffmpeg", "-y", "-i", src,
                  *extra_inputs, "-vf", f"{base_vf},setpts={factor:.4f}*PTS,fps=30", "-t", f"{dur:.3f}",
                  *audio_out, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
        elif mode == "freeze":
            # 冻结末帧（旧行为，仅当显式要求）
            _run(["ffmpeg", "-y", "-i", src,
                  *extra_inputs, "-vf", f"{base_vf},fps=30,tpad=stop_mode=clone:stop_duration={dur:.3f}",
                  "-t", f"{dur:.3f}", *audio_out, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
        else:  # loop：循环填满，画面持续运动（循环点有轻微跳变）
            _run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", src, *extra_inputs, "-t", f"{dur:.3f}",
                  "-vf", f"{base_vf},fps=30", *audio_out,
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
    else:
        src = shot.get("image")
        if not src or not Path(src).is_file():
            fail(f"shot 图片不存在：{src}")
        frames = max(1, int(dur * 30))
        extra_inputs, audio_out = audio_args(None)
        motion = str(shot.get("motion") or image_motion)
        # static 用于文字卡/slide/图表；Ken Burns 只用于适合裁切的照片。
        vf = _image_filter(motion, w, h, frames)
        _run(["ffmpeg", "-y", "-loop", "1", "-i", src, *extra_inputs, "-t", f"{dur:.3f}",
              "-vf", vf, *audio_out, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])


TARGET_LUFS = -16.0   # the owner, 2026-10-23: every finished video lands at -16 LUFS integrated (issue 31)
TARGET_PEAK_DBTP = -1.5   # the finished file must stay at or under -1 dBTP; the AAC encode can add a little, so aim lower


def _normalise_loudness(stage: Path, out: Path) -> Path:
    """整条成片的声音一次性调到 TARGET_LUFS：先量（第一遍）再按量到的值调（第二遍），一遍调不准。

    对**混好的整条**调一次，不是对各轨分别调，所以音乐相对配音的音量、压低都原样保留。
    响度滤镜输出 192 kHz，所以最后把采样率放回 48 kHz（issue 28）。没有音轨、或音轨是纯静音（量不出响度）时原样返回。
    画面不重编码。
    """
    if not _has_audio(str(stage)):
        return stage
    measure = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(stage), "-vn", "-af",
         f"loudnorm=I={TARGET_LUFS}:TP={TARGET_PEAK_DBTP}:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    blocks = re.findall(r"\{[^{}]*\}", measure.stderr)
    try:
        m = json.loads(blocks[-1])
        measured = {k: float(m[f"input_{k}"]) for k in ("i", "tp", "lra", "thresh")} | {"offset": float(m["target_offset"])}
    except (IndexError, KeyError, ValueError):
        fail(f"量成片响度失败：\n" + "\n".join((measure.stderr or "").splitlines()[-8:]), 4)
    if not all(map(math.isfinite, measured.values())):
        print("  ⚠️ 成片的声音是纯静音，量不出响度，没有调整。", file=sys.stderr)
        return stage
    _run(["ffmpeg", "-y", "-i", str(stage), "-map", "0:v", "-map", "0:a", "-c:v", "copy",
          "-af", (f"loudnorm=I={TARGET_LUFS}:TP={TARGET_PEAK_DBTP}:LRA=11:measured_I={measured['i']}"
                  f":measured_TP={measured['tp']}:measured_LRA={measured['lra']}:measured_thresh={measured['thresh']}"
                  f":offset={measured['offset']}:linear=true,aresample=48000"),
          "-c:a", "aac", "-b:a", "192k", str(out)])
    return out


def cmd_assemble(args) -> int:
    _check_ffmpeg()
    raw = sys.stdin.read() if args.storyboard == "-" else Path(args.storyboard).read_text(encoding="utf-8")
    try:
        sb = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"storyboard 不是有效 JSON：{e}")

    shots = sb.get("shots") or []
    if not shots:
        fail("storyboard.shots 为空。")
    image_motion = str(sb.get("image_motion") or "ken-burns")
    if image_motion not in {"static", "ken-burns"}:
        fail("storyboard.image_motion 只能是 static / ken-burns")
    size = str(sb.get("size") or "1080x1920")
    try:
        w, h = (int(x) for x in size.lower().split("x"))
    except ValueError:
        fail(f"size 格式错误：{size}（应如 1080x1920）")
    keep_words = sb.get("subtitle_keep_words") or []
    if not isinstance(keep_words, list) or not all(isinstance(k, str) and k.strip() for k in keep_words):
        fail("storyboard.subtitle_keep_words 必须是非空字符串的列表（字幕断行时不许拆开的词，如品牌词）")
    plan_size = sb.get("subtitle_size")
    if plan_size is not None and (not isinstance(plan_size, int) or isinstance(plan_size, bool) or plan_size <= 0):
        fail("storyboard.subtitle_size 必须是正整数（字幕字号，单位像素，如 96）")
    sub_size = getattr(args, "sub_size", None) or plan_size   # 命令行 > storyboard > 默认（None → 短边 ×0.05）

    narration = sb.get("narration")
    if narration and not Path(narration).is_file():
        fail(f"配音文件不存在：{narration}")

    # 决定每个 shot 时长：有显式 duration 用之；否则若有配音则均分配音时长；否则默认 3s
    durations: list[float] = []
    explicit = [float(s["duration"]) for s in shots if s.get("duration")]
    if narration and len(explicit) < len(shots):
        total = _probe_duration(narration)
        per = max(1.0, total / len(shots)) if total > 0 else 3.0
        durations = [float(s.get("duration") or per) for s in shots]
    else:
        durations = [float(s.get("duration") or 3.0) for s in shots]

    # 背景音乐：渲染前先查清楚（文件在不在、够不够长、淡出设得对不对），有问题就在画面开始渲染前停下。
    bgm_loop = sb.get("bgm_loop", False)
    if not isinstance(bgm_loop, bool):
        fail("storyboard.bgm_loop 只能是 true 或 false")
    bgm_fade = 0.0
    if sb.get("bgm"):
        if not Path(sb["bgm"]).is_file():
            fail(f"BGM 文件不存在：{sb['bgm']}")
        try:
            bgm_fade = float(sb.get("bgm_fade_out") or 0.0)
        except (TypeError, ValueError):
            fail("storyboard.bgm_fade_out 必须是秒数（数字）")
        if not 0.0 <= bgm_fade <= sum(durations):
            fail(f"storyboard.bgm_fade_out 须在 0 到视频总长 {sum(durations):.1f}s 之间，实得 {bgm_fade}")
        short = sum(durations) - _probe_duration(sb["bgm"])
        if short > 0.05 and not bgm_loop:
            fail(f"背景音乐比视频短 {short:.1f} 秒（视频 {sum(durations):.1f}s），合成前停下，没有渲染。"
                 f"请换一首至少长 {short:.1f} 秒的音乐，或在 storyboard 里加 \"bgm_loop\": true 让它循环。")

    # 原生音频处理：**只有 native 镜**（audit 判「原声可用」）直通其原生音轨（人声+环境音）；
    # **dub 镜的原生音轨整轨丢弃、改由独立 TTS 配音替代**——因为无人声分离时原生轨里的完整人声无法只去人声、
    # 留了就会和 TTS **双重人声/回声**（真机踩过）。代价是 dub 镜丢失环境音（重复比丢环境音严重得多）。
    # 只有源片段无音轨（图片/静音 clip）也补静音。
    def _shot_keeps_audio(s: dict) -> bool:
        v = s.get("video")
        # dub 镜：视频模型原生音轨（含模型生成人声）不并入 abase，
        # 完全由独立 TTS 配音替代，防止双重人声。只有 native 镜的原轨直通。
        return (s.get("audio_mode") == "native"
                and bool(v) and Path(v).is_file() and _has_audio(v))
    keeps_audio = [_shot_keeps_audio(s) for s in shots]
    native_audio = any(keeps_audio)   # 是否存在「环境音底」（下方 abase 用它拼接，而非全程静音）

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        # 字幕先备好：优先用户给的 srt，否则用 caption 自动生成；转 ASS 时有字幕放不进 2 行就在这里停下，
        # 不等到画面都渲染完才发现。
        sub_path = None
        if sb.get("subtitle") and Path(sb["subtitle"]).is_file():
            sub_path = Path(sb["subtitle"])
        elif any(s.get("caption") for s in shots):
            sub_path = workdir / "auto.srt"
            _auto_srt(shots, durations, sub_path)
        ass_path = None
        if sub_path:
            if sub_path.suffix.lower() == ".ass":
                if sub_size:
                    # 现成的 ASS 自带字号，原样烧录；给了字号却不生效，必须报错，不能悄悄忽略
                    fail(f"字幕字号 {sub_size}px 不能用在现成的 ASS 文件上（{sub_path.name} 自带样式、原样烧录）。"
                         "请改传 SRT 字幕，由合成器按字号生成样式。")
                ass_path = sub_path
            else:
                ass_path = workdir / "sub.ass"
                _srt_to_ass(sub_path, ass_path, w, h,
                            font=getattr(args, "sub_font", None) or DEFAULT_SUB_FONT,
                            font_size=sub_size,
                            margin_v=getattr(args, "sub_margin_v", None),
                            keep_words=keep_words)
        # 视频短于所需时长时如何填满：优先命令行，其次 storyboard，默认 auto（慢放/循环，保持画面运动）
        pad_mode = getattr(args, "pad_mode", None) or str(sb.get("pad_mode") or "auto")
        clips = []
        for i, (shot, dur) in enumerate(zip(shots, durations)):
            clip = workdir / f"clip_{i:03d}.mp4"
            print(f"  合成分镜 {i+1}/{len(shots)}（{dur:.1f}s）...", file=sys.stderr)
            _make_shot_clip(shot, dur, w, h, clip, workdir, pad_mode,
                            include_audio=native_audio,
                            preserve_audio=keeps_audio[i],
                            image_motion=image_motion)
            clips.append(clip)

        # 拼接
        concat_list = workdir / "list.txt"
        concat_list.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
        silent = workdir / "silent.mp4"
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
              "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent)])

        video_dur = sum(durations)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 音效轨：storyboard.sfx = [{"file": 路径, "at": 全局秒, "volume": 相对音量}]
        # （枪声/椅子移动/脚步/开门…按时间点叠进成片音轨，占用非台词时间，让画面有声音层次）
        sfx_list = [s for s in (sb.get("sfx") or []) if s.get("file") and Path(s["file"]).is_file()]
        for s in (sb.get("sfx") or []):
            if s.get("file") and not Path(s["file"]).is_file():
                print(f"  ⚠️ 音效文件不存在，跳过：{s['file']}", file=sys.stderr)

        # 音频：配音 + BGM + 定时音效 混音
        stage = silent
        if narration or sb.get("bgm") or sfx_list:
            stage2 = workdir / "with_audio.mp4"
            inputs = ["-i", str(silent)]
            filters = []
            amix_srcs = []
            ai = 1
            # 原生音频片段已与静音片段拼成一条连续底轨；无原生音频时才创建静音基底。
            if native_audio:
                filters.append("[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[abase]")
            else:
                inputs += ["-f", "lavfi", "-t", f"{video_dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
                filters.append(f"[{ai}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[abase]")
                ai += 1
            # 配音轨（旁白 + 未通过审计需换的对白；align 已把通过审计的 native 画内对白移除）
            has_voice = False
            if narration:
                inputs += ["-i", narration]
                filters.append(f"[{ai}:a]aresample=48000[voice]")
                has_voice = True
                ai += 1
            has_bgm = bool(sb.get("bgm"))
            if has_bgm:
                vol = float(sb.get("bgm_volume") or 0.25)
                inputs += [*(["-stream_loop", "-1"] if bgm_loop else []), "-i", sb["bgm"]]
                filters.append(f"[{ai}:a]aresample=44100,volume={vol}[bgm0]")
                ai += 1
            # 侧链闪避：有配音时，用 TTS/旁白作侧链把「原生底轨（native 镜）」和「背景音乐」在**说话瞬间**压低、
            # 说完恢复，让旁白干净盖在它们之上；native 镜自身对白处配音轨为静音→不触发压低。
            # （dub 镜已不并入原生轨，这里不涉及 dub 的人声——双重人声从源头避免。）
            # 压低这一步与 audio_mix.py 共用（duck_filters：key 补静音到无限长，被压低的轨不会在配音结束处被截断）。
            ducked = []   # [(被压低的轨, 压低后的轨)]
            if has_voice and native_audio:
                ducked.append(("abase", "abaseduck"))
            if has_voice and has_bgm:
                ducked.append(("bgm0", "bgmduck"))
            if ducked:
                from audio_mix import duck_filters
                keys = [f"voicekey{n}" for n in range(len(ducked))]
                filters.append(f"[voice]asplit={len(keys) + 1}[voicemix]" + "".join(f"[{k}]" for k in keys))
                for (src, out_label), key in zip(ducked, keys):
                    filters += duck_filters(src, key, out_label)
            amix_srcs.append("[abaseduck]" if has_voice and native_audio else "[abase]")
            if has_voice:
                amix_srcs.append("[voicemix]" if ducked else "[voice]")
            if has_bgm:
                bgm_label = "bgmduck" if has_voice else "bgm0"
                if bgm_fade:   # 只淡音乐：配音、原声、音效不经过这一步
                    filters.append(f"[{bgm_label}]afade=t=out:st={video_dur - bgm_fade:.3f}:d={bgm_fade:.3f}[bgmout]")
                    bgm_label = "bgmout"
                amix_srcs.append(f"[{bgm_label}]")
            for si, s in enumerate(sfx_list):
                ms = max(0, int(round(float(s.get("at") or 0.0) * 1000)))
                vol = float(s.get("volume") or 0.9)
                inputs += ["-i", str(s["file"])]
                filters.append(f"[{ai}:a]aresample=44100,volume={vol},adelay={ms}|{ms}[sfx{si}]")
                amix_srcs.append(f"[sfx{si}]")
                ai += 1
            # 基底在首位 → duration=first=视频时长；normalize=0 保各轨原音量（不因轨数被均分压低）。
            filters.append(f"{''.join(amix_srcs)}amix=inputs={len(amix_srcs)}:duration=first:normalize=0[aout]")
            _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
                  "-map", "0:v", "-map", "[aout]", "-t", f"{video_dur:.3f}",
                  "-c:v", "copy", "-c:a", "aac", str(stage2)])
            stage = stage2

        # 整条成片的声音调到 -16 LUFS（有声音轨才做；音轨来自上面的混音，或只有 native 镜头的原声）
        stage = _normalise_loudness(stage, workdir / "loud.mp4")

        # 烧字幕：上面已把 SRT 转成带完整样式的 ASS（尺寸/位置可控，底部居中、字号合适），这里烧录
        if ass_path:
            escaped = str(ass_path).replace("'", "\\'").replace(":", "\\:")
            _run(["ffmpeg", "-y", "-i", str(stage),
                  "-vf", f"subtitles='{escaped}'",
                  "-c:a", "copy", str(out)])
        else:
            shutil.copy(str(stage), str(out))

        # 成片出完再查：字幕有没有盖住卡片镜头上的字或便签。只报告，出错也不能让成片算失败。
        overlap_report: list[str] = []
        if ass_path:
            try:
                overlap_report = _subtitle_card_report(shots, durations, ass_path, w, h, image_motion)
            except Exception as e:  # noqa: BLE001
                overlap_report = [f"字幕与卡片重叠检查没能运行（成片不受影响）：{type(e).__name__}: {e}"]

    print(f"✅ 成片已生成：{out}（{video_dur:.1f}s，{w}x{h}）")
    for line in overlap_report:
        print(line)
    return 0


def cmd_selftest(_args) -> int:
    _check_ffmpeg()
    static_vf = _image_filter("static", 1080, 1920, 60)
    kenburns_vf = _image_filter("ken-burns", 1080, 1920, 60)
    if "zoompan" in static_vf or "crop=" in static_vf or "pad=" not in static_vf:
        fail("自检失败：static 图片过滤器发生裁切或移动", 1)
    if "zoompan" not in kenburns_vf:
        fail("自检失败：Ken Burns 过滤器未生效", 1)
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        # 造两张测试图（ffmpeg lavfi）
        imgs = []
        for i, color in enumerate(("red", "blue")):
            p = wd / f"img{i}.png"
            _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:d=1",
                  "-frames:v", "1", str(p)])
            imgs.append(str(p))
        # 造一段配音（正弦音代替）
        voice = wd / "v.mp3"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
              "-q:a", "5", str(voice)])
        sb = {"size": "1080x1920", "narration": str(voice),
              "shots": [{"image": imgs[0], "duration": 2, "caption": "第一句字幕测试"},
                        {"image": imgs[1], "duration": 2, "caption": "第二句字幕测试",
                         "motion": "static"}]}
        sbf = wd / "sb.json"
        sbf.write_text(json.dumps(sb), encoding="utf-8")
        out = wd / "final.mp4"
        ns = argparse.Namespace(storyboard=str(sbf), output=str(out))
        cmd_assemble(ns)
        if not (out.is_file() and out.stat().st_size > 0 and _probe_duration(str(out)) > 3):
            fail("自检失败：成片未正确生成", 1)
        print("[PASS] assemble 自检通过（真出成片，含 Ken Burns/static + 配音 + 字幕）")

        # 字幕 ASS：显式 PlayRes + 底部居中 + 字号按分辨率（治「字幕过大」）
        srt = wd / "t.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,500\n第一句\n\n"
                       "2\n00:00:01,500 --> 00:00:03,000\n第二句\n", encoding="utf-8")
        ass = wd / "t.ass"
        _srt_to_ass(srt, ass, 1080, 1920)
        at = ass.read_text(encoding="utf-8")
        ok_ass = ("PlayResX: 1080" in at and "PlayResY: 1920" in at
                  and f"Default,{DEFAULT_SUB_FONT},54," in at   # 1080*0.05=54，不再等效 106
                  and at.count("Dialogue:") == 2
                  and ",2,"  # Alignment=2 底部居中（样式行倒数第 4 组）
                  in at.split("Style: Default,")[1])
        print(f"[{'PASS' if ok_ass else 'FAIL'}] 字幕 ASS：PlayRes=视频尺寸/字号54/底部居中/2段")
        if not ok_ass:
            fail("ASS 样式不正确", 1)

        # 视频镜精确到 dur 且**保持画面运动**（不冻结）：源 1s
        vid = wd / "clip1s.mp4"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=1080x1920:d=1",
              "-c:v", "libx264", "-pix_fmt", "yuv420p", str(vid)])
        def _wsb(wd, vid, d):
            p = wd / f"sb_{d}.json"
            p.write_text(json.dumps({"size": "1080x1920",
                                     "shots": [{"video": str(vid), "duration": d}]}), encoding="utf-8")
            return p
        # a) 要求 1.8s → factor 1.8≤2 → 慢放拉伸填满
        out_s = wd / "stretch.mp4"
        cmd_assemble(argparse.Namespace(storyboard=str(_wsb(wd, vid, 1.8)), output=str(out_s)))
        ds = _probe_duration(str(out_s))
        # b) 要求 3s → factor 3>2 → 循环填满
        out_l = wd / "loop.mp4"
        cmd_assemble(argparse.Namespace(storyboard=str(_wsb(wd, vid, 3.0)), output=str(out_l), pad_mode="auto"))
        dl = _probe_duration(str(out_l))
        ok_pad = (1.6 <= ds <= 2.0) and (2.7 <= dl <= 3.3)
        print(f"[{'PASS' if ok_pad else 'FAIL'}] 视频保持运动填满：慢放 1s→{ds:.2f}s(目标1.8) / 循环 1s→{dl:.2f}s(目标3)")
        if not ok_pad:
            fail("视频未按 dur 精确填满", 1)

        # c) trim（自然）模式：够长→裁到 dur（1s 片段要 0.8s → 裁到 0.8s，自然，不填充）
        out_t = wd / "trim.mp4"
        cmd_assemble(argparse.Namespace(storyboard=str(_wsb(wd, vid, 0.8)), output=str(out_t), pad_mode="trim"))
        dt = _probe_duration(str(out_t))
        ok_trim = 0.6 <= dt <= 1.0
        print(f"[{'PASS' if ok_trim else 'FAIL'}] trim 够长裁到 dur：1s→{dt:.2f}s(目标0.8，不填充)")
        if not ok_trim:
            fail("trim 裁剪异常", 1)
        # d) trim 模式片段比 dur 短 → **硬失败**（绝不冻结/拉伸/循环）
        import subprocess as _sp
        r = _sp.run([sys.executable, __file__, "assemble",
                     "--storyboard", str(_wsb(wd, vid, 3.0)), "-o", str(wd / "x.mp4"),
                     "--pad-mode", "trim"], capture_output=True, text=True)
        ok_trim_fail = r.returncode != 0 and "禁止冻结" in (r.stderr + r.stdout)
        print(f"[{'PASS' if ok_trim_fail else 'FAIL'}] trim 片段不足→硬失败(不冻结)：rc={r.returncode}")
        if not ok_trim_fail:
            fail("trim 片段不足未硬失败", 1)

        # 字幕折行：长中文行按视频宽度确定性折成多行（不超边界、不挤成一行）
        long_units = max(6.0, (1080 - 2 * int(round(1080 * 0.06))) / 54 * 0.94)
        wrapped = wrap_caption("这是一句非常非常长的中文字幕需要按视频宽度自动折行绝不能超出画面边界挤成一行", long_units)
        ok_wrap = (len(wrapped) >= 2
                   and all(sum(_char_units(c) for c in ln) <= long_units + 0.5 for ln in wrapped)
                   and "".join(wrapped).replace(" ", "").startswith("这是一句非常"))
        print(f"[{'PASS' if ok_wrap else 'FAIL'}] 字幕按宽度折行：长行→{len(wrapped)}行，每行≤{long_units:.1f}单位、不超边界")
        if not ok_wrap:
            fail("字幕折行不正确", 1)
        # 96px（负责人定的字幕字号）：两行、在停顿处断、行首不是标点、不出现孤立的「？」
        units96 = max(6.0, (1080 - 2 * int(round(1080 * 0.06))) / 96 * 0.94)
        chk_q = wrap_caption("燕麦蛋白，到底早上喝，还是晚上喝？", units96)
        if chk_q != ["燕麦蛋白，到底早上喝，", "还是晚上喝？"]:
            fail(f"字幕折行未均衡/未避头：{chk_q}", 1)
        # 只在词与词之间断：keep_words 里的词不拆
        chk_kw = wrap_caption("每天早上喝一勺燕麦肽冷热水都能冲泡", units96, ["燕麦肽"])
        if not any("燕麦肽" in ln for ln in chk_kw):
            fail(f"keep_words 里的词被拆开了：{chk_kw}", 1)
        # 英文断行处不粘词（旧版会烧出 "ornight"）
        chk_en = wrap_caption("Oatmeal, morning or night? It works either way", units96)
        if len(chk_en) != 2 or " ".join(chk_en) != "Oatmeal, morning or night? It works either way":
            fail(f"英文断行粘词或行数不对：{chk_en}", 1)
        # 短行不折
        chk_short = wrap_caption("你好", long_units)
        if chk_short != ["你好"]:
            fail(f"短行被误折：{chk_short}", 1)

        # 定时音效轨：图片 4s + 一个在 2s 处的音效，应正常出片且时长≈4s（音效叠进音轨）
        sfx = wd / "ding.wav"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=0.4",
              str(sfx)])
        sbx = wd / "sbx.json"
        sbx.write_text(json.dumps({"size": "1080x1920",
            "shots": [{"image": imgs[0], "duration": 4.0, "caption": "音效测试"}],
            "sfx": [{"file": str(sfx), "at": 2.0, "volume": 0.8}]}), encoding="utf-8")
        out_x = wd / "sfx.mp4"
        cmd_assemble(argparse.Namespace(storyboard=str(sbx), output=str(out_x)))
        dx = _probe_duration(str(out_x))
        ok_sfx = out_x.is_file() and 3.6 <= dx <= 4.4
        print(f"[{'PASS' if ok_sfx else 'FAIL'}] 定时音效轨：图4s + 2s处音效 → 成片 {dx:.2f}s（音效已叠入音轨）")
        if not ok_sfx:
            fail("定时音效轨合成异常", 1)

        # 原生音频直通：有声视频标 native 后，最终文件必须仍有音轨（不再被 -an 删除）。
        native_src = wd / "native.mp4"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=yellow:s=320x568:d=1.2",
              "-f", "lavfi", "-i", "sine=frequency=660:duration=1.2",
              "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(native_src)])
        native_sb = wd / "native.json"
        native_sb.write_text(json.dumps({"size": "320x568", "pad_mode": "trim",
            "shots": [{"video": str(native_src), "duration": 1.0, "audio_mode": "native"}]}),
            encoding="utf-8")
        native_out = wd / "native-final.mp4"
        cmd_assemble(argparse.Namespace(storyboard=str(native_sb), output=str(native_out)))
        ok_native = _has_audio(str(native_out)) and 0.8 <= _probe_duration(str(native_out)) <= 1.2
        print(f"[{'PASS' if ok_native else 'FAIL'}] native 原生 AAC 经裁剪/拼接后仍保留")
        if not ok_native:
            fail("原生音频未正确保留", 1)
        native_mix_sb = wd / "native-mix.json"
        native_mix_sb.write_text(json.dumps({"size": "320x568", "pad_mode": "trim",
            "narration": str(voice),
            "shots": [{"video": str(native_src), "duration": 1.0, "audio_mode": "native"}]}),
            encoding="utf-8")
        native_mix_out = wd / "native-mix-final.mp4"
        cmd_assemble(argparse.Namespace(storyboard=str(native_mix_sb), output=str(native_mix_out)))
        if not (_has_audio(str(native_mix_out)) and 0.8 <= _probe_duration(str(native_mix_out)) <= 1.2):
            fail("原生音频与独立配音轨混音异常", 1)

        # dub 镜**不得**把视频模型原生人声并入成片（否则会与 TTS 配音**重复/回声**——真机踩过）。
        # 一个 dub 镜（源片自带人声）、无独立配音/BGM → 成片应**无音轨**（原生人声被丢弃，而非混进去）。
        # 旧的「dub 保留原生轨当环境音底」行为下此断言会失败——正是那次重复 bug 的回归防线。
        dub_sb = wd / "dub-drop-native.json"
        dub_sb.write_text(json.dumps({"size": "320x568", "pad_mode": "trim",
            "shots": [{"video": str(native_src), "duration": 1.0, "audio_mode": "dub"}]}),
            encoding="utf-8")
        dub_out = wd / "dub-drop-native.mp4"
        cmd_assemble(argparse.Namespace(storyboard=str(dub_sb), output=str(dub_out)))
        ok_dub = not _has_audio(str(dub_out))   # dub 镜原生人声未并入 → 该无声成片无音轨
        print(f"[{'PASS' if ok_dub else 'FAIL'}] dub 镜原生人声被丢弃（不与 TTS 配音重复）")
        if not ok_dub:
            fail("dub 镜原生人声未被丢弃（会与 TTS 配音重复！）", 1)

        # 背景音乐：配音说话处压低、说完恢复；音乐比视频短且没写 bgm_loop → 渲染前停下。
        from audio_mix import _band_db
        music = wd / "music.wav"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=8", str(music)])
        bgm_sb = wd / "bgm.json"
        bgm_sb.write_text(json.dumps({"size": "320x568", "narration": str(voice), "bgm": str(music),
            "shots": [{"image": imgs[0], "duration": 3}, {"image": imgs[1], "duration": 3}]}), encoding="utf-8")
        bgm_out = wd / "bgm.mp4"
        cmd_assemble(argparse.Namespace(storyboard=str(bgm_sb), output=str(bgm_out)))
        speaking, after = _band_db(bgm_out, 200, 0.5, 1.0), _band_db(bgm_out, 200, 4.6, 1.0)
        ok_duck = after - speaking >= 5
        print(f"[{'PASS' if ok_duck else 'FAIL'}] 配音说话处压低音乐：说话 {speaking:.1f} dB → 说完 {after:.1f} dB")
        if not ok_duck:
            fail("背景音乐没有被配音压低", 1)
        short_music = wd / "music-short.wav"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=2", str(short_music)])
        bgm_sb.write_text(json.dumps({"size": "320x568", "bgm": str(short_music),
            "shots": [{"image": imgs[0], "duration": 3}, {"image": imgs[1], "duration": 3}]}), encoding="utf-8")
        r = _sp.run([sys.executable, __file__, "assemble", "--storyboard", str(bgm_sb), "-o", str(wd / "y.mp4")],
                    capture_output=True, text=True)
        ok_short = r.returncode != 0 and "比视频短" in r.stderr and not (wd / "y.mp4").exists()
        print(f"[{'PASS' if ok_short else 'FAIL'}] 音乐比视频短且不循环 → 渲染前停下：rc={r.returncode}")
        if not ok_short:
            fail("音乐不够长时没有在渲染前停下", 1)

        print("[PASS] assemble 全部自检通过")
        return 0
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="短视频合成器（分镜素材→成片）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("assemble", help="按 storyboard 合成成片")
    p.add_argument("--storyboard", required=True, help="storyboard JSON 文件路径（- 表示 stdin）")
    p.add_argument("-o", "--output", required=True,
                   help="成片输出路径；必须位于 outputs/<人类可读主题>/")
    p.add_argument("--sub-font", dest="sub_font", default=None,
                   help=f"字幕字体（默认 {DEFAULT_SUB_FONT}）")
    p.add_argument("--sub-size", dest="sub_size", type=int, default=None,
                   help="字幕字号（优先于 storyboard.subtitle_size；都没给则按短边 ≈*0.05，1080→54）")
    p.add_argument("--sub-margin-v", dest="sub_margin_v", type=int, default=None,
                   help="字幕距底边距（默认按高度 ≈h*0.07）")
    p.add_argument("--pad-mode", dest="pad_mode", default=None,
                   choices=["trim", "auto", "stretch", "loop", "freeze"],
                   help="视频短于所需时长时填满方式：trim=自然(裁/仅冻结尾巴,不慢放不循环,短剧默认)、"
                        "auto=慢放/循环、stretch/loop/freeze=强制。默认读 storyboard.pad_mode，缺则 auto")
    p.set_defaults(func=cmd_assemble)
    p2 = sub.add_parser("selftest", help="自检（生成测试成片）")
    p2.set_defaults(func=cmd_selftest)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
