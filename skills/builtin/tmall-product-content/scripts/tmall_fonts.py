"""A font on the page must carry a commercial-use licence in its own file; being installed is not a licence."""
from __future__ import annotations
import json
from pathlib import Path
from fontTools.ttLib import TTCollection, TTFont

LIST_FILE = Path(__file__).resolve().parents[1] / "references" / "fonts-licensed.json"
OK = ("SIL Open Font License", "Apache License", "Open Font License")

class FontNotLicensed(RuntimeError):
    pass

def load_list(path: Path = LIST_FILE) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _fonts(path):
    path = str(path)
    return TTCollection(path, lazy=True).fonts if path.lower().endswith(".ttc") else [TTFont(path, lazy=True)]

def licence_text(path, family: str) -> str:
    for font in _fonts(path):
        name = font["name"]
        if family in {name.getDebugName(1), name.getDebugName(16)}:
            return name.getDebugName(13) or ""
    return ""

def is_commercially_licensed(path, family: str) -> bool:
    text = licence_text(path, family)
    return any(k.lower() in text.lower() for k in OK)

def assert_allowed(family: str, listed: list[dict] | None = None) -> None:
    entry = next((e for e in (listed or load_list()) if e["family"] == family), None)
    if entry is None:
        raise FontNotLicensed(f"{family}: not in the licensed list")
    for f in [entry["file"], *entry.get("also", [])]:     # "also": the weights the page renders from, such as the bold file a 700-weight headline uses
        if not Path(f).exists():          # the browser would fall back to a font nobody checked (autoplan review)
            raise FontNotLicensed(f"{family}: font file {f} is not on this machine, so the licence cannot be read")
        if not is_commercially_licensed(f, family):
            raise FontNotLicensed(f"{family}: {f} carries no commercial-use licence text")
