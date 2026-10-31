"""plan_page.py build: the photo-scene plan page, built from the set plan (issue 87).

Seam: the `build` and `covers` command lines of skills/builtin/xhs-reference-visual/scripts/plan_page.py, run on
example plans written for these tests. The plan layout under test is the one skills/builtin/xhs-reference-visual/
references/photo-scene-plan-page.md fixes (five headed tables, or the line 这套不用图标 in place of the icon list). The page is
read back with an HTML parser through the classes the script documents: each card is an element of class `card`
(data-card = the card), holding its plan cells (`v` spans with data-field) and a `figure.studied` holding the studied
set's image (`img.set-image`) and that set's row; each colour row is a `div.colour-row` with a `span.swatch`
(data-hex); each icon is a `div.icon-row`. Issue 88 adds the cover directions: each is an element of class `direction`
(data-direction = A, B or C) holding the table row's cells and a `figure.dir-set` with its studied set's image
(`img.dir-image`) and that set's row. The covers page (the `covers` command) is read back through `div.covers`, holding
one `article.cover` per direction with the drawn cover (`img.cover-image`), the label (`h3.cover-label`) and the
direction's row (`div.dir-row`). Issue 90 adds the set page (the `set` command): a `div.set` holding one `article.set-card`
per row of the 逐张计划 table in plan order (cover first), each with its label (`h3.set-label`), the drawn card
(`img.card-image`), the whole plan row (`div.plan-row`) and, for a card whose check file has 如实 lines, `span.not-passing`
and one `p.honest` per line.

Expected values are the literals written in the example plans below, never read back from the script.
"""

from __future__ import annotations

import base64
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "builtin" / "xhs-reference-visual" / "scripts" / "plan_page.py"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

SETS_HEAD = "| 图集 | 并排图 | 点赞 | 收藏 | 合计 | 借什么 |\n|---|---|---|---|---|---|\n"
CARDS_HEAD = ("| 卡 | 读者的问题 | 主体 | 场景和小事 | 道具 | 机位 | 短文案 | 包装角色 | 手和人物 | 借的图集 |\n"
              "|---|---|---|---|---|---|---|---|---|---|\n")
COLOURS_HEAD = "| 层级 | 颜色 | 覆盖的元素 |\n|---|---|---|\n"
ICONS_HEAD = "| 图标 | 意思 | 出现的卡 |\n|---|---|---|\n"

SETS_ROWS = (
    "| 套A（冷水化开） | oat-water-A.png | 3200 | 4100 | 7300 | 步骤卡的排法 & 小框 |\n"
    "| 套B（早餐台面） | oat-breakfast-B.png | 1500 | 2900 | 4400 | 封面构图 |\n"
    "| 套C（蓝杯特写） | oat-cup-C.png | 900 | 2100 | 3000 | 封面的特写 |\n"
    "| 套D（窗边下午茶） | oat-tea-D.png | 800 | 1700 | 2500 | 封面的光 |\n")
CARDS_ROWS = (
    "| 1 | 一份是多少？ | 打开的量勺 | 厨房台面，舀一勺 | 量勺、玻璃杯 | 俯拍 | 一勺就够 | 主角 | 手从右侧入画 | 套A（冷水化开） |\n"
    "| 2 | 冷水能化开吗？ | 玻璃杯 | 倒水，粉末在落 | 玻璃杯、勺子 | 平视 | 冷水也能化 <开> | 很小 | 无 | 套B（早餐台面） |\n")
COLOURS_ROWS = (
    "| 页头标题 | 暖橙 #F28C28 | 封面大标题、每张卡的页头 |\n"
    "| 对勾 | 青绿 #2FA58A | 每步完成的对勾 |\n")
DIRECTIONS_HEAD = ("| 方向 | 借的图集 | 角度 | 取景 | 领头 | 撞上的卡和改法 | 记忆点 | 和另外两个怎么不同 |\n"
                   "|---|---|---|---|---|---|---|---|\n")
AXES_LINE = "三个轴：角度、取景、领头"
DIRECTIONS_ROWS = (
    "| A | 套A（冷水化开） | 俯拍 | 近景 | 量勺里的粉 |  | 一勺粉倒进水里就化开，记住“不用搅” | 俯拍对平视和斜侧；近景对中景和特写；量勺里的粉领头，另两个是桌面和杯子 |\n"
    "| B | 套B（早餐台面） | 平视 | 中景 | 整个早餐台面 | 第 2 张：用了倒水的画面，选 B 则第 2 张改成勺子搅拌 | 满桌早餐里一杯清水，记住“早上顺手就能喝” | 平视对俯拍和斜侧；中景对近景和特写；整个早餐台面领头，另两个是粉和杯子 |\n"
    "| C | 套C（蓝杯特写） | 斜侧 45 度 | 特写 | 手里的杯子 |  | 一只握着的蓝杯，记住“随身带着喝” | 斜侧 45 度对俯拍和平视；特写对近景和中景；手里的杯子领头，另两个是粉和桌面 |\n"
    "| D | 套D（窗边下午茶） | 仰拍 | 远景 | 窗边的光 |  | 一扇窗和一只杯子，记住“下午也能喝” | 仰拍对俯拍、平视和斜侧；远景对近景、中景和特写；窗边的光领头，另三个是粉、桌面和杯子 |\n")
ICONS_ROWS = (
    "| 细线对勾，线条，线宽 2 | 这一步做完了 | 1、2 |\n"
    "| 水滴，填充 | 加水 | 2 |\n")


CANDIDATES_HEADING = "### 候选方向表（只留在计划文件里，不上计划页）"
CANDIDATES_TABLE = "| 候选 | 丢掉的理由 |\n|---|---|\n| 候选甲 | 太像别的套 |\n"


def plan_text(sets=SETS_ROWS, cards=CARDS_ROWS, colours=COLOURS_ROWS, icons: str | None = ICONS_ROWS,
              sets_head=SETS_HEAD, no_icons_line: str | None = None, directions: str | None = DIRECTIONS_ROWS,
              axes_line: str | None = AXES_LINE) -> str:
    """A made-up set plan with every fixed section of issue 123, in the fixed order."""
    axes = f"{axes_line}\n\n" if axes_line else ""
    directions_part = ("" if directions is None else
                       f"{axes}{DIRECTIONS_HEAD}{directions}\n{CANDIDATES_HEADING}\n{CANDIDATES_TABLE}")
    icons_part = (f"{ICONS_HEAD}{icons}" if icons is not None else (no_icons_line or ""))
    sections = [
        ("研究了哪一次", "测试：这篇帖子自己的主题，一次搜索。\n"),
        ("研究的图集", f"{sets_head}{sets}"),
        ("同一个家（厨房）", "一间亮亮的厨房。\n"),
        ("人物：同一个人，身份来源只有一张", "身份来源：`refs/identity.png`\n"),
        ("服装（早上）", "白 T 恤。\n"),
        ("人物真实感（手和脸）", "手上有指纹。\n"),
        ("逐张计划", f"{CARDS_HEAD}{cards}"),
        ("真实包装照片清单", "- `refs/pack.png`\n"),
        ("真实状态来源清单", "- `refs/state.png`\n"),
        ("封面方向", directions_part),
        ("字体体系（封面的字）", "字样：`refs/lettering.png`\n"),
        ("颜色和层级", "" if colours is None else f"{COLOURS_HEAD}{colours}"),
        ("图标清单", icons_part),
        ("上图逐字清单（全套）", "- 一勺就够\n"),
        ("已定的三件事（2026-10-29）", "- 一、二、三\n"),
        ("出图顺序（先封面）", "- 先封面，再按顺序\n"),
    ]
    if directions is None:
        sections = [x for x in sections if x[0] != "封面方向"]
    if colours is None:
        sections = [x for x in sections if x[0] != "颜色和层级"]
    if icons is None and not no_icons_line:
        sections = [x for x in sections if x[0] != "图标清单"]
    return "# 测试套系计划\n\n研究：测试用，不是真实帖子。\n\n" + "\n".join(f"## {n}\n{b}" for n, b in sections)


COMPANIONS = {
    "icon-list.md": "# 图标清单\n\n- 细线对勾：这一步做完了\n",
    "layout-plan-card_1-ABC.md": "# 封面版面计划\n\n- A 版：量勺在中间\n- B 版：台面在下半\n",
    "layout-plan-card_2.md": "# 卡 2 版面计划\n\n- 玻璃杯居中 <有尖括号>\n",
}


@pytest.fixture
def work(tmp_path):
    (tmp_path / "image-sets").mkdir()
    for name in ("oat-water-A.png", "oat-breakfast-B.png", "oat-cup-C.png", "oat-tea-D.png"):
        (tmp_path / "image-sets" / name).write_bytes(PNG)
    (tmp_path / "images").mkdir()
    for letter in "ABCD":
        (tmp_path / "images" / f"cover-{letter}.png").write_bytes(PNG)
    (tmp_path / "refs").mkdir()
    for name in ("identity", "pack", "state", "lettering"):
        (tmp_path / "refs" / f"{name}.png").write_bytes(PNG)
    for name, body in COMPANIONS.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def build(work: Path, text: str, *extra: str):
    plan = work / "set-plan.md"
    plan.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "build", "--plan", str(plan), *extra],
                          capture_output=True, text=True, timeout=120)


class Page(HTMLParser):
    def __init__(self, page: str):
        super().__init__()
        self.cards: list[dict] = []
        self.colours: list[dict] = []
        self.icons: list[dict] = []
        self.no_icons: list[str] = []
        self.directions: list[dict] = []
        self._scope = None  # (kind, dict)
        self._field = None
        self._capture = None
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if "card" in classes:
            self.cards.append({"card": a.get("data-card"), "plan": {}, "set": {}, "img": None, "set_name": None})
            self._scope = ("plan", self.cards[-1])
        elif "studied" in classes:
            self.cards[-1]["set_name"] = a.get("data-set")
            self._scope = ("set", self.cards[-1])
        elif "direction" in classes:
            self.directions.append({"direction": a.get("data-direction"), "row": {}, "set": {}, "img": None,
                                    "set_name": None})
            self._scope = ("row", self.directions[-1])
        elif "dir-set" in classes:
            self.directions[-1]["set_name"] = a.get("data-set")
            self._scope = ("set", self.directions[-1])
        elif "colour-row" in classes:
            self.colours.append({"cells": {}, "hex": None, "style": None})
            self._scope = ("colour", self.colours[-1])
        elif "icon-row" in classes:
            self.icons.append({"cells": {}})
            self._scope = ("icon", self.icons[-1])
        elif "no-icons" in classes:
            self._capture = ("no-icons", None)
            self.no_icons.append("")
        if tag == "img" and "set-image" in classes and self.cards:
            self.cards[-1]["img"] = a.get("src")
        if tag == "img" and "dir-image" in classes and self.directions:
            self.directions[-1]["img"] = a.get("src")
        if "swatch" in classes and self.colours:
            self.colours[-1]["hex"] = a.get("data-hex")
            self.colours[-1]["style"] = a.get("style")
        if "v" in classes and a.get("data-field") and self._scope:
            self._field = a["data-field"]
            self._capture = ("field", a["data-field"])
            self._buffer = ""

    def handle_endtag(self, tag):
        if tag == "figure" and self._scope and self._scope[0] == "set" and "direction" in self._scope[1]:
            self._scope = ("row", self._scope[1])
        elif tag == "figure" and self.cards:
            self._scope = ("plan", self.cards[-1])
        if self._capture and self._capture[0] == "field" and tag == "span":
            kind, holder = self._scope
            target = holder["cells"] if kind in ("colour", "icon") else holder[kind]
            target[self._capture[1]] = self._buffer
            self._capture = None
        if self._capture and self._capture[0] == "no-icons" and tag == "p":
            self._capture = None

    def handle_data(self, data):
        if self._capture and self._capture[0] == "field":
            self._buffer += data
        elif self._capture and self._capture[0] == "no-icons":
            self.no_icons[-1] += data


def ok(work: Path, text: str, *extra: str) -> Page:
    proc = build(work, text, *extra)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return Page((work / "计划页-审批稿.html").read_text(encoding="utf-8"))


# ---- the page copies the plan --------------------------------------------------------------------


def test_every_cell_of_every_card_row_is_on_the_page_exactly_as_written(work):
    page = ok(work, plan_text(), "--sets-folder", str(work / "image-sets"))
    assert [c["card"] for c in page.cards] == ["1", "2"]
    assert page.cards[0]["plan"] == {
        "卡": "1", "读者的问题": "一份是多少？", "主体": "打开的量勺", "场景和小事": "厨房台面，舀一勺",
        "道具": "量勺、玻璃杯", "机位": "俯拍", "短文案": "一勺就够", "包装角色": "主角",
        "手和人物": "手从右侧入画", "借的图集": "套A（冷水化开）"}
    assert page.cards[1]["plan"]["短文案"] == "冷水也能化 <开>"
    assert page.cards[1]["plan"]["读者的问题"] == "冷水能化开吗？"


def test_each_card_sits_beside_the_image_and_the_row_of_the_studied_set_its_row_names(work):
    page = ok(work, plan_text(), "--sets-folder", str(work / "image-sets"))
    first, second = page.cards
    assert first["set_name"] == "套A（冷水化开）"
    assert unquote(first["img"]).endswith("image-sets/oat-water-A.png")
    assert first["set"] == {"图集": "套A（冷水化开）", "点赞": "3200", "收藏": "4100", "合计": "7300",
                            "借什么": "步骤卡的排法 & 小框"}
    assert second["set_name"] == "套B（早餐台面）"
    assert unquote(second["img"]).endswith("image-sets/oat-breakfast-B.png")
    assert second["set"]["合计"] == "4400"


def test_each_colour_row_has_a_swatch_with_that_rows_hex_value_and_its_words(work):
    page = ok(work, plan_text(), "--sets-folder", str(work / "image-sets"))
    assert [c["hex"] for c in page.colours] == ["#F28C28", "#2FA58A"]
    assert "#F28C28" in page.colours[0]["style"] and "#2FA58A" in page.colours[1]["style"]
    assert page.colours[0]["cells"] == {"层级": "页头标题", "颜色": "暖橙 #F28C28", "覆盖的元素": "封面大标题、每张卡的页头"}
    assert page.colours[1]["cells"]["层级"] == "对勾"


def test_each_icon_appears_with_its_description_and_its_one_meaning(work):
    page = ok(work, plan_text(), "--sets-folder", str(work / "image-sets"))
    assert page.icons[0]["cells"] == {"图标": "细线对勾，线条，线宽 2", "意思": "这一步做完了", "出现的卡": "1、2"}
    assert page.icons[1]["cells"]["意思"] == "加水"


def test_a_plan_that_says_the_set_uses_no_icons_shows_that_line_instead_of_a_list(work):
    text = plan_text(icons=None, no_icons_line="这套不用图标")
    page = ok(work, text, "--sets-folder", str(work / "image-sets"))
    assert page.icons == []
    assert "这套不用图标" in "".join(page.no_icons)


def test_the_page_is_written_beside_the_plan_with_relative_image_paths(work):
    proc = build(work, plan_text(), "--sets-folder", str(work / "image-sets"))
    assert proc.returncode == 0, proc.stderr
    page_file = work / "计划页-审批稿.html"
    assert page_file.is_file()
    assert str(page_file) in proc.stdout
    page = Page(page_file.read_text(encoding="utf-8"))
    for card in page.cards:
        src = unquote(card["img"])
        assert not re.match(r"^(/|[A-Za-z]:|file:)", src), src
        assert (page_file.parent / src).resolve().is_file()


def test_the_sets_folder_defaults_to_image_sets_beside_the_plan_and_an_output_path_is_honoured(work):
    out = work / "elsewhere" / "page.html"
    proc = build(work, plan_text(), "-o", str(out))
    assert proc.returncode == 0, proc.stderr
    page = Page(out.read_text(encoding="utf-8"))
    assert (out.parent / unquote(page.cards[0]["img"])).resolve().is_file()


# ---- an unreadable plan stops the build, naming the section and the row --------------------------


def fails(work: Path, text: str, *needles: str):
    proc = build(work, text, "--sets-folder", str(work / "image-sets"))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    for needle in needles:
        assert needle in proc.stderr, (needle, proc.stderr)
    assert not (work / "计划页-审批稿.html").exists()


def test_a_card_naming_a_studied_set_that_is_not_in_the_table_stops_the_build(work):
    bad = CARDS_ROWS.replace("套B（早餐台面）", "套Z（没有这套）")
    fails(work, plan_text(cards=bad), "逐张计划", "卡 2", "套Z（没有这套）", "研究的图集")


def test_a_studied_set_image_that_is_not_on_disk_stops_the_build(work):
    (work / "image-sets" / "oat-breakfast-B.png").unlink()
    fails(work, plan_text(), "研究的图集", "套B（早餐台面）", "oat-breakfast-B.png")


def test_a_colour_row_without_a_valid_hex_value_stops_the_build(work):
    for bad_cell in ("暖橙", "暖橙 #F28C2", "暖橙 #GG8C28"):
        bad = COLOURS_ROWS.replace("暖橙 #F28C28", bad_cell)
        fails(work, plan_text(colours=bad), "颜色和层级", "页头标题")


def test_a_missing_colour_table_stops_the_build(work):
    fails(work, plan_text(colours=None), "颜色和层级")


def test_a_missing_icon_list_with_no_no_icons_line_stops_the_build(work):
    fails(work, plan_text(icons=None), "图标清单")


def test_a_wrong_header_stops_the_build_naming_the_section(work):
    fails(work, plan_text(sets_head=SETS_HEAD.replace("并排图", "图片")), "研究的图集", "表头")


def test_a_card_row_with_the_wrong_number_of_cells_stops_the_build_naming_the_row(work):
    bad = CARDS_ROWS.replace("| 俯拍 |", "|")
    fails(work, plan_text(cards=bad), "逐张计划", "卡 1")


def test_an_empty_borrowed_set_cell_stops_the_build(work):
    bad = CARDS_ROWS.replace("套B（早餐台面） |", " |")
    fails(work, plan_text(cards=bad), "逐张计划", "卡 2", "借的图集")


def test_a_side_by_side_image_cell_with_a_path_in_it_stops_the_build(work):
    bad = SETS_ROWS.replace("oat-breakfast-B.png", "../elsewhere/oat-breakfast-B.png")
    fails(work, plan_text(sets=bad), "研究的图集", "套B（早餐台面）", "文件名")


def test_two_studied_set_rows_with_the_same_name_stop_the_build(work):
    bad = SETS_ROWS.replace("套B（早餐台面）", "套A（冷水化开）")
    fails(work, plan_text(sets=bad), "研究的图集", "套A（冷水化开）", "同一个图集名")


# ---- issue 88: the three cover directions on the plan page ---------------------------------------


def test_each_cover_direction_is_on_the_plan_page_exactly_as_written_beside_its_studied_sets_image(work):
    page = ok(work, plan_text(), "--sets-folder", str(work / "image-sets"))
    assert [d["direction"] for d in page.directions] == ["A", "B", "C", "D"]
    assert page.directions[0]["row"] == {
        "方向": "A", "借的图集": "套A（冷水化开）", "角度": "俯拍", "取景": "近景", "领头": "量勺里的粉", "撞上的卡和改法": "",
        "记忆点": "一勺粉倒进水里就化开，记住“不用搅”",
        "和另外两个怎么不同": "俯拍对平视和斜侧；近景对中景和特写；量勺里的粉领头，另两个是桌面和杯子"}
    assert page.directions[1]["row"]["撞上的卡和改法"] == "第 2 张：用了倒水的画面，选 B 则第 2 张改成勺子搅拌"
    assert page.directions[2]["row"]["角度"] == "斜侧 45 度"
    assert [d["set_name"] for d in page.directions] == ["套A（冷水化开）", "套B（早餐台面）", "套C（蓝杯特写）", "套D（窗边下午茶）"]
    assert unquote(page.directions[3]["img"]).endswith("image-sets/oat-tea-D.png")
    assert unquote(page.directions[2]["img"]).endswith("image-sets/oat-cup-C.png")
    assert page.directions[2]["set"] == {"图集": "套C（蓝杯特写）", "点赞": "900", "收藏": "2100", "合计": "3000",
                                        "借什么": "封面的特写"}


def test_a_plan_without_the_cover_directions_table_stops_the_build(work):
    fails(work, plan_text(directions=None), "封面方向")


def test_a_direction_naming_a_set_that_is_not_in_the_studied_sets_table_stops_the_build_naming_the_row(work):
    bad = DIRECTIONS_ROWS.replace("套C（蓝杯特写）", "套Z（没有这套）")
    fails(work, plan_text(directions=bad), "封面方向", "方向 C", "套Z（没有这套）", "研究的图集")


def test_two_directions_naming_the_same_set_stop_the_build_naming_both_rows(work):
    bad = DIRECTIONS_ROWS.replace("套C（蓝杯特写）", "套B（早餐台面）")
    fails(work, plan_text(directions=bad), "封面方向", "方向 C", "套B（早餐台面）", "方向 B", "同一个图集")


@pytest.mark.parametrize("cell,old", [("角度", "平视"), ("取景", "中景"), ("领头", "整个早餐台面")])
def test_a_direction_with_an_empty_angle_framing_or_lead_stops_the_build_naming_the_row_and_the_cell(work, cell, old):
    bad = DIRECTIONS_ROWS.replace(f"| {old} |", "|  |")
    fails(work, plan_text(directions=bad), "封面方向", "方向 B", cell)


def test_directions_that_share_angle_framing_and_lead_together_are_not_four_directions_and_stop_the_build(work):
    bad = DIRECTIONS_ROWS.replace("| 斜侧 45 度 | 特写 | 手里的杯子 |", "| 俯拍 | 近景 | 量勺里的粉 |")
    fails(work, plan_text(directions=bad), "封面方向", "方向 C", "方向 A", "角度")


def test_fewer_than_four_studied_sets_stop_the_build_instead_of_reusing_or_inventing_a_direction(work):
    three_sets = "".join(SETS_ROWS.splitlines(keepends=True)[:3])
    three_directions = "".join(DIRECTIONS_ROWS.splitlines(keepends=True)[:3])
    fails(work, plan_text(sets=three_sets, directions=three_directions), "研究的图集", "不足四套")


def test_directions_must_be_exactly_a_b_c_and_d(work):
    fails(work, plan_text(directions=DIRECTIONS_ROWS.replace("| D |", "| E |")), "封面方向", "A、B、C、D")


# ---- issue 88: the covers page (the three drawn covers side by side) -----------------------------


class CoversPage(HTMLParser):
    """div.covers holds one article.cover per direction: h3.cover-label, img.cover-image, div.dir-row cells."""

    def __init__(self, page: str):
        super().__init__()
        self.covers: list[dict] = []
        self.has_covers_block = False
        self.container: list[str] = []
        self._in_label = False
        self._field = None
        self._buffer = ""
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if "covers" in classes:
            self.has_covers_block = True
            self.container = classes
        if "cover" in classes:
            self.covers.append({"direction": a.get("data-direction"), "label": "", "img": None, "row": {}})
        if "cover-label" in classes:
            self._in_label = True
        if tag == "img" and "cover-image" in classes and self.covers:
            self.covers[-1]["img"] = a.get("src")
        if "v" in classes and a.get("data-field") and self.covers:
            self._field, self._buffer = a["data-field"], ""

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_label = False
        if self._field and tag == "span":
            self.covers[-1]["row"][self._field] = self._buffer
            self._field = None

    def handle_data(self, data):
        if self._in_label:
            self.covers[-1]["label"] += data
        elif self._field:
            self._buffer += data


def covers(work: Path, text: str, *extra: str):
    plan = work / "set-plan.md"
    plan.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "covers", "--plan", str(plan), *extra],
                          capture_output=True, text=True, timeout=120)


def test_the_covers_page_shows_the_four_covers_labelled_a_b_c_d_each_with_its_row_as_written(work):
    proc = covers(work, plan_text())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    page_file = work / "封面对比页.html"
    assert str(page_file) in proc.stdout
    page = CoversPage(page_file.read_text(encoding="utf-8"))
    assert page.has_covers_block
    assert [c["direction"] for c in page.covers] == ["A", "B", "C", "D"]
    assert [c["label"].strip() for c in page.covers] == ["A", "B", "C", "D"]
    for cover, letter in zip(page.covers, "ABCD"):
        src = unquote(cover["img"])
        assert src.endswith(f"images/cover-{letter}.png")
        assert not re.match(r"^(/|[A-Za-z]:|file:)", src), src
        assert (page_file.parent / src).resolve().is_file()
    assert page.covers[1]["row"] == {
        "方向": "B", "借的图集": "套B（早餐台面）", "角度": "平视", "取景": "中景", "领头": "整个早餐台面",
        "撞上的卡和改法": "第 2 张：用了倒水的画面，选 B 则第 2 张改成勺子搅拌",
        "记忆点": "满桌早餐里一杯清水，记住“早上顺手就能喝”",
        "和另外两个怎么不同": "平视对俯拍和斜侧；中景对近景和特写；整个早餐台面领头，另两个是粉和杯子"}
    assert page.covers[0]["row"]["撞上的卡和改法"] == ""
    assert page.covers[2]["row"]["领头"] == "手里的杯子"
    assert page.covers[3]["row"]["领头"] == "窗边的光"


def test_the_covers_page_accepts_other_image_types_and_an_images_folder_and_an_output_path(work):
    (work / "drawn").mkdir()
    for letter, ext in zip("ABCD", ("jpg", "webp", "png", "jpeg")):
        (work / "drawn" / f"cover-{letter}.{ext}").write_bytes(PNG)
    out = work / "elsewhere" / "covers.html"
    proc = covers(work, plan_text(), "--images-folder", str(work / "drawn"), "-o", str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    page = CoversPage(out.read_text(encoding="utf-8"))
    assert [unquote(c["img"]).rsplit(".", 1)[1] for c in page.covers] == ["jpg", "webp", "png", "jpeg"]
    assert all((out.parent / unquote(c["img"])).resolve().is_file() for c in page.covers)


def test_a_missing_cover_image_stops_the_covers_page_naming_the_direction(work):
    (work / "images" / "cover-B.png").unlink()
    proc = covers(work, plan_text())
    assert proc.returncode == 2
    assert "方向 B" in proc.stderr and "cover-B" in proc.stderr
    assert not (work / "封面对比页.html").exists()


def test_a_bad_direction_row_stops_the_covers_page_naming_the_row(work):
    bad = DIRECTIONS_ROWS.replace("| 俯拍 | 近景 |", "| 俯拍 |  |")
    proc = covers(work, plan_text(directions=bad))
    assert proc.returncode == 2
    assert "封面方向" in proc.stderr and "方向 A" in proc.stderr and "取景" in proc.stderr
    assert not (work / "封面对比页.html").exists()


class SetPage(HTMLParser):
    """div.set holds one article.set-card per plan row: h3.set-label, img.card-image, div.plan-row cells, honest lines."""

    def __init__(self, page: str):
        super().__init__()
        self.cards: list[dict] = []
        self.has_set_block = False
        self.container: list[str] = []
        self._target = None
        self._field = None
        self._buffer = ""
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if "set" in classes:
            self.has_set_block = True
            self.container = classes
        if "set-card" in classes:
            self.cards.append({"card": a.get("data-card"), "label": "", "img": None, "row": {}, "not_passing": False,
                               "honest": []})
        if not self.cards:
            return
        if "set-label" in classes:
            self._target = "label"
        if tag == "img" and "card-image" in classes:
            self.cards[-1]["img"] = a.get("src")
        if "not-passing" in classes:
            self.cards[-1]["not_passing"] = True
        if "honest" in classes:
            self._target, self._buffer = "honest", ""
        if "v" in classes and a.get("data-field"):
            self._field, self._buffer = a["data-field"], ""

    def handle_endtag(self, tag):
        if tag == "h3" and self._target == "label":
            self._target = None
        if tag == "p" and self._target == "honest":
            self.cards[-1]["honest"].append(self._buffer)
            self._target = None
        if self._field and tag == "span":
            self.cards[-1]["row"][self._field] = self._buffer
            self._field = None

    def handle_data(self, data):
        if self._target == "label":
            self.cards[-1]["label"] += data
        elif self._target == "honest" or self._field:
            self._buffer += data


HONEST_LINES = ["包装约占画面 1/4（计划 ≤1/8）", "手从左侧入画（计划：右侧）"]


@pytest.fixture
def drawn(work):
    """Both cards drawn; card 2 has a check file with two 如实 lines, card 1 a check file with an empty 如实 section."""
    for card in ("1", "2"):
        (work / "images" / f"card-{card}.png").write_bytes(PNG)
    (work / "checks").mkdir()
    (work / "checks" / "card-2.md").write_text(
        "# 卡 2 检查\n\n## 通过\n- 手：五指\n\n## 如实\n" + "\n".join(f"- {x}" for x in HONEST_LINES) + "\n",
        encoding="utf-8")
    (work / "checks" / "card-1.md").write_text("# 卡 1 检查\n\n## 如实\n\n", encoding="utf-8")
    return work


def setpage(work: Path, text: str, *extra: str):
    plan = work / "set-plan.md"
    plan.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "set", "--plan", str(plan), *extra],
                          capture_output=True, text=True, timeout=120)


def test_the_set_page_shows_every_card_in_plan_order_cover_first_each_beside_its_row_as_written(drawn):
    proc = setpage(drawn, plan_text())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    page_file = drawn / "整套并排页.html"
    assert str(page_file) in proc.stdout
    page = SetPage(page_file.read_text(encoding="utf-8"))
    assert page.has_set_block
    assert [c["card"] for c in page.cards] == ["1", "2"]
    for card, name in zip(page.cards, ("card-1.png", "card-2.png")):
        src = unquote(card["img"])
        assert src == f"images/{name}"
        assert not re.match(r"^(/|[A-Za-z]:|file:)", src), src
        assert (page_file.parent / src).resolve().is_file()
    assert page.cards[0]["label"].strip() == "1"
    assert page.cards[1]["row"] == {
        "卡": "2", "读者的问题": "冷水能化开吗？", "主体": "玻璃杯", "场景和小事": "倒水，粉末在落",
        "道具": "玻璃杯、勺子", "机位": "平视", "短文案": "冷水也能化 <开>", "包装角色": "很小", "手和人物": "无",
        "借的图集": "套B（早餐台面）"}


def test_a_card_with_honest_report_lines_is_marked_not_passing_with_the_lines_as_written_and_a_clean_card_is_not(drawn):
    assert setpage(drawn, plan_text()).returncode == 0
    page = SetPage((drawn / "整套并排页.html").read_text(encoding="utf-8"))
    assert page.cards[1]["not_passing"] is True
    assert page.cards[1]["honest"] == HONEST_LINES
    assert page.cards[0]["not_passing"] is False and page.cards[0]["honest"] == []


def test_the_set_page_needs_no_check_files_and_honours_the_images_checks_and_output_options(work):
    (work / "drawn").mkdir()
    (work / "drawn" / "card-1.jpg").write_bytes(PNG)
    (work / "drawn" / "card-2.webp").write_bytes(PNG)
    out = work / "elsewhere" / "set.html"
    proc = setpage(work, plan_text(), "--images-folder", str(work / "drawn"), "--checks-folder", str(work / "none"),
                   "-o", str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    page = SetPage(out.read_text(encoding="utf-8"))
    assert [unquote(c["img"]).rsplit(".", 1)[1] for c in page.cards] == ["jpg", "webp"]
    assert all(not c["not_passing"] for c in page.cards)
    assert all((out.parent / unquote(c["img"])).resolve().is_file() for c in page.cards)


def test_a_card_in_the_plan_with_no_image_stops_the_set_page_naming_the_card(drawn):
    (drawn / "images" / "card-2.png").unlink()
    proc = setpage(drawn, plan_text())
    assert proc.returncode == 2
    assert "卡 2" in proc.stderr and "card-2" in proc.stderr
    assert not (drawn / "整套并排页.html").exists()


def test_two_images_for_one_card_stop_the_set_page_naming_the_card(drawn):
    (drawn / "images" / "card-1.jpg").write_bytes(PNG)
    proc = setpage(drawn, plan_text())
    assert proc.returncode == 2 and "卡 1" in proc.stderr
    assert not (drawn / "整套并排页.html").exists()


def test_a_missing_plan_table_stops_the_set_page(drawn):
    proc = setpage(drawn, "# 空计划\n\n没有表。\n")
    assert proc.returncode == 2 and "逐张计划" in proc.stderr
    assert not (drawn / "整套并排页.html").exists()


def test_a_missing_plan_file_exits_2(work):
    proc = subprocess.run([sys.executable, str(SCRIPT), "build", "--plan", str(work / "nope.md")],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2 and "plan not found" in proc.stderr


def test_the_video_storyboard_command_is_untouched():
    text = (ROOT / "skills" / "shared" / "scripts" / "storyboard_page.py").read_text(encoding="utf-8")
    assert 'COLUMNS = ["镜", "时间", "口播", "画面", "来源", "分镜图", "备注"]' in text
    assert "plan_page" not in text


def test_each_direction_memory_point_appears_on_the_plan_page_exactly_as_written(work):
    page = ok(work, plan_text(), "--sets-folder", str(work / "image-sets"))
    assert [d["row"]["记忆点"] for d in page.directions] == [
        "一勺粉倒进水里就化开，记住“不用搅”", "满桌早餐里一杯清水，记住“早上顺手就能喝”", "一只握着的蓝杯，记住“随身带着喝”",
        "一扇窗和一只杯子，记住“下午也能喝”"]


def test_a_direction_with_an_empty_memory_point_stops_the_build_naming_the_row(work):
    bad = DIRECTIONS_ROWS.replace("满桌早餐里一杯清水，记住“早上顺手就能喝”", "")
    fails(work, plan_text(directions=bad), "封面方向", "方向 B", "记忆点")


# ---- issue 99: declared axes, pairwise difference, mixed picks -----------------------------------

MIX_ROW = ("| A+C | 套A（冷水化开）、套C（蓝杯特写） | 俯拍 | 特写 | 手里的杯子 |  | 一只握着的杯子在俯拍里，记住“握杯就化开” "
           "| 角度取自 A，取景和领头取自 C |\n")
MIX_DIFFERS = "角度取自 A，取景和领头取自 C"


def test_the_axes_line_and_each_kept_directions_how_it_differs_line_are_on_the_plan_page_unchanged(work):
    proc = build(work, plan_text(), "--sets-folder", str(work / "image-sets"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html_text = (work / "计划页-审批稿.html").read_text(encoding="utf-8")
    assert re.search(r'<p class="axes">三个轴：角度、取景、领头</p>', html_text)
    page = Page(html_text)
    assert [d["row"]["和另外两个怎么不同"] for d in page.directions] == [
        "俯拍对平视和斜侧；近景对中景和特写；量勺里的粉领头，另两个是桌面和杯子",
        "平视对俯拍和斜侧；中景对近景和特写；整个早餐台面领头，另两个是粉和杯子",
        "斜侧 45 度对俯拍和平视；特写对近景和中景；手里的杯子领头，另两个是粉和桌面",
        "仰拍对俯拍、平视和斜侧；远景对近景、中景和特写；窗边的光领头，另三个是粉、桌面和杯子"]


def test_a_plan_without_the_axes_line_stops_the_build(work):
    fails(work, plan_text(axes_line=None), "封面方向", "三个轴：")


@pytest.mark.parametrize("axis,old,new", [("角度", "| 平视 |", "| 俯拍 |"), ("取景", "| 中景 |", "| 近景 |"),
                                          ("领头", "| 整个早餐台面 |", "| 量勺里的粉 |")])
def test_two_kept_directions_sharing_one_axis_value_stop_the_build_naming_both_rows_and_the_axis(work, axis, old, new):
    assert old in DIRECTIONS_ROWS
    fails(work, plan_text(directions=DIRECTIONS_ROWS.replace(old, new)), "封面方向", "方向 B", "方向 A", axis)


def test_an_empty_how_it_differs_line_stops_the_build_naming_the_row(work):
    bad = DIRECTIONS_ROWS.replace("平视对俯拍和斜侧；中景对近景和特写；整个早餐台面领头，另两个是粉和杯子", "")
    fails(work, plan_text(directions=bad), "封面方向", "方向 B", "和另外两个怎么不同")


def test_a_mixed_row_does_not_appear_on_the_plan_page_and_does_not_break_the_build(work):
    page = ok(work, plan_text(directions=DIRECTIONS_ROWS + MIX_ROW), "--sets-folder", str(work / "image-sets"))
    assert [d["direction"] for d in page.directions] == ["A", "B", "C", "D"]


def test_a_row_after_d_that_is_not_a_mix_of_the_letters_stops_the_build(work):
    fails(work, plan_text(directions=DIRECTIONS_ROWS + MIX_ROW.replace("A+C", "E")), "封面方向", "混合", "E")


def test_a_mixed_row_naming_a_set_that_is_not_studied_stops_the_build_naming_the_row(work):
    bad = MIX_ROW.replace("套C（蓝杯特写）", "套Z（没有这套）")
    fails(work, plan_text(directions=DIRECTIONS_ROWS + bad), "封面方向", "方向 A+C", "套Z（没有这套）")


@pytest.fixture
def mixed(work):
    (work / "images" / "cover-A+C.png").write_bytes(PNG)
    return work


def test_the_plain_covers_page_still_shows_a_b_c_d_only_when_the_plan_has_a_mixed_row(mixed):
    proc = covers(mixed, plan_text(directions=DIRECTIONS_ROWS + MIX_ROW))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    page = CoversPage((mixed / "封面对比页.html").read_text(encoding="utf-8"))
    assert [c["direction"] for c in page.covers] == ["A", "B", "C", "D"]


def test_covers_mix_shows_the_mixed_cover_alone_with_its_row_unchanged(mixed):
    proc = covers(mixed, plan_text(directions=DIRECTIONS_ROWS + MIX_ROW), "--mix", "A+C")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html_text = (mixed / "封面对比页.html").read_text(encoding="utf-8")
    assert '<p class="axes">三个轴：角度、取景、领头</p>' in html_text
    page = CoversPage(html_text)
    assert [c["direction"] for c in page.covers] == ["A+C"]
    assert page.covers[0]["label"].strip() == "A+C"
    assert unquote(page.covers[0]["img"]).endswith("images/cover-A+C.png")
    assert page.covers[0]["row"] == {
        "方向": "A+C", "借的图集": "套A（冷水化开）、套C（蓝杯特写）", "角度": "俯拍", "取景": "特写", "领头": "手里的杯子",
        "撞上的卡和改法": "", "记忆点": "一只握着的杯子在俯拍里，记住“握杯就化开”", "和另外两个怎么不同": MIX_DIFFERS}


@pytest.mark.parametrize("label", ["B", "D", "A+B", "A"])
def test_covers_mix_with_a_plain_letter_or_a_label_not_in_the_table_stops_with_exit_2(mixed, label):
    proc = covers(mixed, plan_text(directions=DIRECTIONS_ROWS + MIX_ROW), "--mix", label)
    assert proc.returncode == 2 and label in proc.stderr
    assert not (mixed / "封面对比页.html").exists()


def test_covers_mix_without_exactly_one_mixed_cover_image_stops_naming_the_label(mixed):
    (mixed / "images" / "cover-A+C.png").unlink()
    proc = covers(mixed, plan_text(directions=DIRECTIONS_ROWS + MIX_ROW), "--mix", "A+C")
    assert proc.returncode == 2 and "cover-A+C" in proc.stderr


# ---- issue 123: the page shows the whole plan and its companion files in the approved layout -----

FIXED_HEADINGS = [
    "研究了哪一次", "研究的图集", "同一个家（厨房）", "人物：同一个人，身份来源只有一张", "服装（早上）",
    "人物真实感（手和脸）", "逐张计划", "真实包装照片清单", "真实状态来源清单", "封面方向", "字体体系（封面的字）",
    "颜色和层级", "图标清单", "上图逐字清单（全套）", "已定的三件事（2026-10-29）", "出图顺序（先封面）"]
FILE_ORDER = ["set-plan.md", "icon-list.md", "layout-plan-card_1-ABC.md", "layout-plan-card_2.md"]


class Whole(HTMLParser):
    """section.file-box (data-file) holds items in page order: ("line", raw) from data-line or p.axes, ("picture", src)."""

    def __init__(self, page: str):
        super().__init__()
        self.boxes: list[dict] = []
        self.menu: list[tuple[str, str]] = []
        self.lead = ""
        self._lead = self._axes = self._link = False
        self._href = ""
        self._text = ""
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if "file-box" in classes:
            self.boxes.append({"file": a.get("data-file"), "id": a.get("id"), "items": []})
        elif "lead" in classes:
            self._lead = True
        elif tag == "a":
            self._link, self._href, self._text = True, a.get("href"), ""
        if "axes" in classes:
            self._axes, self._text = True, ""
        elif a.get("data-line") is not None and self.boxes:
            self.boxes[-1]["items"].append(("line", a["data-line"]))
        if tag == "img" and "named-picture" in classes and self.boxes:
            self.boxes[-1]["items"].append(("picture", unquote(a.get("src", ""))))

    def handle_endtag(self, tag):
        if self._axes and tag == "p":
            self.boxes[-1]["items"].append(("line", self._text))
            self._axes = False
        if self._link and tag == "a":
            self.menu.append((self._href, self._text))
            self._link = False
        if self._lead and tag == "p":
            self._lead = False

    def handle_data(self, data):
        if self._lead:
            self.lead += data
        if self._axes or self._link:
            self._text += data


def whole(work: Path, text: str | None = None) -> Whole:
    proc = build(work, text or plan_text(), "--sets-folder", str(work / "image-sets"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return Whole((work / "计划页-审批稿.html").read_text(encoding="utf-8"))


def lines_of(text: str, skip_candidate_rows: bool = False) -> list[str]:
    out, skipping = [], False
    for line in text.splitlines():
        if line.startswith("#"):
            skipping = skip_candidate_rows and "候选方向表" in line
        elif skipping or not line.strip():
            continue
        out.append(line.rstrip())
    return out


def lines_in(box: dict) -> list[str]:
    return [v for kind, v in box["items"] if kind == "line"]


def test_the_page_shows_the_plan_and_each_companion_file_in_the_fixed_order_every_line_unchanged(work):
    page = whole(work)
    assert [b["file"] for b in page.boxes] == FILE_ORDER
    assert lines_in(page.boxes[0]) == lines_of(plan_text(), skip_candidate_rows=True)
    for box in page.boxes[1:]:
        assert lines_in(box) == lines_of(COMPANIONS[box["file"]])


def test_a_lead_line_names_the_files_shown_and_a_menu_bar_links_each_section(work):
    page = whole(work)
    for name in FILE_ORDER:
        assert name in page.lead
    assert page.menu == [(f"#{b['id']}", b["file"]) for b in page.boxes]


def test_the_candidate_direction_table_stays_off_the_page_but_its_heading_line_is_shown(work):
    page = whole(work)
    shown = lines_in(page.boxes[0])
    assert CANDIDATES_HEADING in shown
    assert "| 候选甲 | 太像别的套 |" not in shown and "| 候选 | 丢掉的理由 |" not in shown


def test_a_picture_the_plan_names_comes_right_after_the_section_that_names_it(work):
    items = whole(work).boxes[0]["items"]
    for heading, picture in (("## 人物：同一个人，身份来源只有一张", "identity.png"), ("## 真实包装照片清单", "pack.png"),
                             ("## 真实状态来源清单", "state.png"), ("## 字体体系（封面的字）", "lettering.png")):
        at = items.index(("line", heading))
        pics = [i for i, (k, v) in enumerate(items) if k == "picture" and v.endswith("/" + picture)]
        assert len(pics) == 1, (picture, items)
        later = [i for i, (k, v) in enumerate(items) if k == "line" and v.startswith("## ") and i > at]
        assert at < pics[0] < min(later), picture


def test_the_plan_names_no_picture_the_page_shows_none_of_its_own_choosing(work):
    text = plan_text().replace("`refs/pack.png`", "一张真实包装照")
    items = whole(work, text).boxes[0]["items"]
    assert not any(v.endswith("pack.png") for k, v in items if k == "picture")


def stops(work: Path, text: str, *needles: str):
    proc = build(work, text, "--sets-folder", str(work / "image-sets"))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    for needle in needles:
        assert needle in proc.stderr, (needle, proc.stderr)
    assert not (work / "计划页-审批稿.html").exists()


def test_a_missing_section_stops_the_build_naming_the_file_and_the_section(work):
    text = plan_text().replace("## 字体体系（封面的字）\n字样：`refs/lettering.png`\n\n", "")
    stops(work, text, "set-plan.md", "字体体系", "缺")


def test_an_out_of_order_section_stops_the_build_naming_the_file_and_the_section(work):
    text = plan_text()
    a, b = "## 服装（早上）\n白 T 恤。\n\n", "## 同一个家（厨房）\n一间亮亮的厨房。\n\n"
    stops(work, text.replace(a + "## 人物", "## 人物").replace(b, b + a), "set-plan.md", "顺序")


def test_a_duplicated_section_stops_the_build_naming_the_file_and_the_section(work):
    stops(work, plan_text() + "\n## 出图顺序（再来一次）\n- 重复\n", "set-plan.md", "出图顺序", "重复")


def test_a_section_the_layout_does_not_have_stops_the_build_instead_of_being_added(work):
    stops(work, plan_text() + "\n## 变更记录\n- 测试用\n", "set-plan.md", "变更记录")


def test_a_heading_with_the_post_specific_part_missing_is_not_the_fixed_section(work):
    stops(work, plan_text().replace("## 同一个家（厨房）", "## 同一个家"), "set-plan.md", "同一个家")


@pytest.mark.parametrize("name", FILE_ORDER[1:])
def test_a_missing_companion_file_stops_the_build_naming_it(work, name):
    (work / name).unlink()
    stops(work, plan_text(), name)


def test_a_picture_the_plan_names_that_is_not_on_disk_stops_the_build_naming_file_and_section(work):
    (work / "refs" / "pack.png").unlink()
    stops(work, plan_text(), "set-plan.md", "真实包装照片清单", "refs/pack.png")


# ---- issue 125: the plan names the account's creation guide at the top -------------------------


def test_a_plan_naming_the_creation_guide_before_its_first_section_builds_and_the_page_shows_that_line(work):
    guide = "创作指南：profiles/acme-test/creation-guide.md（最后修改 2026-10-29）"
    text = plan_text().replace("研究：测试用", f"{guide}\n\n研究：测试用", 1)
    assert text.index(guide) < text.index("## 研究了哪一次")
    ok(work, text, "--sets-folder", str(work / "image-sets"))
    html = (work / "计划页-审批稿.html").read_text(encoding="utf-8")
    assert guide in html


# ---- issue 140: every pick is a two-by-two grid by default, one row on request (the set of five or more cards is always one row)


def more_cards(count: int) -> str:
    extra = "".join(CARDS_ROWS.splitlines(keepends=True)[1].replace("| 2 |", f"| {n} |", 1)
                    for n in range(3, count + 1))
    return CARDS_ROWS + extra


def draw(work: Path, count: int) -> None:
    for n in range(1, count + 1):
        (work / "images" / f"card-{n}.png").write_bytes(PNG)


def test_the_covers_page_is_a_two_by_two_grid_by_default_and_one_row_with_the_row_flag(work):
    assert covers(work, plan_text()).returncode == 0
    grid = CoversPage((work / "封面对比页.html").read_text(encoding="utf-8"))
    assert "grid" in grid.container and "row" not in grid.container
    assert covers(work, plan_text(), "--row").returncode == 0
    row = CoversPage((work / "封面对比页.html").read_text(encoding="utf-8"))
    assert "row" in row.container and "grid" not in row.container
    assert [c["direction"] for c in row.covers] == [c["direction"] for c in grid.covers] == ["A", "B", "C", "D"]


def test_a_card_set_of_four_or_fewer_is_a_grid_by_default_and_one_row_with_the_row_flag(work):
    draw(work, 4)
    assert setpage(work, plan_text(cards=more_cards(4))).returncode == 0
    grid = SetPage((work / "整套并排页.html").read_text(encoding="utf-8"))
    assert [c["card"] for c in grid.cards] == ["1", "2", "3", "4"]
    assert "grid" in grid.container and "row" not in grid.container
    assert setpage(work, plan_text(cards=more_cards(4)), "--row").returncode == 0
    row = SetPage((work / "整套并排页.html").read_text(encoding="utf-8"))
    assert "row" in row.container and "grid" not in row.container


@pytest.mark.parametrize("flags", [(), ("--row",)])
def test_a_finished_set_of_five_or_more_cards_is_always_one_row_and_the_flag_changes_nothing(work, flags):
    draw(work, 5)
    assert setpage(work, plan_text(cards=more_cards(5)), *flags).returncode == 0
    page = SetPage((work / "整套并排页.html").read_text(encoding="utf-8"))
    assert [c["card"] for c in page.cards] == ["1", "2", "3", "4", "5"]
    assert "row" in page.container and "grid" not in page.container
