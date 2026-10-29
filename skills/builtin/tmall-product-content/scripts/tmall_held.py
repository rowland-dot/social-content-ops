"""Fails closed: a tool listed as held (or not listed) is refused."""
from __future__ import annotations
import json
from pathlib import Path

HELD_FILE = Path(__file__).resolve().parents[1] / "references" / "held.json"

class HeldError(RuntimeError):
    pass

def require_released(tool: str, held_file: Path = HELD_FILE) -> None:
    try:
        entry = json.loads(Path(held_file).read_text(encoding="utf-8")).get(tool)
    except (OSError, ValueError, AttributeError) as e:     # a missing, unreadable or malformed hold file is a hold, not a crash
        raise HeldError(f"{tool} is held: the hold file {Path(held_file).name} cannot be read ({type(e).__name__}); nothing is released without it") from e
    if entry is None or entry.get("held", True):
        why = (entry or {}).get("until", "no release is recorded for this tool")
        raise HeldError(f"{tool} is held until: {why}. The hold is lifted only by setting held to false in {Path(held_file).name}, "
                        "after both Easel fixes are confirmed on main and the owner has been told")
