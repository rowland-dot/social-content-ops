from __future__ import annotations
import json, re
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parents[1] / "references" / "tmall-rules.md"
STATUSES = {"confirmed", "unconfirmed", "from-spec", "proposal"}

def walk(node, prefix=""):
    if isinstance(node, dict) and "value" in node and "status" in node:
        yield prefix, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{prefix}.{k}" if prefix else k)

def load(path: Path = RULES_FILE) -> dict:
    block = re.search(r"```json\n(.*?)\n```", Path(path).read_text(encoding="utf-8"), re.S)
    if not block:
        raise ValueError("no json block in the rules file")
    data = json.loads(block.group(1))
    for p, rule in walk(data):
        if rule["status"] not in STATUSES or not rule.get("source"):
            raise ValueError(f"rule {p} needs a status and a source")
    return data

def value(rules: dict, path: str):
    node = rules
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"no rule {path!r} in the Tmall rules file ({RULES_FILE.name}); stopped at {part!r}")
        node = node[part]
    return node["value"]

def for_width(rules: dict, path: str, width: int):
    """A number worked out from the image width (minimum type size) is a table keyed by the width as text; a plain number
    applies to every width. A width with no entry gets the strictest (largest) entry, never none."""
    v = value(rules, path)
    return v.get(str(width), max(v.values())) if isinstance(v, dict) else v

def not_confirmed(rules: dict) -> list[str]:
    return [p for p, r in walk(rules) if r["status"] in {"unconfirmed", "proposal"}]

def _hits(text: str, words) -> list[str]:
    return [w for w in words if w in text]

def _listed(rules: dict, path: str) -> list[str]:
    """Words a page names, plus the old leads no page names (`<path>_unlisted`): the second list still stops images, so reading
    the pages never releases a word the earlier list stopped."""
    try:
        extra = value(rules, path + "_unlisted")
    except KeyError:
        extra = []
    return value(rules, path) + extra

def banned_hits(text, rules): return _hits(text, _listed(rules, "words.banned"))
def after_state_hits(text, rules): return _hits(text, value(rules, "words.after_state"))
def bonded_hits(text, rules): return _hits(text, _listed(rules, "bonded.must_not"))
