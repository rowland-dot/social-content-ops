"""Document check for issue 92: the article-image step no longer bans the brand's own model.

The owner's rule (CLAUDE.md, "People in the images are not restricted"). The old line "避免真实人脸（肖像权风险）"
is replaced: real faces of people the brand has no rights to are still avoided; the brand's own model
(taken from the team's own graphics, passed as the identity reference) is not.

Run: python skills/builtin/xhs-note-creator/brand-model.test.py   (exit 0 = pass). The same assertions are
in tests/test_codex_image_identity.py, which CI collects; this copy sits beside the skill.
"""
from pathlib import Path
import sys

text = (Path(__file__).resolve().parent / "references" / "image-sourcing.md").read_text(encoding="utf-8")

required = {
    "the blanket real-face line is gone": "避免真实人脸（肖像权风险）" not in text,
    "faces the brand has no rights to are still avoided": "避免品牌没有权利的真人的脸（肖像权风险）" in text,
    "the brand's own model is not blocked": "品牌自己的模特不在此限" in text,
    "it says how the model is passed": "--identity-image" in text,
}
missing = [why for why, ok in required.items() if not ok]
if missing:
    print("missing:", "; ".join(missing))
    sys.exit(1)
print("ok")
