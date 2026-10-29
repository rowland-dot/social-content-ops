#!/usr/bin/env python3
"""storyboard_page.py — the storyboard approval page, built from a video plan (issue 51).

The owner's rule (a brand's settings, 2026-10-15): every script and shot timeline goes to him as a web page, one row per
shot, the still or card on the left, the voice line, scene and timing on the right, text copied from the plan
unchanged. This builds that page from the plan's own shot table; it reads nothing else and rewords nothing.

The plan layout it reads is defined once, in skills/builtin/video-script/SKILL.md: a heading containing 分镜表
followed by a table with the columns 镜 | 时间 | 口播 | 画面 | 来源 | 分镜图 | 备注.

The page marks its parts with classes (the tests read them): each shot is an element of class `shot`
(data-shot = the shot number) holding the fields `no`, `time`, `voice`, `scene`, `source`, `note` and an image of
class `still`. The note, the voice line and the scene each sit in their own element, so a ruling note never
becomes part of the spoken line.

Usage:
    storyboard_page.py build --plan outputs/<brand>/<month>/<video>/plan.md
                             [--storyboard <folder of stills>] [--script-only] [-o <page.html>]

--script-only is for the first approval, when the script is ready and no still exists yet: the page shows the same
rows with the words 分镜图还没出 where the picture will go, and the 分镜图 column is not read. The owner approves the
topic, then the script, then a still for every shot, so the script stage needs this and the stills stage does not.

A short-drama episode is built the same way from its own shot list: `build --drama-episode episodes/epNN` reads
shots.json and lines.json (format: skills/builtin/short-drama/references/shot-prompt-format.md) and shows, word for
word, 镜 = idx, 时间 = span, 口播 = that shot's lines from lines.json as `speaker：text` in file order, 画面 = desc,
来源 = refs joined with 、, 分镜图 = the file name of frame (in `shots/` beside them, or --storyboard), 备注 = tail.
The generation prompt and the caption are not shown, and there is no ending switch. Same --script-only, same -o.

Defaults: the stills are in `storyboard/` beside the plan and the page is saved beside the plan, so the image
paths on the page are relative and the whole folder opens anywhere. Exit code 0 on success, 2 for bad input.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

COLUMNS = ["镜", "时间", "口播", "画面", "来源", "分镜图", "备注"]
DEFAULT_PAGE_NAME = "分镜脚本-审批稿.html"
DEFAULT_STILLS_FOLDER = "storyboard"


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def split_row(line: str) -> list[str]:
    """The cells of one markdown table row. `\\|` is a pipe inside a cell."""
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.replace("\\|", "|").strip() for c in cells[1:-1]]


def tables(text: str) -> list[tuple[str, list[str]]]:
    """Every table in the plan as (the heading above it, its lines)."""
    found, heading, current = [], "", None
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            if current is None:
                current = (heading, [])
                found.append(current)
            current[1].append(line)
            continue
        current = None
        match = re.match(r"^#{1,6}\s+(.*?)\s*$", line)
        if match:
            heading = match.group(1)
    return found


LAYOUT_HINT = f"（计划里要有标题含「分镜表」的一张表，列依次为 {' | '.join(COLUMNS)}；写法见 skills/builtin/video-script/SKILL.md）"


def check_still(where: str, still: str, stills: Path) -> None:
    if not still:
        _die(f"{where}：分镜图 一格是空的")
    if "/" in still or "\\" in still:
        _die(f"{where}：分镜图 一格只能写文件名，不能带路径：{still}")
    if not (stills / still).is_file():
        _die(f"{where}：分镜图「{still}」不在 {stills}（这一格只写文件名，别的说明放进 备注）")


def shots_of(heading: str, table_lines: list[str], stills: Path | None) -> list[dict[str, str]]:
    """The shots of one table, every row checked. Anything unreadable stops the build and names the row: the page
    is a copy of the plan, so a row the script has to guess at is a row it must not show. `stills` is None for the
    script stage (--script-only), when no still exists yet and the 分镜图 column is not read."""
    rows = [split_row(line) for line in table_lines]
    if rows[0] != COLUMNS:
        _die(f"「{heading}」的表头不对：应为 {' | '.join(COLUMNS)}，实际是 {' | '.join(rows[0])}。{LAYOUT_HINT}")
    if len(rows) < 3 or not all(re.fullmatch(r":?-{3,}:?", c) for c in rows[1]):
        _die(f"「{heading}」的表头下面没有分隔行，或没有任何一镜。{LAYOUT_HINT}")
    shots = []
    for row in rows[2:]:
        where = f"「{heading}」镜 {row[0] if row else '?'}"
        if len(row) != len(COLUMNS):
            _die(f"{where}：这一行有 {len(row)} 格，应有 {len(COLUMNS)} 格。{LAYOUT_HINT}")
        shot = dict(zip(COLUMNS, row))
        if stills is not None:
            check_still(where, shot["分镜图"], stills)
        shots.append(shot)
    return shots


def e(text: str) -> str:
    return html.escape(text, quote=True)


def article(shot: dict[str, str], page_folder: Path, stills: Path | None) -> str:
    if stills is None:
        picture = '<div class="no-still">分镜图还没出</div>'
    else:
        path = os.path.relpath(stills / shot["分镜图"], page_folder).replace(os.sep, "/")
        picture = f'<img class="still" src="{quote(path)}" alt="镜 {e(shot["镜"])}">'
    note = f'<p class="note-line"><span class="k">备注</span><span class="note">{e(shot["备注"])}</span></p>' \
        if shot["备注"] else ""
    return (
        f'<article class="shot" data-shot="{e(shot["镜"])}">'
        f'<div class="img">{picture}</div>'
        f'<div class="txt"><div class="hd"><span class="k">镜</span><span class="no">{e(shot["镜"])}</span>'
        f'<span class="time">{e(shot["时间"])}</span></div>'
        f'<p><span class="k">口播</span><span class="voice">{e(shot["口播"])}</span></p>'
        f'<p><span class="k">画面</span><span class="scene">{e(shot["画面"])}</span></p>'
        f'<p><span class="k">来源</span><span class="source">{e(shot["来源"])}</span></p>'
        f"{note}</div></article>"
    )


def ending_label(heading: str) -> str | None:
    """The name of an open ending from its heading `待定结尾：<name>`, or None when it is not one."""
    match = re.match(r"^待定结尾\s*[:：]\s*(.+)$", heading)
    return match.group(1).strip() if match else None


STYLE = """
body{margin:0;background:#FBF8F3;color:#25292B;font-family:"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 24px 64px}
h1{font-size:28px;margin:0 0 18px}
.switches{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px}
button.switch{font:inherit;font-size:16px;padding:8px 18px;border:2px solid #602271;border-radius:999px;background:#fff;color:#602271;cursor:pointer}
button.switch[aria-pressed=true]{background:#602271;color:#fff}
.shot{display:flex;gap:20px;padding:16px;background:#fff;border-bottom:1px solid #e6dfd3}
.shot .img{flex:0 0 230px}.shot .img img{width:216px;border-radius:6px;display:block;box-shadow:0 2px 8px rgba(0,0,0,.12)}
.shot .txt{flex:1;min-width:0}
.hd{display:flex;gap:14px;align-items:baseline;margin-bottom:8px}.no{background:#602271;color:#fff;border-radius:4px;padding:2px 10px;font-weight:600}
.time{color:#602271;font-weight:600}
p{margin:6px 0;font-size:16px;line-height:1.65}.k{display:inline-block;min-width:3.6em;color:#8a7f70;font-size:13px}
.voice{white-space:pre-line}
.note-line{background:#fff7d6;border-radius:4px;padding:2px 8px}
section.option{margin:0 0 8px}
@media(max-width:640px){.shot{flex-direction:column}.shot .img{flex:none}}
"""

SCRIPT = """
(function(){
  var buttons=[].slice.call(document.querySelectorAll('button.switch'));
  var options=[].slice.call(document.querySelectorAll('section.option'));
  function show(name){
    options.forEach(function(o){o.hidden=o.getAttribute('data-option')!==name;});
    buttons.forEach(function(b){b.setAttribute('aria-pressed',b.getAttribute('data-option')===name?'true':'false');});
  }
  buttons.forEach(function(b){b.addEventListener('click',function(){show(b.getAttribute('data-option'));});});
  if(buttons.length){show(buttons[0].getAttribute('data-option'));}
})();
"""


def read_json(path: Path):
    if not path.is_file():
        _die(f"找不到 {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        _die(f"{path} 不是有效的 JSON：{err}")


def drama_shots(episode: Path, stills: Path | None) -> list[dict[str, str]]:
    """The shots of a short-drama episode (skills/builtin/short-drama/references/shot-prompt-format.md), in the
    page's own columns. Nothing is reworded: the long generation prompt and the caption are not shown. Anything
    unreadable stops the build and names the shot, as the table reader does. `stills` is None at the script stage."""
    data = read_json(episode / "shots.json")
    lines = read_json(episode / "lines.json")
    shots, seen = [], set()
    for n, s in enumerate(data.get("shots") or [], 1):
        if "idx" not in s:
            _die(f"shots.json 第 {n} 个镜头没有 idx")
        where = f"镜 {s['idx']}"
        for key in ("span", "desc"):
            if not s.get(key):
                _die(f"{where}：shots.json 里没有 {key}")
        seen.add(s["idx"])
        shot = {"镜": str(s["idx"]), "时间": s["span"], "画面": s["desc"], "来源": "、".join(s.get("refs") or []),
                "分镜图": Path(s["frame"] or "").name, "备注": s.get("tail") or ""}
        if stills is not None:
            if not s.get("frame"):
                _die(f"{where}：shots.json 里的 frame 是空的，这一镜还没有首帧图")
            check_still(where, shot["分镜图"], stills)
        shots.append((s["idx"], shot))
    for l in lines:
        if "shot" not in l or "speaker" not in l or "text" not in l:
            _die(f"lines.json 里「{l.get('speaker', '?')}：{l.get('text', '?')}」缺 speaker、text 或 shot")
        if l["shot"] not in seen:
            _die(f"lines.json 里「{l['speaker']}：{l['text']}」的 shot {l['shot']} 在 shots.json 里没有这一镜")
    for idx, shot in shots:
        shot["口播"] = "\n".join(f"{l['speaker']}：{l['text']}" for l in lines if l["shot"] == idx)
    return [shot for _, shot in shots]


def build_page(plan: Path, stills: Path | None, page: Path) -> str:
    text = plan.read_text(encoding="utf-8")
    main_tables = [(h, lines) for h, lines in tables(text) if "分镜表" in h]
    if len(main_tables) != 1:
        _die(f"计划里应有且只有一张标题含「分镜表」的表，找到 {len(main_tables)} 张。{LAYOUT_HINT}")
    main = shots_of(*main_tables[0], stills)
    endings: list[tuple[str, list[dict[str, str]]]] = []
    for heading, lines in tables(text):
        if not heading.startswith("待定结尾"):
            continue
        label = ending_label(heading)
        if label is None:
            _die(f"标题「{heading}」没有写结尾的名字：写成「待定结尾：方案 A（名字）」。{LAYOUT_HINT}")
        if label in [name for name, _ in endings]:
            _die(f"两个待定结尾同名：「{label}」")
        endings.append((label, shots_of(heading, lines, stills)))
    rows = "\n".join(article(s, page.parent, stills) for s in main)
    switches = options = ""
    if endings:
        switches = '<nav class="switches">' + "".join(
            f'<button class="switch" type="button" data-option="{e(label)}">{e(label)}</button>'
            for label, _ in endings) + "</nav>"
        options = "\n".join(
            f'<section class="option" data-option="{e(label)}">\n'
            + "\n".join(article(s, page.parent, stills) for s in shots) + "\n</section>"
            for label, shots in endings)
    title = next((m.group(1) for m in re.finditer(r"^#\s+(.*?)\s*$", text, re.M)), plan.parent.name)
    return render(title, rows, switches, options)


def render(title: str, rows: str, switches: str, options: str) -> str:
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{e(title)}</title><style>{STYLE}</style></head><body><div class=\"wrap\"><h1>{e(title)}</h1>\n"
        f"{rows}\n{switches}\n{options}\n</div><script>{SCRIPT}</script></body></html>\n"
    )


def build_drama_page(episode: Path, stills: Path | None, page: Path) -> str:
    rows = "\n".join(article(s, page.parent, stills) for s in drama_shots(episode, stills))
    return render(episode.name, rows, "", "")


def cmd_build(a) -> int:
    if a.drama_episode:
        episode = Path(a.drama_episode)
        stills = None if a.script_only else Path(a.storyboard) if a.storyboard else episode / "shots"
        page = Path(a.output) if a.output else episode / DEFAULT_PAGE_NAME
        content = build_drama_page(episode, stills, page)
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(content, encoding="utf-8")
        print(f"OK: {page}")
        return 0
    if not a.plan:
        _die("build needs --plan <plan.md> or --drama-episode <episodes/epNN>")
    plan = Path(a.plan)
    if not plan.is_file():
        _die(f"plan not found: {plan}")
    stills = None if a.script_only else Path(a.storyboard) if a.storyboard else plan.parent / DEFAULT_STILLS_FOLDER
    page =Path(a.output) if a.output else plan.parent / DEFAULT_PAGE_NAME
    content = build_page(plan, stills, page)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    print(f"OK: {page}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the storyboard approval page from a video plan")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("build", help="build the page")
    p.add_argument("--plan", help="the video's plan.md")
    p.add_argument("--drama-episode", help="a short-drama episode folder (episodes/epNN) instead of a plan")
    p.add_argument("--storyboard", help="the folder of stills (default: storyboard/ beside the plan)")
    p.add_argument("--script-only", action="store_true",
                   help="the script stage, before any still is made: show the script, say the stills are not made")
    p.add_argument("-o", "--output", help="the page to write (default: beside the plan)")
    p.set_defaults(func=cmd_build)
    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
