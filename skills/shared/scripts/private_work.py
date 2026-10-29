"""Where the private work folder is, and what to say when it is missing (issue 136).

The public project keeps only the engine. The owner's and the team's own material (the project rules, specs,
plans, issue records, the team's photo-scene package) lives in `work/`, a folder with its own git repository
that the public project ignores. Code that needs a file from there asks this module, and a fresh public
clone, which has no `work/`, gets a plain message instead of a crash.
"""
from __future__ import annotations

from pathlib import Path

WORK_FOLDER = "work"


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def work_dir(root: Path | None = None) -> Path | None:
    folder = (root or project_root()) / WORK_FOLDER
    return folder if folder.is_dir() else None


def private_file(rel: str, root: Path | None = None) -> Path | None:
    folder = work_dir(root)
    if folder is None:
        return None
    path = folder / rel
    return path if path.exists() else None


def missing_message(what: str) -> str:
    return (f"{what} lives in the private work folder (work/), and that folder is not here. "
            "Nothing was read from it. A copy of the project made without that folder cannot use it.")
