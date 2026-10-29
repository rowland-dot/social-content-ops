"""Line endings of what the repository stores, issue 56.

Seam: the bytes git stores (the index, read with `git show :<path>`), never the files on disk,
whose endings depend on each machine's checkout settings (this PC's Git for Windows says
core.autocrlf=true, so a fresh clone would show every file as CRLF).

The owner, 2026-10-23: "Add a project rule, fix our 14 (Recommended)". Our 14 files are LF; the two
Windows start files stay CRLF; the team's photo-scene package stays byte for byte with its hashes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OUR_FILES = [
    "ops/libtv-update-gate/libtv_answers.py",
    "ops/libtv-update-gate/libtv_candidate.py",
    "ops/libtv-update-gate/libtv_detect.py",
    "ops/libtv-update-gate/libtv_gate.py",
    "ops/libtv-update-gate/libtv_hook.py",
    "ops/libtv-update-gate/libtv_http.py",
    "ops/libtv-update-gate/libtv_report.py",
    "ops/libtv-update-gate/libtv_settings.py",
    "skills/builtin/auto-short-video/scripts/assemble.py",
    "skills/shared/scripts/sound_check.py",
    "tests/test_assemble_music.py",
    "tests/test_sound_check.py",
    "tests/test_storyboard_page.py",
]
CMD_FILES = ["ops/easel-start/easel-start.cmd", "ops/easel-start/easel-web-window.cmd"]


def _stored(path: str) -> bytes:
    return subprocess.run(
        ["git", "show", ":" + path], cwd=ROOT, capture_output=True, check=True, timeout=60
    ).stdout


def test_our_files_are_stored_without_carriage_returns():
    crlf = [p for p in OUR_FILES if b"\r" in _stored(p)]
    assert crlf == []


def test_windows_start_files_are_stored_with_crlf_on_every_line():
    for path in CMD_FILES:
        data = _stored(path)
        assert data.count(b"\n") > 0, path
        assert data.count(b"\r\n") == data.count(b"\n"), path




def test_gitattributes_makes_text_lf_and_leaves_windows_files_alone():
    lines = [
        ln.split() for ln in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    assert ["*", "text=auto", "eol=lf"] in lines
    assert ["*.cmd", "-text"] in lines
