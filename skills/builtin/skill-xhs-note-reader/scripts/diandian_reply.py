"""Which 点点 replies are saved as a summary of a note, and which are not.

A port of FavSense's reply rules (repository C:\\Users\\<user>\\Codex\\小红书收藏整理, commit 756ec6d):
  - is_refusal / is_incomplete: skills/xhs-favorites-organizer/scripts/diandian_refusal.py
  - clean_summary / the footer list / the check for note addresses and access codes:
    skills/xhs-diandian-summarize-note/scripts/save_diandian_summary.py (commit 746ebca)
  - the shortest summary kept (20 characters): runtime/browser-contract.json, "minimum_summary_chars"
Copied for issue 70 and never imported from FavSense at run time. Change them only to follow FavSense's files.
The tests hold the port to FavSense's own real-reply tables (tests/fixtures).
"""
from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import unquote

# The page wraps bold words in zero-width spaces, so they sit inside real replies.
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")

# A refusal says so at the start; a summary that merely contains these words further in is not one.
_LEAD_CHARS = 400
# Form 1: opens with an apology and says "cannot" in that same sentence.
_APOLOGY_THEN_CANNOT = re.compile(r"^\s*(?:很)?抱歉[^。！？!?\n]*?无法")
# Form 2: asks for the note's text or a screenshot to be sent back, with or without an apology.
_ASKS_TO_SEND_THE_NOTE = re.compile(r"(?:复制|粘贴|截图|截屏)[^。！？!?\n]{0,30}?(?:发给我|发送给我|发我|贴给我|给我)")
# A reply that lost text where list items were joined has a "- " list marker straight after a full stop, comma,
# colon or exclamation mark, in the middle of a line.
_LIST_MARKER_AFTER_PUNCTUATION = re.compile(r"[。，：！]- ")

MINIMUM_SUMMARY_CHARS = 20
_FOOTERS = (
    re.compile(r"(?:以上内容|本回答|本内容|内容)由\s*AI\s*生成[，, ]*(?:仅供参考)?[。！!]?"),
    re.compile(r"如果你还想了解更多(?:内容)?[，, ]*可以继续问我[。！!]?"),
    re.compile(r"你还可以继续问我(?:关于这篇笔记)?的问题[。！!]?"),
    re.compile(r"还有其他问题(?:的话)?[，, ]*欢迎继续提问[。！!]?"),
)
_SENSITIVE_SOURCE = re.compile(
    r"(?i)(?:xsec[\s_-]*token\s*=|"
    r"\b(?:access_token|refresh_token|authorization|cookie|password|secret)\s*[:=]|"
    r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}|"
    r"(?:(?:https?:)?//)?(?:www\.)?xiaohongshu\.com/)"
)


def is_refusal(text: object) -> bool:
    if not isinstance(text, str):
        return False
    lead = _INVISIBLE.sub("", text)[:_LEAD_CHARS]
    return bool(_APOLOGY_THEN_CANNOT.search(lead) or _ASKS_TO_SEND_THE_NOTE.search(lead))


def is_incomplete(text: object) -> bool:
    if not isinstance(text, str):
        return False
    return _LIST_MARKER_AFTER_PUNCTUATION.search(_INVISIBLE.sub("", text)) is not None


def _is_footer(paragraph: str) -> bool:
    compact = re.sub(r"\s+", "", paragraph)
    return any(pattern.fullmatch(compact) for pattern in _FOOTERS)


def clean_summary(text: str) -> tuple[str, list[str]]:
    """The reply without a recognised trailing footer (only whole paragraphs that match one), and what was removed."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs = [
        "\n".join(line.rstrip() for line in part.strip().splitlines()).strip()
        for part in re.split(r"\n\s*\n", normalized) if part.strip()
    ]
    removed: list[str] = []
    while paragraphs and _is_footer(paragraphs[-1]):
        removed.insert(0, paragraphs.pop())
    return "\n\n".join(paragraphs), removed


def _scan_text(value: str) -> str:
    """The text as a reader's browser would show it: entities and percent-escapes undone, invisible marks dropped."""
    seen = value
    for _ in range(8):
        decoded = unicodedata.normalize("NFKC", unquote(html.unescape(seen)))
        decoded = "".join(c for c in decoded if unicodedata.category(c) != "Cf")
        if decoded == seen:
            break
        seen = decoded
    return seen


def summary_problem(text: str) -> str | None:
    """Why this reply must not be saved as a summary, or None when it can be."""
    summary, _ = clean_summary(text or "")
    if not summary:
        return "empty"
    if is_refusal(summary):
        return "refusal"
    if is_incomplete(summary):
        return "incomplete"
    if len(summary) < MINIMUM_SUMMARY_CHARS:
        return "too short"
    if _SENSITIVE_SOURCE.search(_scan_text(summary)):
        return "holds a note address or access code"
    return None


def usable_summary(text: str) -> str:
    """The text to save: the whole finished reply minus a recognised footer. Call only when summary_problem is None."""
    return clean_summary(text)[0]
