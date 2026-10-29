"""The gate's own small store, kept outside git: what it has recorded, what the owner answered, the kept copy of the pin."""

from __future__ import annotations

import json
import os
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)

    @property
    def state_file(self) -> Path:
        return self.path / "state.json"

    def load(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save(self, state: dict) -> None:
        """Whole-file replace, so two sessions opening at once never leave half a file."""
        self.path.mkdir(parents=True, exist_ok=True)
        tmp = self.path / f"state.json.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.state_file)

    def pinned_copy(self, version: str) -> Path:
        return self.path / "pinned" / version / "libtv-linux-x64.zip"
