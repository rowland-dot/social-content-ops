#!/usr/bin/env python3
"""Validate a Xiaohongshu meta.json against the schema in references/meta-schema.md.

Checks (fatal unless noted). Common to both post_format:
- JSON parses
- required top-level: title, platform=="小红书", created_at, caption, hashtags
- title length: 1..30 (warn if >20)
- caption length: 100..1000 (code points); target ~300, warn above 800
- hashtags: 5..10 items, each startswith "#"

post_format == "image" (default when field absent):
- card_count + cards required
- card_count == len(cards) and in 3..9
- cards[0].type == "cover", cards[-1].type == "ending", middle all "content"
- every card: (title or content non-empty), cp_len(title)+cp_len(content) <= 80

post_format == "video":
- shots[] required, 6..12 items
- cards[] optional; if present, exactly 1 item with type=="cover"
- every shot: index int, duration_sec > 0, narration/on_screen_text/visual non-empty,
  cp_len(narration) <= 30, cp_len(on_screen_text) <= 15

Claim record (both post_formats, issue 102): top-level `claims` list is required (empty list = no claims).
- each entry: `text` (the claim as written in the post) plus EITHER evidence_type + source
  OR fallback ("removed" | "reworded", reworded also needs `now`, the new wording)
- an evidenced claim's text, and a reworded entry's `now`, must appear word for word in the post's own text
  (long draft = the .md at the note folder's top level, caption, cards, shots); a removed claim must not
- a fetched_reference / user_material source that is a relative path must exist inside the note folder

Creation guide (issue 125): top-level `creation_guide` {path, date} is required: the guide the writer read first.

Reference analysis (issue 68): top-level `reference_analysis` (path, inside the note folder, of reference/reference-analysis.json) is required.
- the file parses; `posts[]` is non-empty; each post has kind (team_supplied | team_rewrite | topic_study), source, record (an existing
  path, in the note folder or as given), structure{hook, order, product_entry, cta, length} and context{speaker, situation, audience}
- `voice` is {"from": [non-empty list]} or {"none": "non-empty statement"}; `draft_plan` is non-empty
- the post's own text shares no run of 20+ characters with a saved reference text (caption.md in a record folder, or the record file)

Exit 0 clean, 1 on errors. Prints one "ERROR:" / "WARN:" per line.

Usage: python3 validate_meta.py path/to/meta.json
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


EVIDENCE_TYPES = ("brand_document", "fetched_reference", "team_statement", "user_material")
FALLBACKS = ("removed", "reworded")
LOCAL_EVIDENCE_TYPES = ("fetched_reference", "user_material")


def cp_len(s: str) -> int:
    return len(s or "")


def post_text(meta: dict, folder: Path) -> str:
    """The post's own words: long draft, caption, card title/content, shot narration/on-screen text."""
    parts = [str(meta.get("caption") or "")]
    for c in meta.get("cards") or []:
        if isinstance(c, dict):
            parts += [str(c.get("title") or ""), str(c.get("content") or "")]
    for s in meta.get("shots") or []:
        if isinstance(s, dict):
            parts += [str(s.get("narration") or ""), str(s.get("on_screen_text") or "")]
    parts += [m.read_text(encoding="utf-8") for m in sorted(folder.glob("*.md"))]
    return "\n".join(parts)


def is_local_path(source: str) -> bool:
    return not (source.startswith(("http://", "https://", "/", "~")) or (len(source) > 1 and source[1] == ":"))


def check_creation_guide(meta: dict, err) -> None:
    g = meta.get("creation_guide")
    if not isinstance(g, dict) or not str(g.get("path") or "").strip():
        err("missing field: creation_guide (path of the account's creation guide the writer read first, and its date)")
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(g.get("date") or "")):
        err("creation_guide.date must be YYYY-MM-DD (the guide's last-changed date)")


REF_KINDS = ("team_supplied", "team_rewrite", "topic_study")
REF_STRUCTURE = ("hook", "order", "product_entry", "cta", "length")
REF_CONTEXT = ("speaker", "situation", "audience")
COPY_RUN = 20


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def check_reference_analysis(meta: dict, folder: Path, err) -> None:
    rel = str(meta.get("reference_analysis") or "").strip()
    if not rel:
        err("missing field: reference_analysis (path of reference/reference-analysis.json, the decomposition of the reference posts)")
        return
    f = folder / rel
    try:
        a = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(a, dict)
    except Exception as e:
        err(f"reference_analysis file {rel} is missing or does not parse: {e}")
        return
    posts = a.get("posts")
    saved: list[str] = []
    if not isinstance(posts, list) or not posts:
        err("reference_analysis lists no analysed post (posts[] is empty)")
        posts = []
    for i, p in enumerate(posts):
        at = f"reference_analysis posts[{i}]"
        if not isinstance(p, dict):
            err(f"{at} must be an object")
            continue
        if p.get("kind") not in REF_KINDS:
            err(f"{at}.kind must be one of {REF_KINDS}, got {p.get('kind')!r}")
        if not str(p.get("source") or "").strip():
            err(f"{at}.source is empty")
        rec = str(p.get("record") or "").strip()
        # a record may sit outside the note folder (read_note.py's own folder, the team's material folder)
        r = folder / rec if (folder / rec).exists() else Path(rec)
        if not rec:
            err(f"{at}.record is empty")
        elif not r.exists():
            err(f"{at}.record does not exist (in the note folder or as given): {rec}")
        else:
            cap = r / "caption.md" if r.is_dir() else r
            if cap.is_file():
                saved.append(_squash(cap.read_text(encoding="utf-8")))
        for key, fields in (("structure", REF_STRUCTURE), ("context", REF_CONTEXT)):
            d = p.get(key)
            for k in fields:
                if not isinstance(d, dict) or not str(d.get(k) or "").strip():
                    err(f"{at}.{key}.{k} is empty")
    v = a.get("voice")
    if not (isinstance(v, dict) and ((isinstance(v.get("from"), list) and v["from"])
                                     or (not v.get("from") and str(v.get("none") or "").strip()))):
        err("reference_analysis voice must be {\"from\": [saved team rewrites]} or {\"none\": \"plain statement\"}")
    if not str(a.get("draft_plan") or "").strip():
        err("reference_analysis draft_plan is empty (which structure the new post takes from which posts)")
    mine = _squash(post_text(meta, folder))
    grams = {mine[i:i + COPY_RUN] for i in range(len(mine) - COPY_RUN + 1)}
    for s in saved:
        for i in range(len(s) - COPY_RUN + 1):
            if s[i:i + COPY_RUN] in grams:
                err(f"reference_analysis: the post copies {COPY_RUN}+ characters of a saved reference text: {s[i:i + COPY_RUN]!r}")
                break


def check_claims(meta: dict, folder: Path, err) -> None:
    if "claims" not in meta:
        err("missing field: claims (the claim record; use [] when the post makes no factual claims)")
        return
    claims = meta["claims"]
    if not isinstance(claims, list):
        err("claims must be list")
        return
    text = post_text(meta, folder)
    for i, c in enumerate(claims):
        at = f"claims[{i}]"
        if not isinstance(c, dict) or not str(c.get("text") or "").strip():
            err(f"{at} needs a non-empty text")
            continue
        claim = c["text"]
        fallback = c.get("fallback")
        if fallback:
            if fallback not in FALLBACKS:
                err(f"{at}.fallback must be one of {FALLBACKS}, got {fallback!r}")
            elif fallback == "removed":
                if claim in text:
                    err(f"{at} is 'removed' but its text is still in the post: {claim!r}")
            else:
                now = str(c.get("now") or "").strip()
                if not now:
                    err(f"{at} is 'reworded' but has no `now` (the new wording)")
                elif now not in text:
                    err(f"{at}.now is not in the post word for word: {now!r}")
            continue
        etype, source = c.get("evidence_type"), str(c.get("source") or "").strip()
        if not etype:
            err(f"{at} has neither evidence_type+source nor fallback")
            continue
        if etype not in EVIDENCE_TYPES:
            err(f"{at}.evidence_type must be one of {EVIDENCE_TYPES}, got {etype!r}")
            continue
        if not source:
            err(f"{at}.source is empty")
        elif etype in LOCAL_EVIDENCE_TYPES and is_local_path(source) and not (folder / source).exists():
            err(f"{at}.source file does not exist in the note folder: {source}")
        if claim not in text:
            err(f"{at}.text is not in the post word for word: {claim!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验小红书图文/视频 meta.json")
    parser.add_argument("meta", help="meta.json 路径")
    args = parser.parse_args()
    p = Path(args.meta)
    errors: list[str] = []
    warns: list[str] = []

    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot parse json: {e}")
        return 1

    def err(m): errors.append(m)
    def warn(m): warns.append(m)

    for k in ("title", "platform", "created_at", "caption", "hashtags"):
        if k not in meta:
            err(f"missing field: {k}")

    if meta.get("platform") != "小红书":
        err(f"platform must be '小红书', got {meta.get('platform')!r}")

    post_format = meta.get("post_format", "image")
    if post_format not in ("image", "video"):
        err(f"post_format must be 'image' or 'video', got {post_format!r}")

    title = meta.get("title", "")
    if not title:
        err("title empty")
    elif cp_len(title) > 30:
        err(f"title too long ({cp_len(title)} > 30)")
    elif cp_len(title) > 20:
        warn(f"title {cp_len(title)} chars; Xiaohongshu feed prefers 10-20")

    cap = meta.get("caption", "")
    cl = cp_len(cap)
    if cl < 100:
        err(f"caption too short ({cl} < 100)")
    elif cl > 1000:
        err(f"caption too long ({cl} > 1000, Xiaohongshu's limit)")
    elif cl > 800:
        warn(f"caption is {cl} chars; recommended range is 300-800")

    tags = meta.get("hashtags", [])
    if not isinstance(tags, list) or not (5 <= len(tags) <= 10):
        err(f"hashtags must have 5..10 items, got {len(tags) if isinstance(tags, list) else 'n/a'}")
    else:
        for t in tags:
            if not (isinstance(t, str) and t.startswith("#")):
                err(f"hashtag must be string starting with '#': {t!r}")

    if post_format == "image":
        if "card_count" not in meta:
            err("missing field: card_count (required for post_format=image)")
        if "cards" not in meta:
            err("missing field: cards (required for post_format=image)")
        cards = meta.get("cards", [])
        count = meta.get("card_count")
        if not isinstance(cards, list):
            err("cards must be list")
        else:
            if count is not None and count != len(cards):
                err(f"card_count={count} != len(cards)={len(cards)}")
            if not (3 <= len(cards) <= 9):
                err(f"cards count must be 3..9, got {len(cards)}")
            for i, c in enumerate(cards):
                t = c.get("type")
                if i == 0 and t != "cover":
                    err(f"cards[0].type must be 'cover', got {t!r}")
                elif i == len(cards) - 1 and t != "ending":
                    err(f"cards[-1].type must be 'ending', got {t!r}")
                elif 0 < i < len(cards) - 1 and t != "content":
                    err(f"cards[{i}].type must be 'content', got {t!r}")
                total = cp_len(c.get("title", "")) + cp_len(c.get("content", ""))
                if total == 0:
                    err(f"cards[{i}] has empty title+content")
                if total > 80:
                    err(f"cards[{i}] over 80 chars ({total})")
    else:  # video
        shots = meta.get("shots", [])
        if not isinstance(shots, list) or not shots:
            err("shots must be non-empty list for post_format=video")
        else:
            if not (6 <= len(shots) <= 12):
                err(f"shots count must be 6..12, got {len(shots)}")
            for i, s in enumerate(shots):
                if not isinstance(s.get("index"), int):
                    err(f"shots[{i}].index must be int")
                d = s.get("duration_sec")
                if not (isinstance(d, (int, float)) and d > 0):
                    err(f"shots[{i}].duration_sec must be > 0")
                for k, limit in (("narration", 30), ("on_screen_text", 15)):
                    v = s.get(k, "")
                    if not v:
                        err(f"shots[{i}].{k} empty")
                    elif cp_len(v) > limit:
                        err(f"shots[{i}].{k} over {limit} chars ({cp_len(v)})")
                if not s.get("visual"):
                    err(f"shots[{i}].visual empty")
        cards = meta.get("cards")
        if cards is not None:
            if not (isinstance(cards, list) and len(cards) == 1
                    and cards[0].get("type") == "cover"):
                err("for post_format=video, cards must be omitted or a single cover card")

    check_creation_guide(meta, err)
    check_reference_analysis(meta, p.resolve().parent, err)
    check_claims(meta, p.resolve().parent, err)

    for w in warns:
        print(f"WARN:  {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        print(f"\n{len(errors)} error(s), {len(warns)} warning(s)")
        return 1
    print(f"OK ({len(warns)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
