"""Document check for issue 97: the carousel planner stops calling its hook formulas "verified".

Run: python skills/builtin/skill-carousel-planner/no-verified-claim.test.py   (exit 0 = pass).

hook-library.md opened with "6 种经过验证的封面 Hook 公式" while its own table says "非精确数据，仅供评分参考".
SKILL.md repeated the claim twice and scoring-system.md rewarded "使用经过验证的 Hook 公式" in its top cover band.
No file of the planner may make the claim now. The six formulas, their examples and the table rows stay word for word.
The owner's rule (CLAUDE.md, "Content is studied from real posts, never invented"): "Nothing is briefed from invention."
"""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
files = {
    "SKILL.md": (here / "SKILL.md").read_text(encoding="utf-8"),
    "hook-library.md": (here / "references" / "hook-library.md").read_text(encoding="utf-8"),
    "scoring-system.md": (here / "references" / "scoring-system.md").read_text(encoding="utf-8"),
    "format-specs.md": (here / "references" / "format-specs.md").read_text(encoding="utf-8"),
}
skill, hook, scoring = (files[n] for n in ("SKILL.md", "hook-library.md", "scoring-system.md"))


def lines_of(text: str) -> list[str]:
    return text.splitlines()


def line_has_all(text: str, *needles: str) -> bool:
    return any(all(n in line for n in needles) for line in lines_of(text))


required: dict[str, bool] = {}

for name, text in files.items():
    required[f"{name}: no 经过验证"] = "经过验证" not in text
required["hook-library.md keeps the 非精确数据 caveat"] = "非精确数据，仅供评分参考" in hook
required["hook-library.md says what the formulas are: common cover patterns, tendencies"] = line_has_all(
    hook, "6 种", "常见封面", "倾向"
)
required["SKILL.md reference list says what the library is"] = line_has_all(skill, "references/hook-library.md", "常见封面", "倾向")
required["SKILL.md cover step names 6 common cover patterns from the library"] = line_has_all(
    skill, "references/hook-library.md", "6 个常见封面模式"
)
top_band = [l for l in lines_of(scoring) if l.startswith("| 9-10 |") and "封面文字 ≤8 字" in l]
required["scoring top band: one row, rewards a pattern seen in the studied posts"] = len(top_band) == 1 and "研究" in top_band[0]
required["scoring top band keeps its other criteria"] = len(top_band) == 1 and all(
    k in top_band[0] for k in ("封面文字 ≤8 字", "在缩略图尺寸下清晰可读", "好奇缺口强烈")
)

# The six formulas, their examples and the engagement table rows are unchanged.
for pin in (
    "## 1. 数字清单 (Number-led)",
    "## 2. 反常识 (Contrarian)",
    "## 3. 对比冲击 (Before/After)",
    "## 4. 直击痛点 (Pain Point)",
    "## 5. 颠覆声明 (Bold Claim)",
    "## 6. 身份认同 (Identity)",
    "- \"5 个毁掉皮肤的习惯\"",
    "- \"别再这样敷面膜了\"",
    "- \"租房改造 | 花 500 块的效果\"",
    "- \"为什么你总是穿不好基础款\"",
    "- \"这个方法改变了我的皮肤\"",
    "- \"i 人社交自救指南\"",
    "| 数字清单 | 中 | 高 | 中 | 教程、干货 |",
    "| 反常识 | 高 | 中 | 高 | 科普、纠错 |",
    "| 对比冲击 | 高 | 中 | 中 | 变化、改造 |",
    "| 直击痛点 | 中高 | 中 | 高 | 解决方案 |",
    "| 颠覆声明 | 高 | 中低 | 中 | 推荐、测评 |",
    "| 身份认同 | 中 | 高 | 中高 | 指南、清单 |",
):
    required[f"hook-library pin: {pin}"] = pin in hook

missing = [why for why, ok in required.items() if not ok]
if missing:
    print("missing:", "; ".join(missing))
    sys.exit(1)
print("ok")
