"""Test helper (issue 68): writes stand-in saved reference posts (read_note.py folder shape) and a complete
reference/reference-analysis.json into a generated note folder. Makes no Xiaohongshu request."""
import json
from pathlib import Path

FIELD = "reference_analysis"
ANALYSIS_PATH = "reference/reference-analysis.json"
SAVED_TEXT = "这是被保存下来的参考帖正文，讲的是通勤路上怎么补充营养的一段真实分享，和新帖子没有重复的句子。"
REWRITE_TEXT = "团队改写过的一篇文案，语气像朋友聊天，先说结果再说过程，结尾轻轻问一句你们呢。"


def complete_analysis() -> dict:
    structure = {"hook": "反问开头", "order": "场景-做法-感受", "product_entry": "第三段自然带出", "cta": "评论区问一句", "length": "约300字"}
    context = {"speaker": "普通上班族", "situation": "通勤路上", "audience": "同样赶时间的人"}
    return {
        "posts": [
            {"kind": "team_supplied", "source": "https://www.xiaohongshu.com/explore/abc", "record": "reference/saved-1",
             "structure": dict(structure), "context": dict(context)},
            {"kind": "team_rewrite", "source": "team text file", "record": "reference/team-rewrite.md",
             "structure": dict(structure), "context": dict(context)},
        ],
        "voice": {"from": ["reference/team-rewrite.md"]},
        "draft_plan": "钩子取第一篇的反问开头，段落顺序取第二篇的先结果后过程。",
    }


def write_analysis(folder: Path, analysis: dict | None = None) -> None:
    """Save the stand-in records and the analysis (default: a complete one) under folder/reference/."""
    ref = folder / "reference"
    (ref / "saved-1").mkdir(parents=True, exist_ok=True)
    (ref / "saved-1" / "caption.md").write_text(SAVED_TEXT, encoding="utf-8")
    (ref / "saved-1" / "record.json").write_text(json.dumps({"parts": []}), encoding="utf-8")
    (ref / "team-rewrite.md").write_text(REWRITE_TEXT, encoding="utf-8")
    (ref / "reference-analysis.json").write_text(
        json.dumps(analysis if analysis is not None else complete_analysis(), ensure_ascii=False), encoding="utf-8")
