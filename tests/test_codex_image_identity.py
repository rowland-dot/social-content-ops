"""The brand's own model as an identity reference on the Codex subscription route (issue 92).

The owner's rule (CLAUDE.md, "People in the images are not restricted"): where a post needs a person, the
model is taken from the team's own brand graphics and redrawn in new poses, angles and clothing; "that
is a real model, not an "AI person"". Seams (the issue's "Agreed seams"): the command line
`ai_image.py img2img` with its separate `--identity-image` option, the helper's own command line
(`codex_image.py`, used by the WeChat script), and behind them the prompt and the `codex` arguments.
Only the outside world is faked: a `codex` program on PATH that records its arguments and the prompt on
standard input (the `listening` fixture of test_codex_image_roles.py). No real image is drawn.
Expected values are literals.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "codex_image_roles_helpers", Path(__file__).with_name("test_codex_image_roles.py"))
_roles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_roles)
AI_IMAGE, REPO, run = _roles.AI_IMAGE, _roles.REPO, _roles.run
world = _roles.world  # fixtures, used by name
listening = _roles.listening

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fake codex is a POSIX script")

# The owner, 2026-10-28, the wording the post's prompt follows when it needs the model in a new shot.
RO_WORDING = ("redraw the model in different postures more movements from different angled shots, "
              "in gym clothing or sportswears")


@pytest.fixture
def pictures(listening):
    for name in ("model.png", "model-2.png"):
        (listening.tmp / name).write_bytes((listening.tmp / "pack.png").read_bytes())
    return listening


def _img2img(w, images: list[str], identity: list[str] | None = None, *, prompt: str = RO_WORDING,
             env_extra: dict | None = None):
    args = ["img2img", "--prompt", prompt, "--size", "3:4",
            "--output", str(w.root / "outputs/post/out.png")]
    for image in images:
        args += ["--image", str(w.tmp / image)]
    for image in identity or []:
        args += ["--identity-image", str(w.tmp / image)]
    return run(w, AI_IMAGE, *args, env_extra=env_extra)


def _image_arguments(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, token in enumerate(argv) if token == "-i"]


def test_product_identity_and_one_style_reference_reach_codex_and_the_prompt_names_the_person(pictures):
    proc = _img2img(pictures, ["pack.png", "style-main.png"], ["model.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / n) for n in
                                              ("pack.png", "style-main.png", "model.png")]
    prompt = call["prompt"]
    assert RO_WORDING in prompt
    assert "Image 1 is the product: keep its shape, colours and printed label exactly." in prompt
    assert ("Image 2 is a style reference: take only its look (light, scene, composition, lettering "
            "style), none of its products, people, hands or words.") in prompt
    assert ("Image 3 is the identity reference: keep this person recognisably the same (face and "
            "identity) and redraw them in the pose, angle and clothing the prompt describes.") in prompt


def test_the_cap_rises_by_exactly_the_identity_slot_product_two_styles_and_the_person_go_through(pictures):
    proc = _img2img(pictures, ["pack.png", "style-main.png", "style-support.png"], ["model.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / n) for n in
                                              ("pack.png", "style-main.png", "style-support.png",
                                               "model.png")]
    prompt = call["prompt"]
    assert "Image 2 is the main style reference" in prompt
    assert "Image 3 is the supporting style reference" in prompt
    assert "Image 4 is the identity reference" in prompt


def test_product_and_identity_alone_name_the_person_as_image_two(pictures):
    proc = _img2img(pictures, ["pack.png"], ["model.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert "Image 1 is the product" in call["prompt"]
    assert "Image 2 is the identity reference" in call["prompt"]
    assert "style reference" not in call["prompt"]


def test_a_second_identity_image_is_refused_before_codex_is_started_naming_the_limit(pictures):
    proc = _img2img(pictures, ["pack.png", "style-main.png"], ["model.png", "model-2.png"])
    assert proc.returncode == 1
    assert "at most 1 identity image" in proc.stderr
    assert pictures.calls() == []


def test_one_image_past_the_new_total_is_refused_before_codex_is_started_naming_the_limit(pictures):
    proc = _img2img(pictures, ["pack.png", "style-main.png", "style-support.png", "extra.png"],
                    ["model.png"])
    assert proc.returncode == 1
    assert "at most 4" in proc.stderr
    assert pictures.calls() == []


def test_a_fourth_plain_image_is_still_refused_with_an_identity_image_absent(pictures):
    proc = _img2img(pictures, ["pack.png", "style-main.png", "style-support.png", "extra.png"])
    assert proc.returncode == 1
    assert "at most 3" in proc.stderr
    assert pictures.calls() == []


IDENTITY_ROLE_ALONE = ("Image 1 is the identity reference: keep this person recognisably the same (face "
                       "and identity) and redraw them in the pose, angle and clothing the prompt describes.")
NO_PACK_LINE = "No product or pack is drawn unless the prompt describes one."


def test_an_identity_image_alone_reaches_codex_as_the_only_image_and_the_prompt_says_no_pack(pictures):
    proc = _img2img(pictures, [], ["model.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / "model.png")]
    prompt = call["prompt"]
    assert RO_WORDING in prompt
    assert IDENTITY_ROLE_ALONE in prompt
    assert NO_PACK_LINE in prompt
    assert "Image 1 is the product" not in prompt


def test_the_issue_command_img2img_identity_image_model_png_sends_only_model_png_to_codex(pictures):
    # The issue's own words: `img2img --identity-image model.png`, reaching Codex as `-i model.png`.
    proc = run(pictures, AI_IMAGE, "img2img", "--identity-image", "model.png", "--prompt", RO_WORDING,
               "--size", "3:4", "--output", str(pictures.root / "outputs/post/out.png"))
    assert proc.returncode == 0, proc.stderr
    assert "An identity image needs a product image as image 1." not in proc.stderr  # the old refusal
    (call,) = pictures.calls()
    argv = call["argv"]
    assert argv.count("-i") == 1
    assert argv[argv.index("-i") + 1].endswith("model.png")
    assert IDENTITY_ROLE_ALONE in call["prompt"]


def test_the_codex_helper_draws_from_an_identity_image_alone(pictures, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "codex_image_under_test", REPO / "skills/shared/scripts/codex_image.py")
    codex_image = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codex_image)
    for key, value in pictures.env.items():
        monkeypatch.setenv(key, value)
    assert codex_image.generate_png("x", identity=str(pictures.tmp / "model.png"))
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / "model.png")]
    assert IDENTITY_ROLE_ALONE in call["prompt"]
    assert NO_PACK_LINE in call["prompt"]


def test_a_call_with_a_product_image_never_says_no_pack(pictures):
    proc = _img2img(pictures, ["pack.png"], ["model.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert NO_PACK_LINE not in call["prompt"]


def test_img2img_with_no_image_at_all_is_refused_before_codex_is_started_naming_the_limit(pictures):
    proc = _img2img(pictures, [])
    assert proc.returncode == 1
    assert "at least one image" in proc.stderr
    assert pictures.calls() == []


def test_a_second_identity_image_without_a_product_image_is_refused_before_codex_is_started(pictures):
    proc = _img2img(pictures, [], ["model.png", "model-2.png"])
    assert proc.returncode == 1
    assert "at most 1 identity image" in proc.stderr
    assert pictures.calls() == []


def test_without_the_codex_route_an_identity_image_alone_is_refused_naming_the_codex_setting(pictures):
    # issue 95: without the setting every generate command stops with the one plain message
    proc = _img2img(pictures, [], ["model.png"], env_extra={"IMG_PROVIDER": ""})
    assert proc.returncode == 1
    assert "IMG_PROVIDER=codex" in proc.stderr
    assert pictures.calls() == []


def test_without_the_codex_route_img2img_with_no_image_at_all_is_still_refused(pictures):
    proc = _img2img(pictures, [], env_extra={"IMG_PROVIDER": ""})
    assert proc.returncode == 1
    assert "IMG_PROVIDER=codex" in proc.stderr
    assert pictures.calls() == []


def test_without_the_codex_route_an_identity_image_is_refused_not_silently_dropped(pictures):
    proc = _img2img(pictures, ["pack.png"], ["model.png"], env_extra={"IMG_PROVIDER": ""})
    assert proc.returncode == 1
    assert "IMG_PROVIDER=codex" in proc.stderr
    assert pictures.calls() == []


def test_the_helper_command_line_takes_the_identity_image_as_its_own_option(pictures):
    done = subprocess.run(
        [sys.executable, str(REPO / "skills/shared/scripts/codex_image.py"), "--ratio", "3:4",
         "--image", str(pictures.tmp / "pack.png"),
         "--identity-image", str(pictures.tmp / "model.png")],
        input=RO_WORDING.encode(), env=pictures.env, cwd=pictures.tmp, capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / "pack.png"),
                                              str(pictures.tmp / "model.png")]
    assert "Image 2 is the identity reference" in call["prompt"]


def test_the_helper_command_line_draws_from_an_identity_image_alone(pictures):
    done = subprocess.run(
        [sys.executable, str(REPO / "skills/shared/scripts/codex_image.py"), "--ratio", "3:4",
         "--identity-image", str(pictures.tmp / "model.png")],
        input=RO_WORDING.encode(), env=pictures.env, cwd=pictures.tmp, capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr
    (call,) = pictures.calls()
    assert _image_arguments(call["argv"]) == [str(pictures.tmp / "model.png")]
    assert IDENTITY_ROLE_ALONE in call["prompt"]
    assert NO_PACK_LINE in call["prompt"]


def test_the_helper_command_line_refuses_a_second_identity_image_before_codex_is_started(pictures):
    done = subprocess.run(
        [sys.executable, str(REPO / "skills/shared/scripts/codex_image.py"),
         "--image", str(pictures.tmp / "pack.png"),
         "--identity-image", str(pictures.tmp / "model.png"),
         "--identity-image", str(pictures.tmp / "model-2.png")],
        input=b"x", env=pictures.env, cwd=pictures.tmp, capture_output=True, timeout=120)
    assert done.returncode == 1
    assert b"at most 1 identity image" in done.stderr
    assert pictures.calls() == []


def test_calls_that_pass_no_identity_image_send_the_same_arguments_and_prompt_as_before(pictures):
    # the single-image prompt and the product-plus-styles prompts, pinned literally in
    # test_codex_image_roles.py, are not changed by the new option; spot-check the two-image role line.
    proc = _img2img(pictures, ["pack.png", "style-main.png"])
    assert proc.returncode == 0, proc.stderr
    (call,) = pictures.calls()
    assert call["argv"] == ["exec", "--json", "--skip-git-repo-check", "-s", "read-only", "--ephemeral",
                            "-i", str(pictures.tmp / "pack.png"), "-i", str(pictures.tmp / "style-main.png")]
    assert "identity" not in call["prompt"]


# ── The skill texts (The owner's rule: the brand's own model is not blocked) ─────────────────────────────

SKILLS = REPO / "skills/builtin"
OLD_REAL_FACE_LINE = "避免真实人脸（肖像权风险）"
STYLE_REFERENCE_NO_PEOPLE = "不照抄参考图里的人物、婴儿、手和道具"
RO_RULE = ""  # the skills no longer point at the rules file by its wording (issue 136)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_photo_scene_skill_says_the_brands_own_model_is_the_exception_passed_as_identity():
    text = _text(SKILLS / "xhs-reference-visual/SKILL.md")
    for need in (
        STYLE_REFERENCE_NO_PEOPLE,          # style references still lend no people
        "品牌自己的模特是上一条的例外",
        "模特取自品牌自己的模特图",              # the model comes from the brand's own graphics
        "--identity-image",
        RO_RULE,                             # the owner's rule in CLAUDE.md
        "不是“AI 人物”",
        "重画模特，换姿势、多动作、换角度；服装配合这篇帖子的场景",  # issue 125: the sportswear wording moved to the account guide
        "风格参考仍然不借人物",
    ):
        assert need in text, f"xhs-reference-visual does not say: {need}"
    exception = text.index("品牌自己的模特是上一条的例外")
    assert text.index(STYLE_REFERENCE_NO_PEOPLE) < exception, "the exception must come after the line it excepts"


def test_the_article_image_step_no_longer_bans_the_brands_own_model_but_keeps_other_real_faces_out():
    text = _text(SKILLS / "xhs-note-creator/references/image-sourcing.md")
    assert OLD_REAL_FACE_LINE not in text
    for need in ("避免品牌没有权利的真人的脸（肖像权风险）", "品牌自己的模特不在此限", "--identity-image", RO_RULE):
        assert need in text, f"image-sourcing.md does not say: {need}"


def test_the_image_skill_documents_the_identity_role_and_the_new_total():
    text = _text(SKILLS / "ai-image-gen/SKILL.md")
    for need in (
        "不带它的商品、人物、手、文字",     # the style-reference wording stays
        "最多 3 张",
        "--identity-image",
        "身份参考",
        "共最多 4 张",
        "至多 1 张",
    ):
        assert need in text, f"ai-image-gen does not say: {need}"


def test_the_image_help_text_describes_the_identity_role():
    done = subprocess.run([sys.executable, str(AI_IMAGE), "img2img", "--help"], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    flat = " ".join(done.stdout.split())
    assert "--identity-image" in flat
    assert "身份参考" in flat
    assert "不带它的商品、人物、手、文字" in flat


def test_the_photo_scene_skill_says_how_a_person_card_with_no_pack_is_drawn():
    text = _text(SKILLS / "xhs-reference-visual/SKILL.md")
    for need in (
        "不带包装的人物卡",
        "只传 `--identity-image`，不传 `--image`",
        "提示词写明不画商品和包装",
        "风格参考仍然不借人物",
    ):
        assert need in text, f"xhs-reference-visual does not say: {need}"


def test_the_image_skill_says_an_identity_image_can_be_given_alone_for_a_card_with_no_pack():
    text = _text(SKILLS / "ai-image-gen/SKILL.md")
    for need in (
        "也可以单独给 `--identity-image`（不给 `--image`）",
        "不画商品和包装",
    ):
        assert need in text, f"ai-image-gen does not say: {need}"
    assert "它必须和商品图一起给" not in text


def test_the_image_help_text_says_the_identity_image_can_stand_alone():
    done = subprocess.run([sys.executable, str(AI_IMAGE), "img2img", "--help"], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    flat = " ".join(done.stdout.split())
    assert "也可以单独给 --identity-image" in flat
