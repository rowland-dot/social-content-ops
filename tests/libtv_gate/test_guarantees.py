"""What the LibTV update gate must never do (issue 37), across every command it has.

Seams: the gate's command line (each command, against the stand-in LibTV, with a `libtv` stand-in first on PATH that
writes down any call), and the gate's own source files.
"""

from __future__ import annotations

import re
from pathlib import Path

GATE_DIR = Path(__file__).resolve().parents[2] / "ops" / "libtv-update-gate"


def _every_command(lt):
    """one run of each command the gate has, on a world with a newer version published and a settings change"""
    lt.run("check")                                  # baselines
    lt.publish_candidate("1.1.4")
    lt.set_settings("182", {"video": [{"modelKey": "m-new", "modelName": "New"}]})
    runs = [
        ("check", "--deep"),
        ("keep-pin",),
        ("candidate", "1.1.4"),
        ("hook",),
        ("book", "1.1.4"),
        ("decline", "1.1.5"),
        ("ack-settings",),
        ("check",),
    ]
    return [(args, lt.run(*args)) for args in runs]


def test_no_libtv_program_is_ever_run_by_any_command(lt):
    results = _every_command(lt)
    assert all(r.code in (0, 1) for _, r in results), [(a, r.code, r.err) for a, r in results]
    assert lt.libtv_calls() == "", "the libtv stand-in on PATH was called"


def test_the_gate_cannot_start_a_program_or_read_a_login_at_all():
    """a stand-in only catches a program named libtv; the sources themselves hold no way to start one or read a login"""
    starters = re.compile(r"\b(subprocess|os\.system|os\.exec\w*|os\.spawn\w*|Popen|pty|ctypes)\b")
    logins = re.compile(r"credentials|LIBTV_CONFIG_DIR|usertoken|useruuid|\.libtv\b", re.I)
    for source in sorted(GATE_DIR.glob("*.py")):
        text = source.read_text(encoding="utf-8")
        assert not starters.search(text), f"{source.name} can start a program"
        assert not logins.search(text), f"{source.name} refers to a login"


def test_the_pins_and_vendored_files_are_read_never_written_by_any_command(lt):
    before = lt.pin_hashes()
    _every_command(lt)
    assert lt.pin_hashes() == before


def test_the_gates_own_files_are_kept_under_scratch_by_default_so_git_never_lists_them(lt):
    lt.run("check", default_store=True)
    lt.run("keep-pin", default_store=True)
    assert (lt.root / ".scratch" / "libtv-update-gate" / "state.json").is_file()
    assert (lt.root / ".scratch" / "libtv-update-gate" / "pinned" / "1.1.3" / "libtv-linux-x64.zip").is_file()


def test_a_command_with_something_that_is_not_a_version_number_is_refused_before_it_touches_anything(lt):
    for command in ("book", "decline", "candidate"):
        result = lt.run(command, "../../etc")
        assert result.code == 2 and "not a version number" in result.err
    assert lt.requests() == []
    assert not lt.store.exists()


def test_a_repo_whose_pin_cannot_be_read_is_refused_not_guessed(lt, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = lt.run("check", root=empty)
    assert result.code == 2 and "cannot read the pin" in result.err
    assert lt.requests() == []
