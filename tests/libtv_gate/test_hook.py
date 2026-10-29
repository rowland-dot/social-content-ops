"""The note at session open (issue 37, the owner's ruling 1): a Claude Code SessionStart hook runs the gate.

The owner sees one short line (`systemMessage`) and Claude's context gets what it needs to put the question to him
(`additionalContext`). A finding comes back at every session open until the owner answers it through the question tool;
a session without the owner never answers for him. Seams: `libtv_gate.py hook`, `decline`, `book`, `ack-settings`
against the stand-in LibTV.
"""

from __future__ import annotations

import json


def _hook(lt, **kw):
    result = lt.run("hook", **kw)
    assert result.code == 0, f"a hook never fails the session: {result.out} {result.err}"
    if not result.out.strip():
        return result, None
    return result, json.loads(result.out)


def _context(note: dict) -> str:
    return note["hookSpecificOutput"]["additionalContext"]


def _new_version(lt, version="1.1.4"):
    lt.publish_candidate(version)


# ---- when there is nothing to say ---------------------------------------------------------------------


def test_with_nothing_new_the_hook_prints_nothing(lt):
    result, note = _hook(lt)
    assert note is None and result.out.strip() == ""


# ---- a new version ------------------------------------------------------------------------------------


def test_a_new_version_gives_ro_a_line_and_claude_the_way_to_ask(lt):
    _new_version(lt)
    _, note = _hook(lt)
    assert "1.1.4" in note["systemMessage"] and "1.1.3" in note["systemMessage"]
    assert note["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    context = _context(note)
    assert "question tool" in context
    assert "libtv_gate.py candidate 1.1.4" in context, "Claude is told how to read what the version changes first"
    assert "libtv_gate.py book 1.1.4" in context and "libtv_gate.py decline 1.1.4" in context
    assert "not now" in context.lower()


def test_nothing_is_downloaded_when_a_session_opens(lt):
    _new_version(lt)
    _hook(lt)
    assert [p for p in lt.requests("GET") if p.endswith(".zip")] == []


def test_the_note_comes_back_at_every_session_open_until_ro_answers(lt):
    _new_version(lt)
    for _ in range(3):
        assert _hook(lt)[1] is not None


def test_declining_a_version_silences_it_until_the_channel_moves_past_it(lt):
    _new_version(lt)
    assert lt.run("decline", "1.1.4").code == 0
    assert _hook(lt)[1] is None
    _new_version(lt, "1.1.5")
    _, note = _hook(lt)
    assert "1.1.5" in note["systemMessage"]


def test_booking_a_version_silences_the_note(lt):
    _new_version(lt)
    assert lt.run("keep-pin").code == 0
    assert lt.run("book", "1.1.4").code == 0
    assert _hook(lt)[1] is None


def test_the_context_keeps_headless_sessions_from_answering_for_ro(lt):
    _new_version(lt)
    context = _context(_hook(lt)[1])
    assert "headless" in context.lower() and "never" in context.lower()
    assert "only after the owner answers" in context


def test_the_context_forbids_running_or_installing_libtv(lt):
    _new_version(lt)
    context = _context(_hook(lt)[1])
    assert "never run the libtv program" in context.lower()
    assert "never install" in context.lower()


def test_a_version_whose_bytes_changed_between_fetches_is_reported_but_not_offered(lt):
    _new_version(lt)
    a, b = lt.make_zip(lt.BASE_DOCS), lt.make_zip({**lt.BASE_DOCS, "SKILL.md": "other\n"})
    lt.route("/cli/1.1.4/libtv-cli-skill.zip", sequence=[a, b])
    assert lt.run("candidate", "1.1.4").code == 1
    _, note = _hook(lt)
    assert "not offered" in note["systemMessage"]
    assert "libtv_gate.py book 1.1.4" not in _context(note)


# ---- the other findings -------------------------------------------------------------------------------


def test_changed_settings_ask_ro_to_acknowledge(lt):
    lt.run("check")
    lt.set_settings("182", {"video": [{"modelKey": "m-new", "modelName": "New"}]})
    _, note = _hook(lt)
    assert "run-time settings" in note["systemMessage"]
    assert "libtv_gate.py ack-settings" in _context(note)


def test_a_notice_from_libtv_is_shown_and_never_acknowledged_away(lt):
    lt.set_notice(True, "请尽快升级")
    _, note = _hook(lt)
    assert "请尽快升级" in note["systemMessage"]
    assert "ack-settings" not in _context(note)
    assert _hook(lt)[1] is not None, "it stays until LibTV withdraws it"


# ---- LibTV cannot be reached, or the hook cannot run --------------------------------------------------


def test_an_unreachable_libtv_is_a_could_not_check_note_never_a_quiet_session(lt):
    _, note = _hook(lt, api_base=lt.closed_base())
    assert "could not check" in note["systemMessage"].lower()
    assert "no update" not in note["systemMessage"].lower()


def test_the_hook_ends_within_its_time_limit_when_libtv_hangs(lt):
    for path in list(lt.server.routes):
        if path.startswith("/api/"):
            lt.server.routes[path].delay = 30
    result, note = _hook(lt, env={"LIBTV_GATE_TIMEOUT": "60", "LIBTV_GATE_DEADLINE": "2"})
    assert result.seconds < 15
    assert "could not check" in note["systemMessage"].lower()


def test_an_unreadable_pin_is_said_in_the_session_and_does_not_fail_it(lt, tmp_path):
    empty = tmp_path / "no-repo"
    empty.mkdir()
    result, note = _hook(lt, root=empty)
    assert "pin" in note["systemMessage"].lower()
