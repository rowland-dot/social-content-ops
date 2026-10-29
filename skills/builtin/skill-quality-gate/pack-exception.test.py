"""Red/green check for issue 94: the quality gate never reads what is printed on the real product pack.

The owner's rule (CLAUDE.md, "Product pack wording is never checked"): the wording printed on a real product pack is
never checked, flagged, raised with the owner, or used as a reason to resize or hide the pack in an image. Easel's own
words on the image, and the post's text, are still checked.

Run: python skills/builtin/skill-quality-gate/pack-exception.test.py   (exit 0 = pass). The same assertions run in
tests/test_skill_quality_gate_pack_exception.py, which CI collects (it loads this file); this copy sits beside the skill.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKUP = HERE.parents[2] / "archive" / "skill-backups" / "skill-quality-gate" / "2026-10-28"
REFS = HERE / "references"

RO_RULE = "Product pack wording is never checked"
RO_QUOTE = (
    "The wording printed on a real product pack, English or any other language, is never checked, flagged, "
    "raised with the owner, or used as a reason to resize or hide the pack in an image."
)
# the short exception every touched rule file carries beside the rule it could trip
SHORT_NEEDS = ["真实商品包装", "不读、不列、不标记", RO_RULE]

SKILL_NEEDS = [
    "以负责人的规则为准", RO_RULE, RO_QUOTE,
    "不读、不列、不引用、不标记", "品牌自己的 Logo 和标记", "二维码、条形码和平台名",
    "不拿它当判定或修改建议的理由", "不提出缩小、裁掉、转向、模糊或藏起包装",
    "Easel 自己加到图上的字", "标题、标签、贴纸、装饰英文、字幕",
    "帖子的标题、正文、话题标签和任何脚本或文案", "照旧按全部规则检查",
    "即使这些字和包装上印的是同一句话",
]
GENERAL_SECTIONS = ["绝对化用语", "虚假宣传", "医疗/药品违规", "版权风险"]


def sections(text: str) -> dict:
    parts = text.split("\n## ")
    return {p.split("\n", 1)[0].strip(): p for p in parts[1:]}


def problems() -> list:
    out = []
    skill = (HERE / "SKILL.md").read_text(encoding="utf-8")
    for need in SKILL_NEEDS:
        if need not in skill:
            out.append(f"SKILL.md does not say: {need}")
    step_one = skill.split("1. 读取内容", 1)[-1].split("2. 加载通用合规规则", 1)[0]
    if RO_RULE not in step_one:
        out.append("SKILL.md: the exception is not in compliance step 1 (读取内容)")
    quality = skill.split("### 第二关：质量审核", 1)[-1].split("### 综合判定", 1)[0]
    if "真实商品包装" not in quality or RO_RULE not in quality:
        out.append("SKILL.md: the image quality step does not carry the exception")

    general = sections((REFS / "general-rules.md").read_text(encoding="utf-8"))
    for name in GENERAL_SECTIONS:
        sec = next((v for k, v in general.items() if k.startswith(name)), "")
        for need in SHORT_NEEDS:
            if need not in sec:
                out.append(f"general-rules.md section {name} does not say: {need}")

    xhs = sections((REFS / "platform-xiaohongshu.md").read_text(encoding="utf-8")).get("导流外站", "")
    for need in SHORT_NEEDS + ["二维码", "平台名"]:
        if need not in xhs:
            out.append(f"platform-xiaohongshu.md 导流外站 does not say: {need}")

    douyin = (REFS / "platform-douyin.md").read_text(encoding="utf-8")
    for need in SHORT_NEEDS:
        if need not in douyin:
            out.append(f"platform-douyin.md does not say: {need}")

    images = (REFS / "review-dimensions.md").read_text(encoding="utf-8")
    images = images.split("## 图片类产物", 1)[-1].split("## 视频类产物", 1)[0]
    for need in SHORT_NEEDS + ["内容匹配"]:
        if need not in images:
            out.append(f"review-dimensions.md image table does not say: {need}")

    # Bilibili has no line a pack could trip: untouched
    if (REFS / "platform-bilibili.md").read_bytes() != (BACKUP / "references" / "platform-bilibili.md").read_bytes():
        out.append("platform-bilibili.md was changed")

    # nothing lost: every original non-empty line is still there word for word
    if not BACKUP.is_dir():
        out.append("the 2026-10-28 backup folder is missing")
    for old in sorted(BACKUP.rglob("*.md")) if BACKUP.is_dir() else []:
        rel = old.relative_to(BACKUP)
        now = HERE / rel
        if not now.is_file():
            out.append(f"{rel} is gone")
            continue
        have = set(now.read_text(encoding="utf-8").splitlines())
        for line in old.read_text(encoding="utf-8").splitlines():
            if line.strip() and line not in have:
                out.append(f"{rel} lost the line: {line}")
    return out


if __name__ == "__main__":
    found = problems()
    if found:
        print("\n".join(found))
        sys.exit(1)
    print("ok")
