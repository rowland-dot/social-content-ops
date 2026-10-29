"""Document check for issue 96: the note writer's methodology stops telling a photo-scene cover to avoid handwriting.

Run: python skills/builtin/xhs-note-creator/cover-lettering-scope.test.py   (exit 0 = pass).

The rule (issue 89, photo-scene step 4): lettering is picked as three clearly different typefaces and three
stylings, never plain heavy black strokes.

The methodology reference said, for every cover, "不靠大 emoji / 手写感" and called the 手写感 look "已废弃".
Both lines are true only for the HTML text-card path (`html_card`). A `photo_scene` cover follows
xhs-reference-visual's lettering pick. The HTML card rules must stay word for word.
"""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
method = (here / "references" / "xiaohongshu-viral-methodology.md").read_text(encoding="utf-8")
lines = method.splitlines()

PICKS = "../../xhs-reference-visual/references/photo-scene-lettering-picks.md"


def with_text(needle: str) -> list[str]:
    return [line for line in lines if needle in line]


ban_lines = with_text("手写感")
retired_lines = with_text("已废弃")

required = {
    # The scoping itself (fails on today's text).
    "the 不靠大 emoji / 手写感 sentence is still there": any("不靠大 emoji / 手写感" in l for l in lines),
    "every line that says 手写感 names html_card as the path it covers": bool(ban_lines)
    and all("html_card" in l for l in ban_lines),
    "the 已废弃 remark names html_card as the path it covers": bool(retired_lines)
    and all("html_card" in l for l in retired_lines),
    "the 已废弃 remark sends photo_scene lettering to xhs-reference-visual": any(
        "已废弃" in l and "photo_scene" in l and PICKS in l for l in lines
    ),
    "the cover template intro sends photo_scene lettering to xhs-reference-visual, allows handwriting, "
    "bans plain heavy black strokes": any(
        "不靠大 emoji / 手写感" in l
        and "photo_scene" in l
        and PICKS in l
        and "允许手写" in l
        and "不用纯粗黑笔画" in l
       
        for l in lines
    ),
    # HTML card rules stay word for word (seam 4).
    "pin: core principle line (card-design, 字大字细、填满画幅、禁大 emoji 廉价感)": "视觉走 [card-design](../../card-design/SKILL.md) 设计系统**（选风格锁 spec、字大字细、填满画幅、禁大 emoji 廉价感）"
    in method,
    "pin: cover skeleton wording": "card-design 的封面骨架（大标题细字重 + 钩子副标 + kicker/信息行），用字号层级和留白营造张力"
    in method,
    "pin: old look retired for html cards, reason kept": '旧版"纯色 + 大 emoji + 手写感 + 看起来不专业 + 文生图 prompt"已废弃——那套糙美学与高级感冲突、执行效果差'
    in method,
    "pin: html_card route steps": "出卡时走 `html_card` 路径：读 card-design → **选一个风格**" in method
    and "写 HTML → `render_card.py` 渲染 → `card_audit.py` 硬门禁" in method,
    "pin: 素人感 is delivered through style choice, not big emoji or rough layout": "**不是**靠大 emoji 和糙排版" in method,
    "pin: real-photo cards stay restrained": "叠字/拼图也保持克制、不堆 emoji" in method,
    "pin: glossary row for 素人感": "视觉仍走 card-design，不靠糙排版" in method,
    "pin: checklist visual line": "视觉走了 card-design 选定风格、填满画幅、`card_audit` PASS？（不是糙卡）" in method,
}
missing = [why for why, ok in required.items() if not ok]
if missing:
    print("missing:", "; ".join(missing))
    sys.exit(1)
print("ok")
