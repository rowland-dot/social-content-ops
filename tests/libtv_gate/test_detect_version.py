"""Version detection of the LibTV update gate (issue 37), through its command line against a stand-in LibTV.

Seams (the issue's Agent Brief): `libtv_gate.py check` and its `--json` form. LibTV's answers come from the
stand-in server in conftest.py; the gate reads its pin from the fixture repo's setup.sh and checks.sh.
"""

from __future__ import annotations


def _zip_gets(lt) -> list[str]:
    return [p for p in lt.requests("GET") if p.startswith("/cli/") and p.endswith(".zip")]


def test_channel_at_the_pin_reports_no_update(lt):
    result = lt.run("check", "--json")
    data = result.json()
    assert result.code == 0
    assert data["pinned"] == "1.1.3" and data["channel"] == "1.1.3"
    assert "new-version" not in result.kinds()
    assert "no update" in lt.run("check").out.lower()


def test_newer_channel_version_is_reported_and_nothing_is_downloaded(lt):
    lt.set_channel("1.1.4")
    lt.publish("1.1.4", program_zip_bytes=lt.program_zip("1.1.4"), skill_docs=lt.BASE_DOCS)
    result = lt.run("check", "--json")
    assert result.finding("new-version")["version"] == "1.1.4"
    assert _zip_gets(lt) == [], "a check downloads no package"


def test_the_version_channel_wins_over_the_old_manifest(lt):
    # cli/latest/manifest.json is the pointer only the old installer reads; here it even names a newer version
    lt.server.routes["/cli/latest/manifest.json"].body = b'{"version": "1.9.9"}'
    result = lt.run("check", "--json")
    assert "new-version" not in result.kinds()
    assert any("1.9.9" in line for line in result.json()["info"]), "reported as information only"


def test_a_channel_older_than_the_pin_is_reported_not_called_an_update(lt):
    lt.set_channel("1.1.2")
    result = lt.run("check", "--json")
    assert "channel-behind-pin" in result.kinds()
    assert "new-version" not in result.kinds()


def test_a_newer_version_is_offered_with_the_answers_that_decide_it(lt):
    lt.set_channel("1.1.4")
    lt.publish("1.1.4", program_zip_bytes=lt.program_zip("1.1.4"), skill_docs=lt.BASE_DOCS)
    finding = lt.run("check", "--json").finding("new-version")
    assert finding["action"] == "book-or-decline"
