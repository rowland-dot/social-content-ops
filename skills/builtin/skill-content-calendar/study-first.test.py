"""Document check for issue 97: plans and hook formulas are no longer built from invented benchmarks.

Run: python skills/builtin/skill-content-calendar/study-first.test.py   (exit 0 = pass).

The owner's rule (CLAUDE.md, "Content is studied from real posts, never invented"):
"Before writing copy, making cards or images, or briefing Easel on either, Claude studies the real material first
... Nothing is briefed from invention."

Calendar: it used to say that without tools it works as normal, skips research, notes assumptions and builds the plan
"基于品牌上下文和最佳实践"; research was headed "研究（可选）" and the requirements step asked whether research was wanted.
Now a plan is built only after real posts are studied; with no study possible the calendar tells the user and stops.

The carousel planner half of the issue is checked beside that skill, in no-verified-claim.test.py.
"""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
calendar = (here / "SKILL.md").read_text(encoding="utf-8")


def lines_of(text: str) -> list[str]:
    return text.splitlines()


def line_has_all(text: str, *needles: str) -> bool:
    return any(all(n in line for n in needles) for line in lines_of(text))


required: dict[str, bool] = {}

# --- Calendar: nothing is planned from best practice or noted assumptions ---
required["calendar: 基于品牌上下文和最佳实践构建排期 is gone"] = "基于品牌上下文和最佳实践构建排期" not in calendar
required["calendar: 没有外部工具时照常工作 is gone"] = "没有外部工具时照常工作" not in calendar
required["calendar: no 最佳实践 fallback anywhere"] = "最佳实践" not in calendar
required["calendar: no 标注假设 anywhere"] = "标注假设" not in calendar
required["calendar: 缺失的输入 line is a stop, not an assumption"] = any(
    "缺失的输入" in l and "停下" in l and "假设" not in l for l in lines_of(calendar)
)

# --- Calendar: research is mandatory ---
phase2 = [l for l in lines_of(calendar) if l.startswith("## Phase 2")]
required["calendar: Phase 2 heading exists and is not 可选"] = len(phase2) == 1 and "可选" not in phase2[0] and "研究" in phase2[0]
required["calendar: requirements step no longer asks whether research is wanted"] = "是否需要竞品分析或热搜趋势研究" not in calendar

# --- Calendar: plan only after real posts are studied, three kinds of material, plan names what was studied ---
required["calendar: a plan is built only after real posts are studied"] = line_has_all(calendar, "只有研究过真实帖子", "才能排期")
for kind in ("高表现的小红书帖子", "团队给的参考和创作者帖子", "品牌账号自己过去发的帖子"):
    required[f"calendar: names study material: {kind}"] = kind in calendar
required["calendar: the plan names what was studied (searches, posts or sets, where saved)"] = line_has_all(
    calendar, "排期必须写明研究了什么", "搜索", "保存"
)

# --- Calendar: no study possible = tell the user and stop ---
required["calendar: no study possible -> tell the user plainly, say what is missing, stop, no plan"] = line_has_all(
    calendar, "如实告诉用户", "缺什么", "停下", "不排期"
)

# --- Calendar: hotlist stays one input among others; reads stay within the reader's limits ---
required["calendar: still points at hotlist-apis.md"] = "../../shared/hotlist-apis.md" in calendar
required["calendar: hotlist is not a substitute for studying posts"] = line_has_all(calendar, "热搜", "不能替代")
required["calendar: reads stay within 100 a day, spaced"] = line_has_all(calendar, "100", "间隔")

# --- Calendar: unchanged hand-offs and inputs ---
for pin in (
    "python skills/shared/scripts/calendar_ops.py context --days 14",
    "../../shared/pillar-and-cadence.md",
    "`lrb-monthly-excel`",
    "不要自己写 xlsx",
):
    required[f"calendar pin: {pin}"] = pin in calendar

missing = [why for why, ok in required.items() if not ok]
if missing:
    print("missing:", "; ".join(missing))
    sys.exit(1)
print("ok")
