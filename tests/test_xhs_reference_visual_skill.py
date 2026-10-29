"""The team's Xiaohongshu reference-visual package as an Easel skill, issue 58.

Seams (the issue's "Agreed seams"): the real skill check (scripts/validate_skills.py), the real
skill-library function in web/app.py, the vendored team folder compared with its recorded
per-file checksums through the compare script's command line and with the team's own two image
manifests, every relative link inside the vendored folder, the note skill's written strategy
table and metadata document, and the three brand profiles' pointers.
The team's own files sit unchanged under <资料包目录>/; SKILL.md is Easel's wrapper.
Issue 132: each brand's style file, post images, case index and image list live in that brand's profile folder in the
client knowledge base (under photo-scene/), found through the profile setting; none of them is in the skill.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import web.app as web

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "builtin" / "xhs-reference-visual"
VENDOR = SKILL_DIR / "references" / "vendor"
MANIFEST = ROOT / "docs" / "vendored" / "xhs-reference-visual-files.sha256"
NOTE = ROOT / "docs" / "vendored" / "xhs-reference-visual-source.md"
COMPARE = ROOT / "ops" / "wsl-setup" / "libtv-vendor-compare.py"
NOTE_SKILL = ROOT / "skills" / "builtin" / "xhs-note-creator"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _mapped_brand_names() -> list[str]:
    """The brand names this machine maps in EASEL_PROFILE_DIRS (git-ignored), so no brand name is written in a test."""
    from easel.persona import external_profile_dirs
    return list(external_profile_dirs())


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _validator():
    spec = importlib.util.spec_from_file_location("validate_skills", ROOT / "scripts" / "validate_skills.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compare(source: Path, folder: Path):
    return subprocess.run(
        [sys.executable, str(COMPARE), str(source), str(folder)], capture_output=True, text=True, timeout=120
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def _all_files(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}


# ---- the team's files, byte for byte -------------------------------------------------------------








def _tracked(prefix: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", "--", prefix], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ln for ln in out.stdout.splitlines() if ln.strip()]


def _is_brand_part(path: str) -> bool:
    """A brand style file (anything in the team's file/ folder except the design memory) or anything under case/."""
    if "<资料包目录>/case/" in path:
        return True
    folder, _, name = path.rpartition("/")
    return folder.endswith("<资料包目录>/file") and name != "DESIGN-MEMORY.md"




def test_the_brand_part_check_catches_a_style_file_a_post_image_and_the_case_index():
    base = "skills/builtin/xhs-reference-visual/<资料包目录>"
    assert _is_brand_part(f"{base}/file/Madeup.md")
    assert _is_brand_part(f"{base}/case/references/Madeup/01-madeup.png")
    assert _is_brand_part(f"{base}/case/CASES.md")
    assert not _is_brand_part(f"{base}/file/DESIGN-MEMORY.md")
    assert not _is_brand_part(f"{base}/standards/ecommerce-natural-v1/CASES.md")




# Links in the team's pages that point at parts which moved to the brands' profile folders (issue 132). Only these targets
# are skipped, and each must really be missing (a stale entry fails the second test below).
MOVED_LINK_TARGETS = {
    "skill/SKILL.md -> ../case/CASES.md",
    "skill/SKILL.md -> ../case/manifest.json",
    "INDEX.md -> case/CASES.md",
    "playbook/PLAYBOOK.md -> ../case/CASES.md",
}


def _vendored_links():
    for doc in VENDOR.rglob("*.md"):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", _text(doc)):
            clean = target.split("#", 1)[0].strip()
            if not clean or "://" in clean or clean.startswith("mailto:"):
                continue
            yield doc, target, (doc.parent / clean).exists()






def test_the_vendored_team_skill_is_not_a_second_skill_in_the_library():
    assert sum(1 for s in web.get_skills() if "reference-visual" in s["name"].lower()) == 1


# ---- Easel's skill contract ---------------------------------------------------------------------






def test_vendored_documents_add_no_output_layout_error():
    assert _validator().validate_output_layout_references() == []


def test_skill_library_lists_it_under_produce_and_it_is_not_hidden():
    listed = [s for s in web.get_skills() if s["name"] == "xhs-reference-visual"]
    assert len(listed) == 1
    assert listed[0]["layer"] == "produce"
    header = _text(SKILL_DIR / "SKILL.md").split("---", 2)[1]
    assert "disable-model-invocation" not in header


def test_description_carries_a_trigger_phrase_only_an_explicit_request_matches():
    description = next(s for s in web.get_skills() if s["name"] == "xhs-reference-visual")["description"]
    assert "照片场景帖" in description and "photo-scene post" in description


# ---- what the wrapper says ----------------------------------------------------------------------


def test_wrapper_sends_the_agent_to_the_team_skill_and_follows_its_reading_order():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "`<资料包目录>/skill/SKILL.md`" in text
    order = [text.index(p) for p in (
        "<资料包目录>/file/DESIGN-MEMORY.md",
        "photo-scene/file/",
        "photo-scene/case/CASES.md",
        "<资料包目录>/playbook/PLAYBOOK.md",
    )]
    assert order == sorted(order), "reading order is design memory, brand file, case index, playbook"
    assert "<资料包目录>/playbook/EXECUTION-BRIEF.md" in text


def test_wrapper_reads_the_19_image_standard_and_records_what_the_team_has_not_sent():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "<资料包目录>/standards/ecommerce-natural-v1/STANDARD.md" in text
    assert "<资料包目录>/standards/ecommerce-natural-v1/CASES.md" in text
    assert "reference-product-scene" in text and "Codex工作框架_图像生成设计流程" in text
    assert "未收到" in text


def test_wrapper_starts_only_on_an_explicit_call_and_hands_over_from_the_note_skill():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "只在两种情况下启动" in text
    assert "照片场景帖" in text and "xhs-note-creator" in text


def test_wrapper_makes_the_playbook_rules_hold_in_easel():
    text = _text(SKILL_DIR / "SKILL.md")
    for needle in (
        "逐字清单",           # every on-image word confirmed before generating
        "问题工具",           # ... through the question tool
        "先画三个封面",       # three cover versions before a set (issue 88; this was 先做一张小样)
        "逐字核对",           # actual image checked word by word
        "实际像素",           # real pixel size read from the file
        "1086×1448",          # what Codex returns for 3:4
        "不沿用 1242×1660",   # the team's export size is not carried over by default
        "背景差异",           # background-difference check before a set is extended
    ):
        assert needle in text, f"the wrapper does not say: {needle}"


def test_wrapper_edits_with_roles_on_the_codex_route_and_never_a_paid_route():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "ai_image.py img2img" in text
    assert text.count("--image") >= 2
    assert "IMG_PROVIDER=codex" in text
    assert "不用 API key" in text


def test_wrapper_does_not_copy_the_teams_claims_and_adds_no_global_preference():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "参考图里的功效" in text and "不照搬" in text
    assert "不把风格归纳写成全局偏好" in text


def test_wrapper_never_checks_the_wording_printed_on_the_real_pack():
    # issue 72, the owner's rule in CLAUDE.md "Product pack wording is never checked"
    text = _text(SKILL_DIR / "SKILL.md")
    for old in (
        "包装字",
        "逐字核对图上的每个字（中文逐字、小标签、包装字）和确认过的清单：对不上就重出或如实报告，不交付。",
        "对照真实商品照核对品牌、包装形状、容量和标签；检查手、握持和比例。",
        "哪些字核对过、哪些没法核实",
    ):
        assert old not in text, f"the wrapper still says: {old}"


def test_wrapper_still_checks_by_look_that_the_pack_is_the_real_unaltered_pack():
    text = _text(SKILL_DIR / "SKILL.md")
    for need in ("同款同规格", "形状和比例", "颜色", "Logo 和标签的位置", "没有多出也没有少掉"):
        assert need in text, f"the real-pack look check does not say: {need}"
    assert "第 1 张是商品，必须原样保留" in text




# issue 73: photo-scene sets repeated one composition. Same assertions as wrapper.test.py beside the skill.
ISSUE_73_NEEDS = {
    "set_plan_before_any_card": [
        "套系计划", "set-plan.md", "对标笔记库/image-sets", "整套图集，不只看封面", "画任何一张之前"],
    "cover_then_step_story_with_exception": ["封面加步骤故事", "参考图集显示另一种", "计划里写明"],
    "pack_is_hero_on_one_card_at_most": ["最多在一张卡上是主角", "包装角色"],
    "lettering_system_in_every_prompt": [
        "字体体系", "写进每一张的提示词", "默认字体", "small plain rectangular label boxes"],
    "layout_plan_per_card": [
        "版面计划", "layout-plan", "归哪一组", "位置和理由", "阅读顺序", "a tiny line at the bottom"],
    "side_by_side_check_with_fail_outcomes": [
        "两张卡构图重复，整套不交付", "字体和封面、参考图不一致", "违反版面计划"],
    "stop_when_nothing_to_study": ["没有可研究的", "不凭空编"],
    "plans_go_on_the_plan_page_before_the_sample": ["计划页", "小样"],
    "stronger_check_overrides_vendored_background_check": ["套系背景差异检查", "只比背景"],
}


@pytest.mark.parametrize("behaviour", sorted(ISSUE_73_NEEDS))
def test_wrapper_requires_the_issue_73_set_planning_behaviours(behaviour):
    text = _text(SKILL_DIR / "SKILL.md")
    for need in ISSUE_73_NEEDS[behaviour]:
        assert need in text, f"the wrapper does not say: {need}"


def test_wrapper_requires_the_set_plan_before_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find("套系计划") < text.find("**出图（只走 Codex")


def test_wrapper_pins_the_two_issue_phrases_as_forbidden_or_refused():
    text = _text(SKILL_DIR / "SKILL.md")
    for phrase, marker in (("a tiny line at the bottom", "禁止"), ("small plain rectangular label boxes", "拒绝")):
        lines = [ln for ln in text.splitlines() if phrase in ln]
        assert lines, f"'{phrase}' is not in the instructions"
        for ln in lines:
            assert marker in ln and ("词表" in ln or "字体" in ln), ln




# issue 77: the scene comes from the product's own ritual or place, with tidy props. Same assertions as
# wrapper.test.py beside the skill.
ISSUE_77_NEEDS = {
    "place_from_the_post_topic_moment_from_the_product": ["地方从帖子主题来，小事从商品来"],
    "moment_and_at_most_three_props_per_card": [
        "这一张正在发生的小事", "道具清单", "每件道具都证明这张卡的小动作", "证明", "摆在哪里"],
    "stock_props_refused_in_the_plan": ["咖啡杯、书、植物、毯子", "计划里一律拒绝"],
    "open_scoop_glass_spoon_as_wanted_props": ["这张卡的小动作里用到的那个物件"],
    "tidy_never_messy_and_no_mirror_unless_asked": [
        "污渍、碎屑、散落的包装纸、冒热气的饮品", "整洁", "除非用户要求，不出现镜子"],
    "prompt_names_the_props_and_adds_no_others": ["提示词写明这张卡的道具", "不加其他道具"],
    "delete_the_product_test_in_the_check": ["删掉商品测试", "拿掉商品，画面照样成立"],
    "prop_fail_outcomes_in_the_check": [
        "不证明这张卡小动作的道具", "计划外的道具", "杂乱", "没要求的镜子", "重出或如实报告"],
    "delete_test_judges_the_scene_not_the_pack_wording": [
        "只看场景，不看包装的大小、角度和包装上的字是否清楚"],
    "replace_the_product_only_keeps_the_reference_scene": [
        "只替换产品", "保留参考图的场景和道具", "计划里记下这张卡是替换模式"],
    "lovart_review_named_as_the_source": ["Lovart 技能包评审"],
}


@pytest.mark.parametrize("behaviour", sorted(ISSUE_77_NEEDS))
def test_wrapper_requires_the_issue_77_scene_from_the_product_behaviours(behaviour):
    text = _text(SKILL_DIR / "SKILL.md")
    for need in ISSUE_77_NEEDS[behaviour]:
        assert need in text, f"the wrapper does not say: {need}"


def test_wrapper_no_longer_lets_the_post_topic_choose_the_scene():
    assert "场景按这篇帖子的主题选" not in _text(SKILL_DIR / "SKILL.md")


def test_wrapper_never_asks_the_pack_wording_to_face_the_camera_or_be_legible():
    text = _text(SKILL_DIR / "SKILL.md")
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰"):
        assert banned not in text, banned


def test_wrapper_requires_the_ritual_or_place_before_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find("地方从帖子主题来，小事从商品来") < text.find("**出图（只走 Codex")




# issue 78: AI-look check before delivery, clean redraws. Same assertions as wrapper.test.py beside the skill.
VENDORED_FIX_LINE = "发现明确缺陷时进行有针对性的修正，避免反复全图重生成造成漂移"
PROMPT_SKILL = VENDOR / "prompt-skill" / "my-precise-image-generation-prompt" / "SKILL.md"


def _delivery_check() -> str:
    return _text(SKILL_DIR / "SKILL.md").split("**交付前检查实际图片**", 1)[1]


def _ai_look_block() -> str:
    check = _delivery_check()
    assert "AI 感检查" in check, "the delivery check has no AI-look check"
    return check.split("AI 感检查", 1)[1].split("\n- ", 1)[0]


def _drawing_step() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    return text.split("**出图（只走 Codex", 1)[1].split("**交付前检查实际图片**", 1)[0]


def _reading_order() -> str:
    return _text(SKILL_DIR / "SKILL.md").split("## 动手前先读", 1)[1].split("## 团队说过", 1)[0]


def test_ai_look_check_is_done_at_full_size_and_thumbnail_size_with_the_existing_command():
    block = _ai_look_block()
    for need in ("原尺寸", "手机缩略图", "python3 skills/shared/scripts/image_ops.py thumbnail", "256 像素"):
        assert need in block, need


def test_ai_look_check_names_the_five_signs():
    block = _ai_look_block()
    for sign in ("发脏的米色、灰色或黄色色偏", "强烈的颜色铺满整个画面", "发雾发闷或被压死的影调",
                 "每个区域都一样清晰、一样满", "同一种颗粒感"):
        assert sign in block, sign


def test_ai_look_check_fails_the_card_which_is_redrawn_or_reported_never_passed():
    block = _ai_look_block()
    for need in ("这张卡不合格", "如实报告给用户", "不能当合格交付", "干净重出"):
        assert need in block, need


def test_ai_look_check_ignores_the_packs_colours_and_never_reads_its_printed_wording():
    block = _ai_look_block()
    assert "真实包装自己的颜色不算" in block
    assert "不读、不列、不报包装上印的字" in block


def test_ai_look_check_names_the_lovart_review_as_its_source():
    assert "Lovart 技能包评审" in _ai_look_block()


def test_every_redraw_outcome_in_the_delivery_check_falls_under_the_clean_redraw_rule():
    assert "都按上面的干净重出办" in _delivery_check()


def test_drawing_step_makes_every_redraw_from_the_original_photo_and_reference_never_a_generated_version():
    drawing = _drawing_step()
    for need in ("干净重出", "不论原因", "原始商品照", "这张卡选定的参考图", "改正过的提示词",
                 "不得把这张卡已经画出的任何一版", "保留这张图，只改某处", "越改越脏",
                 "没有批准的卡", "已批准卡的修改"):  # issue 91: scoped to unapproved cards
        assert need in drawing, need


def test_drawing_step_still_allows_the_approved_cover_as_look_reference_and_logs_each_versions_inputs():
    drawing = _drawing_step()
    assert "另一张卡的第一次画" in drawing
    assert "传入了哪几张图" in drawing


def test_reading_order_says_ros_clean_redraw_ruling_overrides_the_vendored_targeted_correction_line():
    reading = _reading_order()
    for need in (VENDORED_FIX_LINE, "干净重出", "越改越脏", "以负责人的规则为准", "没有批准的卡"):
        assert need in reading, need




# issue 91: a change to an approved card starts from that card, changes only what the owner named, and is checked side by
# side against it; the clean redraw of issue 78 is for cards the owner has not approved. Same assertions as wrapper.test.py
# beside the skill.
APPROVED_START = "**已批准卡的修改（issue 91"
ISSUE_91_APPROVED = {
    "ros_rule_and_his_own_words_quoted": [
        ],
    "only_a_card_ro_explicitly_approved_counts": [
        "只有负责人明确批准过的卡", "他选中的封面", "他通过的小样", "并排看过整套后批准",
        "Easel 自己判断合格的卡不算已批准", "按没有批准办"],
    "change_starts_from_the_approved_card_and_changes_only_what_ro_named": [
        "从这张已批准的卡本身改起", "只改负责人点名的地方", "手、背景、道具、构图、色调"],
    # issue 115: the approved card goes in as the base image, its own option; the prompt no longer overrides a label
    "real_photo_then_approved_card_passed_as_the_base_image": [
        "先传真实商品照", "再传这张已批准的卡", "--base-image <已批准的卡>", "不是风格参考",
        "脚本会在提示词里写明第 2 张是要保留的底图"],
    "typed_set_passes_the_base_from_before_its_words_and_a_lettering_only_request_resets_words_only": [
        "设字之前的底图", "typed-styling.json", "只把字重新设一遍"],
    "changed_card_checked_side_by_side_against_the_approved_version_before_delivery": [
        "和已批准的那一版并排看", "负责人没点名的任何一处变了，这张卡不合格", "手、背景、产品大小或色偏",
        "从已批准的卡改起重画", "如实报告给用户", "不能当合格交付"],
    "existing_delivery_checks_still_apply_and_none_reads_the_pack_wording": [
        "AI 感检查", "手和动作检查", "不读包装上印的字"],
    "saved_prompt_file_names_the_approved_version_and_ros_words": [
        "它是从哪一个已批准的版本改出来的", "逐字写下负责人要改的那一句话"],
}


def _approved_card_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert APPROVED_START in text, "the drawing step has no approved-card section"
    return text.split(APPROVED_START, 1)[1].split("**交付前检查实际图片**", 1)[0]


def _clean_redraw_block() -> str:
    drawing = _drawing_step()
    assert "**干净重出（issue 78" in drawing, "the drawing step has no clean-redraw section"
    return drawing.split("**干净重出（issue 78", 1)[1].split("**已批准卡的修改", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_91_APPROVED))
def test_approved_card_section_requires_the_issue_91_behaviours(behaviour):
    block = _approved_card_block()
    for need in ISSUE_91_APPROVED[behaviour]:
        assert need in block, f"the approved-card section does not say: {need}"


def test_approved_card_section_no_longer_tells_the_prompt_to_override_the_script_role_label():
    # issue 115: the contradiction is removed by a base-image role, not by asking the prompt to win.
    assert "盖过脚本的那句角色说明" not in _approved_card_block()


def test_approved_card_rule_is_inside_the_drawing_step():
    assert APPROVED_START in _drawing_step()


def test_clean_redraw_rule_says_it_is_for_unapproved_cards_points_to_the_approved_card_rule_and_still_bans_passing_back():
    block = _clean_redraw_block()
    assert "没有批准" in block.split("\n", 1)[0], "the clean-redraw heading does not name unapproved cards"
    assert "已批准卡的修改" in block
    for key in ("不得把这张卡已经画出的任何一版当作输入图再传回去", "不论原因"):
        lines = [ln for ln in block.splitlines() if key in ln]
        assert lines, key
        for ln in lines:
            assert "没有批准的卡" in ln, ln


def test_reading_order_override_is_scoped_to_unapproved_cards_and_the_two_rules_do_not_clash_for_approved_ones():
    reading = _reading_order()
    for need in ("没有批准的卡", "已批准卡的修改", "两者不冲突"):
        assert need in reading, need
    lines = [ln for ln in reading.splitlines() if "干净重出" in ln and VENDORED_FIX_LINE in ln]
    assert lines
    for ln in lines:
        assert "没有批准的卡" in ln, ln


def test_delivery_check_splits_redraw_outcomes_between_the_clean_redraw_and_the_approved_card_rule():
    lines = [ln for ln in _delivery_check().splitlines() if "都按上面的干净重出办" in ln]
    assert lines
    for ln in lines:
        assert "没有批准的卡" in ln and "已批准卡的修改" in ln, ln


# issue 79: hand and action rules, one room. Same assertions as wrapper.test.py beside the skill.
HAND_PLAN_START = "**手和动作（issue 79"
ISSUE_79_PLAN = {
    "per_hand_card_contact_grip_movement_response_scale_entry": [
        "有手或手臂入画的卡", "接触点", "握法", "移动方向", "物体的反应", "手的大小比例",
        "进画面的方向", "没有主人的手", "没有手的卡不受这一节影响"],
    "close_up_names_what_it_proves": ["特写", "证明什么", "没有写明用途的裁切，计划里一律拒绝"],
    "one_home_setting_for_the_whole_set": [
        "整套只在一个地方", "换角落、台面、机位和主体，不换地方", "最后几张不跳到新的世界"],
    "grip_by_eye_pack_never_turned_for_its_text": [
        "握法只凭眼睛判断", "不要求把包装转向、放大或让印的字读得清"],
    "lovart_review_named_as_the_source": [
        "Lovart 技能包评审"],
}
ISSUE_79_HAND_CHECK = [
    "手和动作检查", "看不到接触点", "握法拿不住", "看不出移动方向", "物体没有反应", "手和物体的大小不对",
    "悬空的手", "多指或手指粘连", "产品边缘变形", "影子和光线对不上", "按形状判断，不读包装上的字",
    "这张卡不合格", "如实报告给用户",
]
PLAYBOOK = VENDOR / "playbook" / "PLAYBOOK.md"


def _hand_plan_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert HAND_PLAN_START in text, "the set plan has no hand-and-action section"
    return text.split(HAND_PLAN_START, 1)[1].split("**计划页（issue 87）**", 1)[0]


def _hand_check_block() -> str:
    check = _delivery_check()
    assert "手和动作检查" in check, "the delivery check has no hand-and-action check"
    return check.split("手和动作检查", 1)[1].split("\n- ", 1)[0]


def _side_by_side_block() -> str:
    check = _delivery_check()
    assert "套系并排检查" in check
    return check.split("套系并排检查", 1)[1].split("\n- ", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_79_PLAN))
def test_set_plan_requires_the_issue_79_hand_action_and_room_behaviours(behaviour):
    block = _hand_plan_block()
    for need in ISSUE_79_PLAN[behaviour]:
        assert need in block, f"the hand-and-action section does not say: {need}"


def test_hand_and_action_plan_comes_before_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find("有手或手臂入画的卡") < text.find("**出图（只走 Codex")


def test_drawing_step_puts_the_planned_action_mechanics_in_the_prompt():
    need = "提示词写明这张卡计划好的接触点、握法、移动方向、物体的反应、手的大小比例和进画面的方向"
    assert need in _drawing_step()


def test_delivery_check_replaces_the_bare_hand_line_with_the_hand_and_action_check():
    assert "另外检查手、握持和比例" not in _text(SKILL_DIR / "SKILL.md")
    block = "手和动作检查" + _hand_check_block()
    for need in ISSUE_79_HAND_CHECK:
        assert need in block, need


def test_side_by_side_check_fails_a_card_in_another_room_and_a_close_up_with_no_purpose():
    block = _side_by_side_block()
    for need in ("不在同一个地方", "特写没有写明用途", "不合格的卡重出"):
        assert need in block, need


def test_reading_order_says_ros_one_room_ruling_overrides_the_vendored_different_background_wording():
    reading = _reading_order()
    for need in ("明显不同背景", "整套一个地方", "以负责人的规则为准"):
        assert need in reading, need




def test_issue_79_wording_still_never_asks_the_pack_text_to_face_the_camera_or_be_legible():
    text = _text(SKILL_DIR / "SKILL.md")
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰"):
        assert banned not in text, banned


# issue 80: the set plan names the reader question each card answers. Same assertions as wrapper.test.py beside the skill.
QUESTION_START = "**读者的问题（issue 80"
ISSUE_80_PLAN = {
    "every_card_cover_included_gets_one_reader_question": [
        "每一张卡（封面也算）", "这张卡回答", "画任何一张之前写完"],
    "question_is_chinese_in_the_readers_words_at_that_moment": [
        "用中文", "读者自己的话", "那个时刻", "读者在这一步真会问的一个具体的数量或条件", "读者在这一步真会问的一个具体的数量或条件"],
    "broad_kinds_are_examples_not_a_menu": [
        "这是什么、为什么要在意、怎么用、凭什么信、适不适合我、下一步做什么", "只是举例，不是固定菜单"],
    "duplicate_questions_refused_unless_the_plan_says_why": [
        "两张卡问的是同一个问题", "写明两张都要的理由", "否则删掉其中一张"],
    "only_as_many_cards_as_the_story_needs": [
        "取决于故事要回答几个问题", "不预先定张数"],
    "lovart_story_orders_only_with_named_real_sets": [
        "推荐帖和教程帖的故事顺序", "写明已存的哪几套真实图集", "内容从真实帖子里学", "封面加步骤故事"],
    "sharpens_the_vendored_standard_task_line": [
        "每张图片或每屏有明确任务", "<资料包目录>/standards/ecommerce-natural-v1/STANDARD.md"],
    "lovart_review_named_as_the_source": [
        "Lovart 技能包评审", "Lovart 的文件没有拿进来"],
    "no_question_about_the_packs_printed_text": ["不问包装上印的字写了什么"],
}
VENDORED_TASK_LINE = "信息表达：每张图片或每屏有明确任务；情绪图、产品识别图、使用图、质地图、细节说明图各自有信息作用。"
STANDARD = VENDOR / "standards" / "ecommerce-natural-v1" / "STANDARD.md"


def _question_plan_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert QUESTION_START in text, "the set plan has no reader-question section"
    return text.split(QUESTION_START, 1)[1].split("**计划页（issue 87）**", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_80_PLAN))
def test_set_plan_requires_the_issue_80_reader_question_behaviours(behaviour):
    block = _question_plan_block()
    for need in ISSUE_80_PLAN[behaviour]:
        assert need in block, f"the reader-question section does not say: {need}"


def test_the_existing_per_card_line_of_the_set_plan_lists_the_readers_question():
    lines = [ln for ln in _text(SKILL_DIR / "SKILL.md").splitlines() if "再逐张写" in ln]
    assert lines, "the set plan has no per-card line"
    for ln in lines:
        assert "读者的问题" in ln, ln


def test_reader_question_is_required_before_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find(QUESTION_START) < text.find("**出图（只走 Codex")




def test_issue_80_wording_still_never_asks_the_pack_text_to_face_the_camera_or_be_legible():
    text = _text(SKILL_DIR / "SKILL.md")
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰"):
        assert banned not in text, banned


# issue 81: typed fonts are set by code from one stored styling. Same assertions as wrapper.test.py beside the skill.
# The code test is skills/builtin/xhs-note-creator/typed-text.test.py.
TYPED_START = "**打字字体的整套（issue 81"
ISSUE_81_PLAN = {
    "plan_records_the_kind_and_stores_the_styling_once_with_its_fields": [
        "打字字体", "手绘", "typed-styling.json", "font_file", "fill", "outline_width", "outline_color", "shadow",
        "sizes", "每个标题层级一个字号", "main title", "subtitle", "整套只存一次"],
    "installed_free_fonts_found_on_this_wsl": [
        "Noto Serif CJK SC", "Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/", "免费字体"],
    "no_prompt_asks_codex_to_draw_the_typed_words_and_text_areas_stay_clear": [
        "不让 Codex 画 Easel 自己的打字字", "留空"],
    "hand_drawn_lettering_doodles_and_brush_underlays_are_still_codexs": [
        "手绘的字、涂鸦（例如标题旁的小装饰）、笔刷底和其他承托仍然问 Codex", "手写字仍归 Codex"],
    "code_sets_the_words_cover_included_without_cropping_or_resizing": [
        "封面也由代码设字", "skills/builtin/xhs-note-creator/scripts/text_on_image.py",
        "--styling", "--blocks", "--record", "不裁、不缩放"],
    "every_card_keeps_a_record_of_the_values_it_used": ["每张卡一份记录", "font_file", "outline_width", "blocks"],
    "a_hand_drawn_set_works_as_today": ["手绘的整套照旧"],
    "words_follow_the_layout_plan_positions_not_the_styling": ["位置不在样式里", "版面计划"],
}
ISSUE_81_DRAWING = ["设字之前的封面", "字再按样式设一遍", "不让 Codex 画 Easel 自己的打字字"]
ISSUE_81_CHECK = ["打字字体一致检查", "--check-records", "typed-styling.json", "只有字号随标题层级不同",
                  "这张卡不合格", "如实报告给用户"]


def _typed_plan_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert TYPED_START in text, "the set plan has no typed-font section"
    return text.split(TYPED_START, 1)[1].split("**计划页（issue 87）**", 1)[0]


def _typed_check_block() -> str:
    delivery = _delivery_check()
    assert "打字字体一致检查" in delivery, "the delivery check has no typed-font consistency check"
    return "打字字体一致检查" + delivery.split("打字字体一致检查", 1)[1].split("\n- ", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_81_PLAN))
def test_set_plan_requires_the_issue_81_typed_font_behaviours(behaviour):
    block = _typed_plan_block()
    for need in ISSUE_81_PLAN[behaviour]:
        assert need in block, f"the typed-font section does not say: {need}"


def test_the_lettering_line_records_typed_or_hand_drawn_and_keeps_the_prompt_rule_for_hand_drawn():
    lines = [ln for ln in _text(SKILL_DIR / "SKILL.md").splitlines() if ln.startswith("- 字体体系")]
    assert lines, "the set plan has no lettering line"
    for ln in lines:
        assert "打字字体" in ln and "手绘" in ln and "写进每一张的提示词" in ln, ln


def test_typed_font_plan_comes_before_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find(TYPED_START) < text.find("**出图（只走 Codex")


def test_drawing_step_passes_the_cover_from_before_its_words_and_sets_them_again_on_a_clean_redraw():
    drawing = _drawing_step()
    for need in ISSUE_81_DRAWING:
        assert need in drawing, need


def test_delivery_check_compares_every_cards_record_with_the_sets_styling_and_keeps_the_old_checks():
    block = _typed_check_block()
    for need in ISSUE_81_CHECK:
        assert need in block, need
    delivery = _delivery_check()
    assert "逐字核对" in delivery and "套系并排检查" in delivery


# issue 116: a third typed font (LXGW WenKai Medium, installed by the WSL setup) is listed in the typed-font section.
# Same assertions as wrapper.test.py beside the skill.
# Issue 119 replaced the needles "三种" and "没有合适的就问负责人，不自己装" with "已装的是起点" and "不用为了装而问负责人".
ISSUE_116_FONT_LINE = ["LXGW WenKai", "霞鹜文楷", "LXGWWenKai-Medium.ttf", "/usr/local/share/fonts/lxgw-wenkai/",
                       "已装的是起点", "不用为了装而问负责人"]


def test_the_typed_font_line_lists_the_third_font_and_says_a_font_may_be_installed_without_asking_ro():
    lines = [ln for ln in _typed_plan_block().splitlines() if ln.startswith("- 字体：")]
    assert len(lines) == 1, lines
    for need in ISSUE_116_FONT_LINE:
        assert need in lines[0], f"the typed-font line does not say: {need}"


def test_skill_md_stays_within_the_200_line_limit():
    assert len(_text(SKILL_DIR / "SKILL.md").splitlines()) <= 200


def test_the_typed_word_setter_code_test_passes():
    # the code test sets two levels on two plain images from one styling and drives the comparison check
    test = NOTE_SKILL / "typed-text.test.py"
    proc = subprocess.run([sys.executable, str(test)], capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_issue_81_wording_still_never_asks_the_pack_text_to_face_the_camera_or_be_legible():
    text = _text(SKILL_DIR / "SKILL.md")
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰"):
        assert banned not in text, banned


# issue 110: a photography brief per person, one identity across the set, a same-energy retry for a refused pose,
# and a person-and-identity check. Same assertions as wrapper.test.py beside the skill.
PERSON_START = "**人物的摄影说明（issue 110"
ISSUE_110_PLAN = {
    "brief_per_person_card_with_the_five_items_and_a_card_missing_one_is_refused": [
        "整个人入画的卡", "主光", "软还是硬", "哪些影子留着", "镜头距离", "视线",
        "看商品、看动作、看画外、看镜头", "身体在动，不是静站", "服装", "缺一样的卡不进出图",
        "只有手入画的卡仍归上面“手和动作”一节"],
    "movement_is_one_purposeful_pose_never_stacked": [
        "和这张卡的小事有关", "站、坐、走三选一，不叠在一起"],
    "clothing_is_ros_sentence_verbatim": [
        "服装配合这篇帖子的场景"],
    "praise_words_alone_are_refused": [
        "beautiful premium model", "flawless skin", "精致、高级", "只有夸奖词的说明，计划里一律拒绝"],
    "one_identity_source_named_for_the_whole_set": [
        "整套唯一的身份来源", "品牌自己的模特图", "中式还是欧美", "写明理由", "每张有人的卡都用同一个人"],
    "drinking_is_planned_through_the_hand_items_plus_movement_and_gaze": [
        "喝东西的卡", "接触点", "杯子和嘴唇", "液体的反应", "这一口看起来是真的一刻"],
    "vendored_portrait_review_cited_and_the_prompt_skill_defaults_not_adopted": [
        "<资料包目录>/standards/ecommerce-natural-v1/PORTRAIT-WORKFLOW-REVIEW-2026-10-20.md",
        "<资料包目录>/standards/ecommerce-natural-v1/STANDARD.md",
        "my-precise-image-generation-prompt", "一个项目的默认值", "不采用"],
}
ISSUE_110_DRAWING = [
    "提示词带上这张卡的摄影说明（主光、镜头距离、视线、动作、服装）",
    "`--identity-image`", "整套同一张身份来源图",
    "被拒的姿势", "Codex 没有产出图片", "最后一句话", "同样的劲头",
    "同一个小事、同样和商品的互动、同样多的动作",
    "不为了绕过拒绝而去掉人物或互动",
    "被拒的原话和新姿势存进这张卡的提示词文件",
    "和用户批准的计划不同",
]
ISSUE_110_CHECK = [
    "人物和身份检查", "所有有人的卡并排", "身份来源图", "看起来是另一个人", "姿势没有目的", "没有动作",
    "光从另一边来", "视线在别处", "这张卡不合格", "如实报告给用户", "不能当合格交付",
    "身份是用眼睛比的", "不保证像素级一样", "最后一句话归负责人",
]


def _person_plan_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert PERSON_START in text, "the set plan has no person-brief section"
    return text.split(PERSON_START, 1)[1].split("**计划页（issue 87）**", 1)[0]


def _person_check_block() -> str:
    delivery = _delivery_check()
    assert "人物和身份检查" in delivery, "the delivery check has no person-and-identity check"
    return "人物和身份检查" + delivery.split("人物和身份检查", 1)[1].split("\n- ", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_110_PLAN))
def test_set_plan_requires_the_issue_110_person_brief_behaviours(behaviour):
    block = _person_plan_block()
    for need in ISSUE_110_PLAN[behaviour]:
        assert need in block, f"the person-brief section does not say: {need}"


def test_person_brief_comes_after_the_hand_section_and_before_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    hand_at, person_at = text.find(HAND_PLAN_START), text.find(PERSON_START)
    assert 0 <= hand_at < person_at < text.find("**计划页（issue 87）**") < text.find("**出图（只走 Codex")


def test_drawing_step_carries_the_brief_passes_the_identity_image_and_retries_a_refused_pose_with_the_same_energy():
    drawing = _drawing_step()
    for need in ISSUE_110_DRAWING:
        assert need in drawing, need


def test_delivery_check_compares_every_person_card_with_the_identity_source_and_leaves_the_last_word_to_ro():
    block = _person_check_block()
    for need in ISSUE_110_CHECK:
        assert need in block, need
    delivery = _delivery_check()
    assert "手和动作检查" in delivery and "套系并排检查" in delivery




def test_issue_110_wording_still_never_asks_the_pack_text_to_face_the_camera_or_be_legible():
    text = _text(SKILL_DIR / "SKILL.md")
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰"):
        assert banned not in text, banned


# issue 82: The owner's step 1 is a gate in front of the set plan: a study of this post's own topic must exist and be named.
# Same assertions as wrapper.test.py beside the skill.
STUDY_START = "**这篇帖子自己的主题研究（issue 82"
STUDY_END = "**套系计划（`set-plan.md`）**"
ISSUE_82_STUDY = {
    "ros_rule_named_with_his_words_quoted": [
        "Photo-scene post images follow one approval process", "第 1 步",
        ],
    "set_plan_not_written_until_the_posts_own_topic_study_exists": [
        "这篇帖子自己的主题研究", "没有存在之前", "`set-plan.md` 不写"],
    "one_search_ranked_by_likes_plus_favourites_whole_sets_saved_with_a_summary": [
        "一次搜索", "点赞加收藏", "整套图集", "对标笔记库/image-sets", "书面小结"],
    "the_plan_names_the_study_it_used": [
        "套系计划开头写明用的是哪一次研究", "存下的图集文件名", "小结文件名", "没有点名的计划不成立"],
    "sets_from_another_post_topic_are_refused_as_the_study": [
        "别的帖子主题", "不算这篇帖子的研究", "拒绝"],
    "the_teams_references_on_their_own_are_refused_as_the_study": ["团队的参考图", "单独", "不能当研究"],
    "with_no_study_the_skill_says_so_and_stops_inventing_nothing": [
        "如实告诉用户", "然后停下", "不凭空编套系"],
    "searching_ranking_and_saving_are_left_to_issues_83_and_84": ["issue 83、84", "这里只管这道门"],
    "the_study_is_made_by_the_readers_study_command_issue_84": [
        "skill-xhs-note-reader/scripts/study_topic.py", "references/photo-scene-topic-study.md", "没有这条命令存的图集不算研究"],
}
ISSUE_82_GONE = ["先看已存的真实图集", "抓新图集不归这个技能（那是阅读器的事）"]


def _study_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert STUDY_START in text, "the set-plan step has no topic-study gate"
    return text.split(STUDY_START, 1)[1].split(STUDY_END, 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_82_STUDY))
def test_set_plan_step_requires_the_issue_82_topic_study_behaviours(behaviour):
    block = _study_block()
    for need in ISSUE_82_STUDY[behaviour]:
        assert need in block, f"the topic-study gate does not say: {need}"


def test_the_topic_study_reference_exists_and_names_the_summary_rule_and_the_command_that_exists():
    reference = _text(SKILL_DIR / "references" / "photo-scene-topic-study.md")
    for need in ("study_topic.py", "summary.md", "一字不改", "退出码 0 才是做完"):
        assert need in reference, need
    assert (SKILL_DIR.parent / "skill-xhs-note-reader" / "scripts" / "study_topic.py").is_file()


def test_the_old_lines_that_let_any_saved_set_stand_as_the_research_are_gone():
    text = _text(SKILL_DIR / "SKILL.md")
    for old in ISSUE_82_GONE:
        assert old not in text, old


def test_topic_study_gate_comes_before_the_set_plan_and_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find(STUDY_START) < text.find(STUDY_END) < text.find("**出图（只走 Codex")


def test_the_set_plans_research_and_naming_lines_point_back_to_the_topic_study():
    text = _text(SKILL_DIR / "SKILL.md")
    assert STUDY_END in text
    bullets = text.split(STUDY_END, 1)[1].split("\n- ", 3)[1:3]
    assert len(bullets) == 2 and all("主题研究" in b for b in bullets), bullets
    named = [ln for ln in text.splitlines() if ln.startswith("- 计划写明")]
    assert named and all("主题研究" in ln for ln in named), named


# issue 85: the set plan carries a colour-to-level table, one colour per level, no colour on two levels. Same assertions
# as wrapper.test.py beside the skill.
COLOUR_START = "**颜色和层级的对应表（issue 85"
RO_COLOUR_SENTENCE = (
    "")
ISSUE_85_PLAN = {
    "ros_rule_named_with_his_words_quoted": [
        "Photo-scene post images follow one approval process", "第 2 步", RO_COLOUR_SENTENCE],
    "one_row_per_level_a_colour_as_name_and_hex_and_the_elements_it_covers": [
        "每个层级一行", "颜色名加十六进制值", "一层一色", "这一层覆盖的元素", "页头标题", "条目编号", "对勾"],
    "no_colour_on_two_rows": ["不同的层级不得用同一个颜色", "同一个颜色不出现在两行"],
    "a_plan_without_the_table_is_not_finished_and_no_card_is_drawn_from_it": [
        "没有这张表的套系计划没有写完", "不画任何一张卡"],
    "the_table_names_the_studied_sets_it_came_from": [
        "取自这篇帖子自己的主题研究存下的图集", "团队设计记忆", "写明这张表取自哪几套"],
    "scene_and_pack_colours_are_not_levels_and_the_table_never_reads_the_pack_words": [
        "场景自己的颜色和真实包装自己的颜色不是层级", "不读、不列、不核对包装上印的字"],
    "typed_sets_stored_fill_and_outline_are_the_lettering_row_one_row_for_all_title_levels": [
        "typed-styling.json", "fill", "outline_color", "“字”这一行", "只有字号不同", "是同一行",
        "样式文件的字段不变"],
    "abc_lettering_stylings_avoid_other_rows_colours_and_the_picked_one_becomes_the_lettering_row": [
        "A/B/C", "不得是别的行的颜色", "负责人选中的样式的颜色成为“字”这一行的颜色"],
    "sharpens_the_vendored_standard_and_playbook_colour_lines_which_stay_as_shipped": [
        "<资料包目录>/standards/ecommerce-natural-v1/STANDARD.md", "主色与辅助色", "文字层级",
        "<资料包目录>/playbook/PLAYBOOK.md", "主辅色", "原样不动"],
    "the_table_goes_to_the_user_with_the_plan_with_a_hex_value_per_row": [
        "和套系计划一起交给用户", "每一行都有十六进制值"],
}
ISSUE_85_DRAWING = [
    "颜色（issue 85）", "每张卡的提示词写明这张卡上出现的每个层级的颜色", "取自对应表",
    "只管 Codex 画的元素", "打字字由代码设，不进提示词", "表里没有的颜色",
]
ISSUE_85_CHECK = [
    "颜色和层级检查", "每张卡都做", "对着对应表", "用眼睛", "一个颜色用在了两个层级的元素上",
    "穿了表里没有的颜色", "场景自己的颜色和真实包装自己的颜色不算", "这张卡不合格", "干净重出",
    "已批准卡的修改", "如实报告给用户", "不能当合格交付", "不读包装上印的字",
]
VENDORED_STANDARD_COLOUR_LINE = (
    "给出本项目视觉约定：主色与辅助色、主光与明暗、场景、道具、景别、产品占比、文字层级。关键方向由用户确认。")
VENDORED_PLAYBOOK_COLOUR_LINE = "字体笔画与层级、文字底形、主辅色、产品占位、场景与道具、光线、元素密度。"


def _colour_plan_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert COLOUR_START in text, "the set plan has no colour-to-level table section"
    return text.split(COLOUR_START, 1)[1].split("**计划页（issue 87）**", 1)[0]


def _colour_prompt_block() -> str:
    drawing = _drawing_step()
    assert "颜色（issue 85）" in drawing, "the drawing step has no colour rule"
    return "颜色（issue 85）" + drawing.split("颜色（issue 85）", 1)[1].split("\n- ", 1)[0]


def _colour_check_block() -> str:
    delivery = _delivery_check()
    assert "颜色和层级检查（issue 85" in delivery, "the delivery check has no colour-and-level check"
    return "颜色和层级检查（issue 85" + delivery.split("颜色和层级检查（issue 85", 1)[1].split("\n- ", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_85_PLAN))
def test_set_plan_requires_the_issue_85_colour_to_level_table_behaviours(behaviour):
    block = _colour_plan_block()
    for need in ISSUE_85_PLAN[behaviour]:
        assert need in block, f"the colour-to-level section does not say: {need}"


def test_colour_to_level_table_comes_after_the_typed_font_section_and_before_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    typed_at, colour_at = text.find(TYPED_START), text.find(COLOUR_START)
    assert 0 <= typed_at < colour_at < text.find("**计划页（issue 87）**") < text.find("**出图（只走 Codex")


def test_drawing_step_puts_each_cards_level_colours_in_its_prompt_and_leaves_typed_words_out():
    block = _colour_prompt_block()
    for need in ISSUE_85_DRAWING:
        assert need in block, need


def test_delivery_check_fails_a_colour_on_two_levels_or_an_added_element_off_the_table():
    block = _colour_check_block()
    for need in ISSUE_85_CHECK:
        assert need in block, need


def test_side_by_side_set_check_runs_the_colour_and_level_check_and_the_old_checks_stay():
    assert "颜色和层级检查" in "套系并排检查" + _side_by_side_block()
    delivery = _delivery_check()
    for kept in ("AI 感检查", "手和动作检查", "套系并排检查"):
        assert kept in delivery, kept




def test_issue_85_wording_adds_no_line_that_reads_the_pack_text():
    text = _text(SKILL_DIR / "SKILL.md")
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
        assert banned not in text, banned


# issue 86: the set plan carries one icon list for the whole set, each icon one meaning, shown to the owner with the plan; the
# prompts name only the card's listed icons; the delivery check fails an off-list icon, an icon used for a second meaning
# and two icons for one meaning. The detail lives in references/photo-scene-icon-list.md because SKILL.md is at the
# 200-line limit; SKILL.md keeps the gate, the drawing rule and the check. Same assertions as wrapper.test.py.
ICON_START = "**图标清单（issue 86"
ICON_REF = SKILL_DIR / "references" / "photo-scene-icon-list.md"
RO_ICON_SENTENCE = ""
ISSUE_86_PLAN = {
    "ros_rule_named_with_his_words_quoted": [
        "Photo-scene post images follow one approval process", "第 2 步", RO_ICON_SENTENCE],
    "one_list_for_the_whole_set_or_a_no_icons_statement": ["整套唯一一张图标清单", "这套不用图标"],
    "a_plan_without_either_is_not_finished_and_no_card_is_drawn_from_it": [
        "没有清单也没有这句话的套系计划没有写完", "不画任何一张卡"],
    "one_meaning_per_icon_and_one_icon_per_meaning": [
        "一个图标一个意思", "一个意思一个图标", "两个不同的图标表示同一个意思"],
    "each_row_describes_the_icon_so_the_plan_page_can_show_it": [
        "用平常话描述", "细线对勾", "线条还是填充", "线宽", "它的唯一意思", "出现在哪几张卡"],
    "the_list_names_the_studied_sets_it_came_from": [
        "取自这篇帖子自己的主题研究存下的图集", "团队设计记忆", "写明这张清单取自哪几套"],
    "what_counts_as_an_icon_and_what_does_not": [
        "Easel 自己加到照片上", "文字和数字是字，不是图标", "装饰字的涂鸦", "字体样式", "不在清单里"],
    "the_packs_own_symbols_are_not_on_the_list_and_the_pack_wording_is_never_read": [
        "真实包装上印的符号不在清单里", "不读、不列、不核对包装上印的字"],
    "an_icon_that_is_a_colour_level_wears_that_levels_colour": [
        "颜色和层级的对应表", "穿那一层的颜色", "两张表要对得上"],
    "the_list_goes_to_the_user_with_the_plan_in_a_form_the_plan_page_can_show": [
        "随套系计划一起交给用户", "计划页（issue 87）", "每个图标有描述和意思", "用户批准的是计划、颜色和图标一次过"],
    "sharpens_the_vendored_standard_and_design_memory_lines_which_stay_as_shipped": [
        "图标风格、线宽、间距统一", "箭头和图标可能暗示效果，不能只审核文字而忽视其视觉含义。",
        "STANDARD.md", "DESIGN-MEMORY.md", "原样不动"],
}
ISSUE_86_DRAWING = [
    "图标（issue 86）", "这张卡上清单里的图标", "描述", "意思", "位置", "版面计划", "不画清单以外的任何符号",
    "打字字体的整套也一样", "设字只设字", "穿那一层的颜色",
]
ISSUE_86_CHECK = [
    "图标检查", "每张卡都做", "对着图标清单", "用眼睛", "画了清单以外的图标", "用在了它的意思以外",
    "两个不同的图标表示同一个意思", "这张卡不合格", "干净重出", "已批准卡的修改", "如实报告给用户",
    "不能当合格交付", "不读包装上印的字", "这套不用图标",
]
VENDORED_STANDARD_ICON_LINE = "图标风格、线宽、间距统一"
VENDORED_MEMORY_ICON_LINE = "箭头和图标可能暗示效果，不能只审核文字而忽视其视觉含义。"


def _icon_plan_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert ICON_START in text, "the set plan has no icon-list section"
    section = text.split(ICON_START, 1)[1].split("**计划页（issue 87）**", 1)[0]
    return section + "\n" + (_text(ICON_REF) if ICON_REF.is_file() else "")


def _icon_prompt_block() -> str:
    drawing = _drawing_step()
    assert "图标（issue 86）" in drawing, "the drawing step has no icon rule"
    return "图标（issue 86）" + drawing.split("图标（issue 86）", 1)[1].split("\n- ", 1)[0]


def _icon_check_block() -> str:
    delivery = _delivery_check()
    assert "图标检查（issue 86" in delivery, "the delivery check has no icon check"
    return "图标检查（issue 86" + delivery.split("图标检查（issue 86", 1)[1].split("\n- ", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_86_PLAN))
def test_set_plan_requires_the_issue_86_icon_list_behaviours(behaviour):
    block = _icon_plan_block()
    for need in ISSUE_86_PLAN[behaviour]:
        assert need in block, f"the icon-list section does not say: {need}"


def test_icon_list_comes_after_the_colour_table_and_before_the_drawing_step_and_points_to_its_detail_file():
    text = _text(SKILL_DIR / "SKILL.md")
    colour_at, icon_at = text.find(COLOUR_START), text.find(ICON_START)
    assert 0 <= colour_at < icon_at < text.find("**计划页（issue 87）**") < text.find("**出图（只走 Codex")
    assert "references/photo-scene-icon-list.md" in text.split("**计划页（issue 87）**", 1)[0].split(ICON_START, 1)[1]
    assert ICON_REF.is_file(), "references/photo-scene-icon-list.md does not exist"


def test_the_plan_hand_over_line_sends_the_icon_list_to_the_user_with_the_plan():
    line = _text(SKILL_DIR / "SKILL.md").split("**计划页（issue 87）**", 1)[1].split("\n", 1)[0]
    assert "图标清单" in line, line


def test_drawing_step_names_only_the_cards_listed_icons_in_its_prompt_typed_sets_included():
    block = _icon_prompt_block()
    for need in ISSUE_86_DRAWING:
        assert need in block, need


def test_delivery_check_fails_an_off_list_icon_a_second_meaning_and_two_icons_for_one_meaning():
    block = _icon_check_block()
    for need in ISSUE_86_CHECK:
        assert need in block, need


def test_side_by_side_set_check_runs_the_icon_check_and_the_old_checks_stay():
    assert "图标检查" in "套系并排检查" + _side_by_side_block()
    delivery = _delivery_check()
    for kept in ("AI 感检查", "手和动作检查", "套系并排检查", "颜色和层级检查"):
        assert kept in delivery, kept




def test_skill_md_stays_within_the_200_line_limit():
    assert len(_text(SKILL_DIR / "SKILL.md").splitlines()) <= 200


def test_issue_86_wording_adds_no_line_that_reads_the_pack_text():
    for path in (SKILL_DIR / "SKILL.md", ICON_REF):
        if not path.is_file():
            continue
        text = _text(path)
        for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
            assert banned not in text, (path.name, banned)


# issue 93: more vendored lines read the pack's printed words than the five examples issue 72 named. The owner's rule overrides
# each of them; the detail lives in references/pack-wording-override.md because SKILL.md is at the 200-line limit. The
# vendored files stay as shipped. Same assertions as wrapper.test.py.
OVERRIDE_REF = SKILL_DIR / "references" / "pack-wording-override.md"
_MEMORY = "standards/ecommerce-natural-v1/PRODUCT-REPLACEMENT-MEMORY.md"
ISSUE_93_LINES = [
    ("standards/ecommerce-natural-v1/STANDARD.md", "产品形态、包装、颜色和文字是否准确？"),
    ("prompt-skill/my-precise-image-generation-prompt/SKILL.md", "包装、颜色、文字依据提供的素材"),
    (_MEMORY, "生成工具曾改错包装中的 Restore joint health"),
    (_MEMORY, "产品原图约束包装形状、比例、文字、图案、品牌颜色与规格"),
    (_MEMORY, "包装放大比对"),
    ("reviews/2026-10-20-product-scene-replacement-review.md", "外形、长宽比例、封口、文字、图案、品牌色、规格等不能任意修改"),
    ("standards/ecommerce-natural-v1/CASES.md", "原图标签部分文字不自然，后续必须依据真实包装纠正"),
]


def _override_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    reading = text.split("## 动手前先读", 1)[1].split("## 团队说过", 1)[0]
    assert "references/pack-wording-override.md" in reading, "the reading-order section does not point to the override list"
    assert OVERRIDE_REF.is_file(), "references/pack-wording-override.md does not exist"
    return reading + "\n" + _text(OVERRIDE_REF)




def test_override_reference_adds_no_line_that_reads_the_pack_text_and_skill_md_stays_within_200_lines():
    _override_block()
    assert len(_text(SKILL_DIR / "SKILL.md").splitlines()) <= 200
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
        assert banned not in _text(OVERRIDE_REF), banned






# ---- the note skill hands photo-scene posts over ------------------------------------------------


def test_note_skill_intake_offers_photo_scene_post():
    text = _text(NOTE_SKILL / "SKILL.md")
    intake = text.split("### Step 0 — Intake", 1)[1].split("### Step 0.5", 1)[0]
    assert "photo-scene post" in intake and "照片场景帖" in intake


def test_note_skill_strategy_table_sends_photo_scene_to_the_new_skill_and_text_cards_stay():
    text = _text(NOTE_SKILL / "SKILL.md")
    rows = {ln.split("|")[1].strip(): ln for ln in text.splitlines() if ln.startswith("| `")}
    assert "../xhs-reference-visual/SKILL.md" in rows["`photo_scene`"]
    assert "../card-xiaohongshu/SKILL.md" in rows["`html_card`"]
    assert "scripts/text_on_image.py" in rows["`text_on_photo`"]
    assert "scripts/collage_3x4.py" in rows["`collage`"]


def test_note_skill_never_picks_photo_scene_on_its_own_and_keeps_its_text_check():
    text = _text(NOTE_SKILL / "SKILL.md")
    assert "只有用户在 Step 0 选了照片场景帖" in text
    visual_gate = text.split("**② 视觉门**", 1)[1].split("任一非 0", 1)[0]
    assert "仅 `html_card`" in visual_gate
    text_gate = text.split("**① 文本/结构门**", 1)[1].split("**② 视觉门**", 1)[0]
    assert "photo_scene" in text_gate


def test_metadata_document_lists_the_new_strategy_in_both_places():
    schema = _text(NOTE_SKILL / "references" / "meta-schema.md")
    assert schema.count("html_card | text_on_photo | collage | photo_scene") >= 2
    assert "html_card | text_on_photo | collage\"" not in schema


def test_note_skill_still_passes_the_skill_check():
    assert _validator().validate(NOTE_SKILL / "SKILL.md") == []


# ---- the skill finds a brand's photo-scene files through the profile setting (issue 132) --------

from easel.persona import profile_dir  # noqa: E402

MADEUP = "madeup-test"      # a made-up brand: the skill's tests name no real brand
MADEUP_FILE = "Madeup"      # the name its style file and post-image folder carry


def _madeup_profile(root: Path) -> Path:
    profile = root / "client-kb" / "brands" / MADEUP / "profile"
    (profile / "assets" / "products").mkdir(parents=True)
    (profile / "assets" / "products" / "pack.png").write_bytes(b"x")
    (profile / "photo-scene" / "file").mkdir(parents=True)
    (profile / "photo-scene" / "case" / "references" / MADEUP_FILE).mkdir(parents=True)
    (profile / "photo-scene" / "file" / f"{MADEUP_FILE}.md").write_text("style\n", encoding="utf-8")
    (profile / "photo-scene" / "case" / "CASES.md").write_text("# index\n", encoding="utf-8")
    (profile / "photo-scene" / "case" / "manifest.json").write_text("[]", encoding="utf-8")
    (profile / "photo-scene" / "case" / "references" / MADEUP_FILE / "01-madeup.png").write_bytes(b"x")
    return profile


def _profile_relative_reads() -> list[str]:
    """Every path the wrapper tells the agent to read from the brand's profile folder."""
    text = _text(SKILL_DIR / "SKILL.md")
    found = re.findall(r"`((?:<画像目录>/)?(?:photo-scene|assets)/[^`]+)`", text)
    return sorted({p.replace("<画像目录>/", "").replace("<品牌>", MADEUP_FILE).replace("<图>", "01-madeup.png")
                   for p in found})


def test_the_wrapper_reads_a_brands_photo_scene_files_from_the_folder_the_profile_setting_points_to(tmp_path, monkeypatch):
    profile = _madeup_profile(tmp_path)
    monkeypatch.setenv("EASEL_PROFILE_DIRS", f"{MADEUP}={profile}")
    assert profile_dir(MADEUP) == profile
    reads = _profile_relative_reads()
    assert {"photo-scene/file/Madeup.md", "photo-scene/case/CASES.md",
            "photo-scene/case/references/Madeup/01-madeup.png", "assets/products/"} <= set(reads), reads
    for rel in reads:
        assert (profile_dir(MADEUP) / rel).exists(), f"does not resolve from the profile folder: {rel}"


def test_the_wrapper_never_reads_a_brands_style_file_or_case_index_from_the_vendored_folder():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "<资料包目录>/case" not in text
    assert re.findall(r"<资料包目录>/file/(?!DESIGN-MEMORY\.md)", text) == []


def test_a_brand_without_photo_scene_reads_no_team_references_says_so_and_goes_on():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "没有 `photo-scene/`" in text
    sentence = next(ln for ln in text.splitlines() if "没有 `photo-scene/`" in ln)
    assert "如实说一句" in sentence and "继续" in sentence


def test_the_style_files_pack_wording_line_is_covered_by_one_override_line_that_names_no_brand(tmp_path, monkeypatch):
    profile = _madeup_profile(tmp_path)
    style = profile / "photo-scene" / "file" / f"{MADEUP_FILE}.md"
    style.write_text("# style\n- 锁定瓶型/袋型、Logo、文字、颜色、容量\n", encoding="utf-8")
    monkeypatch.setenv("EASEL_PROFILE_DIRS", f"{MADEUP}={profile}")
    snippet = "锁定瓶型/袋型、Logo、文字、颜色、容量"
    assert snippet in (profile_dir(MADEUP) / "photo-scene" / "file" / f"{MADEUP_FILE}.md").read_text(encoding="utf-8")
    named = [ln for ln in _override_block().splitlines() if snippet in ln]
    assert len(named) == 1, named
    assert "photo-scene/file/" in named[0] and "不执行" in named[0] and "其余照旧" in named[0]
    for brand in _mapped_brand_names():
        assert brand.lower() not in named[0].lower()


# ---- the repository's documentation path check ---------------------------------------------------




# issue 87: The owner's step 3. Before any card is drawn the set plan becomes a web page, built by a command (never by hand)
# from the plan's own text, and drawing waits for the user's one approval of that page. The old "plan rides with the
# sample, no extra approval step" line is gone. The fixed layout and the command's rules live in
# references/photo-scene-plan-page.md because SKILL.md is at its 200-line limit. The command's own test is
# tests/test_xhs_plan_page.py. Same assertions as wrapper.test.py beside the skill.
PLAN_PAGE_START = "**计划页（issue 87）**"
PLAN_PAGE_REF = SKILL_DIR / "references" / "photo-scene-plan-page.md"
RO_STEP_3 = (
    "")
OLD_RIDE_ALONG_LINE = "**一起交给用户**：套系计划和小样的版面计划，和小样一起交给用户，走下面“先做一张小样”已有的这一次确认；不另加确认步骤。"
ISSUE_87_SKILL = {
    "ros_step_3_rule_quoted_word_for_word": [
        "Photo-scene post images follow one approval process", "第 3 步", RO_STEP_3],
    "page_is_built_by_the_command_from_the_set_plan_never_by_hand": [
        "用命令从 `set-plan.md` 建计划页", "从不手写"],
    "no_card_of_any_kind_is_drawn_before_the_user_approves_the_page": [
        "任何一张卡（小样、封面或别的）都不画", "用户自己的回复批准这一页之前", "然后停下"],
    "approval_is_recorded_in_the_set_plan_with_its_date": ["批准记入批准记录 `approvals.json`"],
    "a_changed_plan_means_a_rebuilt_page_and_a_new_approval": [
        "计划改了就重建页、重新交给用户", "批准的是重建后的那一版"],
    "icon_list_goes_with_the_page_and_detail_is_in_the_reference_file": [
        "图标清单", "references/photo-scene-plan-page.md"],
}
ISSUE_87_REF = {
    "ros_step_3_rule_quoted_word_for_word": [RO_STEP_3],
    "studied_sets_table_fixed_with_the_saved_side_by_side_image_named_by_file": [
        "## 研究的图集", "| 图集 | 并排图 | 点赞 | 收藏 | 合计 | 借什么 |", "品牌资料/对标笔记库/image-sets"],
    "per_card_table_fixed_with_the_new_studied_set_column": [
        "## 逐张计划",
        "| 卡 | 读者的问题 | 主体 | 场景和小事 | 道具 | 机位 | 短文案 | 包装角色 | 手和人物 | 借的图集 |",
        "借的图集", "研究的图集"],
    "colour_table_and_icon_list_are_read_as_issues_85_and_86_define_them": [
        "## 颜色和层级", "| 层级 | 颜色 | 覆盖的元素 |", "颜色名加十六进制值",
        "## 图标清单", "| 图标 | 意思 | 出现的卡 |", "这套不用图标"],
    "built_by_command_with_its_arguments_and_exit_codes": [
        "python3 skills/builtin/xhs-reference-visual/scripts/plan_page.py build --plan", "--sets-folder", "-o",
        "退出码 0", "退出码 2"],
    "all_text_is_copied_unchanged_the_command_adds_only_fixed_headings_and_labels": [
        "逐字复制", "只加固定的标题和标签", "不改写"],
    "unreadable_plan_stops_the_build_naming_section_and_row": [
        "缺一张表", "表头不对", "借的图集不在", "并排图不在磁盘上", "没有有效的十六进制值", "报出表名和行", "不猜、不补"],
    "saved_beside_the_set_plan_in_outputs_with_relative_image_paths": [
        "`outputs/`", "set-plan.md` 旁边", "相对路径", "不写进临时文件夹"],
    "pack_wording_stays_out": ["不读、不列、不报包装上印的字"],
    "the_video_storyboard_command_is_the_pattern_and_stays_untouched": [
        "skills/shared/scripts/storyboard_page.py", "不改它"],
}


def _plan_page_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert PLAN_PAGE_START in text, "the set-plan step has no plan-page section"
    return text.split(PLAN_PAGE_START, 1)[1].split("\n## ", 1)[0].split("\n\n", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_87_SKILL))
def test_set_plan_step_requires_the_issue_87_plan_page_behaviours(behaviour):
    block = _plan_page_block()
    for need in ISSUE_87_SKILL[behaviour]:
        assert need in block, f"the plan-page section does not say: {need}"


def test_plan_page_section_comes_after_the_icon_list_and_before_the_sample_and_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find(ICON_START) < text.find(PLAN_PAGE_START) < text.find(COVERS_START) \
        < text.find("**出图（只走 Codex")


def test_the_old_plan_rides_with_the_sample_line_and_its_no_extra_approval_step_are_gone():
    for path in (SKILL_DIR / "SKILL.md", ICON_REF, PLAN_PAGE_REF):
        text = _text(path) if path.is_file() else ""
        assert OLD_RIDE_ALONG_LINE not in text, path.name
        assert "不另加确认步骤" not in text, path.name
        assert "连同上面的套系计划" not in text, path.name


def test_the_covers_step_waits_for_the_approved_plan_page_and_carries_only_each_covers_own_layout_plan():
    block = _covers_block()
    assert "计划页得到用户批准之后" in block
    assert "每个封面各自的版面计划" in block
    assert "套系计划" not in block.split("每个封面各自的版面计划", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_87_REF))
def test_plan_page_reference_requires_the_issue_87_behaviours(behaviour):
    assert PLAN_PAGE_REF.is_file(), "references/photo-scene-plan-page.md does not exist"
    text = _text(PLAN_PAGE_REF)
    for need in ISSUE_87_REF[behaviour]:
        assert need in text, f"the plan-page reference does not say: {need}"


def test_the_fixed_columns_in_the_reference_are_the_ones_the_command_reads():
    spec = importlib.util.spec_from_file_location("plan_page", SKILL_DIR / "scripts" / "plan_page.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = _text(PLAN_PAGE_REF)
    for columns in module.SECTIONS.values():
        assert "| " + " | ".join(columns) + " |" in text, columns


def test_the_video_storyboard_command_is_the_pattern_and_is_not_changed_by_issue_87():
    video = _text(ROOT / "skills" / "shared" / "scripts" / "storyboard_page.py")
    assert "plan_page" not in video and "xhs-reference-visual" not in video


def test_the_plan_page_command_test_passes_from_the_skill_folder():
    proc = subprocess.run([sys.executable, str(SKILL_DIR / "plan-page.test.py")], capture_output=True, text=True,
                          timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_issue_87_wording_adds_no_line_that_reads_the_pack_text():
    for path in (SKILL_DIR / "SKILL.md", PLAN_PAGE_REF, SKILL_DIR / "scripts" / "plan_page.py"):
        if not path.is_file():
            continue
        text = _text(path)
        for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
            assert banned not in text, (path.name, banned)


# issue 117: a person-and-scene realism check after drawing (skin, face, body, light, how hands and objects touch),
# looked at full size beside one of the post's own studied real sets; drawing wording that asks for an unposed real
# moment and never for grain; the Lovart sources named as origin with what was not taken. The detail lives in
# references/photo-scene-realism.md. Same assertions as wrapper.test.py beside the skill.
REALISM_REF = SKILL_DIR / "references" / "photo-scene-realism.md"
RO_REALISM_SENTENCE = (
    "")
RO_LOOKUP_SENTENCE = (
    "")
RO_WEIRD_SENTENCE = ""
REALISM_CHECK_START = "人物和画面真实感检查（issue 117"
ISSUE_117_CHECK = [
    "人物和画面真实感检查", "issue 117", RO_REALISM_SENTENCE,
    "image-cleanup-director", "references/human-rendering.md", "marketing-style-lifestyle-scene", "没有拿进来",
    "Easel 只走 Codex 订阅", "不自动二次生成", "干净重出规则不变", "photo-scene-realism.md",
    "每张有人或有手入画的卡", "小样和成套都一样", "原尺寸", "这篇帖子自己研究存下的一套真实图集并排", "不凭记忆",
    "皮肤", "脸", "身体", "光", "物体接触",
    "这张卡不合格", "干净重出", "已批准卡的修改", "如实报告", "不能当合格交付", "重出没有次数上限",
    "不读、不列、不报包装上印的字",
]
ISSUE_117_DRAWING = [
    "身份图只定这个人是谁", "不定皮肤怎么修", "修过的广告图", "最大的、修得最少的那一张",
    "不摆拍的真实一刻", "一个看得出来源的主光", "没有修图的真实拍出来的皮肤", "有重量并有接触的物体",
    "不为了显得真实而要求颗粒、噪点、色散、固定镜头或失焦", "a little natural noise in the darker areas",
    "photo-scene-realism.md",
]
ISSUE_117_REF = {
    "ros_three_sentences_quoted_word_for_word": [
        "Photo-scene post images follow one approval process", RO_REALISM_SENTENCE, RO_LOOKUP_SENTENCE,
        RO_WEIRD_SENTENCE],
    "why_the_check_carries_the_weight_the_prompt_already_asked_and_the_covers_still_looked_ai": [
        "提示词里已经写了", "封面还是画出了 AI 感", "检查是主力", "品牌自己的模特图里剪出来的一小块"],
    "the_skin_signs": [
        "## 皮肤", "修得发亮的匀净皮肤", "蜡感", "塑料感", "瓷感", "整张脸一个光泽", "反过来", "重复的毛孔或颗粒"],
    "the_face_signs": [
        "## 脸", "镜像对称", "被“修正”过的五官", "玻璃一样的眼睛", "融化的睫毛", "粘连的牙", "广告表情"],
    "the_body_signs": ["## 身体", "摆给镜头", "商品递向镜头", "图库式摆拍", "计划里的那一刻"],
    "the_light_signs": ["## 光", "四面均匀", "没有影子", "人和房间各打各的光", "抠出来贴上去"],
    "the_object_contact_signs": [
        "## 手和物体怎么接触", "手搭在杯子上却没握住", "勺子捏着没有压力", "立在台面上没有接触阴影", "像贴上去的包"],
    "judged_beside_one_of_this_posts_own_studied_sets_never_from_memory": [
        "和这篇帖子自己研究存下的一套真实图集并排", "原尺寸", "不凭记忆", "点名文件名"],
    "a_failed_card_goes_to_the_existing_outcomes_with_no_cap_on_redraws": [
        "干净重出", "已批准卡的修改", "如实报告", "不能当合格交付", "重出没有次数上限", "issue 101"],
    "the_check_never_reads_the_packs_printed_wording": ["不读、不列、不报包装上印的字"],
    "drawing_wording_visible_descriptions_only_no_grain_or_noise_as_fake_realism": [
        "不摆拍的真实一刻", "一个看得出来源的主光", "没有修图的真实拍出来的皮肤", "有重量并有接触的物体",
        "不为了显得真实而要求颗粒、噪点、色散、固定镜头或失焦", "a little natural noise in the darker areas"],
    "the_identity_image_fixes_who_the_person_is_not_the_retouching": [
        "身份图只定这个人是谁", "最大的、修得最少的那一张", "修过的广告图"],
    "what_was_taken_from_the_lovart_pack": [
        "## 从 Lovart 技能包取了什么", "image-cleanup-director", "references/human-rendering.md",
        "references/repair-branches.md", "marketing-style-lifestyle-scene", "整本读完"],
    "what_was_refused_from_the_lovart_pack_and_why": [
        "## 没取什么", "Nano Banana Pro", "Image2", "Easel 只走 Codex 订阅", "不自动二次生成",
        "干净重出规则不变", "胶片颗粒", "传感器噪声", "35mm/50mm", "商品印刷面转向镜头", "包装上的字从不检查"],
    "the_room_furnishing_note_keeps_issue_77s_record_and_points_to_ros_answer": [
        "issue 77", "1 到 3 件", "issue 118", "photo-scene-setting.md"],
}


def _realism_check_block() -> str:
    delivery = _delivery_check()
    assert REALISM_CHECK_START in delivery, "the delivery check has no person-and-scene realism check"
    return "人物和画面真实感检查" + delivery.split("人物和画面真实感检查", 1)[1].split("\n- ", 1)[0]


def test_realism_check_names_the_five_signs_and_the_lovart_origin_and_what_was_not_taken():
    block = _realism_check_block()
    for need in ISSUE_117_CHECK:
        assert need in block, f"the realism check does not say: {need}"


def test_realism_check_sits_between_the_ai_look_check_and_the_set_side_by_side_check():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find("AI 感检查（issue 78") < text.find(REALISM_CHECK_START) < text.find("套系并排检查（成套时必做）")


def test_drawing_step_says_the_identity_image_fixes_the_person_not_the_retouching_and_asks_for_no_fake_realism():
    drawing = _drawing_step()
    for need in ISSUE_117_DRAWING:
        assert need in drawing, need


def test_delivery_note_names_the_studied_set_the_card_was_judged_against_and_leaves_the_last_word_to_ro():
    note = [ln for ln in _delivery_check().splitlines() if ln.startswith("- 交付时写明")]
    assert note, "the delivery check has no delivery-note line"
    for need in ("点名文件名的那一套真实图集并排看", "最后一句话归负责人"):
        assert need in note[0], need


@pytest.mark.parametrize("behaviour", sorted(ISSUE_117_REF))
def test_realism_reference_requires_the_issue_117_behaviours(behaviour):
    assert REALISM_REF.is_file(), "references/photo-scene-realism.md does not exist"
    text = _text(REALISM_REF)
    for need in ISSUE_117_REF[behaviour]:
        assert need in text, f"the realism reference does not say: {need}"


def test_the_wrapper_carries_neither_the_lovart_wording_nor_a_grain_or_lens_ask_and_stays_within_200_lines():
    text = _text(SKILL_DIR / "SKILL.md")
    assert len(text.splitlines()) <= 200
    for banned in ("Nano Banana", "35mm/50mm", "胶片颗粒", "传感器噪声", "Photographic Skin Quality Gate"):
        assert banned not in text, banned


def test_no_lovart_file_was_copied_into_the_vendored_folder():
    names = [p.as_posix() for p in VENDOR.rglob("*")]
    assert not any("image-cleanup-director" in n or "marketing-style-lifestyle-scene" in n for n in names)


def test_issue_117_wording_never_asks_the_pack_text_to_face_the_camera_or_be_legible():
    for path in (SKILL_DIR / "SKILL.md", REALISM_REF):
        if not path.is_file():
            continue
        text = _text(path)
# issue 88: The owner's step 4. After the plan page is approved the skill draws three cover versions, A, B and C, each from a
# different studied set and differing in angle, framing or lead; they are shown side by side on a page built by the
# `covers` command and no other card is drawn until the owner picks one. The old single sample is gone. The set plan gains a
# cover-directions table (fixed in references/photo-scene-plan-page.md); the covers procedure is in
# references/photo-scene-cover-versions.md because SKILL.md is at its 200-line limit. The command's own test is
# tests/test_xhs_plan_page.py. Same assertions as wrapper.test.py beside the skill.
COVERS_START = "**先画三个封面 A/B/C（issue 88）**"
COVERS_REF = SKILL_DIR / "references" / "photo-scene-cover-versions.md"
RO_STEP_4 = (
    "")
RO_QUOTE_88 = (
    "")
VENDORED_ONE_SAMPLE_LINES = {
    "playbook/PLAYBOOK.md": [
        "可在同体系内提供至多三个微变体", "只给风格名：提供三个同风格变体，等确认。", "先一张代表性小样，用户审核后扩展"],
    "standards/ecommerce-natural-v1/STANDARD.md": ["先制作一张有代表性的小样，用户审核后再展开套系或整页"],
    "skill/SKILL.md": ["先做小样，用户审核后扩展"],
}
ISSUE_88_SKILL = {
    "ros_step_4_rule_and_quote_word_for_word": [
        "Photo-scene post images follow one approval process", "第 4 步", RO_STEP_4, RO_QUOTE_88],
    "three_covers_each_from_a_different_studied_set_differing_in_angle_framing_or_lead": [
        "三个封面", "A、B、C", "各借不同的一套研究过的图集", "角度、取景或照片领头的东西不同"],
    "drawn_after_the_plan_page_approval_without_asking_again_one_at_a_time": [
        "计划页得到用户批准之后", "不再另问", "一次一张"],
    "shown_side_by_side_on_a_page_built_by_the_command_never_by_hand": [
        "plan_page.py covers", "并排", "从不手写"],
    "no_other_card_is_drawn_before_the_pick": ["用户选定之前", "其他任何一张卡都不画", "然后停下"],
    "fewer_than_three_studied_sets_means_tell_the_user_and_stop": ["不足三套", "如实告诉用户", "不重用一套"],
    "the_detail_is_in_the_reference_file": ["references/photo-scene-cover-versions.md"],
    "ros_rule_overrides_the_team_packages_one_sample_lines_naming_each": [
        "以负责人的规则为准", "PLAYBOOK.md:17-18", "PLAYBOOK.md:26", "STANDARD.md:36", "先做小样",
        "资料包里这些句子原样不动"],
}
ISSUE_88_REF = {
    "ros_step_4_rule_and_quote_word_for_word": [RO_STEP_4, RO_QUOTE_88],
    "three_directions_in_the_set_plan_each_with_its_own_layout_plan": [
        "封面方向表", "photo-scene-plan-page.md", "每个方向各有一份版面计划", "画任何一张之前"],
    "real_differences_only": [
        "三个方向借三套不同的图集", "角度、取景和领头每一样都不同", "换个颜色或裁小一点不是不同的方向"],
    "fewer_than_three_studied_sets_stop": ["不足三套", "不重用一套", "不凭空编方向"],
    "a_direction_names_the_later_card_it_collides_with_and_how_that_card_changes": [
        "撞上的卡和改法", "选哪个方向，那张卡就怎么改", "不再另问"],
    "the_plan_page_approval_releases_the_three_draws": ["计划页的批准", "不再问第二次", "耗负责人的 ChatGPT 额度"],
    "each_cover_goes_through_the_existing_drawing_and_checks": [
        "AI 感检查", "手和动作检查", "真实包装", "逐字核对", "干净重出", "打字字体", "一次一张"],
    "covers_page_built_by_the_command_with_arguments_and_exit_codes": [
        "python3 skills/builtin/xhs-reference-visual/scripts/plan_page.py covers --plan", "--images-folder", "-o",
        "cover-A", "封面对比页.html", "退出码 0", "退出码 2", "什么也不写"],
    "covers_page_has_the_three_covers_side_by_side_labelled_with_each_row_unchanged": [
        "并排", "标着 A、B、C", "逐字复制", "相对路径"],
    "no_other_card_before_the_pick": ["用户选定之前", "其他任何一张卡都不画"],
    "after_the_pick_it_is_the_sets_cover_recorded_with_its_date_and_the_others_are_marked": [
        "选定的封面就是这套的封面", "他选中的封面", "记入批准记录", "没选的两张留在磁盘上", "标明没选"],
    "pack_wording_stays_out": ["不读、不列、不报包装上印的字"],
    "out_of_scope_stays_with_its_own_issues": ["issue 99", "issue 89", "issue 90"],
}


def _covers_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert COVERS_START in text, "the skill has no three-covers step"
    return text.split(COVERS_START, 1)[1].split("\n\n", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_88_SKILL))
def test_the_three_covers_step_requires_the_issue_88_behaviours(behaviour):
    block = _covers_block()
    for need in ISSUE_88_SKILL[behaviour]:
        assert need in block, f"the three-covers step does not say: {need}"


def test_the_three_covers_step_replaces_the_single_sample_step_everywhere_in_the_skill_text():
    for path in (SKILL_DIR / "SKILL.md", PLAN_PAGE_REF, ICON_REF, COVERS_REF):
        text = _text(path) if path.is_file() else ""
        assert "先做一张小样" not in text, path.name
        assert "这张小样的版面计划" not in text, path.name


def test_the_plan_page_section_tells_the_set_plan_to_carry_the_cover_directions_table():
    block = _plan_page_block()
    assert "封面方向" in block and "references/photo-scene-cover-versions.md" in block


@pytest.mark.parametrize("behaviour", sorted(ISSUE_88_REF))
def test_the_cover_versions_reference_requires_the_issue_88_behaviours(behaviour):
    assert COVERS_REF.is_file(), "references/photo-scene-cover-versions.md does not exist"
    text = _text(COVERS_REF)
    for need in ISSUE_88_REF[behaviour]:
        assert need in text, f"the cover-versions reference does not say: {need}"


def test_the_plan_page_reference_fixes_the_cover_directions_table_with_its_rules():
    text = _text(PLAN_PAGE_REF)
    for need in ("## 封面方向", "| 方向 | 借的图集 | 角度 | 取景 | 领头 | 撞上的卡和改法 |", "A、B、C", "不足三套",
                 "同一个图集", "角度、取景和领头"):
        assert need in text, f"the plan-page reference does not say: {need}"




def test_the_skill_text_cites_the_vendored_one_sample_lines_it_overrides_as_they_are_shipped():
    block = _covers_block()
    for line in ("可在同体系内提供至多三个微变体", "只给风格名：提供三个同风格变体，等确认。", "先一张代表性小样，用户审核后扩展",
                 "先制作一张有代表性的小样，用户审核后再展开套系或整页", "先做小样，用户审核后扩展"):
        assert line in block, line


def test_issue_88_wording_adds_no_line_that_reads_the_pack_text():
    for path in (SKILL_DIR / "SKILL.md", COVERS_REF, PLAN_PAGE_REF):
        text = _text(path) if path.is_file() else ""
        for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
            assert banned not in text, (path.name, banned)


# issue 89: The owner's step 4, second half. On the cover the owner picks, before any other card is drawn, the skill offers two separate
# picks in order, typeface A/B/C first and then styling A/B/C of the picked typeface; the three typefaces differ in letter
# form, each styling states colour, outline, fill and decoration, plain heavy black strokes are never offered (The owner's words
# quoted); typed options are set by code with nothing drawn, hand-drawn options are Codex drawings that wait for the user's
# yes naming how many; the pick is written into the set plan's lettering line (typed: typed-styling.json, issue 81's record
# check unchanged; hand-drawn: the picked cover's lettering is the reference). The old "the plan fixes one lettering system
# alone" wording is gone. The detail is in references/photo-scene-lettering-picks.md because SKILL.md is at its 200-line
# limit. Same assertions as wrapper.test.py beside the skill.
LETTERING_REF = SKILL_DIR / "references" / "photo-scene-lettering-picks.md"
LETTERING_BULLET_START = "- 选定封面之后、其他任何一张卡画之前（issue 89）"
RO_FONT_QUOTE = (
    "")
RO_THREE_MORE_QUOTE = (
    "")
RO_BLACK_QUOTE = ""
OLD_LETTERING_WORDING = "计划为整套定一种字体体系，取自选定的主参考和团队设计记忆"
ISSUE_89_BULLET = {
    "after_the_cover_is_picked_and_before_any_other_card_is_drawn": ["选定封面之后", "其他任何一张卡画之前"],
    "two_separate_picks_in_order_never_one_menu_of_nine": [
        "分两步", "先选字体 A/B/C/D", "再在选定的字体上选样式 A/B/C/D", "不并成一张九选一的菜单"],
    "the_three_typefaces_differ_in_letter_form": ["字形不同", "不是一种字体换颜色或换粗细"],
    "each_styling_states_colour_outline_fill_and_decoration": ["颜色、描边、填充、装饰"],
    "plain_heavy_black_strokes_are_never_offered_with_ros_words": [
        "纯粗黑笔画", "永不作为样式出现", RO_BLACK_QUOTE],
    "typed_options_are_set_by_code_on_the_cover_with_the_title_area_clear_and_nothing_drawn": [
        "打字字体", "由代码设", "标题区留空", "不画图"],
    "hand_drawn_options_are_codex_drawings_that_wait_for_the_users_yes_naming_how_many": [
        "手绘", "Codex", "只改字", "等用户的 yes", "写明画几张"],
    "the_pick_is_written_into_the_set_plans_lettering_line_typed_also_into_the_stored_styling": [
        "写进套系计划的字体体系一行", "typed-styling.json"],
    "the_detail_is_in_the_reference_file": ["references/photo-scene-lettering-picks.md"],
}
ISSUE_89_LETTERING_LINE = [
    "由负责人在选定的封面上选", "只是选项的来源", "打字字体", "手绘", "写进每一张的提示词", "默认字体",
    "small plain rectangular label boxes"]
ISSUE_89_REF = {
    "ros_words_word_for_word": [
        RO_FONT_QUOTE, RO_THREE_MORE_QUOTE, RO_BLACK_QUOTE, "Photo-scene post images follow one approval process",
        "第 4 步"],
    "after_the_cover_pick_before_any_other_card_in_two_separate_steps_in_order": [
        "选定封面之后", "其他任何一张卡画之前", "第一步：字体 A/B/C/D", "第二步：样式 A/B/C/D", "不并成一张九选一的菜单"],
    "typefaces_differ_in_letter_form_drawn_from_the_installed_typed_fonts_and_the_design_memory_families": [
        "字形不同", "两种粗细或一种字体换颜色不算", "Noto Serif CJK SC", "Noto Sans CJK SC", "LXGW WenKai",
        "<资料包目录>/file/DESIGN-MEMORY.md", "圆润粗笔/细笔手写", "有干刷和飞白感的白色笔字",
        "厚重无衬线大标题", "打字（", "手绘（"],
    "all_options_side_by_side_on_the_same_picked_cover_so_only_the_lettering_differs": [
        "并排", "标 A、B、C、D", "同一张选定的封面", "只有字不同"],
    "each_styling_states_colour_outline_fill_and_decoration_and_colours_avoid_the_other_table_rows": [
        "颜色、描边、填充、装饰", "不得是颜色和层级对应表里别的行的颜色"],
    "plain_heavy_black_strokes_are_defined_and_refused_like_the_system_default_fonts": [
        "纯粗黑笔画", "黑色或接近黑色", "没有颜色、没有另一种颜色的描边、没有装饰", "和拒绝系统默认字体一样"],
    "typed_options_are_set_by_code_on_the_clear_cover_with_nothing_drawn_and_need_no_permission": [
        "text_on_image.py", "标题区留空", "不画图", "不用问", "免费"],
    "hand_drawn_options_are_codex_drawings_that_change_only_the_lettering_and_wait_for_the_users_yes": [
        "Codex", "只改字", "已批准的卡", "--base-image", "用问题工具问", "写明要画几张", "ChatGPT 额度"],
    "a_mixed_answer_is_built_as_one_new_option_and_shown_once_more": ["混着选", "新做成一个选项", "再给用户看一次"],
    "the_pick_comes_only_from_the_users_own_reply": ["用户自己的回复", "沉默", "不替他选"],
    "the_pick_is_written_to_the_set_plans_lettering_line": ["写进套系计划的字体体系一行", "set-plan.md"],
    "typed_pick_becomes_the_stored_styling_and_issue_81s_record_check_passes_unchanged": [
        "typed-styling.json", "font_file", "fill", "outline_width", "outline_color", "shadow", "sizes",
        "--check-records", "照旧通过"],
    "hand_drawn_pick_makes_the_picked_covers_lettering_the_reference_and_a_differing_card_fails": [
        "选定封面上的字", "字体和风格参考", "套系并排检查", "这张卡不合格"],
    "the_design_memory_text_is_only_the_source_of_the_options": ["只是选项的来源", "不是计划自己做的决定"],
    "pack_wording_stays_out": ["不读、不列、不报包装上印的字"],
    "out_of_scope_stays_with_its_own_issues": ["issue 99", "issue 81", "issue 91", "issue 96"],
}
DESIGN_MEMORY_LETTERING_LINE = (
    "字体至少有三类，不能一律归为同一种手写体：圆润粗笔/细笔手写（01—04、10—12）；有干刷和飞白感的白色笔字（05—07、09）；"
    "厚重无衬线大标题（08、13—14）。")


def _lettering_bullet() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert LETTERING_BULLET_START in text, "the covers step has no lettering-picks bullet"
    assert LETTERING_BULLET_START in _covers_block(), "the lettering-picks bullet is not inside the covers step"
    return LETTERING_BULLET_START + text.split(LETTERING_BULLET_START, 1)[1].split("\n", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_89_BULLET))
def test_the_covers_step_offers_the_lettering_picks_with_the_issue_89_behaviours(behaviour):
    bullet = _lettering_bullet()
    for need in ISSUE_89_BULLET[behaviour]:
        assert need in bullet, f"the lettering-picks bullet does not say: {need}"


def test_the_set_plans_lettering_line_is_picked_by_ro_and_no_longer_decided_by_the_plan_alone():
    lines = [ln for ln in _text(SKILL_DIR / "SKILL.md").splitlines() if ln.startswith("- 字体体系")]
    assert len(lines) == 1, lines
    for need in ISSUE_89_LETTERING_LINE:
        assert need in lines[0], f"the set plan's lettering line does not say: {need}"
    assert OLD_LETTERING_WORDING not in _text(SKILL_DIR / "SKILL.md")


@pytest.mark.parametrize("behaviour", sorted(ISSUE_89_REF))
def test_the_lettering_picks_reference_requires_the_issue_89_behaviours(behaviour):
    assert LETTERING_REF.is_file(), "references/photo-scene-lettering-picks.md does not exist"
    text = _text(LETTERING_REF)
    for need in ISSUE_89_REF[behaviour]:
        assert need in text, f"the lettering-picks reference does not say: {need}"


def test_the_lettering_picks_reference_does_not_bring_back_the_plan_decides_wording():
    assert LETTERING_REF.is_file(), "references/photo-scene-lettering-picks.md does not exist"
    assert OLD_LETTERING_WORDING not in _text(LETTERING_REF)




def test_issue_89_wording_adds_no_line_that_reads_the_pack_text():
    for path in (SKILL_DIR / "SKILL.md", LETTERING_REF):
        text = _text(path) if path.is_file() else ""
        for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
            assert banned not in text, (path.name, banned)


# issue 121: The owner, 2026-10-28. Each lettering pick (typeface, then styling) shows four options A to D: the lettering the cover
# already carries as the original (原版), then three new ones; the original is never redrawn and is not counted in the
# drawings asked about; the covers are shown carrying the plan's lettering. Same assertions as wrapper.test.py.
ISSUE_121_QUOTE = (
    "")
ISSUE_121_BULLET = {
    "four options A to D for each pick, A the original": ["原版", "四个选项", "A 到 D"],
    "the original is never redrawn": ["不重画"],
}
ISSUE_121_REF = {
    "The owner's words word for word": [ISSUE_121_QUOTE],
    "four options A to D for each pick": ["各是四选一", "A 到 D", "A 是原版"],
    "the original at the typeface pick is the picked cover's own lettering as shown in the cover comparison": [
        "选项 A 是选定封面自带的字", "封面对比里给用户看的样子"],
    "the original at the styling pick is the lettering as picked in the typeface step": ["选项 A 是上一步选定的字"],
    "the original is not redrawn and not counted in the hand-drawn drawings asked about": ["不重画", "不算在手绘的张数里"],
    "the covers are shown carrying the plan's lettering": ["三个封面都带计划里的字", "手绘的封面自带它的字"],
    "picking the original at both steps leaves the cover as it is": ["两步都选原版", "封面的字原样不动", "typed-styling.json"],
}
ISSUE_121_COVERS = ["原版加三个新的", "手绘的封面自带它的字"]
ISSUE_121_GONE = "手绘的字也留出来"
ISSUE_121_CLAUDE_MD = [ISSUE_121_QUOTE, "the original plus three new"]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_121_BULLET))
def test_the_lettering_picks_bullet_offers_the_original_plus_three_new(behaviour):
    bullet = _lettering_bullet()
    for need in ISSUE_121_BULLET[behaviour]:
        assert need in bullet, f"the lettering-picks bullet does not say: {need}"


@pytest.mark.parametrize("behaviour", sorted(ISSUE_121_REF))
def test_the_lettering_picks_reference_requires_the_issue_121_behaviours(behaviour):
    text = _text(LETTERING_REF)
    for need in ISSUE_121_REF[behaviour]:
        assert need in text, f"the lettering-picks reference does not say: {need}"


def test_the_lettering_picks_reference_no_longer_leaves_hand_drawn_lettering_off_the_covers():
    assert ISSUE_121_GONE not in _text(LETTERING_REF)


def test_the_cover_versions_reference_says_the_covers_carry_their_lettering():
    text = _text(COVERS_REF)
    for need in ISSUE_121_COVERS:
        assert need in text, f"the cover-versions reference does not say: {need}"




# issue 90: The owner's step 4, last sentence. Once the cover and the lettering are picked, the remaining cards are drawn straight
# through in plan order with no stop for the user between cards, every per-card check still runs and a failed card is
# redrawn clean without asking, then the whole set is shown on a page (plan_page.py set) before delivery; delivered cards
# stay one file each; approval of the page makes the set approved (issue 91's words). SKILL.md is at its 200-line limit, so
# it only points; the detail is in references/photo-scene-set-page.md. Same assertions as wrapper.test.py beside the skill.
SET_PAGE_REF = SKILL_DIR / "references" / "photo-scene-set-page.md"
RO_STEP_4_SENTENCE = ""
ISSUE_90_SKILL_LINES = {
    "- 选定封面之后、其他任何一张卡画之前（issue 89）": ['中间不停下来问用户', 'photo-scene-set-page.md'],
    "- 【整套，按级】套系并排检查（成套时必做）": ['套系并排检查（成套时必做）', '整套并排页', '再交付', 'photo-scene-set-page.md'],
}
ISSUE_90_REF = {
    "ros_step_4_sentence_word_for_word": [
        "Photo-scene post images follow one approval process",
        "第 4 步"
    ],
    "released_by_the_plan_page_approval_plus_both_picks_with_no_new_ask": [
        "封面和字体都选定之后",
        "用户已批准的计划页",
        "不再问用户",
        "不需要另外要一个 yes"
    ],
    "drawn_in_plan_order_one_at_a_time_with_no_stop_between_cards": [
        "顺序",
        "一张接一张画完",
        "中间不停下来问用户",
        "不在两张卡之间等批准"
    ],
    "each_card_follows_the_picked_direction": [
        "选定的封面当字体和风格参考",
        "typed-styling.json"
    ],
    "every_per_card_check_still_runs_and_a_failed_card_is_redrawn_clean_without_asking": [
        "每一张卡的检查照常做",
        "一项不省",
        "重出，不用问用户",
        "还没批准",
        "`## 如实`"
    ],
    "set_checks_run_after_the_last_card": [
        "最后一张画完",
        "套系并排检查",
        "打字字体一致检查",
        "人物检查"
    ],
    "the_whole_set_is_shown_on_a_page_before_delivery": [
        "plan_page.py set --plan",
        "整套并排页.html",
        "outputs/",
        "相对路径",
        "原样照抄",
        "读者的问题",
        "未通过检查"
    ],
    "the_page_command_exit_codes_and_stop_on_a_card_with_no_image": [
        "退出码 0",
        "退出码 2",
        "点出这张卡的名字",
        "不猜、不跳过"
    ],
    "the_location_goes_to_the_user_and_the_skill_stops": [
        "把页面的位置交给用户，然后停下"
    ],
    "delivered_cards_stay_one_file_each_never_a_contact_sheet": [
        "每张卡一个文件",
        "不做联系表",
        "逐张独立输出"
    ],
    "approval_of_the_page_makes_the_set_approved_by_issue_91": [
        "用户批准整套页",
        "记入批准记录",
        "日期",
        "issue 91",
        "他并排看过整套后批准的那一套"
    ],
    "changes_before_approval_redraw_the_named_cards_and_rebuild_the_page": [
        "只重画被点名的卡",
        "重建这张页，再给用户看一次"
    ],
    "pack_wording_stays_out": [
        "不读、不列、不报包装上印的字"
    ]
}


@pytest.mark.parametrize("start", sorted(ISSUE_90_SKILL_LINES))
def test_skill_md_points_to_the_set_page_step_from_the_lettering_bullet_and_the_set_check(start):
    text = _text(SKILL_DIR / "SKILL.md")
    assert start in text, start
    line = start + text.split(start, 1)[1].split("\n", 1)[0]
    for need in ISSUE_90_SKILL_LINES[start]:
        assert need in line, f"{start} does not say: {need}"


@pytest.mark.parametrize("behaviour", sorted(ISSUE_90_REF))
def test_the_set_page_reference_requires_the_issue_90_behaviours(behaviour):
    assert SET_PAGE_REF.is_file(), "references/photo-scene-set-page.md does not exist"
    text = _text(SET_PAGE_REF)
    for need in ISSUE_90_REF[behaviour]:
        assert need in text, f"the set-page reference does not say: {need}"


def test_ros_step_4_sentence_is_in_the_skill_text_word_for_word():
    assert RO_STEP_4_SENTENCE in _text(SKILL_DIR / "SKILL.md")
    assert SET_PAGE_REF.is_file() and RO_STEP_4_SENTENCE in _text(SET_PAGE_REF)


def test_skill_md_stays_within_200_lines_after_issue_90():
    assert len(_text(SKILL_DIR / "SKILL.md").splitlines()) <= 200


def test_issue_90_wording_adds_no_line_that_reads_the_pack_text():
    for path in (SKILL_DIR / "SKILL.md", SET_PAGE_REF):
        text = _text(path) if path.is_file() else ""
        for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
            assert banned not in text, (path.name, banned)


# issue 118: The owner, 2026-10-28, "Why need to ask me???". The set's place comes from what the post is about (fitness: a gym,
# everyday life: a lived-in room, work or commuting: work or the commute, travel or outdoors: the trip), with the ordinary
# things found there, derived and never asked. The product still gives each card's small moment; the 3-prop cap and the
# stock-prop refusal cover only the objects in that small action, and the place's ordinary things are not props. One place
# per set replaces one home per set (The owner's override of the playbook's 明显不同背景 line stands, the vendored line is
# unchanged). The prompt names the place and its ordinary things and refuses a line that strips the place bare. The
# scene-and-props check fails a card in the wrong place and a bare showroom-like place where the studied sets show a
# lived-in one, with no redraw cap. The detail is in references/photo-scene-setting.md because SKILL.md is at its
# 200-line limit; the old closing section of references/photo-scene-realism.md now records the owner's answer. Same
# assertions as wrapper.test.py beside the skill.
SETTING_REF = SKILL_DIR / "references" / "photo-scene-setting.md"
RO_SETTING_SENTENCE = (
    "")
POST_04_BARE_LINE = "No skincare bottles, no mug, no plants, no books, no laptop, no phone, no decor objects."
SCENE_START = "**场景和道具（issue 77"
ISSUE_118_PLACE = {
    "place_from_the_post_topic_with_ros_sentence_word_for_word": [
        "地方从帖子主题来，小事从商品来", "issue 118", RO_SETTING_SENTENCE],
    "the_four_places_by_topic": [
        "健身帖是健身房", "日常生活帖是有生活气的房间", "工作或通勤帖是工作的地方或通勤路上", "旅行或户外帖是旅途或户外"],
    "derived_by_the_plan_never_asked_of_the_user_or_ro": ["由计划自己推出", "从不问用户，也不问负责人"],
    "a_topic_that_fits_none_gets_its_place_from_this_posts_studied_sets": [
        "这四类都不是的，地方取自这篇帖子自己研究的图集"],
    "ordinary_things_from_studied_sets_by_file_name_are_setting_not_props": [
        "普通东西", "点名文件名", "它们是场景，不是道具，不占下面的 3 件"],
    "detail_file_is_named": ["references/photo-scene-setting.md"],
    "three_prop_cap_and_stock_prop_refusal_cover_only_the_small_actions_objects": [
        "只管这张卡小动作里用到的东西", "地方里普通的东西不在这条之内", "每件道具都证明这张卡的小动作", "计划里一律拒绝"],
    "tidy_and_no_mirror_stay": ["整洁", "除非用户要求，不出现镜子"],
}
ISSUE_118_GONE = [
    "场景从商品来，不从帖子主题或参考图来", "商品真正属于的仪式或地方", "哪个家、哪个角落、哪个日常时刻",
    "不是随便哪个能放下它的台面", "同一个家里场景", "整套只在一个家里场景", "不在同一个房间", "场景按这篇帖子的主题选",
]
ISSUE_118_ONE_PLACE = [
    "同一个地方：整套只在一个地方", "一个健身房、一个家、一处工作或通勤、一趟旅行", "换角落、台面、机位和主体，不换地方",
    "最后几张不跳到新的世界", "换的是角落和主体，不是地方"]
ISSUE_118_DRAWING = [
    "每张有人的卡，提示词写明这套的地方和它的普通东西", "看得见的描述", POST_04_BARE_LINE,
    "除非这篇帖子研究的图集显示的地方就是光的", "photo-scene-setting.md", "提示词写明这张卡的道具", "不加其他道具"]
ISSUE_118_CHECK = [
    "删掉商品测试", "不证明这张卡小动作的道具", "道具指这张卡小动作里的东西", "地方里的普通东西不数",
    "卡上的地方不是这套的地方", "地方光秃、像样板间", "研究的图集显示的是有生活气的地方", "重出没有次数上限",
    "不读、不列、不报包装上印的字"]
ISSUE_118_REF = {
    "ros_sentence_word_for_word_and_where_it_is_recorded": [
        RO_SETTING_SENTENCE, "Photo-scene post images follow one approval process", "issue 118"],
    "the_four_places_with_the_ordinary_things_found_there": [
        "## 健身", "器械", "橡胶地面", "## 日常生活", "床", "灯", "架子", "## 工作或通勤", "桌子", "车座",
        "## 旅行或户外", "步道", "酒店房间"],
    "a_topic_that_fits_none_gets_its_place_from_the_posts_own_sets_never_asked": [
        "这四类都不是", "这篇帖子自己研究的图集", "从不问"],
    "ordinary_things_are_the_setting_not_props_and_do_not_count_toward_the_three": [
        "不是道具", "它们是场景，不是道具", "只管这张卡小动作里用到的东西"],
    "the_proposals_are_marked_as_claudes_for_ros_read_through": ["Claude 的提议", "负责人通读"],
    "one_place_per_set": ["一个健身房、一个家、一处工作或通勤、一趟旅行", "明显不同背景"],
    "a_bare_place_line_is_refused_with_post_04s_lines_as_the_example": [
        POST_04_BARE_LINE, "remove all unnecessary clutter and decoration", "光秃",
        "除非这篇帖子研究的图集显示的地方就是光的"],
    "two_new_fail_outcomes_and_the_existing_outcomes_with_no_redraw_cap": [
        "卡上的地方不是这套的地方", "地方光秃、像样板间", "干净重出", "已批准卡的修改", "如实报告", "重出没有次数上限", "issue 101"],
    "pack_wording_stays_out": ["不读、不列、不报包装上印的字"],
}


def _scene_block() -> str:
    text = _text(SKILL_DIR / "SKILL.md")
    assert SCENE_START in text, "the set plan has no scene-and-props section"
    return text.split(SCENE_START, 1)[1].split("**手和动作（issue 79", 1)[0]


@pytest.mark.parametrize("behaviour", sorted(ISSUE_118_PLACE))
def test_scene_section_requires_the_issue_118_place_from_the_post_topic_behaviours(behaviour):
    block = _scene_block()
    for need in ISSUE_118_PLACE[behaviour]:
        assert need in block, f"the scene-and-props section does not say: {need}"


def test_wrapper_no_longer_says_the_scene_comes_from_the_product_or_the_set_stays_in_one_home():
    text = _text(SKILL_DIR / "SKILL.md")
    for gone in ISSUE_118_GONE:
        assert gone not in text, gone


def test_the_place_from_the_post_topic_is_required_before_the_drawing_step():
    text = _text(SKILL_DIR / "SKILL.md")
    assert 0 <= text.find("地方从帖子主题来，小事从商品来") < text.find("**出图（只走 Codex")


def test_the_whole_set_stays_in_one_place_and_the_step_story_default_keeps_it():
    text = _text(SKILL_DIR / "SKILL.md")
    block = text.split("**手和动作（issue 79", 1)[-1].split("**人物的摄影说明", 1)[0]
    for need in ISSUE_118_ONE_PLACE:
        assert need in block, need
    assert "同一个地方，每张换一个新主体" in text


def test_drawing_step_names_the_place_and_its_ordinary_things_and_refuses_a_bare_place_line():
    drawing = _drawing_step()
    for need in ISSUE_118_DRAWING:
        assert need in drawing, need


def test_scene_and_props_check_fails_the_wrong_place_and_a_bare_place_and_never_counts_the_places_things():
    line = [ln for ln in _text(SKILL_DIR / "SKILL.md").splitlines() if ln.startswith("- 【一、二级】场景和道具检查")]
    assert line, "the delivery check has no scene-and-props check"
    for need in ISSUE_118_CHECK:
        assert need in line[0], need


def test_side_by_side_check_fails_a_card_outside_the_sets_one_place():
    assert "不在同一个地方" in _side_by_side_block()


def test_reading_order_carries_ros_override_as_one_place_for_the_whole_set():
    reading = _reading_order()
    assert "整套一个地方" in reading and "明显不同背景" in reading


@pytest.mark.parametrize("behaviour", sorted(ISSUE_118_REF))
def test_setting_reference_requires_the_issue_118_behaviours(behaviour):
    assert SETTING_REF.is_file(), "references/photo-scene-setting.md does not exist"
    text = _text(SETTING_REF)
    for need in ISSUE_118_REF[behaviour]:
        assert need in text, f"the setting reference does not say: {need}"


def test_realism_reference_no_longer_says_ro_has_not_answered_and_records_his_answer():
    text = _text(REALISM_REF)
    for gone in ("负责人还没回答", "道具规则一个字不动"):
        assert gone not in text, gone
    for need in (RO_SETTING_SENTENCE, "photo-scene-setting.md"):
        assert need in text, need


def test_issue_118_wording_never_asks_the_pack_text_to_face_the_camera_or_be_legible():
    for path in (SKILL_DIR / "SKILL.md", SETTING_REF):
        if not path.is_file():
            continue
        text = _text(path)
        for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
            assert banned not in text, (path.name, banned)


def test_skill_md_stays_within_the_200_line_limit_after_issue_118():
    assert len(_text(SKILL_DIR / "SKILL.md").splitlines()) <= 200


# issue 119: The owner, 2026-10-28. The installed fonts are the starting set; when the A/B/C typeface options need a letter form
# none of them has, the agent installs ONE free font with scripts/install_font.py, from a pinned address, only when the
# font's own licence file is the SIL Open Font License 1.1 or the Apache License 2.0, and does not ask the owner just to install.
# A font offered as an option counts as used, nothing is installed in bulk, the set plan's lettering line records the
# font's source and licence. The typed-font line says it in place (SKILL.md is at its 200-line limit); the detail is in
# references/photo-scene-lettering-picks.md. The code is checked by install-font.test.py (run below) and by
# skills/builtin/xhs-note-creator/typed-text.test.py (run above). Same assertions as wrapper.test.py beside the skill.
RO_FONT_LIBRARY_QUOTE = (
    "")
RO_KEEP_LIGHT_QUOTE = (
    "")
ISSUE_119_FONT_LINE = [
    "只用免费字体", "已装的是起点", "skills/builtin/xhs-reference-visual/scripts/install_font.py", "按需装",
    "/usr/local/share/fonts/on-demand/", "一次只装一个", "OFL 1.1 或 Apache 2.0", "不用为了装而问负责人",
    "没有许可合格的字体合适才问负责人", "系统默认字体", "[photo-scene-lettering-picks.md](references/photo-scene-lettering-picks.md)"]
ISSUE_119_REF = {
    "ros_two_quotes_word_for_word": [RO_FONT_LIBRARY_QUOTE, RO_KEEP_LIGHT_QUOTE],
    "where_to_look_first_then_the_curated_lists_as_leads_only_always_from_a_pinned_address": [
        "google/fonts", "ofl/<名字>/", "固定到一个提交", "从不用 main", "jaywcjlove/free-font",
        "kevchentw/awesome-chinese-fonts", "只是找候选的地方", "不从清单下载"],
    "the_fonts_own_licence_must_be_one_of_the_two_anything_else_is_refused_and_goes_to_ro": [
        "SIL Open Font License 1.1", "Apache License 2.0", "免费商用", "什么也不装", "问负责人"],
    "one_font_file_per_call_never_in_bulk_no_font_library_kept": ["一次只装一个字体文件", "不批量装", "不留字体库"],
    "a_font_offered_as_an_option_counts_as_used_and_stays_installed_if_not_picked": [
        "作为 A/B/C 的一个选项给负责人看，就算用上了", "不删"],
    "the_set_plans_lettering_line_records_the_fonts_source_and_licence": ["套系计划的字体体系一行", "来源和许可证"],
    "the_command_where_it_installs_what_it_records_and_running_it_twice": [
        "install_font.py", "/usr/local/share/fonts/on-demand/", "source.json", "sha256", "already done", "同名"],
    "the_word_setter_finds_the_font_by_its_bare_file_name": ["text_on_image.py", "按文件名"],
    "pack_wording_stays_out": ["不读、不列、不报包装上印的字"],
}


def test_the_typed_font_line_says_a_free_font_is_installed_on_demand_under_the_licence_rule():
    lines = [ln for ln in _typed_plan_block().splitlines() if ln.startswith("- 字体：")]
    assert len(lines) == 1, lines
    for need in ISSUE_119_FONT_LINE:
        assert need in lines[0], f"the typed-font line does not say: {need}"


def test_the_old_ask_ro_and_never_install_wording_is_gone():
    text = _text(SKILL_DIR / "SKILL.md")
    for gone in ("没有合适的就问负责人，不自己装", "不自己装"):
        assert gone not in text, gone
    assert "再装更多打字字体：这是负责人另外的决定" not in _text(LETTERING_REF)


@pytest.mark.parametrize("behaviour", sorted(ISSUE_119_REF))
def test_the_lettering_picks_reference_requires_the_issue_119_behaviours(behaviour):
    text = _text(LETTERING_REF)
    for need in ISSUE_119_REF[behaviour]:
        assert need in text, f"the lettering-picks reference does not say: {need}"


def test_the_install_command_code_test_passes():
    # stand-in downloader and a temporary install root: nothing touches the network or this PC's fonts
    proc = subprocess.run([sys.executable, str(SKILL_DIR / "install-font.test.py")], capture_output=True, text=True,
                          timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_issue_119_wording_adds_no_line_that_reads_the_pack_text():
    for path in (SKILL_DIR / "SKILL.md", LETTERING_REF):
        text = _text(path)
        for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
            assert banned not in text, (path.name, banned)


def test_skill_md_stays_within_the_200_line_limit_after_issue_119():
    assert len(_text(SKILL_DIR / "SKILL.md").splitlines()) <= 200


# issue 98: a one-line memory point per cover direction. Same assertions as wrapper.test.py beside the skill.
MEMORY_FILE = "references/photo-scene-memory-point.md"
ISSUE_98 = {
    "the directions table definition has the memory-point column": (
        "references/photo-scene-plan-page.md", ["| 撞上的卡和改法 | 记忆点 |", "一行中文", "看到的东西加上它对读者意味着什么", "不是口号"]),
    "one line per direction, written with the directions table before the plan page and before any cover is drawn": (
        MEMORY_FILE, ["每个方向有一行", "和方向表一起写", "在建计划页之前", "在画任何一张封面之前"]),
    "the picked direction's line is recorded as the cover's memory point, later cards get none": (
        "references/photo-scene-cover-versions.md", ["原样记下选定方向的记忆点", "作为这套封面的记忆点", "后面的卡没有记忆点"]),
    "it differs from the reader question": (MEMORY_FILE, ["读者的问题", "记忆点是看完封面之后留下什么"]),
    "Lovart's line word for word, marked untested, source named": (
        MEMORY_FILE, ["如果只看 5 秒，会记住什么？", "还没有在 Easel 里试过", "缺口表 T1", "Lovart 的文件没有拿进来"]),
    "no reading of the pack's printed words": (MEMORY_FILE, ["不依据真包装上印的字"]),
}


@pytest.mark.parametrize("behaviour", sorted(ISSUE_98))
def test_issue_98_memory_point_behaviours(behaviour):
    rel, wanted = ISSUE_98[behaviour]
    text = _text(SKILL_DIR / rel)
    for need in wanted:
        assert need in text, f"{rel} does not say: {need}"


def test_issue_98_skill_links_the_memory_point_reference_and_stays_within_200_lines():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "references/photo-scene-memory-point.md" in text
    assert len(text.splitlines()) <= 200


def test_issue_98_memory_point_reference_never_asks_the_pack_text_to_face_the_camera_or_be_legible():
    text = _text(SKILL_DIR / "references/photo-scene-memory-point.md")
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰"):
        assert banned not in text, banned

# issue 99: screen cover directions, mixed picks. Same assertions as wrapper.test.py beside the skill.
SCREEN_FILE = "references/photo-scene-cover-screening.md"
ISSUE_99 = {
    "the three declared axes in the owner's words, stated in the plan above the directions table": (
        SCREEN_FILE, ["三个轴：角度、取景、领头", "套系计划自己不挑别的轴"]),
    "at least five written candidates, each naming a studied set from this post's own study, none drawn": (
        SCREEN_FILE, ["至少五个候选", "候选方向", "这篇帖子自己的主题研究", "一个也不画"]),
    "a candidate that differs only by colour, background colour, pose, a small crop or a style label is dropped with a line": (
        SCREEN_FILE, ["只差在颜色、背景色、姿势、小幅裁切或风格标签", "丢掉", "写一行", "太像"]),
    "three kept from three different sets, every pair differing on angle, framing and lead, each with its how-it-differs line": (
        SCREEN_FILE, ["三个不同的图集", "两两", "角度、取景和领头三样都不同", "和另外两个怎么不同"]),
    "the stop when it cannot be met, the rule not relaxed": (
        SCREEN_FILE, ["不足三套", "凑不出三个", "告诉用户，然后停下", "不放宽"]),
    "a mixed pick is written as one new row and drawn once": (
        SCREEN_FILE, ["混合选择", "一行新的方向", "A+C", "取自哪一个", "记下日期", "只画一次", "--mix"]),
    "the picked covers are never joined, overlaid, cut together or used as the image to edit": (
        SCREEN_FILE, ["不拼合、不叠加、不剪接", "不当作要改的图", "用户接受了才成为这套的封面"]),
    "the plan-page reference has the new column, the axes line and the candidates table": (
        "references/photo-scene-plan-page.md", ["| 记忆点 | 和另外两个怎么不同 |", "三个轴：", "候选方向", "不上计划页"]),
    "the cover-versions reference points to the screening and the mixed pick": (
        "references/photo-scene-cover-versions.md", ["photo-scene-cover-screening.md", "--mix"]),
    "the override of the team's in-style variants": (
        "SKILL.md", ["PLAYBOOK.md:17-18", "不适用于封面方向", "photo-scene-cover-screening.md"]),
    "no reading of the pack's printed words": (SCREEN_FILE, ["不依据真包装上印的字"]),
}


@pytest.mark.parametrize("behaviour", sorted(ISSUE_99))
def test_issue_99_screening_and_mixed_pick_behaviours(behaviour):
    rel, wanted = ISSUE_99[behaviour]
    path = SKILL_DIR / rel
    assert path.is_file(), f"{rel} does not exist"
    text = _text(path)
    for need in wanted:
        assert need in text, f"{rel} does not say: {need}"


def test_issue_99_ros_step_4_sentence_is_in_the_skill_word_for_word_and_the_skill_links_the_screening_reference():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "references/photo-scene-cover-screening.md" in text
    assert len(text.splitlines()) <= 200




def test_issue_99_screening_reference_never_asks_the_pack_text_to_face_the_camera_or_be_legible():
    path = SKILL_DIR / SCREEN_FILE
    assert path.is_file()
    text = _text(path)
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
        assert banned not in text, banned


# issue 100: a fixed order for the delivery checks, structure before surface. Same assertions as wrapper.test.py beside the skill.
ORDER_REF = SKILL_DIR / "references" / "photo-scene-check-order.md"
ORDER_SINGLE = [  # (level, the check's name right after its level tag)
    ("一", "真实包装只用眼睛看"), ("一", "人物和身份检查"), ("二", "手和动作检查"), ("二", "人物和画面真实感检查"),
    ("三", "逐字核对 Easel 自己加到图上的每个字"), ("三", "打字字体一致检查"), ("三", "颜色和层级检查"), ("三", "图标检查"),
]
ORDER_MIXED = {  # check name: (prefix tag, [(fail sign, its level)])
    "场景和道具检查": ("【一、二级】", [("删掉商品测试", "一"), ("不证明这张卡小动作的道具", "二"), ("地方光秃", "二")]),
    "AI 感检查": ("【二、三级】", [("眼睛没有第一个落点", "二"), ("发脏的米色", "三"), ("强烈的颜色铺满", "三"),
                              ("发雾发闷", "三"), ("同一种颗粒感", "三")]),
    "套系并排检查": ("【整套，按级】", [("字不按它的版面计划放", "一"), ("包装在不止一张卡上是主角", "一"),
                                   ("两张卡构图重复", "二"), ("不在同一个地方", "二"), ("特写没有写明用途", "二"),
                                   ("字体和封面、参考图不一致", "三"), ("一个颜色在整套里用在了两个层级上", "三"),
                                   ("整套里有清单以外的图标", "三")]),
}
ISSUE_100_SKILL = ["先结构后表面", "一级 产品和版面", "二级 构图", "三级 字和颜色", "photo-scene-check-order.md",
                   "最高那一级"]
ISSUE_100_REF = {
    "the order and the three levels": ["先结构后表面", "一级 产品和版面", "二级 构图", "三级 字和颜色", "从上往下做",
                                       "读像素尺寸不算一级，是做检查之前的前提"],
    "repair at the highest failing level first": ["在最高的那一级修", "改正过的提示词针对那一级",
                                                  "低级的问题写进这张卡的提示词文件", "重出之后再检查"],
    "every check runs again from level 1 after a redraw": ["每次重出之后，所有检查从一级重新做"],
    "a level 1 or 2 failure never passes by a level 3 change only": [
        "一级或二级不合格的卡，只改三级（字、字体、打字字体的样式、颜色）不算合格"],
    "the typed-font words-only reset": ["打字字体的整套只重设字（不重画底图）", "只在一级和二级都合格时才可以"],
    "the set check follows the same order": ["套系并排检查也按这个顺序", "一级或二级不合格的整套不交付", "字怎么改都不行"],
    "the redraw routes are unchanged and there is no cap": [
        "没有批准的卡照干净重出办", "已批准的卡照“已批准卡的修改”办", "重出没有次数上限", "这一条只决定先修哪一个问题"],
    "later checks state their level": ["之后新加的检查，要写明自己属于哪一级"],
    "no reading of the pack's printed words": ["不读、不列、不报包装上印的字"],
}


def _issue_100_failures() -> list[str]:
    failures: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    ref100 = ORDER_REF.read_text(encoding="utf-8") if ORDER_REF.is_file() else ""
    for what, needles in ISSUE_100_REF.items():
        for need in needles:
            if need not in ref100:
                failures.append(f"issue 100: references/photo-scene-check-order.md does not state {what}: missing {need}")
    for need in ISSUE_100_SKILL:
        if need not in text:
            failures.append(f"issue 100: SKILL.md does not say: {need}")
    if text.count("先结构后表面") != 1:
        failures.append(f"issue 100: the order is stated {text.count('先结构后表面')} times in SKILL.md, not once")
    deliv = text.split("**交付前检查实际图片**", 1)[-1]
    dlines = deliv.splitlines()
    if not (0 <= deliv.find("先结构后表面") < deliv.find("\n- 用 `python3 skills/shared/scripts/image_ops.py info")):
        failures.append("issue 100: the order is not stated before the first check bullet")
    at = {}
    for lvl, name in ORDER_SINGLE:
        hits = [i for i, ln in enumerate(dlines) if ln.startswith(f"- 【{lvl}级】{name}")]
        if len(hits) != 1:
            failures.append(f"issue 100: {name} is not one bullet tagged level {lvl}")
        else:
            at[name] = (lvl, hits[0])
    for lvl_a, lvl_b in (("一", "二"), ("二", "三")):
        for a, (la, ia) in at.items():
            for b, (lb, ib) in at.items():
                if la == lvl_a and lb == lvl_b and ia > ib:
                    failures.append(f"issue 100: level {la} check {a} comes after level {lb} check {b}")
    for name, (prefix, signs) in ORDER_MIXED.items():
        hits = [i for i, ln in enumerate(dlines) if ln.startswith(f"- {prefix}{name}")]
        if len(hits) != 1:
            failures.append(f"issue 100: {name} is not one bullet tagged {prefix}")
            continue
        start = hits[0]
        end = next((j for j in range(start + 1, len(dlines)) if dlines[j].startswith("- ")), len(dlines))
        block = "\n".join(dlines[start:end])
        segs = re.split(r"[。；\n]", block)
        seen = []
        for sign, lvl in signs:
            seg = next((s.strip(" -") for s in segs if sign in s), None)
            if seg is None:
                failures.append(f"issue 100: {name} lost the fail sign {sign}")
                continue
            tagged = re.search(r"【([一二三])级】", seg)
            if not tagged or tagged.group(1) != lvl or seg.find(tagged.group(0)) > seg.find(sign):
                failures.append(f"issue 100: in {name} the fail sign {sign} is not tagged level {lvl}")
            seen.append(lvl)
        if seen != sorted(seen, key="一二三".index):
            failures.append(f"issue 100: in {name} the fail signs are not in level order")
    p = {n: next((i for i, ln in enumerate(dlines) if ln.startswith(f"- {pre}{n}")), -1) for n, (pre, _) in ORDER_MIXED.items()}
    if not (at.get("人物和身份检查", ("", -1))[1] < p["场景和道具检查"] < at.get("手和动作检查", ("", 99))[1]
            < p["AI 感检查"] < at.get("人物和画面真实感检查", ("", 99))[1]):
        failures.append("issue 100: the mixed scene and AI-look checks are not placed between their levels' checks")
    if not (at.get("图标检查", ("", -1))[1] < p["套系并排检查"] < next((i for i, ln in enumerate(dlines) if ln.startswith("- 交付时写明")), -1)):
        failures.append("issue 100: the set-level side-by-side check is not after the per-card checks and before the delivery note")
    if "先结构后表面" in text and "最高那一级" in text:
        drawing100 = text.split("**出图（只走 Codex", 1)[-1].split("**交付前检查实际图片**", 1)[0]
        if drawing100.count("最高那一级") < 2:
            failures.append("issue 100: the clean-redraw and approved-card rules do not both point to the highest failing level")
    if len(text.splitlines()) > 200:
        failures.append(f"issue 100: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
    for banned in ("正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "最多重出", "重出两次", "重出三次"):
        if banned in ref100 or banned in deliv.split("先结构后表面", 1)[0][-400:]:
            failures.append(f"issue 100: wording that reads the pack text or caps redraws: {banned}")

    return failures


def test_issue_100_the_delivery_checks_run_in_one_stated_order_structure_before_surface():
    failures = _issue_100_failures()
    assert not failures, "\n".join(failures)


# issue 103: leak check after drawing. Same assertions as wrapper.test.py beside the skill.
def _issue_103_failures() -> list[str]:
    failures: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    ORDER_REF = SKILL_DIR / "references" / "photo-scene-check-order.md"
    LEAK_REF = SKILL_DIR / "references" / "photo-scene-leak-check.md"
    LEAK_REF_NEEDS = {
        "the six fail signs": ["学过的帖子或团队参考图里的品牌名、Logo、商品或包装", "学过的帖子或参考图里的功效、评分、前后对比", "学过的帖子或参考图里的人物、脸或角色",
                               "徽章、贴纸、口味标或照搬整个版面", "A/B/C 对比页上的标签、方向说明", "上一张卡或作为风格参考传入的封面上的字"],
        "the comparison": ["提示词文件里记录的每一张传入的图", "上一张画好的卡", "并排"],
        "the four not-a-leak cases": ["--identity-image", "--base-image", "这张卡自己确认过的字", "替换模式"],
        "the board is never an input": ["对比页", "拼在一起的图", "从不传给 Codex", "选定封面自己的文件"],
        "failed cards": ["干净重出", "已批准的卡", "如实报告", "不能当合格交付", "写进这张卡的检查记录"],
        "levels": ["一级", "三级"],
        "eye check and no pack wording": ["用眼睛", "不读、不列、不报包装上印的字"],
    }
    LEAK_SIGNS = [("学过的帖子或团队参考图里的品牌", "一"), ("学过的帖子或参考图里的人物", "一"), ("徽章、贴纸、口味标", "一"),
                  ("学过的帖子或参考图里的功效", "三"), ("上一张卡或作为风格参考传入的封面上的字", "三")]
    if True:
        refl = LEAK_REF.read_text(encoding="utf-8") if LEAK_REF.is_file() else ""
        for what, needles in LEAK_REF_NEEDS.items():
            for need in needles:
                if need not in refl:
                    failures.append(f"issue 103: references/photo-scene-leak-check.md does not state {what}: missing {need}")
        delivl = text.split("**交付前检查实际图片**", 1)[-1]
        segl = next((s for s in delivl.splitlines() if "【一、三级】泄漏检查" in s), "")
        if not segl:
            failures.append("issue 103: the delivery section has no leak check tagged 【一、三级】")
        if segl and "photo-scene-leak-check.md" not in segl:
            failures.append("issue 103: the leak check does not link photo-scene-leak-check.md")
        if segl and ("不读、不列、不报包装上印的字" not in segl or "用眼睛" not in segl):
            failures.append("issue 103: the leak check is not an eye check that leaves the pack's printed words alone")
        for sign, lvl in LEAK_SIGNS:
            tag = re.search(r"【([一二三])级】[^【。；]*" + re.escape(sign), refl)
            if not tag or tag.group(1) != lvl:
                failures.append(f"issue 103: in the leak reference the fail sign {sign} is not tagged level {lvl}")
        ordl = ORDER_REF.read_text(encoding="utf-8") if ORDER_REF.is_file() else ""
        if "泄漏检查" not in ordl:
            failures.append("issue 103: photo-scene-check-order.md does not place the leak check")
        drawl = text.split("**出图（只走 Codex", 1)[-1].split("**交付前检查实际图片**", 1)[0]
        if "对比页" not in drawl or "从不传给 Codex" not in drawl:
            failures.append("issue 103: the drawing step does not say the cover-comparison board is never passed to Codex")
        if len(text.splitlines()) > 200:
            failures.append(f"issue 103: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
        for banned in ("读包装上印的字", "列出包装上的字", "核对包装上的字", "最多重出", "重出两次"):
            if banned in refl:
                failures.append(f"issue 103: wording that reads the pack text or caps redraws: {banned}")
    return failures


def test_issue_103_leak_check_after_drawing():
    failures = _issue_103_failures()
    assert not failures, "\n".join(failures)


# issue 104: safe margin. Same assertions as wrapper.test.py beside the skill.
def _issue_104_failures() -> list[str]:
    failures: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    ORDER_REF = SKILL_DIR / "references" / "photo-scene-check-order.md"
    MARGIN_REF = SKILL_DIR / "references" / "photo-scene-safe-margin.md"
    MARGIN_NEEDS = {
        "the margin, per side and per axis": ["左右各留宽度的 5%", "上下各留高度的 5%", "1086×1448", "54 px", "72 px", "A/B/C 封面", "小样", "已批准卡的修改"],
        "the layout plan places whole blocks": ["整块字的范围（描边和阴影都算在内）", "不只是中心点"],
        "the prompt rule": ["主体、手绘的字和涂鸦都留在边距里面", "打字字的区域（issue 81）也留在边距里面"],
        "the word setter refuses": ["set_typed_words()", "退出码不是 0", "不写成图", "5% 写死在代码里"],
        "the subject and its three exceptions": ["套系计划里写明的主体", "整个露出来的真实包装", "人的头和脸", "进画面的方向", "很小或只露一角", "场景本身"],
        "an eye check at full size": ["用眼睛，全尺寸看", "靠眼睛"],
        "the redraw routes, no cap": ["干净重出办（issue 78）", "已批准卡的修改”办（issue 91）", "重出没有次数上限"],
        "levels": ["【二级】主体", "【三级】手绘的字或涂鸦"],
        "no reading of the pack's printed words": ["不读、不列、不报包装上印的字"],
    }
    if True:
        refm = MARGIN_REF.read_text(encoding="utf-8") if MARGIN_REF.is_file() else ""
        for what, needles in MARGIN_NEEDS.items():
            for need in needles:
                if need not in refm:
                    failures.append(f"issue 104: references/photo-scene-safe-margin.md does not state {what}: missing {need}")
        if "photo-scene-safe-margin.md" not in text.split("**版面计划", 1)[-1].split("**出图", 1)[0]:
            failures.append("issue 104: the layout-plan block does not link the safe margin")
        drawm = text.split("**出图（只走 Codex", 1)[-1].split("**交付前检查实际图片**", 1)[0]
        if "photo-scene-safe-margin.md" not in drawm or "5% 安全边距" not in drawm:
            failures.append("issue 104: the drawing step does not ask Codex to keep subject and hand-drawn lettering inside the margin")
        delivm = text.split("**交付前检查实际图片**", 1)[-1]
        segm = next((s for s in delivm.splitlines() if "【二、三级】安全边距检查" in s), "")
        if not segm:
            failures.append("issue 104: the delivery section has no safe-margin check tagged 【二、三级】")
        if segm and ("photo-scene-safe-margin.md" not in segm or "用眼睛" not in segm or "不读包装上印的字" not in segm
                     or "issue 78" not in segm or "issue 91" not in segm):
            failures.append("issue 104: the safe-margin check is not an eye check that links the reference and the redraw routes")
        if "安全边距检查" not in (ORDER_REF.read_text(encoding="utf-8") if ORDER_REF.is_file() else ""):
            failures.append("issue 104: photo-scene-check-order.md does not place the safe-margin check")
        if len(text.splitlines()) > 200:
            failures.append(f"issue 104: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
        for banned in ("读包装上印的字", "列出包装上的字", "核对包装上的字", "最多重出", "重出两次"):
            if banned in refm.replace("不读、不列、不报包装上印的字", ""):
                failures.append(f"issue 104: wording that reads the pack text or caps redraws: {banned}")
    return failures


def test_issue_104_safe_margin():
    failures = _issue_104_failures()
    assert not failures, "\n".join(failures)


# issue 106: dark pack separation. Same assertions as wrapper.test.py beside the skill.
def _issue_106_failures() -> list[str]:
    failures: list[str] = []
    HERE = SKILL_DIR
    text = _text(SKILL_DIR / "SKILL.md")
    ORDER_REF = SKILL_DIR / "references" / "photo-scene-check-order.md"
    DARK_REF = HERE / "references" / "photo-scene-dark-pack.md"
    DARK_NEEDS = {
        "the plan records whether the pack is dark": ["深色包装", "主体是黑色或很深的颜色", "套系计划里写一次", "浅色包装不受影响"],
        "two controls, one light and one edge": ["至少两个办法", "至少一个光的办法", "至少一个边的办法", "后面更浅的面", "暖色主光", "更浅的中性背景", "边缘光", "边缘高光", "沿轮廓的反光"],
        "the plan and the prompt name them": ["这张卡的计划和提示词都写明", "缺这两样的深色包装卡不去画"],
        "the check at full size and thumbnail size": ["深色包装分离检查", "原尺寸", "手机缩略图", "image_ops.py thumbnail", "只看包装的轮廓和它周围的光", "描不出", "这张卡不合格"],
        "the fix through scene light or surfaces by the existing routes": ["场景的光或表面", "干净重出办（issue 78）", "已批准卡的修改”办（issue 91）", "如实报告", "不能当合格交付", "重出没有次数上限"],
        "the refused fixes": ["改包装本身的颜色或提亮", "包装外面画描边或光圈", "整个画面发光", "缩小、裁掉、转向或藏起包装"],
        "the level": ["【一级】"],
        "no reading of the pack's printed words": ["不读、不列、不报包装上印的字"],
    }
    if True:
        refd = DARK_REF.read_text(encoding="utf-8") if DARK_REF.is_file() else ""
        for what, needles in DARK_NEEDS.items():
            for need in needles:
                if need not in refd:
                    failures.append(f"issue 106: references/photo-scene-dark-pack.md does not state {what}: missing {need}")
        plan106 = next((s for s in text.splitlines() if s.startswith("- 计划写明这篇帖子的主题研究")), "")
        if "深色包装（issue 106）" not in plan106 or "photo-scene-dark-pack.md" not in plan106:
            failures.append("issue 106: the set-plan line does not record whether the pack is dark and link the reference")
        draw106 = text.split("**出图（只走 Codex", 1)[-1].split("**干净重出", 1)[0]
        if "深色包装（issue 106）" not in draw106 or "一个光的办法和一个边的办法" not in draw106:
            failures.append("issue 106: the drawing step does not make the prompt name a light control and an edge control")
        deliv106 = text.split("**交付前检查实际图片**", 1)[-1]
        seg106 = next((s for s in deliv106.splitlines() if s.startswith("- 【一级】真实包装只用眼睛看")), "")
        for need in ("深色包装分离检查（issue 106）", "原尺寸", "缩略图", "issue 78", "issue 91", "不读、不列、不报包装上印的字", "photo-scene-dark-pack.md"):
            if need not in seg106:
                failures.append(f"issue 106: the level-1 real-pack check does not carry the dark-pack separation check: missing {need}")
        if "深色包装分离检查" not in (ORDER_REF.read_text(encoding="utf-8") if ORDER_REF.is_file() else ""):
            failures.append("issue 106: photo-scene-check-order.md does not place the dark-pack separation check")
        if len(text.splitlines()) > 200:
            failures.append(f"issue 106: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
        new106 = refd + plan106.split("深色包装（issue 106）")[-1] + draw106.split("深色包装（issue 106）")[-1] + seg106.split("深色包装分离检查（issue 106）")[-1]
        for banned in ("读包装上印的字", "列出包装上的字", "核对包装上的字", "正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字", "最多重出", "重出两次"):
            if banned in new106.replace("不读、不列、不报包装上印的字", ""):
                failures.append(f"issue 106: wording that reads the pack text or caps redraws: {banned}")
    return failures


def test_issue_106_dark_pack_separation():
    failures = _issue_106_failures()
    assert not failures, "\n".join(failures)


def _issue_107_failures() -> list[str]:
    failures: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    ORDER_REF = SKILL_DIR / "references" / "photo-scene-check-order.md"
    PACKFACE_REF = SKILL_DIR / "references" / "photo-scene-pack-faces.md"
    PACKFACE_NEEDS = {
        "the real-pack-photo list": ["真实包装照片清单", "这套用到的每一张", "它拍的是哪个商品", "正面、背面、左侧、右侧、顶面、斜侧面", "只用眼睛", "看形状和颜色", "不读、不列、不报包装上印的字"],
        "each card with the pack names a photo and a face": ["不是“不出现”的卡", "点名清单里的一张照片和它露出的面", "只能画这张照片露出的面", "镜头只能移到不露出照片里看不到的面", "没有点名照片的卡不去画", "点名的面照片里没有的卡不去画"],
        "the stop-and-ask": ["先把每张卡配到清单里有的面", "确实需要清单里没有的面", "出图之前停下", "用问题工具问用户", "商品、缺的那个面和这张卡", "补一张那个面的照片（推荐）", "这张卡改成清单里有的面", "这张卡不放包装", "没有“照样画出来”这个选项", "不画猜出来的面"],
        "the drawing step passes the photo": ["点名的那张照片作为这张卡的商品图", "第一个 `--image`"],
        "the delivery check": ["包装的面检查", "和它点名的照片并排", "照片里没有的面", "背面、侧边折角或顶部封口", "这张卡不合格", "形状和颜色", "issue 78", "issue 91", "如实报告", "不能当合格交付", "不要求把包装转过来、放大或让印的字读得清"],
        "the cover directions": ["封面方向", "同样的限制"],
        "the level": ["【一级】"],
    }

    ref = PACKFACE_REF.read_text(encoding="utf-8") if PACKFACE_REF.is_file() else ""
    for what, needles in PACKFACE_NEEDS.items():
        for need in needles:
            if need not in ref and need not in text:
                failures.append(f"issue 107: the pack-faces rule does not state {what}: missing {need}")
    plan = next((s for s in text.splitlines() if s.startswith("- 计划写明这篇帖子的主题研究")), "")
    if "包装的面（issue 107）" not in plan or "photo-scene-pack-faces.md" not in plan:
        failures.append("issue 107: the set-plan line does not carry the pack-face rule and link the reference")
    draw = text.split("**出图（只走 Codex", 1)[-1].split("**干净重出", 1)[0]
    if "包装的面（issue 107）" not in draw or "第一个 `--image`" not in draw:
        failures.append("issue 107: the drawing step does not pass the named photo as the first --image")
    deliv = text.split("**交付前检查实际图片**", 1)[-1]
    seg = next((s for s in deliv.splitlines() if s.startswith("- 【一级】真实包装只用眼睛看")), "")
    for need in ("包装的面检查（issue 107）", "issue 78", "issue 91", "photo-scene-pack-faces.md"):
        if need not in seg:
            failures.append(f"issue 107: the level-1 real-pack check does not carry the pack-face check: missing {need}")
    if "包装的面检查" not in (ORDER_REF.read_text(encoding="utf-8") if ORDER_REF.is_file() else ""):
        failures.append("issue 107: photo-scene-check-order.md does not place the pack-face check")
    if "这一条只看场景，不看包装的大小、角度和包装上的字是否清楚" not in text:
        failures.append("issue 107: the scene-and-props sentence about pack angle was changed")
    if len(text.splitlines()) > 200:
        failures.append(f"issue 107: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
    new = ref + plan.split("包装的面（issue 107）")[-1] + draw.split("包装的面（issue 107）")[-1] + seg.split("包装的面检查（issue 107）")[-1]
    for banned in ("读包装上印的字", "列出包装上的字", "核对包装上的字", "正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字", "照样画出来的选项", "最多重出", "重出两次"):
        if banned in new.replace("不读、不列、不报包装上印的字", "").replace("没有“照样画出来”这个选项", "").replace("不要求把包装转过来、放大或让印的字读得清", ""):
            failures.append(f"issue 107: wording that reads the pack text or caps redraws: {banned}")
    return failures


def test_issue_107_pack_faces_from_real_photos():
    failures = _issue_107_failures()
    assert not failures, "\n".join(failures)


def _issue_108_failures() -> list[str]:
    failures: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    ORDER_REF = SKILL_DIR / "references" / "photo-scene-check-order.md"
    WRAPPER = SKILL_DIR / "SKILL.md"
    LAYER_REF = SKILL_DIR / "references" / "photo-scene-real-pack-layer.md"
    LAYER_NEEDS = {
        "the count": ["真实包装图层（issue 108）", "第一次画不算重出", "其他原因不合格的不计入", "写进每一版保存的提示词文件", "干净重出和已批准卡的修改两条路都算"],
        "the switch": ["失败的重出到 2 次", "下一次画这张卡改用真实包装图层", "不再让 Codex 重画包装"],
        "the scene layer": ["场景层", "不画包装和商品", "留一块干净平整的表面", "不以商品图的角色传入", "--style-image"],
        "the pack layer": ["remove_bg.py remove", "点名的那张真实商品照", "只等比缩放和平移", "不改色、不变形、不转向、不重画", "image_ops.py place", "接触阴影", "背离光的一侧"],
        "the layer order": ["先场景，再包装图层，最后（打字字体的整套）打字字", "手绘的字和涂鸦留在 Codex 画的场景里"],
        "the hand-held stop-and-ask": ["手托着、打开或倒出包装", "停下", "用问题工具问用户", "这张卡改成包装放在手旁边的台面上（推荐）", "这张卡不放包装", "再让 Codex 重画一次"],
        "the layered-card check": ["真实包装图层检查（issue 108）", "包装放在表面上，不是悬空", "影子落在背离场景光的一侧", "包装的大小合适这个场景", "抠出的边缘干净，没有白边或残留的背景", "Codex 没有多画第二个或半个包装", "只看形状和光", "【一级】"],
        "the records": ["场景层（贴包装和打字字之前）", "用了哪张照片、位置、缩放、阴影设置", "同一份记录再放一次"],
        "the delivery note": ["这张卡的包装是代码放进去的真实商品照片"],
        "the go-ahead": ["采用前需确认可用工具及授权", "负责人的这条规则就是这个授权"],
    }
    if WRAPPER.is_file():
        ref108 = LAYER_REF.read_text(encoding="utf-8") if LAYER_REF.is_file() else ""
        if not ref108:
            failures.append("issue 108: references/photo-scene-real-pack-layer.md does not exist")
        for what, needles in LAYER_NEEDS.items():
            for need in needles:
                if need not in ref108 and need not in text:
                    failures.append(f"issue 108: the real-pack-layer rule does not state {what}: missing {need}")
        draw108 = text.split("**出图（只走 Codex", 1)[-1].split("**干净重出", 1)[0]
        clean108 = text.split("**干净重出", 1)[-1].split("**已批准卡的修改", 1)[0]
        edit108 = text.split("**已批准卡的修改", 1)[-1].split("**交付前检查实际图片**", 1)[0]
        deliv108 = text.split("**交付前检查实际图片**", 1)[-1]
        seg108 = next((s for s in deliv108.splitlines() if s.startswith("- 【一级】真实包装只用眼睛看")), "")
        for name, part in (("the drawing step", draw108), ("the clean-redraw section", clean108), ("the approved-card edit section", edit108), ("the level-1 real-pack check", seg108)):
            if "issue 108" not in part or "photo-scene-real-pack-layer.md" not in part:
                failures.append(f"issue 108: {name} does not carry the real-pack-layer rule and link the reference")
        cap108 = next((s for s in clean108.splitlines() if s.startswith("- 重出没有次数上限")), "")
        if "重出没有次数上限" not in text or "真实包装图层（issue 108）" not in cap108 or "其他原因" not in cap108:
            failures.append("issue 108: the redraw-limit line is gone or has no pack exception beside it")
        if "真实包装图层检查" not in (ORDER_REF.read_text(encoding="utf-8") if ORDER_REF.is_file() else ""):
            failures.append("issue 108: photo-scene-check-order.md does not place the real-pack-layer check")
        if len(text.splitlines()) > 200:
            failures.append(f"issue 108: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
        new108 = ref108 + cap108.split("真实包装图层（issue 108）")[-1] + draw108.split("真实包装图层（issue 108）")[-1] + seg108.split("真实包装图层检查（issue 108）")[-1]
        for banned in ("读包装上印的字", "列出包装上的字", "核对包装上的字", "放大比对", "包装放大", "正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字", "最多重出", "重出两次"):
            if banned in new108.replace("不读、不列、不报包装上印的字", ""):
                failures.append(f"issue 108: wording that reads the pack text or caps redraws: {banned}")
    return failures


def test_issue_108_real_pack_layer_when_codex_alters_the_pack():
    failures = _issue_108_failures()
    assert not failures, "\n".join(failures)


def _issue_109_failures() -> list[str]:
    failures: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    ORDER_REF = SKILL_DIR / "references" / "photo-scene-check-order.md"
    STATE_REF = SKILL_DIR / "references" / "photo-scene-product-states.md"
    STATE_NEEDS = {
    "the state-source list": ["真实状态来源清单", "这个品牌自己商品", "商品除了闭合包装之外的任何状态", "品牌商品照片、品牌的商品详情页或品牌图、团队给这个品牌的参考、品牌账号自己以前的帖子", "别的品牌的帖子不算状态来源", "仍可以参考这一步的构图"],
    "each state card names a source": ["显示状态的卡", "点名清单里的一个来源", "颜色、质地、清澈度、包装里面", "没有点名来源的卡不去画", "不显示状态的卡不受影响"],
    "the stop-and-ask": ["确实需要清单里没有的状态", "出图之前停下", "用问题工具问用户", "商品、缺的那个状态和这张卡", "补一张那个状态的照片（推荐）", "这张卡改成不显示这个状态", "删掉这张卡", "没有“照样画出来”这个选项", "不画猜出来的状态"],
    "the drawing step passes the source": ["--state-image", "只借状态", "不借它的场景、道具、人物、手、字", "商品图在前"],
    "the delivery check": ["状态检查", "和它点名的来源并排", "颜色、质地或清澈度明显不同", "这张卡不合格", "issue 78", "issue 91", "如实报告", "不能当合格交付", "【一级】"],
    }
    ref = STATE_REF.read_text(encoding="utf-8") if STATE_REF.is_file() else ""
    if not ref:
        failures.append("issue 109: references/photo-scene-product-states.md does not exist")
    for what, needles in STATE_NEEDS.items():
        for need in needles:
            if need not in ref and need not in text:
                failures.append(f"issue 109: the product-state rule does not state {what}: missing {need}")
    plan = next((s for s in text.splitlines() if s.startswith("- 默认走“封面加步骤故事”")), "")
    if "真实状态来源（issue 109）" not in plan or "photo-scene-product-states.md" not in plan:
        failures.append("issue 109: the cover-plus-step-story line does not carry the state-source rule and link the reference")
    if "默认走“封面加步骤故事”：只有封面是设计过的；后面每张是一个真实的下一步照片（这个商品的使用顺序里一个接一个的小动作），每张一句短文案，小而朴素的框；同一个地方，每张换一个新主体。只有研究的参考图集显示另一种排法时才换，并在计划里写明依据是哪几套。" not in text:
        failures.append("issue 109: the cover-plus-step-story sentence was changed")
    reaction = next((s for s in text.splitlines() if s.startswith("  - 物体的反应")), "")
    if "真实状态来源（issue 109）" not in reaction:
        failures.append("issue 109: the object-reaction item does not carry the state-source rule")
    draw = text.split("**出图（只走 Codex", 1)[-1].split("**干净重出", 1)[0]
    if "真实状态来源（issue 109）" not in draw or "--state-image" not in draw:
        failures.append("issue 109: the drawing step does not pass the named source as --state-image")
    deliv = text.split("**交付前检查实际图片**", 1)[-1]
    seg = next((s for s in deliv.splitlines() if s.startswith("- 【一级】真实包装只用眼睛看")), "")
    for need in ("状态检查（issue 109）", "issue 78", "issue 91", "photo-scene-product-states.md"):
        if need not in seg:
            failures.append(f"issue 109: the level-1 real-pack check does not carry the state check: missing {need}")
    if "状态检查" not in (ORDER_REF.read_text(encoding="utf-8") if ORDER_REF.is_file() else ""):
        failures.append("issue 109: photo-scene-check-order.md does not place the state check")
    if len(text.splitlines()) > 200:
        failures.append(f"issue 109: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
    new = ref + plan.split("真实状态来源（issue 109）")[-1] + reaction.split("真实状态来源（issue 109）")[-1] + draw.split("真实状态来源（issue 109）")[-1] + seg.split("状态检查（issue 109）")[-1]
    for banned in ("读包装上印的字", "列出包装上的字", "核对包装上的字", "放大", "正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字", "照样画出来的选项", "最多重出", "重出两次"):
        if banned in new.replace("不读、不列、不报包装上印的字", "").replace("没有“照样画出来”这个选项", ""):
            failures.append(f"issue 109: wording that reads the pack text or caps redraws: {banned}")
    return failures


def test_issue_109_product_states_from_real_photos():
    failures = _issue_109_failures()
    assert not failures, "\n".join(failures)


def _issue_111_failures() -> list[str]:
    failures: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    APPROVALS_REF = SKILL_DIR / "references" / "photo-scene-approvals.md"
    NEEDS = {
        "one record per post beside the set plan": ["每篇帖子一份批准记录", "approvals.json", "套系计划 `set-plan.md` 旁边"],
        "only the user's own reply makes an entry": ["只有用户自己的回复", "Easel 自己的检查合格，从来不记成一条"],
        "issue 91 reads approved from the record": ["什么算已批准：记录里有一条有效的，就是已批准", "放不上的卡，按没有批准办"],
        "the check runs before a card is used as approved and before delivery": [
            "先跑 `check`，再用", "`--base-image` 之前", "建整套页之前", "交付之前", "交付说明里写是哪几张"],
        "approvals are no longer written into the set plan": ["不再写进套系计划", "只写进这一份"],
        "a voided entry stays on record and a new version never inherits": ["记录只加不删", "从不继承批准", "最后批准的那张图仍在记录里"],
        "The owner's step 5 sentence": [],
        "the Lovart line": ["确认结果逐资产记录；修改或重生成会使旧确认失效。"],
        "the pack wording stays out": ["不读、不列、不报包装上印的字"],
    }
    ref = APPROVALS_REF.read_text(encoding="utf-8") if APPROVALS_REF.is_file() else ""
    if not ref:
        failures.append("issue 111: references/photo-scene-approvals.md does not exist")
    for what, items in NEEDS.items():
        for need in items:
            if need not in ref:
                failures.append(f"issue 111: the approval rule does not state {what}: missing {need}")
    if "references/photo-scene-approvals.md" not in text:
        failures.append("issue 111: SKILL.md does not link references/photo-scene-approvals.md")
    if text.count("approvals.py check") < 3 or "记入批准记录" not in text:
        failures.append("issue 111: SKILL.md does not run the check before the set page, a base image and delivery, or does not record to the record")
    if not (SKILL_DIR / "scripts" / "approvals.py").is_file():
        failures.append("issue 111: scripts/approvals.py does not exist")
    if len(text.splitlines()) > 200:
        failures.append(f"issue 111: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
    for banned in ("读包装上印的字", "列出包装上的字", "核对包装上的字"):
        if banned in ref.replace("不读、不列、不报包装上印的字", ""):
            failures.append(f"issue 111: wording that reads the pack text: {banned}")
    return failures


def test_issue_111_approvals_recorded_per_card():
    failures = _issue_111_failures()
    assert not failures, "\n".join(failures)


def _issue_112_failures() -> list[str]:
    failures: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    REF112 = SKILL_DIR / "references" / "photo-scene-card-brief.md"
    NEEDS112 = {
        "two parts in order": ["第一部分：用户的原话", "第二部分：Easel 追加的", "按这个顺序，不能颠倒"],
        "the user's words whole and untranslated, with who and when": ["整句", "一字不改", "不翻译", "谁说的和哪一天"],
        "each addition names its source": ["每一条追加的要求写明来源", "套系计划", "研究过的图集", "资料包", "没通过的检查"],
        "Claude's suggestions stay suggestions": ["Claude 的建议", "仍然标成建议", "不挪进用户的原话"],
        "a style word limits only what it names": ["只管它点名的那一项", "不扩大成对颜色、道具、人物、版面的禁令", "团队资料包里固定的那句去 AI 感的话，写在第二部分"],
        "one brief per card": ["一张卡一份说明", "不是第二份设计方案"],
        "saved prompt file holds both parts": ["每一张卡的每一版", "两部分都照发出去的样子存进提示词文件", "首次出图、干净重出、已批准卡的修改"],
        "issues 91 and 110 are instances": ["issue 91", "issue 110", "不是例外"],
        "on-image text list stays the only text source": ["逐字清单", "唯一来源"],
        "Lovart sentence 1": ["保留用户原始 Brief，同时追加有证据的执行约束；不要创建第二份设计方案。"],
        "Lovart sentence 2": ["用户说柔光、自然、克制，只约束光线/材质/装饰等已表达维度"],
        "the pack wording stays out": ["不读、不列、不报包装上印的字"],
    }
    ref112 = REF112.read_text(encoding="utf-8") if REF112.is_file() else ""
    if not ref112:
        failures.append("issue 112: references/photo-scene-card-brief.md does not exist")
    for what, items in NEEDS112.items():
        for need in items:
            if need not in ref112:
                failures.append(f"issue 112: the card-brief rule does not state {what}: missing {need}")
    for need in ("追加有证据的执行约束", "只约束光线/材质/装饰等已表达维度", "不要创建第二份设计方案"):
        if need not in ref112:
            failures.append(f"issue 112: the Lovart words are not quoted word for word: {need}")
    if "references/photo-scene-card-brief.md" not in text:
        failures.append("issue 112: SKILL.md does not link references/photo-scene-card-brief.md")
    for marker in ('--prompt "<按 EXECUTION-BRIEF', "每一版保存的提示词文件写明传入了哪几张图", "每一版保存的提示词文件，除了写明传入了哪几张图"):
        line = next((l for l in text.splitlines() if marker in l), "")
        if "issue 112" not in line or "用户的原话" not in line:
            failures.append(f"issue 112: the line with {marker!r} does not carry the two-part rule")
    if len(text.splitlines()) > 200:
        failures.append(f"issue 112: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
    for banned in ("读包装上印的字", "列出包装上的字", "核对包装上的字", "正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字"):
        if banned in ref112.replace("不读、不列、不报包装上印的字", ""):
            failures.append(f"issue 112: wording that reads the pack text: {banned}")
    return failures


def test_issue_112_ro_words_verbatim_in_the_card_brief():
    failures = _issue_112_failures()
    assert not failures, "\n".join(failures)


ISSUE_113_REF_NEEDS = {
    "at least five visible features, praise words refused": ["至少五项", "在画好的图上看得见", "可爱", "灵动", "高级", "lively", "不算"],
    "the three dials with their Chinese names and levels": ["字形压扁程度", "笔画松紧度", "基线波浪起伏强度", "无 / 轻 / 中 / 强", "一句话"],
    "the baseline dial capped at slight, quoting the design memory": ["最多是轻", "轻微倾角", "不靠逐字乱转和不齐基线"],
    "one reference per lettering style with the lend line": ["只有一张参考图", "图 N 只用来定<哪一块字>的<哪几项特征>，不借它的字、版面、颜色、商品和人物", "一张图可以同时是两个字体样式的参考"],
    "the approved cover is the reference for later cards": ["负责人批准封面之后", "已批准的封面", "后面每一张卡"],
    "the plan missing any part is not finished": ["缺任何一部分", "不画任何一张卡", "打字字体的整套不受影响"],
    "every prompt carries features, dials and the lend line, copied from the plan": ["每一张有 Codex 手绘字的卡", "特征、档位和借用句", "照计划原样抄", "提示词对照版面计划的检查"],
    "the reference uses a style-reference slot, the script is unchanged": ["两个风格参考位", "图片脚本不改"],
    "the set check fails a card missing a feature or overshooting a dial": ["套系并排检查", "漏了计划写的特征", "超过计划写的档位", "干净重出", "已批准卡的修改", "用眼睛"],
    "scope: typed, doodles and containers unchanged": ["issue 81", "涂鸦", "笔刷底", "不变"],
    "the pack wording stays out": ["不读、不列、不报包装上印的字"],
}
ISSUE_113_SKILL_LINES = {
    "字体体系": ["issue 113", "photo-scene-lettering-brief.md", "至少五项", "字形压扁程度", "笔画松紧度", "基线波浪起伏强度", "缺任何一部分"],
    "写完提示词，对着这张卡的版面计划查一遍": ["issue 113", "特征、档位和借用句"],
    "每张图的角色由脚本补进提示词": ["issue 113", "两个风格参考位", "图片脚本不改"],
    "【整套，按级】套系并排检查": ["【三级】", "issue 113", "漏了计划写的特征", "超过计划写的档位"],
}
ISSUE_113_BANNED = ("读包装上印的字", "列出包装上的字", "核对包装上的字", "正对镜头", "朝向镜头", "面向镜头", "字清晰可读", "字要清晰", "包装字")


def _issue_113_failures() -> list[str]:
    FAILS: list[str] = []
    text = _text(SKILL_DIR / "SKILL.md")
    REF113 = SKILL_DIR / "references" / "photo-scene-lettering-brief.md"
    SKILL_ROOT = SKILL_DIR
    ref113 = REF113.read_text(encoding="utf-8") if REF113.is_file() else ""
    if not ref113:
        FAILS.append("issue 113: references/photo-scene-lettering-brief.md does not exist")
    for what, items in ISSUE_113_REF_NEEDS.items():
        for need in items:
            if need not in ref113:
                FAILS.append(f"issue 113: the lettering brief does not state {what}: missing {need}")
    for marker, items in ISSUE_113_SKILL_LINES.items():
        line = next((l for l in text.splitlines() if marker in l), "")
        for need in items:
            if need not in line:
                FAILS.append(f"issue 113: the SKILL.md line with {marker!r} does not say: {need}")
    if "(references/photo-scene-lettering-brief.md)" not in text:
        FAILS.append("issue 113: SKILL.md does not link references/photo-scene-lettering-brief.md")
    memory = (SKILL_ROOT / "references" / "vendor" / "file" / "DESIGN-MEMORY.md").read_text(encoding="utf-8")
    for quoted in ("轻微倾角", "不靠逐字乱转和不齐基线"):
        if quoted not in memory:
            FAILS.append(f"issue 113: the design memory no longer says: {quoted}")
    order = (SKILL_ROOT / "references" / "photo-scene-check-order.md").read_text(encoding="utf-8")
    if "手绘字的形态检查" not in order:
        FAILS.append("issue 113: photo-scene-check-order.md does not list the lettering-form check on level 3")
    if len(text.splitlines()) > 200:
        FAILS.append(f"issue 113: SKILL.md is {len(text.splitlines())} lines, over the 200 line limit")
    for banned in ISSUE_113_BANNED:
        if banned in ref113.replace("不读、不列、不报包装上印的字", ""):
            FAILS.append(f"issue 113: wording that reads the pack text: {banned}")
    return FAILS



# Issue 122: universal photo composition standards (3, 4, 5) only; standards 1 and 2 stay out of the skill.
ISSUE_122_RO = ("")
ISSUE_122_REF = [
    ISSUE_122_RO, "Nothing else on the table.", "Four plain clear glasses stand in one gentle row across the LOWER half of the frame",
    "标准 3", "这张卡的字说到或承诺的东西", "看得见的描述", "标准 4", "photo-scene-safe-margin.md", "issue 104", "issue 79", "悬空的手",
    "标准 5", "同一个地方", "光的方向、软硬、一天里的时间", "封面选定后写一次", "不读、不列、不报包装上印的字", "包装的形状和颜色"]
ISSUE_122_SKILL = {
    "set plan": ("计划写明这篇帖子的主题研究", ["issue 122", "这张卡的字说到或承诺的东西", "封面的光", "photo-scene-composition.md"]),
    "drawing": ("项目 `.env` 里是 `IMG_PROVIDER=codex`", ["封面的光", "这张卡的字说到或承诺的东西", "photo-scene-composition.md"]),
    "level 1 check": ("【一、二级】场景和道具检查", ["【一级】照片没有画出这张卡的字说到或承诺的东西", "【二级】", "issue 104", "issue 79", "不另加一条", "重出没有次数上限"]),
    "set check": ("【整套，按级】套系并排检查", ["【二级】光（issue 122）", "光不是封面的光"]),
}
ISSUE_122_ABSENT = ["占大半个画面", "卡的种类", "近景小物", "空桌子", "主体占大半"]


def _issue_122_failures(skill_root, skill_text):
    fails = []
    ref_path = skill_root / "references" / "photo-scene-composition.md"
    ref = ref_path.read_text(encoding="utf-8") if ref_path.is_file() else ""
    if not ref:
        fails.append("issue 122: references/photo-scene-composition.md does not exist")
    for need in ISSUE_122_REF:
        if need not in ref:
            fails.append(f"issue 122: the composition file does not say: {need}")
    for what, (marker, needles) in ISSUE_122_SKILL.items():
        line = next((l for l in skill_text.splitlines() if marker in l), "")
        for need in needles:
            if need not in line:
                fails.append(f"issue 122: the SKILL.md {what} line does not say: {need}")
    order = (skill_root / "references" / "photo-scene-check-order.md").read_text(encoding="utf-8")
    rows = {r[:4]: r for r in order.splitlines() if r.startswith("| 一级") or r.startswith("| 二级")}
    if "照片没有画出这张卡的字说到的东西" not in rows.get("| 一级", ""):
        fails.append("issue 122: the check-order level 1 row lacks the shows-what-the-words-say check")
    if "光不是封面的光" not in rows.get("| 二级", ""):
        fails.append("issue 122: the check-order level 2 row lacks the cover-light check")
    for gone in ISSUE_122_ABSENT:
        if gone in skill_text or gone in ref:
            fails.append(f"issue 122: standards 1 and 2 leaked into the skill: {gone}")
    if len(skill_text.splitlines()) > 200:
        fails.append("issue 122: SKILL.md is over the 200 line limit")
    return fails



def test_issue_122_universal_composition_standards():
    skill_root = SKILL_DIR
    failures = _issue_122_failures(skill_root, (skill_root / "SKILL.md").read_text(encoding="utf-8"))
    assert not failures, "\n".join(failures)

# Issue 123: every photo-scene plan page follows the layout the owner last approved (fixed set-plan sections, built only by the command).
ISSUE_123_QUOTE = ("")
ISSUE_123_QUOTE_2 = ""
ISSUE_123_SECTIONS = [
    "研究了哪一次", "研究的图集", "同一个家（…）", "人物：同一个人，身份来源只有一张", "服装（…）", "人物真实感（…）",
    "逐张计划", "真实包装照片清单", "真实状态来源清单", "封面方向", "字体体系（…）", "颜色和层级", "图标清单",
    "上图逐字清单（…）", "已定的…件事（…）", "出图顺序（…）"]
ISSUE_123_REF = [
    ISSUE_123_QUOTE, ISSUE_123_QUOTE_2, "只由 `plan_page.py build` 建", "checks/plan.md", "icon-list.md",
    "layout-plan-card_1-ABC.md", "layout-plan-card_<N>.md", "候选方向表", "to be matched against the approved page on the PC",
    "不改名、不挪行、不补字"]
ISSUE_123_SKILL_MARKER = "**计划页（issue 87）**"
ISSUE_123_SKILL = ["issue 123", "固定的段落", "checks/plan.md", "photo-scene-plan-page.md", "只用命令建"]


def _issue_123_failures(skill_root, skill_text):
    fails = []
    ref = (skill_root / "references" / "photo-scene-plan-page.md").read_text(encoding="utf-8")
    for need in ISSUE_123_REF:
        if need not in ref:
            fails.append(f"issue 123: the plan-page reference does not say: {need}")
    at = [ref.find(f"`## {s}`") for s in ISSUE_123_SECTIONS]
    if -1 in at:
        fails.append("issue 123: the plan-page reference lacks a fixed section: "
                     + "、".join(s for s, i in zip(ISSUE_123_SECTIONS, at) if i == -1))
    elif at != sorted(at):
        fails.append("issue 123: the plan-page reference lists the fixed sections out of order")
    line = next((l for l in skill_text.splitlines() if l.startswith(ISSUE_123_SKILL_MARKER)), "")
    for need in ISSUE_123_SKILL:
        if need not in line:
            fails.append(f"issue 123: the SKILL.md plan-page line does not say: {need}")
    if len(skill_text.splitlines()) > 200:
        fails.append("issue 123: SKILL.md is over the 200 line limit")
    return fails


def test_issue_123_plan_pages_follow_the_approved_layout():
    failures = _issue_123_failures(SKILL_DIR, _text(SKILL_DIR / "SKILL.md"))
    assert not failures, "\n".join(failures)


# Issue 125: every photo-scene run starts by reading the account's creation guide whole (seams 3 and 5).
ISSUE_125_SKILL = ["creation_guide.py check --brand", "创作指南", "整份读完", "photo-scene-creation-guide.md"]
ISSUE_125_REF = [
    "creation_guide.py check --brand", "profiles/_template/creation-guide.md", "创作指南：", "最后修改",
    "第一个 `##` 段落之前", "没有创作指南", "停下", "告诉负责人", "不研究、不写计划、不画", "EASEL_PROFILE_DIRS",
    "光只有一个来源", "重要的物、人或景", "画面边缘切掉", "照片画的就是这张卡的字说的", "同一个地方和光"]


def _issue_125_failures(skill_root, skill_text):
    fails = []
    lines = skill_text.splitlines()
    first = next((i for i, l in enumerate(lines) if "creation_guide.py check --brand" in l), None)
    vendor = next((i for i, l in enumerate(lines) if l.lstrip().startswith("1. `<资料包目录>/skill/SKILL.md`")), None)
    if first is None:
        fails.append("issue 125: SKILL.md does not make the creation-guide command the first reading step")
    elif vendor is not None and first > vendor:
        fails.append("issue 125: SKILL.md reads the creation guide after the team's skill, not first")
    for need in ISSUE_125_SKILL:
        if need not in skill_text:
            fails.append(f"issue 125: SKILL.md does not say: {need}")
    ref_path = skill_root / "references" / "photo-scene-creation-guide.md"
    if not ref_path.is_file():
        fails.append("issue 125: references/photo-scene-creation-guide.md does not exist")
    else:
        ref = ref_path.read_text(encoding="utf-8")
        for need in ISSUE_125_REF:
            if need not in ref:
                fails.append(f"issue 125: the creation-guide reference does not say: {need}")
    if len(lines) > 200:
        fails.append("issue 125: SKILL.md is over the 200 line limit")
    return fails


def test_issue_125_the_account_creation_guide_is_read_first():
    failures = _issue_125_failures(SKILL_DIR, _text(SKILL_DIR / "SKILL.md"))
    assert not failures, "\n".join(failures)


# Issue 125 pass 2: rules that fit one account left the skills for that account's creation guide.
ISSUE_125_MOVED_GONE = [
    "拿着包装、打开、一勺粉、倒进杯里", "一份是多少？", "例如打开的量勺、玻璃杯、勺子", "粉末在落、液面在升",
    "粉没有落、液面没有动", "例如粉末化开了、勺子里的量", "in gym clothing or sportswears",
    "穿运动服的模特的默认值", "是客户资料库里天猫商品图中的模特", "例如标题旁的小桂花",
    "显示粉末、打开的包装或冲好的饮品的状态", "天猫商品图里剪出来的一小块", "实测 14 px 被嫌挤",
    "超过 3 件", "不来自商品的道具一律拒绝"]
# The universal rule each moved wording leaves behind in the skill.
ISSUE_125_MOVED_KEPT = [
    "这个品牌自己商品的真实图", "每件写明它证明了", "服装配合这篇帖子的场景", "模特取自品牌自己的模特图",
    "商品除了闭合包装之外的任何状态", "身份图只定这个人是谁", "每件道具都证明这张卡的小动作", "留真空间"]


def _issue_125_skill_files():
    for base in (SKILL_DIR, ROOT / "skills" / "builtin" / "card-design", ROOT / "skills" / "builtin" / "xhs-note-creator"):
        for p in base.rglob("*"):
            if p.is_file() and "vendor" not in p.parts and ".test." not in p.name and p.suffix in {".md", ".py"}:
                yield p


def test_issue_125_moved_wordings_left_the_skills():
    text = "\n".join(p.read_text(encoding="utf-8") for p in _issue_125_skill_files())
    assert [n for n in ISSUE_125_MOVED_GONE if n in text] == []


def test_issue_125_universal_rules_stay_in_the_skills():
    text = "\n".join(p.read_text(encoding="utf-8") for p in _issue_125_skill_files())
    assert [n for n in ISSUE_125_MOVED_KEPT if n not in text] == []


# Issue 126: the picked lettering styles titles only; body text is one plain style, with its own delivery check.
ISSUE_126_QUOTE = ""
ISSUE_126_SKILL = [
    "photo-scene-body-text.md", "只给标题", "正文样式一行", "【一级】正文", "【三级】正文",
    "某张卡的标题字体和封面、参考图不一致", "正文段落"]
ISSUE_126_SKILL_GONE = [
    "某张卡的字体和封面、参考图不一致", "手绘的字，这个体系写进每一张的提示词，一张都不能漏"]
ISSUE_126_REF = [
    ISSUE_126_QUOTE, "只给标题", "封面的主标题和副标题", "每张卡的页标题", "篇名", "要点", "引语", "数据", "说明字", "评论问题",
    "一种清楚好认的字形", "一种墨色", "没有描边、胶带、阴影和装饰", "每个正文层级一个字号", "同一组共用一条左边线", "间距均匀",
    "卖点句", "高亮", "确认过的字表", "颜色表里的高亮层", "版面计划", "标题还是正文", "正文样式一行", "没有这一行的套系计划没有写完",
    "参考卡", "还没有", "从不当图片传给 Codex", "标题专用的装饰", "typed-styling.json", "body", "--check-records",
    "一级", "三级", "干净重出", "已批准卡的修改", "如实报告", "不读、不列、不报包装上印的字"]
ISSUE_126_CHECK_ORDER = ["正文没有对齐或间距不均", "正文带了标题的样式", "同一正文层级两个字号", "卖点行没有高亮"]
ISSUE_126_LETTERING_GONE = "字从封面起每一张都一样，只有字号不同"
ISSUE_126_CLAUDE_MD = [ISSUE_126_QUOTE]
ISSUE_126_CLAUDE_MD_GONE = "\x00"  # a text that is never there: the check for the old wording has nothing to find


def _issue_126_failures(skill_root, skill_text, claude_md_path):
    fails = []
    for need in ISSUE_126_SKILL:
        if need not in skill_text:
            fails.append(f"issue 126: SKILL.md does not say: {need}")
    for old in ISSUE_126_SKILL_GONE:
        if old in skill_text:
            fails.append(f"issue 126: SKILL.md still carries the pick to all text: {old}")
    ref_path = skill_root / "references" / "photo-scene-body-text.md"
    ref = ref_path.read_text(encoding="utf-8") if ref_path.is_file() else ""
    if not ref:
        fails.append("issue 126: references/photo-scene-body-text.md does not exist")
    for need in ISSUE_126_REF:
        if ref and need not in ref:
            fails.append(f"issue 126: the body-text reference does not say: {need}")
    order = (skill_root / "references" / "photo-scene-check-order.md").read_text(encoding="utf-8")
    for need in ISSUE_126_CHECK_ORDER:
        if need not in order:
            fails.append(f"issue 126: the check-order table does not list: {need}")
    picks = (skill_root / "references" / "photo-scene-lettering-picks.md").read_text(encoding="utf-8")
    if ISSUE_126_LETTERING_GONE in picks:
        fails.append("issue 126: the lettering-picks reference still carries the lettering to all text")
    if "只给标题" not in picks:
        fails.append("issue 126: the lettering-picks reference does not say the pick is for titles only")
    if claude_md_path.is_file():
        claude = claude_md_path.read_text(encoding="utf-8")
        for need in ISSUE_126_CLAUDE_MD:
            if need not in claude:
                fails.append(f"issue 126: CLAUDE.md photo-scene step 4 does not say: {need}")
        if ISSUE_126_CLAUDE_MD_GONE in claude:
            fails.append("issue 126: CLAUDE.md step 4 still carries the lettering to every card's text")
    if len(skill_text.splitlines()) > 200:
        fails.append("issue 126: SKILL.md is over the 200 line limit")
    return fails




# Issue 127: card titles match the cover title's size and sit on the photo; section labels are body sub-headings;
# every person card's face is compared with the approved cover's face at full size. Same assertions in both test files.
ISSUE_127_QUOTES = []  # the owner's words are not kept in the skill (issue 136); the rules below are checked instead
ISSUE_127_SKILL = ["photo-scene-title-and-face.md", "标题字号", "已批准封面的脸"]
ISSUE_127_REF = ISSUE_127_QUOTES + [
    "由 Easel 会话转述，不是直接听负责人说的", "和封面标题一样大", "在照片上", "白底条", "句话归负责人", "title_size", "--check-records",
    "不读、不列、不报包装上印的字"]
ISSUE_127_CHECK_ORDER = ["标题比封面标题小", "标题落在白底条上", "篇名带色块", "脸和已批准封面的脸不同"]


def _issue_127_failures(skill_root, skill_text):
    fails = []
    for need in ISSUE_127_SKILL:
        if need not in skill_text:
            fails.append(f"issue 127: SKILL.md does not say: {need}")
    ref_path = skill_root / "references" / "photo-scene-title-and-face.md"
    ref = ref_path.read_text(encoding="utf-8") if ref_path.is_file() else ""
    if not ref:
        fails.append("issue 127: references/photo-scene-title-and-face.md does not exist")
    for need in ISSUE_127_REF:
        if ref and need not in ref:
            fails.append(f"issue 127: the title-and-face reference does not say: {need}")
    for brand in _mapped_brand_names():
        if brand.lower() in ref.lower():
            fails.append(f"issue 127: the reference names a brand: {brand}")
    order = (skill_root / "references" / "photo-scene-check-order.md").read_text(encoding="utf-8")
    for need in ISSUE_127_CHECK_ORDER:
        if need not in order:
            fails.append(f"issue 127: the check-order table does not list: {need}")
    if len(skill_text.splitlines()) > 200:
        fails.append("issue 127: SKILL.md is over the 200 line limit")
    return fails


def test_issue_127_titles_match_the_cover_and_faces_match_the_approved_cover():
    failures = _issue_127_failures(SKILL_DIR, _text(SKILL_DIR / "SKILL.md"))
    assert not failures, "\n".join(failures)


# easel-setup-gaps issue 100: emojis in a card's lettering are drawn by the image model in the Apple iOS emoji style.
# Same assertions in both test files.
ISSUE_100E_QUOTES = [
    "Let the image model draw them",
    "Book a session for emoji, but what is the emoji front PC font? I only want the apple ios emoji looks",
    "Image model draws iOS-style (Recommended)",
]
ISSUE_100E_SKILL = ["photo-scene-emoji.md", "iOS"]
ISSUE_100E_DRAW = ["字里带表情的卡", "每个表情", "版面计划", "由出图模型画成 Apple iOS 样式", "photo-scene-emoji.md"]
ISSUE_100E_REF = ISSUE_100E_QUOTES + [
    "easel-setup-gaps issue 100", "Fix the script, code sets them", "Noto Color Emoji", "Segoe UI Emoji", "seguiemj.ttf",
    "fc-list", "C:\\Windows\\Fonts", "Apple iOS", "每一个表情", "任何一张字里带表情的卡", "封面和每一张卡",
    "版面计划", "blocks", "手绘字", "图标清单", "图标 | 意思 | 出现的卡", "缺了", "谷歌", "微软", "线条图标", "涂鸦",
    "不添加、不安装、不改任何表情字体", "text_on_image.py", "不读、不列、不报包装上印的字"]
ISSUE_100E_ICON_LIST = ["表情", "iOS"]
ISSUE_100E_CHECK_ORDER = ["表情缺了或不是 iOS 样式"]
ISSUE_100E_NAMES_GONE = ["[the brand]", "Ro 的话"]  # the new reference uses the role, not the owner's name


def _issue_100e_failures(skill_root, skill_text):
    fails = []
    for need in ISSUE_100E_SKILL:
        if need not in skill_text:
            fails.append(f"easel issue 100: SKILL.md does not say: {need}")
    draw = next((l for l in skill_text.splitlines() if l.startswith("- 图标（issue 86）")), "")
    for need in ISSUE_100E_DRAW:
        if need not in draw:
            fails.append(f"easel issue 100: the SKILL.md drawing rule for icons does not say: {need}")
    ref_path = skill_root / "references" / "photo-scene-emoji.md"
    ref = ref_path.read_text(encoding="utf-8") if ref_path.is_file() else ""
    if not ref:
        fails.append("easel issue 100: references/photo-scene-emoji.md does not exist")
    for need in ISSUE_100E_REF:
        if ref and need not in ref:
            fails.append(f"easel issue 100: the emoji reference does not say: {need}")
    for name in ISSUE_100E_NAMES_GONE:
        if name in ref:
            fails.append(f"easel issue 100: the emoji reference names a brand: {name}")
    icons = (skill_root / "references" / "photo-scene-icon-list.md").read_text(encoding="utf-8")
    for need in ISSUE_100E_ICON_LIST:
        if need not in icons:
            fails.append(f"easel issue 100: the icon-list reference does not say: {need}")
    order = (skill_root / "references" / "photo-scene-check-order.md").read_text(encoding="utf-8")
    for need in ISSUE_100E_CHECK_ORDER:
        if need not in order:
            fails.append(f"easel issue 100: the check-order table does not list: {need}")
    if len(skill_text.splitlines()) > 200:
        fails.append("easel issue 100: SKILL.md is over the 200 line limit")
    return fails


def test_easel_issue_100_emojis_are_drawn_by_the_image_model_in_ios_style():
    failures = _issue_100e_failures(SKILL_DIR, _text(SKILL_DIR / "SKILL.md"))
    assert not failures, "\n".join(failures)
