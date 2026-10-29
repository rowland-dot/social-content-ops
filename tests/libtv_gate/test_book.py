"""The owner's yes (issue 37, ruling 2): booking writes a ready-filled issue and moves nothing.

The pins, the installed program and the vendored files move in that issue's own build, after triage. Seams:
`libtv_gate.py book <version>` and `decline <version>` against the stand-in LibTV, and the fixture repo's files.
"""

from __future__ import annotations

NEW_COMMANDS = {
    "node": {"": [], "create": ["--run", "--type", "--count"], "list": []},
    "login": {"": [], "web": []},
    "image": {"": [], "shortcut": []},
    "video": {"": [], "render": []},
}


def _issues(lt):
    return sorted((lt.root / "work" / ".scratch" / "easel-setup-gaps" / "issues").glob("*.md"))


def _booked(lt, version="1.1.4"):
    lt.publish_candidate(version, commands=NEW_COMMANDS)
    assert lt.run("keep-pin").code == 0
    result = lt.run("book", version)
    assert result.code == 0, result.out + result.err
    return result


def test_booking_writes_one_new_issue_numbered_next_with_the_needs_triage_status(lt):
    before = _issues(lt)
    _booked(lt)
    new = [p for p in _issues(lt) if p not in before]
    assert len(new) == 1
    assert new[0].name.startswith("39-") and "1.1.4" in new[0].name
    assert new[0].read_text(encoding="utf-8").splitlines()[0] == "Status: needs-triage"


def test_the_issue_carries_the_report_the_pins_to_move_the_paid_run_section_and_the_rollback_route(lt):
    _booked(lt)
    text = _issues(lt)[-1].read_text(encoding="utf-8")
    program_zip = lt.server.routes["/cli/1.1.4/libtv-linux-x64.zip"].body
    skill_zip = lt.server.routes["/cli/1.1.4/libtv-cli-skill.zip"].body
    # the report
    assert "Added command `video render`" in text
    # both pins to move, old and new
    assert "LIBTV_ZIP_SHA256" in text and lt.sha256(lt.pinned_program_zip) in text and lt.sha256(program_zip) in text
    assert "LIBTV_SHA256" in text and lt.sha256(lt.program_inside(program_zip)) in text
    assert "LIBTV_URL" in text and "/cli/1.1.4/libtv-linux-x64.zip" in text
    assert lt.sha256(skill_zip) in text
    # what moves together
    assert "references/vendor" in text and "libtv-cli-source.md" in text
    # the paid-run section, with its verdict against CLAUDE.md's list
    assert "NOT on CLAUDE.md's list" in text.split("## Paid-run section", 1)[1]
    # the rollback route, through the kept copy
    assert "Rollback" in text and "LIBTV_ZIP_FILE=" in text and "setup.sh --only libtv" in text


def test_booking_without_the_work_folder_says_so_in_plain_words_and_books_nothing(lt):
    lt.publish_candidate("1.1.4", commands=NEW_COMMANDS)
    assert lt.run("keep-pin").code == 0
    (lt.root / "work").rename(lt.root / "work-away")
    result = lt.run("book", "1.1.4")
    assert result.code == 1, result.out + result.err
    assert "Booking an issue lives in the private work folder (work/)" in result.out
    assert "Nothing was booked." in result.out
    assert not (lt.root / "work").exists() and "Traceback" not in result.err


def test_booking_moves_no_pin_no_vendored_file_and_installs_nothing(lt):
    before = lt.pin_hashes()
    _booked(lt)
    assert lt.pin_hashes() == before
    assert lt.libtv_calls() == ""


def test_booking_the_same_version_twice_writes_one_issue(lt):
    _booked(lt)
    count = len(_issues(lt))
    again = lt.run("book", "1.1.4")
    assert again.code == 0 and len(_issues(lt)) == count
    assert "already booked" in again.out


def test_a_version_never_read_is_read_first_and_then_booked(lt):
    lt.publish_candidate("1.1.4", commands=NEW_COMMANDS)
    result = lt.run("book", "1.1.4")
    assert result.code == 0
    assert lt.requests("GET").count("/cli/1.1.4/libtv-linux-x64.zip") == 2
    assert "Not built" in _issues(lt)[-1].read_text(encoding="utf-8"), "no kept copy of the pin: said in the issue"


def test_a_version_whose_bytes_changed_between_fetches_cannot_be_booked(lt):
    lt.publish_candidate("1.1.4")
    a, b = lt.make_zip(lt.BASE_DOCS), lt.make_zip({**lt.BASE_DOCS, "SKILL.md": "other\n"})
    lt.route("/cli/1.1.4/libtv-cli-skill.zip", sequence=[a, b])
    before = _issues(lt)
    result = lt.run("book", "1.1.4")
    assert result.code == 1 and "not offered" in result.out
    assert _issues(lt) == before


def test_a_version_that_is_not_published_cannot_be_booked(lt):
    before = _issues(lt)
    result = lt.run("book", "9.9.9")
    assert result.code == 1 and "not published" in result.out
    assert _issues(lt) == before


def test_check_stops_offering_a_booked_version_and_says_where_it_went(lt):
    _booked(lt)
    result = lt.run("check", "--json")
    assert "new-version" not in result.kinds()
    assert any("1.1.4" in line and "booked" in line for line in result.json()["info"])


def test_check_stops_offering_a_declined_version_but_not_a_later_one(lt):
    lt.publish_candidate("1.1.4")
    assert lt.run("decline", "1.1.4").code == 0
    assert "new-version" not in lt.run("check", "--json").kinds()
    lt.publish_candidate("1.1.5")
    assert lt.run("check", "--json").finding("new-version")["version"] == "1.1.5"


def test_a_version_number_that_is_not_one_is_refused(lt):
    for command in ("book", "decline", "candidate"):
        assert lt.run(command, "../../etc").code == 2
