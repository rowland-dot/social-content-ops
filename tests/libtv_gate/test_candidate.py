"""The candidate report (issue 37): what a newer LibTV version would change, built by reading its files.

Nothing is run and nothing is installed: both packages are downloaded twice into the gate's own store, the
program is read as a file (its embedded source gives the command tree and the version), and the documents are
compared with the vendored copy. Seams: `libtv_gate.py candidate <version>` against the stand-in LibTV.
"""

from __future__ import annotations

UPDATED = {
    "node": {"": [], "create": ["--run", "--type"], "list": []},
    "login": {"": [], "web": []},
    "image": {"": [], "shortcut": []},
}


def _ready(lt):
    """the kept copy of the pinned package exists, which is what the command comparison starts from"""
    assert lt.run("keep-pin").code == 0


def _line_with(text: str, needle: str) -> str:
    lines = [ln for ln in text.splitlines() if needle in ln]
    assert lines, f"no line says {needle}:\n{text}"
    return lines[0]


# ---- what the files are -------------------------------------------------------------------------------


def test_the_report_gives_size_checksum_and_date_of_both_packages_and_the_program_inside(lt):
    _ready(lt)
    lt.publish_candidate("1.1.4", last_modified="Tue, 13 Oct 2026 03:04:05 GMT")
    skill = lt.server.routes["/cli/1.1.4/libtv-cli-skill.zip"].body
    program = lt.server.routes["/cli/1.1.4/libtv-linux-x64.zip"].body
    result = lt.run("candidate", "1.1.4")
    assert result.code == 0, result.out + result.err
    for expected in (
        str(len(skill)), lt.sha256(skill), str(len(program)), lt.sha256(program),
        "Tue, 13 Oct 2026 03:04:05 GMT", lt.sha256(lt.program_inside(program)), str(len(lt.program_inside(program))),
    ):
        assert expected in result.out, f"the report does not say {expected}"


def test_the_report_names_the_version_found_inside_the_program_and_flags_a_mismatch(lt):
    _ready(lt)
    lt.publish_candidate("1.1.4")
    assert "Version strings found in the program: 1.1.4" in lt.run("candidate", "1.1.4").out
    lt.publish_candidate("1.1.5", program_version="1.1.4")
    out = lt.run("candidate", "1.1.5").out
    assert "Version strings found in the program: 1.1.4" in out
    assert "does not match the published version 1.1.5" in out


# ---- commands, by full path ---------------------------------------------------------------------------


def test_commands_are_compared_by_full_path_so_two_updates_are_two_commands(lt):
    _ready(lt)
    commands = {**UPDATED, "node": {**UPDATED["node"], "update": []}, "project": {"": [], "update": []},
                "workspace": {"": [], "update": [], "create": []}}
    lt.publish_candidate("1.1.4", commands=commands)
    out = lt.run("candidate", "1.1.4").out
    for path in ("workspace", "workspace update", "workspace create", "project update", "node update"):
        assert f"`{path}`" in _line_with(out, f"`{path}`") and "Added command" in _line_with(out, f"`{path}`"), path
    assert "`serve`" not in out, "a command of a bundled library is not LibTV's"


def test_a_removed_command_and_a_changed_option_are_reported(lt):
    _ready(lt)
    lt.publish_candidate("1.1.4", commands={
        "node": {"": [], "create": ["--run", "--type", "--count"], "list": []},
        "login": {"": []},
        "image": {"": [], "shortcut": []},
    })
    out = lt.run("candidate", "1.1.4").out
    assert "Removed command" in _line_with(out, "`login web`")
    assert "Added option" in _line_with(out, "`node create --count`")


def test_without_a_kept_copy_of_the_pin_the_command_comparison_says_it_was_not_built(lt):
    lt.publish_candidate("1.1.4")
    out = lt.run("candidate", "1.1.4").out
    assert "not built" in out and "keep-pin" in out
    assert "Version strings found in the program: 1.1.4" in out, "the rest of the report is still built"


# ---- paid runs ----------------------------------------------------------------------------------------


def test_the_paid_run_section_says_whether_each_generating_command_is_on_claude_mds_list(lt):
    _ready(lt)
    commands = {**UPDATED, "script": {"": [], "storyboard": []}, "video": {"": [], "render": []}}
    commands["node"] = {"": [], "create": ["--run", "--type", "--count"], "list": []}
    lt.publish_candidate("1.1.4", commands=commands)
    out = lt.run("candidate", "1.1.4").out
    assert "Paid-run section" in out
    paid = out.split("Paid-run section", 1)[1]
    assert "On CLAUDE.md's list" in _line_with(paid, "`script storyboard`")
    assert "On CLAUDE.md's list" in _line_with(paid, "`node create --count`")
    assert "NOT on CLAUDE.md's list" in _line_with(paid, "`video render`")


def test_the_paid_run_section_says_plainly_when_the_work_folder_with_the_list_is_missing(lt):
    _ready(lt)
    commands = {**UPDATED, "video": {"": [], "render": []}}
    lt.publish_candidate("1.1.4", commands=commands)
    (lt.root / "work").rename(lt.root / "work-away")
    result = lt.run("candidate", "1.1.4")
    paid = result.out.split("Paid-run section", 1)[1]
    assert "The list of paid LibTV commands lives in the private work folder (work/)" in _line_with(paid, "`video render`")
    assert "Traceback" not in result.err


def test_the_paid_run_section_says_none_when_nothing_can_start_a_generation(lt):
    _ready(lt)
    lt.publish_candidate("1.1.4", commands={**UPDATED, "workspace": {"": [], "create": [], "list": []}})
    out = lt.run("candidate", "1.1.4").out
    assert "Paid-run section: none" in out


def test_generating_words_in_added_document_lines_are_listed_too(lt):
    _ready(lt)
    docs = {**lt.BASE_DOCS, "commands/node.md": "# node\n\n`libtv node <n>`\n\nnew: `libtv node batch --run` starts runs\n"}
    lt.publish_candidate("1.1.4", docs=docs)
    out = lt.run("candidate", "1.1.4").out
    assert "libtv node batch --run" in out.split("Paid-run section", 1)[1]


# ---- documents ----------------------------------------------------------------------------------------


def test_documents_are_reported_as_added_removed_and_changed_with_a_readable_diff(lt):
    lt.write_vendor({"SKILL.md": "# libtv\n\nold line\n", "commands/node.md": "# node\n", "commands/gone.md": "# gone\n"})
    _ready(lt)
    lt.publish_candidate("1.1.4", docs={"SKILL.md": "# libtv\n\nnew line\n", "commands/node.md": "# node\n",
                                        "commands/workspace.md": "# workspace\n"})
    out = lt.run("candidate", "1.1.4").out
    assert "Added: commands/workspace.md" in out
    assert "Removed: commands/gone.md" in out
    assert "Changed: SKILL.md" in out and "commands/node.md" not in _line_with(out, "Changed:")
    assert "-old line" in out and "+new line" in out


def test_identical_documents_are_reported_as_no_document_changes(lt):
    _ready(lt)
    lt.publish_candidate("1.1.4")
    assert "No document changes" in lt.run("candidate", "1.1.4").out


def test_new_self_update_or_install_instructions_in_the_documents_are_listed(lt):
    _ready(lt)
    docs = {**lt.BASE_DOCS, "scripts/install.md": "To update: rm -rf the skill folder, unzip the new one, run install-libtv-cli.sh\n"}
    lt.publish_candidate("1.1.4", docs=docs)
    out = lt.run("candidate", "1.1.4").out
    assert "install-libtv-cli.sh" in out.split("Self-update", 1)[1]
    lt.publish_candidate("1.1.5")
    assert "Self-update or install instructions in added document lines: none" in lt.run("candidate", "1.1.5").out


def test_the_version_channel_the_candidates_installer_names_is_flagged_when_it_is_not_240(lt):
    _ready(lt)
    install = "curl 'https://api2.liblib.art/api/www/landing-activities/getById?id=%s'\n"
    lt.publish_candidate("1.1.4", docs={**lt.BASE_DOCS, "scripts/install-libtv-cli.sh": install % "245"})
    out = lt.run("candidate", "1.1.4").out
    assert "245" in _line_with(out, "installer names") and "NOT 240" in _line_with(out, "installer names")
    lt.publish_candidate("1.1.5", docs={**lt.BASE_DOCS, "scripts/install-libtv-cli.sh": install % "240"})
    line = _line_with(lt.run("candidate", "1.1.5").out, "installer names")
    assert "240" in line and "NOT" not in line


# ---- downloads: twice, kept outside git, nothing installed --------------------------------------------


def test_each_package_is_fetched_twice_and_kept_in_the_store(lt):
    _ready(lt)
    lt.publish_candidate("1.1.4")
    lt.run("candidate", "1.1.4")
    for name in ("libtv-cli-skill.zip", "libtv-linux-x64.zip"):
        assert lt.requests("GET").count(f"/cli/1.1.4/{name}") == 2
        assert (lt.store / "candidates" / "1.1.4" / name).is_file()


def test_the_report_is_built_once_per_version_and_saved(lt):
    _ready(lt)
    lt.publish_candidate("1.1.4")
    first = lt.run("candidate", "1.1.4")
    gets = len(lt.requests("GET"))
    second = lt.run("candidate", "1.1.4")
    assert len(lt.requests("GET")) == gets, "a built report is not downloaded again"
    assert second.out == first.out
    assert (lt.store / "candidates" / "1.1.4" / "report.md").read_text(encoding="utf-8").strip() == first.out.strip()


def test_bytes_that_differ_between_two_fetches_are_reported_and_the_version_is_not_offered(lt):
    _ready(lt)
    lt.publish_candidate("1.1.4")
    a, b = lt.make_zip(lt.BASE_DOCS), lt.make_zip({**lt.BASE_DOCS, "SKILL.md": "changed between fetches\n"})
    lt.route("/cli/1.1.4/libtv-cli-skill.zip", sequence=[a, b])
    result = lt.run("candidate", "1.1.4")
    assert result.code == 1
    assert "differ between two fetches" in result.out and lt.sha256(a) in result.out and lt.sha256(b) in result.out
    assert "not offered" in result.out
    assert "1.1.4" in lt.state()["unstable"]
    assert not (lt.store / "candidates" / "1.1.4" / "report.md").exists()


def test_a_version_that_is_not_published_is_said_so(lt):
    result = lt.run("candidate", "9.9.9")
    assert result.code == 1 and "not published" in result.out


def test_building_a_report_installs_and_changes_nothing_in_the_repo(lt):
    _ready(lt)
    before = lt.pin_hashes()
    lt.publish_candidate("1.1.4", commands={**UPDATED, "workspace": {"": [], "create": []}})
    lt.run("candidate", "1.1.4")
    assert lt.pin_hashes() == before
