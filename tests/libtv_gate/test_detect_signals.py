"""The other things the LibTV update gate watches for (issue 37): versions the channel does not name, LibTV's
broadcast notice, the canary route that would show a retirement, and the case where LibTV cannot be reached.

Seams: `libtv_gate.py check --json` against the stand-in LibTV in conftest.py. The retirement payload is the real
answer LibTV's old skill gave when it was shut down (issue 32's evidence), not an invented error.
"""

from __future__ import annotations

import json

CANARY = "/api/www/account/list"


# ---- folders above the pin that the channel does not name --------------------------------------------


def test_a_version_above_the_pin_that_the_channel_does_not_name_is_reported(lt):
    lt.publish("1.2.0", skill_docs=lt.BASE_DOCS)   # the folder exists; the channel still says 1.1.3
    finding = lt.run("check", "--json").finding("unlisted-version")
    assert finding["version"] == "1.2.0"


def test_the_next_patch_minor_and_major_above_the_pin_are_each_looked_for(lt):
    lt.run("check", "--json")
    probed = " ".join(lt.requests())
    for version in ("1.1.4", "1.2.0", "2.0.0"):
        assert f"/cli/{version}/" in probed, f"{version} was not looked for"


def test_no_folder_above_the_pin_means_nothing_unlisted(lt):
    assert "unlisted-version" not in lt.run("check", "--json").kinds()


# ---- LibTV's broadcast notice ------------------------------------------------------------------------


def test_an_enabled_notice_is_reported_word_for_word(lt):
    lt.set_notice(True, "旧版本将于下周停止服务，请升级到 1.2.0")
    finding = lt.run("check", "--json").finding("notice")
    assert "旧版本将于下周停止服务，请升级到 1.2.0" in finding["text"]


def test_a_message_in_a_disabled_notice_is_still_reported(lt):
    lt.set_notice(False, "scheduled maintenance")
    assert "scheduled maintenance" in lt.run("check", "--json").finding("notice")["text"]


def test_a_notice_that_is_off_and_empty_is_quiet(lt):
    result = lt.run("check", "--json")
    assert "notice" not in result.kinds()
    assert any("notice" in line.lower() and "off" in line.lower() for line in result.json()["info"])


# ---- the canary route: the shape of LibTV's one known retirement -------------------------------------


def test_the_real_retirement_answer_is_an_upgrade_demand_shown_word_for_word(lt):
    lt.set_canary(lt.RETIREMENT_ANSWER)
    finding = lt.run("check", "--json").finding("upgrade-demand")
    assert lt.RETIREMENT_ANSWER["message"] in finding["text"]


def test_the_not_logged_in_baseline_is_quiet_and_named(lt):
    result = lt.run("check", "--json")
    assert not {"upgrade-demand", "canary-other"} & set(result.kinds())
    assert any("baseline" in line.lower() for line in result.json()["info"])


def test_any_other_canary_answer_is_reported_word_for_word(lt):
    body = json.dumps({"code": 500, "msg": "boom"})
    lt.set_canary(body.encode("utf-8"))
    assert body in lt.run("check", "--json").finding("canary-other")["text"]
    lt.set_canary(b"<html>bad gateway</html>", status=502)
    assert "<html>bad gateway</html>" in lt.run("check", "--json").finding("canary-other")["text"]


def test_the_canary_is_asked_as_the_program_asks_and_with_no_credential(lt):
    lt.run("check", "--json")
    sent = [h for path, h in lt.server.header_log if path == CANARY]
    assert sent, "the canary was never called"
    assert sent[0].get("x-from-client") == "cli"
    assert not {"authorization", "cookie", "usertoken"} & set(sent[0])


def test_a_canary_that_gives_no_answer_is_could_not_check(lt):
    lt.route(CANARY, drop=True)
    result = lt.run("check", "--json")
    assert "canary" in result.detectors("could-not-check"), result.out


# ---- LibTV cannot be reached -------------------------------------------------------------------------


def test_an_unreachable_service_is_never_reported_as_no_update(lt):
    result = lt.run("check", "--json", api_base=lt.closed_base())
    data = result.json()
    assert result.code == 0
    assert data["channel"] is None
    detectors = {f["detector"] for f in data["findings"] if f["kind"] == "could-not-check"}
    assert {"version", "canary", "notice"} <= detectors
    assert "no update" not in lt.run("check", api_base=lt.closed_base()).out.lower()


def test_a_service_that_hangs_ends_as_could_not_check_within_the_deadline(lt):
    lt.route("/api/www/landing-activities/getById?id=240", b"{}", delay=30)
    result = lt.run("check", "--json", env={"LIBTV_GATE_TIMEOUT": "60", "LIBTV_GATE_DEADLINE": "2"}, timeout=25)
    assert result.seconds < 15, result.out
    assert "version" in result.detectors("could-not-check"), result.out
    assert result.json()["channel"] is None, result.out


def test_a_hanging_version_channel_and_a_notice_channel_that_drops_are_both_could_not_check(lt):
    lt.route("/api/www/landing-activities/getById?id=240", b"{}", delay=30)
    lt.route("/api/www/landing-activities/getById?id=217", drop=True)
    result = lt.run("check", "--json", env={"LIBTV_GATE_TIMEOUT": "60", "LIBTV_GATE_DEADLINE": "2"}, timeout=25)
    assert {"version", "notice"} <= result.detectors("could-not-check"), result.out
