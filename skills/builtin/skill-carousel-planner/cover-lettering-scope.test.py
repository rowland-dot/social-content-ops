"""Document check for issue 96: the carousel planner stops telling a photo-scene cover to use big bold type.

Run: python skills/builtin/skill-carousel-planner/cover-lettering-scope.test.py   (exit 0 = pass).

The rule (issue 89, photo-scene step 4): lettering is picked as three clearly different typefaces and three
stylings, never plain heavy black strokes.

Three files the planner loads said big, bold type for every cover:
  SKILL.md              "字体必须大、加粗，在缩略图尺寸下也清晰可读"
  references/hook-library.md  "字体大、加粗、高对比度"
  references/format-specs.md  "封面标题字号 | ≥ 60pt，加粗" (Xiaohongshu) and "≥ 56pt，加粗" (Instagram)
Those rules stay for HTML / generic text cards. A photo-scene cover takes its lettering from
xhs-reference-visual's pick. Thumbnail legibility stays for every cover. Nothing else changes.
The "经过验证" claims in hook-library.md are issue 97's and are not pinned here.
"""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
files = {
    "SKILL.md": ((here / "SKILL.md").read_text(encoding="utf-8"), "../xhs-reference-visual/references/photo-scene-lettering-picks.md"),
    "hook-library.md": ((here / "references" / "hook-library.md").read_text(encoding="utf-8"), "../../xhs-reference-visual/references/photo-scene-lettering-picks.md"),
    "format-specs.md": ((here / "references" / "format-specs.md").read_text(encoding="utf-8"), "../../xhs-reference-visual/references/photo-scene-lettering-picks.md"),
}
skill, hook, specs = (files[name][0] for name in ("SKILL.md", "hook-library.md", "format-specs.md"))



def lines_of(text: str) -> list[str]:
    return text.splitlines()


def with_text(text: str, needle: str) -> list[str]:
    return [line for line in lines_of(text) if needle in line]


required = {}

# Every bold-type rule is scoped to HTML / generic text cards (fails on today's text).
for name, (text, _) in files.items():
    bold = with_text(text, "加粗")
    required[f"{name}: every line that says 加粗 names HTML cards as what it covers"] = bool(bold) and all("HTML" in l for l in bold)

# The literal rules are kept for HTML cards, word for word.
required["SKILL.md keeps 字体必须大、加粗，在缩略图尺寸下也清晰可读"] = "字体必须大、加粗，在缩略图尺寸下也清晰可读" in skill
required["hook-library.md keeps 字体大、加粗、高对比度"] = "字体大、加粗、高对比度" in hook
required["format-specs.md keeps ≥ 60pt，加粗"] = "≥ 60pt，加粗" in specs
required["format-specs.md keeps ≥ 56pt，加粗"] = "≥ 56pt，加粗" in specs

# Each file sends a photo-scene cover to xhs-reference-visual's lettering pick.
for name, (text, link) in files.items():
    required[f"{name}: a photo-scene line points to xhs-reference-visual's lettering pick"] = any(
        "照片场景" in l and link in l for l in lines_of(text)
    )
required["SKILL.md: the pointer allows handwriting, bans plain heavy black strokes"] = any(
    "照片场景" in l and "允许手写" in l and "不用纯粗黑笔画" in l for l in lines_of(skill)
)

# Thumbnail legibility stays for every cover.
required["SKILL.md: all covers, photo-scene included, stay readable at thumbnail size"] = any(
    "所有封面" in l and "缩略图" in l for l in lines_of(skill)
)
required["format-specs.md keeps the thumbnail legibility lines"] = (
    "封面缩略图尺寸约 260 x 347 px，文字在此尺寸下必须可读" in specs
    and "**封面是流量入口**，文字/画面在缩略图尺寸下必须清晰" in specs
)

# HTML card and other cover rules stay word for word (seam 4).
for rule in (
    "封面文字不超过 12 个字",
    "**反常识：** \"别再XX了\"",
    "**数字清单：** \"5 个毁掉XX的错误\"",
    "**对比冲击：** 前后对比的视觉悬念",
    "**直击痛点：** \"为什么你XX总是失败\"（陈述式，不加问号）",
    "**颠覆声明：** \"这会改变你的一切\"",
    "**身份认同：** \"XX 人必看\"（收藏率 + 分享率高）",
    "封面不放 logo 或品牌标识（会削弱好奇心）",
    "**视觉统一：** 全篇使用相同的背景风格、字体和配色。",
    "**每页文字不超过 20 字**（文字叠层）",
):
    required[f"SKILL.md pin: {rule}"] = rule in skill
for rule in ("封面文字不超过 12 个字", "数字一律用阿拉伯数字", "不放 logo 或品牌标识"):
    required[f"hook-library.md pin: {rule}"] = rule in hook
for rule in (
    "| 推荐尺寸 | 1080 x 1440 px |",
    "| 正文字号 | 36-48pt |",
    "| 正文字号 | 32-44pt |",
    "| 字体推荐 | 思源黑体、阿里巴巴普惠体、站酷快乐体 |",
    "| 安全区域 | 上下左右各留 80px |",
    "| 安全区域 | 上下左右各留 60px |",
    "4. **颜色对比度**：文字与背景对比度 ≥ 4.5:1（WCAG AA）",
):
    required[f"format-specs.md pin: {rule}"] = rule in specs

missing = [why for why, ok in required.items() if not ok]
if missing:
    print("missing:", "; ".join(missing))
    sys.exit(1)
print("ok")
