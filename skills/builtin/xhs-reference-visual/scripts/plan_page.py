#!/usr/bin/env python3
"""plan_page.py — the photo-scene plan page, built from the set plan (issue 87).

The owner's rule (CLAUDE.md, photo-scene step 3): he sees the plan as a web page, built from Easel's plan with nothing
reworded: each card's plan next to the real set it borrows from, the colour swatches and the icons. This builds that
page from the set plan's own tables; it reads nothing else, rewords nothing, and adds only fixed headings and labels.

The plan layout it reads is fixed once, in references/photo-scene-plan-page.md: five headed tables (研究的图集,
封面方向, 逐张计划, 颜色和层级, 图标清单), or the line 这套不用图标 in place of the icon list. It follows the video
storyboard page command (skills/shared/scripts/storyboard_page.py), whose table reading it reuses and which it does not
change.

The page marks its parts with classes (the tests read them): each card is an element of class `card` (data-card = the
card) holding its plan cells (a span of class `v` with data-field) and a `figure.studied` with the studied set's image
(`img.set-image`) and that set's row; each colour row is a `div.colour-row` with a `span.swatch` (data-hex); each icon
is a `div.icon-row`; `p.no-icons` carries the line 这套不用图标. Issue 88 adds the cover directions (four since issue 140:
every pick offers four options): each is an `article.direction` (data-direction = A, B, C or D) holding the table row's
cells and a `figure.dir-set` with its studied set's image (`img.dir-image`) and that set's row. The covers page (the
`covers` command) is a `div.covers` holding one `article.cover` per direction: the drawn cover (`img.cover-image`), its
label (`h3.cover-label`) and the direction's row (`div.dir-row`), copied unchanged.
The set page (the `set` command, issue 90) shows the drawn set side by side for the user's one look: a `div.set` holding
one `article.set-card` per row of the 逐张计划 table in plan order (cover first), each with `h3.set-label`, the drawn card
(`img.card-image`), the whole plan row (`div.plan-row`) and, when the card's check file has 如实 lines, `span.not-passing`
and one `p.honest` per line, copied unchanged.
Layout (issue 140): the container of the covers page and of the set page carries a second class, `grid` (a two-by-two
田字格, the default, easy to read on a phone) or `row` (one row left to right, for the owner's PC, asked for with --row).
A set page of five cards or more is always `row`; --row changes nothing there.

Usage:
    plan_page.py build  --plan <set-plan.md> [--sets-folder <folder of studied-set images>] [-o <page.html>]
    plan_page.py covers --plan <set-plan.md> [--images-folder <folder of cover-A/B/C/D images>] [--mix <A+C>] [--row] [-o <page.html>]
    plan_page.py set    --plan <set-plan.md> [--images-folder <folder of card-<卡> images>] [--checks-folder <folder of card-<卡>.md>] [--row] [-o <page.html>]

Defaults: the studied-set images are in `image-sets/` beside the plan (pass the brand's own image-sets folder as
--sets-folder), and the page is saved beside the plan, so the image paths on the page are relative and the folder
opens on its own. The covers are `cover-A`, `cover-B`, `cover-C`, `cover-D` (png, jpg, jpeg or webp) in `images/` beside the plan.
Exit code 0 on success, 2 for bad input; nothing is written then.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))
from storyboard_page import _die, split_row, tables  # noqa: E402  (the video page's table reading, unchanged)

SECTIONS = {
    "研究的图集": ["图集", "并排图", "点赞", "收藏", "合计", "借什么"],
    "封面方向": ["方向", "借的图集", "角度", "取景", "领头", "撞上的卡和改法", "记忆点", "和另外两个怎么不同"],
    "逐张计划": ["卡", "读者的问题", "主体", "场景和小事", "道具", "机位", "短文案", "包装角色", "手和人物", "借的图集"],
    "颜色和层级": ["层级", "颜色", "覆盖的元素"],
    "图标清单": ["图标", "意思", "出现的卡"],
}
NO_ICONS = "这套不用图标"
DEFAULT_PAGE_NAME = "计划页-审批稿.html"
COVERS_PAGE_NAME = "封面对比页.html"
SET_PAGE_NAME = "整套并排页.html"
DEFAULT_CHECKS_FOLDER = "checks"
NOT_PASSING = "未通过检查"
DEFAULT_IMAGES_FOLDER = "images"
COVER_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
DIRECTION_LETTERS = ["A", "B", "C", "D"]  # every pick offers four options (issue 140)
LETTER_LIST = "、".join(DIRECTION_LETTERS)
AXES = ("角度", "取景", "领头")  # the owner's three axes, CLAUDE.md photo-scene step 4 (axes, not choices)
AXES_PREFIX = "三个轴："
MIX_LABEL = re.compile(r"[ABCD](\+[ABCD])+")
LONG_SET = 5  # a finished set of this many cards or more is always one row (issue 140)
MUST_FILL = ("借的图集", "角度", "取景", "领头", "记忆点", "和另外两个怎么不同")  # 撞上的卡和改法 may be empty: most directions collide with nothing
DEFAULT_SETS_FOLDER = "image-sets"
HEX = re.compile(r"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])")
LAYOUT_HINT = "（写法见 skills/builtin/xhs-reference-visual/references/photo-scene-plan-page.md）"


def rows_of(name: str, found: list[tuple[str, list[str]]]) -> list[dict[str, str]] | None:
    """The rows of the one table whose heading contains `name`, every row checked; None when there is none."""
    mine = [lines for heading, lines in found if name in heading]
    if not mine:
        return None
    if len(mine) > 1:
        _die(f"「{name}」应只有一张表，找到 {len(mine)} 张。{LAYOUT_HINT}")
    columns, rows = SECTIONS[name], [split_row(line) for line in mine[0]]
    if rows[0] != columns:
        _die(f"「{name}」表头不对：应为 {' | '.join(columns)}，实际是 {' | '.join(rows[0])}。{LAYOUT_HINT}")
    if len(rows) < 3 or not all(re.fullmatch(r":?-{3,}:?", c) for c in rows[1]):
        _die(f"「{name}」的表头下面没有分隔行，或没有任何一行。{LAYOUT_HINT}")
    out = []
    for row in rows[2:]:
        where = f"「{name}」{columns[0]} {row[0] if row else '?'}"
        if len(row) != len(columns):
            _die(f"{where}：这一行有 {len(row)} 格，应有 {len(columns)} 格。{LAYOUT_HINT}")
        out.append(dict(zip(columns, row)))
    return out


def check_directions(directions: list[dict[str, str]], sets: dict) -> None:
    """A, B, C and D first, each on a different studied set and differing from the others on every axis; any rows after
    them are mixed picks (issues 88, 99, 140)."""
    count = len(DIRECTION_LETTERS)
    if len(sets) < count:
        _die(f"「研究的图集」只有 {len(sets)} 套，不足四套：{LETTER_LIST} 四个封面要借四套不同的图集，不重用一套，也不凭空编方向。{LAYOUT_HINT}")
    kept, mixed = directions[:count], directions[count:]
    if [r["方向"] for r in kept] != DIRECTION_LETTERS:
        _die(f"「封面方向」的方向一格应依次为 {LETTER_LIST}，实际是 {'、'.join(r['方向'] for r in kept)}。{LAYOUT_HINT}")
    for row in mixed:
        if not MIX_LABEL.fullmatch(row["方向"]):
            _die(f"「封面方向」方向 {row['方向']}：{LETTER_LIST} 之后的行只能是混合选择，方向一格写 A+C 这样的字母组合。{LAYOUT_HINT}")
    for row in directions:
        where = f"「封面方向」方向 {row['方向']}"
        for column in MUST_FILL:
            if not row[column]:
                _die(f"{where}：{column} 一格是空的。{LAYOUT_HINT}")
        for name in row["借的图集"].split("、") if row in mixed else [row["借的图集"]]:
            if name not in sets:
                _die(f"{where}：借的图集不在「研究的图集」表里：「{name}」")
    for i, row in enumerate(kept):
        for other in kept[:i]:
            if row["借的图集"] == other["借的图集"]:
                _die(f"「封面方向」方向 {row['方向']}：和方向 {other['方向']} 借了同一个图集「{row['借的图集']}」，四个方向要借四套不同的图集")
            for axis in AXES:
                if row[axis] == other[axis]:
                    _die(f"「封面方向」方向 {row['方向']}：和方向 {other['方向']} 的{axis}一样（{row[axis]}），四个方向的角度、取景和领头要各自都不同")


def axes_line(text: str) -> str:
    """The plan's one line stating the declared axes, copied unchanged onto the pages (issue 99)."""
    for line in text.splitlines():
        if line.startswith(AXES_PREFIX):
            return line.strip()
    _die(f"「封面方向」缺一行「{AXES_PREFIX}角度、取景、领头」，写在方向表上面。{LAYOUT_HINT}")


def read_plan(text: str, sets_folder: Path) -> dict:
    found = tables(text)
    sections = {name: rows_of(name, found) for name in SECTIONS}
    for name in ("研究的图集", "封面方向", "逐张计划", "颜色和层级"):
        if sections[name] is None:
            _die(f"计划里缺一张表：标题含「{name}」的表，列依次为 {' | '.join(SECTIONS[name])}。{LAYOUT_HINT}")
    if sections["图标清单"] is None and NO_ICONS not in text:
        _die(f"计划里没有「图标清单」表，也没有「{NO_ICONS}」这句话。{LAYOUT_HINT}")
    sets = {}
    for row in sections["研究的图集"]:
        where = f"「研究的图集」图集 {row['图集']}"
        image = row["并排图"]
        if not image or "/" in image or "\\" in image:
            _die(f"{where}：并排图 一格只能写文件名，不能为空或带路径：{image}")
        if not (sets_folder / image).is_file():
            _die(f"{where}：并排图「{image}」不在磁盘上（找过 {sets_folder}）")
        if row["图集"] in sets:
            _die(f"{where}：两行用了同一个图集名")
        sets[row["图集"]] = row
    check_directions(sections["封面方向"], sets)
    axes_line(text)
    for row in sections["逐张计划"]:
        if row["借的图集"] not in sets:
            _die(f"「逐张计划」卡 {row['卡']}：借的图集不在「研究的图集」表里：「{row['借的图集']}」")
    for row in sections["颜色和层级"]:
        if len(HEX.findall(row["颜色"])) != 1:
            _die(f"「颜色和层级」层级 {row['层级']}：颜色一格没有有效的十六进制值（写成「颜色名 #RRGGBB」）：{row['颜色']}")
    return {**sections, "sets": sets}


def layout_class(row: bool) -> str:
    """The container's layout class: a two-by-two grid (田字格, phone-friendly) by default, one row left to right on request."""
    return "row" if row else "grid"


def e(text: str) -> str:
    return html.escape(text, quote=True)


def cells(row: dict[str, str], skip: tuple[str, ...] = ()) -> str:
    return "".join(
        f'<p class="cell"><span class="k">{e(k)}</span><span class="v" data-field="{e(k)}">{e(v)}</span></p>'
        for k, v in row.items() if k not in skip)


def card_article(row: dict[str, str], sets: dict, sets_folder: Path, page_folder: Path, raw: str = "") -> str:
    studied = sets[row["借的图集"]]
    path = os.path.relpath(sets_folder / studied["并排图"], page_folder).replace(os.sep, "/")
    return (
        f'<article class="card" data-card="{e(row["卡"])}" data-line="{e(raw)}">'
        f'<div class="plan"><h3>卡 {e(row["卡"])}</h3>{cells(row)}</div>'
        f'<figure class="studied" data-set="{e(studied["图集"])}">'
        f'<img class="set-image" src="{quote(path)}" alt="{e(studied["图集"])}">'
        f'<figcaption>{cells(studied, ("并排图",))}</figcaption></figure></article>')


def direction_article(row: dict[str, str], sets: dict, sets_folder: Path, page_folder: Path, raw: str = "") -> str:
    studied = sets[row["借的图集"]]
    path = os.path.relpath(sets_folder / studied["并排图"], page_folder).replace(os.sep, "/")
    return (
        f'<article class="direction" data-direction="{e(row["方向"])}" data-line="{e(raw)}">'
        f'<div class="plan"><h3>封面 {e(row["方向"])}</h3>{cells(row)}</div>'
        f'<figure class="dir-set" data-set="{e(studied["图集"])}">'
        f'<img class="dir-image" src="{quote(path)}" alt="{e(studied["图集"])}">'
        f'<figcaption>{cells(studied, ("并排图",))}</figcaption></figure></article>')


def colour_row(row: dict[str, str], raw: str = "") -> str:
    value = HEX.search(row["颜色"]).group(0)
    return (f'<div class="colour-row" data-line="{e(raw)}"><span class="swatch" data-hex="{e(value)}" style="background:{e(value)}"></span>'
            f'<div>{cells(row)}</div></div>')




STYLE = """
body{margin:0;background:#FBF8F3;color:#25292B;font-family:"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 24px 64px}
h1{font-size:28px;margin:0 0 18px}h2{font-size:22px;margin:32px 0 12px}h3{margin:0 0 8px}
.card{display:flex;gap:20px;padding:16px;background:#fff;border-bottom:1px solid #e6dfd3}
.card .plan{flex:1;min-width:0}.card .studied{flex:0 0 300px;margin:0}.card .studied img{width:100%;border-radius:6px;display:block}
p.cell{margin:6px 0;font-size:16px;line-height:1.65}.k{display:inline-block;min-width:5.6em;color:#8a7f70;font-size:13px}
.direction{display:flex;gap:20px;padding:16px;background:#fff;border-bottom:1px solid #e6dfd3}
.direction .plan{flex:1;min-width:0}.direction .dir-set{flex:0 0 300px;margin:0}.direction .dir-set img{width:100%;border-radius:6px;display:block}
.set{gap:12px;align-items:flex-start}.set.row{display:flex;overflow-x:auto}.set.row .set-card{flex:0 0 260px}.set.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.set-card{background:#fff;padding:12px;border-radius:8px}.set-card img{width:100%;border-radius:6px;display:block}.set-label{font-size:28px;margin:0 0 8px}.not-passing{display:inline-block;background:#b3261e;color:#fff;border-radius:4px;padding:2px 8px;margin-top:8px}.honest{color:#b3261e}
.covers{gap:16px;align-items:flex-start}.covers.row{display:flex}.covers.row .cover{flex:1}.covers.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.cover{min-width:0;background:#fff;padding:12px;border-radius:8px}
.cover img{width:100%;border-radius:6px;display:block}.cover-label{font-size:32px;margin:0 0 8px}
.colour-row{display:flex;gap:14px;align-items:flex-start;padding:10px 16px;background:#fff;border-bottom:1px solid #e6dfd3}
.swatch{flex:0 0 44px;height:44px;border-radius:8px;border:1px solid rgba(0,0,0,.2)}
.icon-row{padding:6px 16px;background:#fff;border-bottom:1px solid #e6dfd3}
.menu{position:sticky;top:0;display:flex;flex-wrap:wrap;gap:8px;padding:8px 0;background:#FBF8F3}.menu a{padding:4px 10px;background:#fff;border-radius:6px;border:1px solid #e6dfd3;color:#25292B;text-decoration:none;font-size:14px}
.lead{font-size:16px;line-height:1.65}.file-box{margin:24px 0;padding:8px 20px 16px;background:#fff;border:1px solid #e6dfd3;border-radius:10px}.file-label{font-size:16px;color:#8a7f70;margin:8px 0}
p.line,p.axes{margin:6px 0;font-size:16px;line-height:1.65;white-space:pre-wrap}h3.heading{margin:20px 0 6px}.named{margin:8px 0}.named img{max-width:100%;border-radius:6px;display:block}
@media(max-width:640px){.card,.direction{flex-direction:column}.card .studied,.direction .dir-set{flex:none}.covers.row{flex-direction:column}}
"""


FIXED_SECTIONS = [  # issue 123: the set plan's sections, in this order; （…） and … are the post's own content
    "研究了哪一次", "研究的图集", "同一个家（…）", "人物：同一个人，身份来源只有一张", "服装（…）", "人物真实感（…）",
    "逐张计划", "真实包装照片清单", "真实状态来源清单", "封面方向", "字体体系（…）", "颜色和层级", "图标清单",
    "上图逐字清单（…）", "已定的…件事（…）", "出图顺序（…）"]
PICTURE_SECTIONS = {3, 7, 8, 10}  # the sections whose backticked image files the page shows after them
PICTURE = re.compile(r"`([^`\n]+\.(?:png|jpe?g|webp))`", re.I)
SECTION_HEADING = re.compile(r"^##\s+(.*?)\s*$")
CANDIDATES = "候选方向表"  # the candidate cover table: its heading shows, its rows stay in the plan file
COMPANION_COVER, COMPANION_ICONS = "layout-plan-card_1-ABC.md", "icon-list.md"


def section_index(heading: str) -> int | None:
    for i, fixed in enumerate(FIXED_SECTIONS):
        pattern = re.escape(fixed).replace("…", ".+").replace("\\（", "（").replace("\\）", "）")
        if re.fullmatch(pattern, heading):
            return i
    return None


def check_sections(text: str, name: str) -> list[tuple[int, str]]:
    """The plan's `## ` sections as (fixed index, heading); stops on a missing, out-of-order, duplicated or unknown one."""
    found: list[tuple[int, str]] = []
    for line in text.splitlines():
        m = SECTION_HEADING.match(line)
        if not m:
            continue
        i = section_index(m.group(1))
        if i is None:
            _die(f"{name}「{m.group(1)}」：不是固定的段落，页上不加没有的段落。{LAYOUT_HINT}")
        if any(j == i for j, _ in found):
            _die(f"{name}「{m.group(1)}」：这一段重复了，应只有一段（固定的「{FIXED_SECTIONS[i]}」）。{LAYOUT_HINT}")
        if found and i < found[-1][0]:
            _die(f"{name}「{m.group(1)}」：段落顺序不对，应排在「{FIXED_SECTIONS[found[-1][0]]}」前面。{LAYOUT_HINT}")
        found.append((i, m.group(1)))
    for i, fixed in enumerate(FIXED_SECTIONS):
        if not any(j == i for j, _ in found):
            _die(f"{name}缺一段：「{fixed}」。{LAYOUT_HINT}")
    return found


def named_pictures(text: str, plan: Path, name: str) -> dict[int, list[Path]]:
    """The image files (in backticks) the plan names in the picture sections; stops when one is not on disk."""
    out: dict[int, list[Path]] = {}
    current = None
    for line in text.splitlines():
        m = SECTION_HEADING.match(line)
        if m:
            current = section_index(m.group(1))
        elif current in PICTURE_SECTIONS:
            for token in PICTURE.findall(line):
                if not (plan.parent / token).is_file():
                    _die(f"{name}「{FIXED_SECTIONS[current]}」：计划写了图 {token}，不在磁盘上（找过 {plan.parent}）")
                out.setdefault(current, []).append(plan.parent / token)
    return out


def line_html(line: str) -> str:
    raw = line.rstrip()
    if raw.startswith(AXES_PREFIX):
        return f'<p class="axes">{e(raw.strip())}</p>'
    m = re.match(r"^#+\s*(.*)$", raw)
    if m:
        return f'<h3 class="line heading" data-line="{e(raw)}">{e(m.group(1))}</h3>'
    return f'<p class="line" data-line="{e(raw)}">{e(raw)}</p>'


def picture_html(paths: list[Path], page_folder: Path) -> str:
    return "".join(
        f'<figure class="named"><img class="named-picture" src="{quote(os.path.relpath(p, page_folder).replace(os.sep, "/"))}"'
        f' alt="{e(p.name)}"></figure>' for p in paths)


def set_plan_box(text: str, structured: dict[str, str], pictures: dict[int, list[Path]], page_folder: Path) -> str:
    """Every line of the set plan, in order, unchanged: table rows with a structured form are that element (the raw row is
    in its data-line); the candidate cover table's rows are left in the plan file; pictures follow the section naming them."""
    out, current, skipping = [], None, False
    def close():
        if current in pictures:
            out.append(picture_html(pictures[current], page_folder))
    for line in text.splitlines():
        m = SECTION_HEADING.match(line)
        if m:
            close()
            current = section_index(m.group(1))
        if line.startswith("#"):
            skipping = CANDIDATES in line
        elif skipping or not line.strip():
            continue
        out.append(structured.get(line.rstrip()) or line_html(line))
    close()
    return "\n".join(out)


def file_box(i: int, name: str, body: str) -> str:
    return f'<section class="file-box" id="file-{i}" data-file="{e(name)}"><h2 class="file-label">{e(name)}</h2>\n{body}\n</section>'


def companion_files(plan: Path, cards: list[str]) -> list[Path]:
    names = [COMPANION_ICONS, COMPANION_COVER, *[f"layout-plan-card_{c}.md" for c in cards[1:]]]
    for n in names:
        if not (plan.parent / n).is_file():
            _die(f"{n}：计划页要显示的文件不在磁盘上（找过 {plan.parent}）。{LAYOUT_HINT}")
    return [plan.parent / n for n in names]


def raw_rows(found: list[tuple[str, list[str]]], name: str) -> list[str]:
    return next(lines[2:] for heading, lines in found if name in heading)


def build_page(plan: Path, sets_folder: Path, page: Path) -> str:
    text = plan.read_text(encoding="utf-8")
    check_sections(text, plan.name)
    pictures = named_pictures(text, plan, plan.name)
    data = read_plan(text, sets_folder)
    companions = companion_files(plan, [r["卡"] for r in data["逐张计划"]])
    title = next((m.group(1) for m in re.finditer(r"^#\s+(.*?)\s*$", text, re.M)), plan.parent.name)
    found = tables(text)
    structured: dict[str, str] = {}
    for row, raw in zip(data["封面方向"][:len(DIRECTION_LETTERS)], raw_rows(found, "封面方向")):
        structured[raw.rstrip()] = direction_article(row, data["sets"], sets_folder, page.parent, raw.rstrip())
    for row, raw in zip(data["逐张计划"], raw_rows(found, "逐张计划")):
        structured[raw.rstrip()] = card_article(row, data["sets"], sets_folder, page.parent, raw.rstrip())
    for row, raw in zip(data["颜色和层级"], raw_rows(found, "颜色和层级")):
        structured[raw.rstrip()] = colour_row(row, raw.rstrip())
    if data["图标清单"] is not None:
        for row, raw in zip(data["图标清单"], raw_rows(found, "图标清单")):
            structured[raw.rstrip()] = f'<div class="icon-row" data-line="{e(raw.rstrip())}">{cells(row)}</div>'
    else:
        line = next(l.rstrip() for l in text.splitlines() if NO_ICONS in l)
        structured[line] = f'<p class="no-icons" data-line="{e(line)}">{e(line)}</p>'
    boxes = [file_box(0, plan.name, set_plan_box(text, structured, pictures, page.parent))]
    for i, path in enumerate(companions, 1):
        body = "\n".join(line_html(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())
        boxes.append(file_box(i, path.name, body))
    names = [plan.name, *[p.name for p in companions]]
    menu = "".join(f'<a href="#file-{i}">{e(n)}</a>' for i, n in enumerate(names))
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><style>{STYLE}</style></head><body><div class="wrap"><h1>{e(title)}</h1>\n'
        f'<p class="lead">本页依次显示：{e("、".join(names))}</p>\n<nav class="menu">{menu}</nav>\n'
        + "\n".join(boxes) + '\n</div></body></html>\n')


def cover_file(images: Path, letter: str) -> Path:
    found = [images / f"cover-{letter}{ext}" for ext in COVER_SUFFIXES if (images / f"cover-{letter}{ext}").is_file()]
    if len(found) != 1:
        _die(f"方向 {letter}：封面图 cover-{letter}（{'、'.join(COVER_SUFFIXES)} 中的一种）应在 {images} 里有且只有一张，找到 {len(found)} 张")
    return found[0]


def build_covers_page(plan: Path, images: Path, page: Path, mix: str | None = None, one_row: bool = False) -> str:
    text = plan.read_text(encoding="utf-8")
    found = tables(text)
    sections = {name: rows_of(name, found) for name in ("研究的图集", "封面方向")}
    for name, rows in sections.items():
        if rows is None:
            _die(f"计划里缺一张表：标题含「{name}」的表，列依次为 {' | '.join(SECTIONS[name])}。{LAYOUT_HINT}")
    sets = {r["图集"]: r for r in sections["研究的图集"]}
    check_directions(sections["封面方向"], sets)
    title = next((m.group(1) for m in re.finditer(r"^#\s+(.*?)\s*$", text, re.M)), plan.parent.name)
    shown = sections["封面方向"][:len(DIRECTION_LETTERS)]
    if mix:
        shown = [r for r in sections["封面方向"][len(DIRECTION_LETTERS):] if r["方向"] == mix]
        if not shown:
            _die(f"--mix {mix}：「封面方向」表里没有这个混合选择的行（{LETTER_LIST} 本身不是混合选择）。{LAYOUT_HINT}")
    articles = []
    for row in shown:
        path = os.path.relpath(cover_file(images, row["方向"]), page.parent).replace(os.sep, "/")
        articles.append(
            f'<article class="cover" data-direction="{e(row["方向"])}"><h3 class="cover-label">{e(row["方向"])}</h3>'
            f'<img class="cover-image" src="{quote(path)}" alt="{e(row["方向"])}"><div class="dir-row">{cells(row)}</div></article>')
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><style>{STYLE}</style></head><body><div class="wrap"><h1>{e(title)}</h1>\n'
        f'<h2>封面方向</h2>\n<p class="axes">{e(axes_line(text))}</p>\n<div class="covers {layout_class(one_row)}">\n' + "\n".join(articles) + '\n</div>\n</div></body></html>\n')


def honest_lines(check: Path) -> list[str]:
    """The non-empty lines under `## 如实` in a card's check file; none when there is no file or no such section."""
    if not check.is_file():
        return []
    out, inside = [], False
    for line in check.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            inside = line.lstrip("#").strip() == "如实"
        elif inside and line.strip():
            out.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
    return out


def card_image(images: Path, card: str) -> Path:
    found = [images / f"card-{card}{ext}" for ext in COVER_SUFFIXES if (images / f"card-{card}{ext}").is_file()]
    if len(found) != 1:
        _die(f"卡 {card}：卡图 card-{card}（{'、'.join(COVER_SUFFIXES)} 中的一种）应在 {images} 里有且只有一张，找到 {len(found)} 张")
    return found[0]


def build_set_page(plan: Path, images: Path, checks: Path, page: Path, one_row: bool = False) -> str:
    text = plan.read_text(encoding="utf-8")
    rows = rows_of("逐张计划", tables(text))
    if rows is None:
        _die(f"计划里缺一张表：标题含「逐张计划」的表，列依次为 {' | '.join(SECTIONS['逐张计划'])}。{LAYOUT_HINT}")
    title = next((m.group(1) for m in re.finditer(r"^#\s+(.*?)\s*$", text, re.M)), plan.parent.name)
    articles = []
    for row in rows:
        card = row["卡"]
        path = os.path.relpath(card_image(images, card), page.parent).replace(os.sep, "/")
        honest = honest_lines(checks / f"card-{card}.md")
        flag = "".join([f'<span class="not-passing">{NOT_PASSING}</span>'] + [f'<p class="honest">{e(x)}</p>' for x in honest]) if honest else ""
        articles.append(
            f'<article class="set-card" data-card="{e(card)}"><h3 class="set-label">{e(card)}</h3>'
            f'<img class="card-image" src="{quote(path)}" alt="{e(card)}"><div class="plan-row">{cells(row)}</div>{flag}</article>')
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><style>{STYLE}</style></head><body><div class="wrap"><h1>{e(title)}</h1>\n'
        f'<h2>整套并排</h2>\n<div class="set {layout_class(one_row or len(rows) >= LONG_SET)}">\n' + "\n".join(articles) + '\n</div>\n</div></body></html>\n')


def cmd_set(a) -> int:
    plan = Path(a.plan)
    if not plan.is_file():
        _die(f"plan not found: {plan}")
    images = Path(a.images_folder) if a.images_folder else plan.parent / DEFAULT_IMAGES_FOLDER
    checks = Path(a.checks_folder) if a.checks_folder else plan.parent / DEFAULT_CHECKS_FOLDER
    page = Path(a.output) if a.output else plan.parent / SET_PAGE_NAME
    content = build_set_page(plan, images, checks, page, a.row)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    print(f"OK: {page}")
    return 0


def cmd_covers(a) -> int:
    plan = Path(a.plan)
    if not plan.is_file():
        _die(f"plan not found: {plan}")
    images = Path(a.images_folder) if a.images_folder else plan.parent / DEFAULT_IMAGES_FOLDER
    page = Path(a.output) if a.output else plan.parent / COVERS_PAGE_NAME
    content = build_covers_page(plan, images, page, a.mix, a.row)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    print(f"OK: {page}")
    return 0


def cmd_build(a) -> int:
    plan = Path(a.plan)
    if not plan.is_file():
        _die(f"plan not found: {plan}")
    sets_folder = Path(a.sets_folder) if a.sets_folder else plan.parent / DEFAULT_SETS_FOLDER
    page = Path(a.output) if a.output else plan.parent / DEFAULT_PAGE_NAME
    content = build_page(plan, sets_folder, page)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    print(f"OK: {page}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the photo-scene plan page from the set plan")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("build", help="build the page")
    p.add_argument("--plan", required=True, help="the post's set-plan.md")
    p.add_argument("--sets-folder", help="the folder of studied-set images (default: image-sets/ beside the plan)")
    p.add_argument("-o", "--output", help="the page to write (default: beside the plan)")
    p.set_defaults(func=cmd_build)
    c = sub.add_parser("covers", help="build the page that shows the four drawn covers (a two-by-two grid by default)")
    c.add_argument("--plan", required=True, help="the post's set-plan.md")
    c.add_argument("--images-folder", help="the folder of cover-A/B/C/D images (default: images/ beside the plan)")
    c.add_argument("--row", action="store_true", help="lay the covers out in one row, left to right (for the owner's PC)")
    c.add_argument("-o", "--output", help="the page to write (default: beside the plan)")
    c.add_argument("--mix", help="show only the mixed cover of this row of the directions table (for example A+C)")
    c.set_defaults(func=cmd_covers)
    t = sub.add_parser("set", help="build the page that shows the whole drawn set (a grid for four cards or fewer, one row for five or more)")
    t.add_argument("--plan", required=True, help="the post's set-plan.md")
    t.add_argument("--row", action="store_true", help="lay four cards or fewer out in one row (a set of five or more is always one row)")
    t.add_argument("--images-folder", help="the folder of card-<卡> images (default: images/ beside the plan)")
    t.add_argument("--checks-folder", help="the folder of card-<卡>.md check files (default: checks/ beside the plan)")
    t.add_argument("-o", "--output", help="the page to write (default: beside the plan)")
    t.set_defaults(func=cmd_set)
    a = ap.parse_args()
    if not getattr(a, "func", None):
        ap.print_help()
        return 2
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
