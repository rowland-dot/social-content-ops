"""Document check for issue 92: the photo-scene skill lets the brand's own model through.

The owner's rule (CLAUDE.md, "People in the images are not restricted"): where a post needs a person, the model
is taken from the team's own brand graphics and redrawn in new poses, angles and clothing. The skill's
"don't copy the reference image's people" line is about style references and stays; the brand's own model,
passed as the identity reference, is its exception.

Run: python skills/builtin/xhs-reference-visual/brand-model.test.py   (exit 0 = pass). The same assertions are
in tests/test_codex_image_identity.py, which CI collects; this copy sits beside the skill.
"""
from pathlib import Path
import sys

text = (Path(__file__).resolve().parent / "SKILL.md").read_text(encoding="utf-8")

required = {
    "style references still lend no people": "不照抄参考图里的人物、婴儿、手和道具" in text,
    "the brand's own model is the exception": "品牌自己的模特是上一条的例外" in text,
    "the model comes from the team's own brand graphics": "模特取自品牌自己的模特图" in text,
    "it is passed with its own option": "--identity-image" in text,
    "a real model, not an AI person": "不是“AI 人物”" in text,
    "The owner's wording for the new shots": "重画模特，换姿势、多动作、换角度；服装配合这篇帖子的场景" in text,
    "style references still lend no people (stated again beside the exception)": "风格参考仍然不借人物" in text,
    # issue 114: a person card with no pack
    "a person card with no pack is named": "不带包装的人物卡" in text,
    "it passes the identity image alone": "只传 `--identity-image`，不传 `--image`" in text,
    "the prompt says no product or pack": "提示词写明不画商品和包装" in text,
}
missing = [why for why, ok in required.items() if not ok]
if missing:
    print("missing:", "; ".join(missing))
    sys.exit(1)
print("ok")
