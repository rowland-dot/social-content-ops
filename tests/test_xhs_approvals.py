"""approvals.py: the photo-scene approval record, one per post (issue 111).

Seam: the `record` and `check` command lines of skills/builtin/xhs-reference-visual/scripts/approvals.py, run on a small
example plan and example images written for these tests. The record is `approvals.json` beside the plan; its fields and
the dependency list are in skills/builtin/xhs-reference-visual/references/photo-scene-approvals.md. Expected values are
the literals written below, never read back from the script.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "builtin" / "xhs-reference-visual" / "scripts" / "approvals.py"

CARDS = ("| 卡 | 读者的问题 | 主体 | 场景和小事 | 道具 | 机位 | 短文案 | 包装角色 | 手和人物 | 借的图集 |\n"
         "|---|---|---|---|---|---|---|---|---|---|\n"
         "| 1 | 一份是多少？ | 量勺 | 厨房台面 | 量勺 | 俯拍 | 一勺就够 | 主角 | 无 | 套A |\n"
         "| 2 | 冷水能化开吗？ | 玻璃杯 | 倒水 | 杯子 | 平视 | 冷水也能化 | 很小 | 无 | 套B |\n"
         "| 3 | 怎么喝？ | 杯子 | 餐桌 | 杯子 | 平视 | 早上喝 | 很小 | 无 | 套B |\n")
COLOURS = "| 层级 | 颜色 | 覆盖的元素 |\n|---|---|---|\n| 页头标题 | 暖橙 #F28C28 | 封面大标题 |\n"
ICONS = "| 图标 | 意思 | 出现的卡 |\n|---|---|---|\n| 细线对勾 | 做完了 | 1、2 |\n"


def plan_text(cards=CARDS, colours=COLOURS, icons=ICONS) -> str:
    return (f"# 测试套系计划\n\n## 逐张计划\n{cards}\n## 颜色和层级\n{colours}\n## 图标清单\n{icons}\n"
            "## 变更记录\n- 测试用\n")


@pytest.fixture
def work(tmp_path):
    (tmp_path / "images").mkdir()
    for name in ("cover-C.png", "card-2.png", "card-3.png"):
        (tmp_path / "images" / name).write_bytes(name.encode())
    (tmp_path / "set-plan.md").write_text(plan_text(), encoding="utf-8")
    return tmp_path


def run(work: Path, *args: str):
    return subprocess.run([sys.executable, str(SCRIPT), args[0], "--plan", str(work / "set-plan.md"), *args[1:]],
                          capture_output=True, text=True, timeout=60)


def record(work: Path, card: str, kind: str, image: str, *extra: str):
    return run(work, "record", "--card", card, "--kind", kind, "--file", f"images/{image}", "--date", "2026-10-28",
               "--words", "批准", *extra)


def approve_all(work: Path):
    assert record(work, "1", "cover-pick", "cover-C.png").returncode == 0
    assert record(work, "2", "set-page", "card-2.png").returncode == 0
    assert record(work, "3", "set-page", "card-3.png").returncode == 0


def entries(work: Path) -> list[dict]:
    return json.loads((work / "approvals.json").read_text(encoding="utf-8"))["entries"]


def voided(work: Path) -> dict[str, str]:
    return {e["card"]: e["voided"]["dependency"] for e in entries(work) if not e["valid"]}


def edit_plan(work: Path, old: str, new: str):
    plan = work / "set-plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_record_then_check_passes(work):
    approve_all(work)
    assert [e["card"] for e in entries(work)] == ["1", "2", "3"]
    assert entries(work)[0]["words"] == "批准" and entries(work)[0]["date"] == "2026-10-28"
    assert run(work, "check", "--today", "2026-10-29").returncode == 0


def test_changing_the_colour_table_voids_every_card_and_names_it(work):
    approve_all(work)
    edit_plan(work, "暖橙 #F28C28", "青绿 #2FA58A")
    proc = run(work, "check", "--today", "2026-10-29")
    assert proc.returncode == 1
    assert voided(work) == {"1": "table:颜色和层级", "2": "table:颜色和层级", "3": "table:颜色和层级"}
    assert entries(work)[0]["voided"]["found_on"] == "2026-10-29"
    assert "table:颜色和层级" in proc.stdout


def test_changing_the_picked_cover_voids_every_other_card_not_the_cover(work):
    approve_all(work)
    (work / "images" / "cover-C.png").write_bytes(b"redrawn cover")
    assert run(work, "check", "--today", "2026-10-29").returncode == 1
    assert voided(work) == {"2": "file:images/cover-C.png", "3": "file:images/cover-C.png"}


def test_changing_one_cards_row_voids_only_that_card(work):
    approve_all(work)
    edit_plan(work, "冷水也能化", "冷水也能化开")
    assert run(work, "check", "--today", "2026-10-29").returncode == 1
    assert voided(work) == {"2": "row:2"}


def test_recording_a_second_approval_voids_nothing(work):
    assert record(work, "1", "cover-pick", "cover-C.png").returncode == 0
    assert record(work, "2", "set-page", "card-2.png").returncode == 0
    assert run(work, "check").returncode == 0
    assert record(work, "3", "set-page", "card-3.png").returncode == 0
    assert run(work, "check").returncode == 0
    assert voided(work) == {}


def test_a_voided_entry_stays_with_its_last_approved_file_and_is_not_revalidated(work):
    approve_all(work)
    edit_plan(work, "冷水也能化", "冷水也能化开")
    run(work, "check", "--today", "2026-10-29")
    edit_plan(work, "冷水也能化开", "冷水也能化")  # change undone: re-approval is a new entry, not a revived one
    assert run(work, "check").returncode == 1
    two = [e for e in entries(work) if e["card"] == "2"]
    assert len(two) == 1 and two[0]["file"] == "images/card-2.png" and two[0]["valid"] is False
    assert record(work, "2", "card-change", "card-2.png").returncode == 0
    assert [e["valid"] for e in entries(work) if e["card"] == "2"] == [False, True]


def test_a_typed_styling_file_and_a_prompt_images_list_are_dependencies(work):
    (work / "typed-styling.json").write_text('{"font_file": "a.ttf"}', encoding="utf-8")
    (work / "images" / "product.png").write_bytes(b"pack")
    (work / "prompt-2.txt").write_text("画一杯水\nimage: images/product.png\n", encoding="utf-8")
    approve_all(work)
    assert record(work, "2", "card-change", "card-2.png", "--prompt-file", "prompt-2.txt").returncode == 0
    (work / "images" / "product.png").write_bytes(b"other pack photo")
    assert run(work, "check").returncode == 1
    assert voided(work) == {"2": "file:images/product.png"}
    (work / "typed-styling.json").write_text('{"font_file": "b.ttf"}', encoding="utf-8")
    run(work, "check")
    assert set(voided(work)) == {"1", "2", "3"}


def test_check_with_no_record_file_exits_2_and_names_it(work):
    proc = run(work, "check")
    assert proc.returncode == 2 and "approvals.json" in proc.stderr
    assert not (work / "approvals.json").exists()


def test_an_entry_naming_a_card_not_in_the_plan_exits_2(work):
    proc = record(work, "9", "set-page", "card-2.png")
    assert proc.returncode == 2 and "9" in proc.stderr
    assert not (work / "approvals.json").exists()
    approve_all(work)
    edit_plan(work, "| 3 | 怎么喝？", "| 4 | 怎么喝？")
    proc = run(work, "check")
    assert proc.returncode == 2 and "3" in proc.stderr


def test_an_approved_image_not_on_disk_exits_2(work):
    proc = record(work, "2", "set-page", "missing.png")
    assert proc.returncode == 2 and "missing.png" in proc.stderr
    assert not (work / "approvals.json").exists()
    approve_all(work)
    (work / "images" / "card-3.png").unlink()
    proc = run(work, "check")
    assert proc.returncode == 2 and "card-3.png" in proc.stderr


# ---- issue 123: a plan-page approval depends on every file the page shows --------------------------


def plan_page_files(work: Path):
    for name in ("icon-list.md", "layout-plan-card_1-ABC.md", "layout-plan-card_2.md", "layout-plan-card_3.md"):
        (work / name).write_text(f"{name} 的计划\n", encoding="utf-8")
    assert record(work, "set", "plan-page", "card-2.png").returncode == 0


def test_changing_a_layout_plan_file_voids_a_plan_page_approval_and_names_the_file(work):
    plan_page_files(work)
    assert run(work, "check").returncode == 0
    (work / "layout-plan-card_2.md").write_text("改过的版面计划\n", encoding="utf-8")
    assert run(work, "check", "--today", "2026-10-29").returncode == 1
    assert voided(work) == {"set": "file:layout-plan-card_2.md"}


@pytest.mark.parametrize("name", ["icon-list.md", "layout-plan-card_1-ABC.md", "layout-plan-card_3.md"])
def test_changing_any_other_file_the_plan_page_shows_voids_the_plan_page_approval(work, name):
    plan_page_files(work)
    (work / name).write_text("改过\n", encoding="utf-8")
    assert run(work, "check").returncode == 1
    assert voided(work) == {"set": f"file:{name}"}


def test_changing_plan_text_outside_the_five_tables_voids_a_plan_page_approval(work):
    plan_page_files(work)
    edit_plan(work, "- 测试用", "- 测试用，改过")
    assert run(work, "check").returncode == 1
    assert voided(work) == {"set": "file:set-plan.md"}
