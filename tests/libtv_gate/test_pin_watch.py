"""Watching the pinned files themselves (issue 37): LibTV changing what sits at the pinned, versioned address, and
the kept copy of the pinned package that makes a rollback independent of LibTV.

Seams: `libtv_gate.py check [--deep]` and `libtv_gate.py keep-pin` against the stand-in LibTV.
"""

from __future__ import annotations

PROGRAM_PATH = "/cli/1.1.3/libtv-linux-x64.zip"


def _flip_last_byte(data: bytes) -> bytes:
    return data[:-1] + bytes([data[-1] ^ 1])


# ---- the published zip changing under the pin --------------------------------------------------------


def test_the_first_check_records_the_published_size_and_date_without_reporting_them(lt):
    result = lt.run("check", "--json")
    assert "pinned-files-changed" not in result.kinds()
    recorded = lt.state()["pinned_files"][PROGRAM_PATH]
    assert recorded["size"] == len(lt.pinned_program_zip)
    assert recorded["last_modified"]


def test_a_pinned_zip_whose_size_changed_is_reported(lt):
    lt.run("check")
    lt.publish("1.1.3", program_zip_bytes=lt.pinned_program_zip + b"extra")
    finding = lt.run("check", "--json").finding("pinned-files-changed")
    assert "libtv-linux-x64.zip" in finding["text"] and "size" in finding["text"]


def test_a_pinned_zip_with_a_new_last_modified_is_reported(lt):
    lt.run("check")
    lt.publish("1.1.3", program_zip_bytes=lt.pinned_program_zip, last_modified="Mon, 12 Oct 2026 01:02:03 GMT")
    finding = lt.run("check", "--json").finding("pinned-files-changed")
    assert "Last-Modified" in finding["text"] and "Mon, 12 Oct 2026 01:02:03 GMT" in finding["text"]


def test_a_pinned_zip_that_has_gone_is_reported(lt):
    lt.run("check")
    del lt.server.routes[PROGRAM_PATH]
    assert "404" in lt.run("check", "--json").finding("pinned-files-changed")["text"]


def test_an_unchanged_pinned_zip_is_quiet_on_every_later_check(lt):
    lt.run("check")
    assert "pinned-files-changed" not in lt.run("check", "--json").kinds()


def test_a_plain_check_downloads_no_zip_but_a_deep_check_rehashes_the_pinned_one(lt):
    altered = _flip_last_byte(lt.pinned_program_zip)   # same size and date: only the bytes tell
    lt.run("check")
    lt.publish("1.1.3", program_zip_bytes=altered)
    plain = lt.run("check", "--json")
    assert "pinned-files-changed" not in plain.kinds()
    assert [p for p in lt.requests("GET") if p.endswith(".zip")] == []
    deep = lt.run("check", "--deep", "--json")
    finding = deep.finding("pinned-files-changed")
    assert "sha256" in finding["text"] and lt.sha256(altered) in finding["text"]


def test_a_deep_check_of_unchanged_bytes_says_they_match_the_pin(lt):
    deep = lt.run("check", "--deep", "--json")
    assert "pinned-files-changed" not in deep.kinds()
    assert any("matches the pin" in line for line in deep.json()["info"])


# ---- the kept copy of the pinned package, for rollback -----------------------------------------------


def test_keep_pin_keeps_a_checked_copy_and_names_the_rollback_command(lt):
    result = lt.run("keep-pin")
    kept = lt.store / "pinned" / "1.1.3" / "libtv-linux-x64.zip"
    assert result.code == 0, result.out + result.err
    assert kept.read_bytes() == lt.pinned_program_zip
    assert "LIBTV_ZIP_FILE=" in result.out and "setup.sh --only libtv" in result.out


def test_keep_pin_refuses_a_download_that_does_not_match_the_pinned_checksum(lt):
    lt.publish("1.1.3", program_zip_bytes=lt.pinned_program_zip + b"tampered")
    result = lt.run("keep-pin")
    assert result.code == 1
    assert "sha256" in (result.out + result.err).lower()
    pinned_dir = lt.store / "pinned"
    assert not pinned_dir.exists() or not [p for p in pinned_dir.rglob("*") if p.is_file()], "nothing is kept"


def test_keep_pin_does_not_download_again_when_the_kept_copy_still_matches(lt):
    lt.run("keep-pin")
    first = [p for p in lt.requests("GET") if p == PROGRAM_PATH]
    result = lt.run("keep-pin")
    assert result.code == 0 and "already kept" in result.out
    assert [p for p in lt.requests("GET") if p == PROGRAM_PATH] == first


def test_keep_pin_replaces_a_kept_copy_that_no_longer_matches(lt):
    lt.run("keep-pin")
    kept = lt.store / "pinned" / "1.1.3" / "libtv-linux-x64.zip"
    kept.write_bytes(b"damaged")
    assert lt.run("keep-pin").code == 0
    assert kept.read_bytes() == lt.pinned_program_zip


def test_keep_pin_sets_the_baseline_the_later_checks_compare_with(lt):
    lt.run("keep-pin")
    recorded = lt.state()["pinned_files"][PROGRAM_PATH]
    assert recorded["size"] == len(lt.pinned_program_zip)
