"""The settings LibTV's program downloads at run time (issue 37, the owner's ruling 4: report only).

A pinned program keeps its commands fixed but not what they reach: the model list and the shortcut scenes change
on LibTV's side with no program update. The gate diffs them against the last snapshot the owner acknowledged; the first
run records a baseline, and the snapshot moves only on `ack-settings`.

Seams: `libtv_gate.py check --json` and `libtv_gate.py ack-settings` against the stand-in LibTV.
"""

from __future__ import annotations

MODELS = "182"
SCENES = "188"


def _models(*models: dict) -> dict:
    return {"video": list(models)}


def _baseline(lt):
    lt.set_settings(MODELS, _models({"modelKey": "m-one", "modelName": "One", "vip": False, "pricingRule": "per second"}))
    lt.run("check", "--json")


# ---- the first run is a baseline, not a change -------------------------------------------------------


def test_the_first_check_records_a_baseline_and_reports_no_change(lt):
    result = lt.run("check", "--json")
    assert "settings-changed" not in result.kinds()
    assert any("baseline" in line.lower() and "settings" in line.lower() for line in result.json()["info"])
    assert set(lt.state()["settings"]) >= {MODELS, SCENES}


def test_unchanged_settings_are_quiet_afterwards(lt):
    _baseline(lt)
    assert "settings-changed" not in lt.run("check", "--json").kinds()


# ---- changes are named by model key ------------------------------------------------------------------


def test_an_added_model_and_a_flipped_vip_flag_are_reported_by_key(lt):
    _baseline(lt)
    lt.set_settings(
        MODELS,
        _models(
            {"modelKey": "m-one", "modelName": "One", "vip": True, "pricingRule": "per second"},
            {"modelKey": "m-two", "modelName": "Two"},
        ),
    )
    finding = lt.run("check", "--json").finding("settings-changed")
    assert finding["action"] == "acknowledge"
    assert "m-two" in finding["text"] and "added" in finding["text"]
    assert "m-one" in finding["text"] and "vip" in finding["text"]


def test_a_changed_pricing_rule_and_a_removed_model_are_reported_by_key(lt):
    _baseline(lt)
    lt.set_settings(MODELS, _models({"modelKey": "m-three", "modelName": "Three"}))
    text = lt.run("check", "--json").finding("settings-changed")["text"]
    assert "m-one" in text and "removed" in text
    lt.set_settings(MODELS, _models({"modelKey": "m-one", "modelName": "One", "vip": False, "pricingRule": "per clip"}))
    text = lt.run("check", "--json").finding("settings-changed")["text"]
    assert "m-one" in text and "pricingRule" in text


def test_the_other_channels_are_summarised(lt):
    lt.run("check")
    lt.set_settings(SCENES, {"slashImage": [{"scene": "s-one", "label": "One"}, {"scene": "s-two", "label": "Two"}]})
    text = lt.run("check", "--json").finding("settings-changed")["text"]
    assert "shortcut scenes" in text and "1 added" in text


# ---- acknowledging ------------------------------------------------------------------------------------


def test_the_voices_channel_is_a_json_list_and_a_new_voice_is_reported_by_its_id(lt):
    # LibTV serves channel 190 as a list of voices, not an object (found by the first live run)
    result = lt.run("check", "--json")
    assert "could-not-check" not in result.kinds()
    lt.set_settings("190", [{"voice_id": "v-one", "name": "One"}, {"voice_id": "v-two", "name": "Two"}])
    text = lt.run("check", "--json").finding("settings-changed")["text"]
    assert "voices" in text and "v-two" in text and "1 added" in text


def test_a_change_is_reported_at_every_check_until_it_is_acknowledged(lt):
    _baseline(lt)
    before = lt.state()["settings"][MODELS]
    lt.set_settings(MODELS, _models({"modelKey": "m-two", "modelName": "Two"}))
    for _ in range(3):
        assert "settings-changed" in lt.run("check", "--json").kinds()
    assert lt.state()["settings"][MODELS] == before, "the acknowledged snapshot has not moved"


def test_acknowledging_moves_the_snapshot_and_the_report_stops(lt):
    _baseline(lt)
    lt.set_settings(MODELS, _models({"modelKey": "m-two", "modelName": "Two"}))
    assert "settings-changed" in lt.run("check", "--json").kinds()
    ack = lt.run("ack-settings")
    assert ack.code == 0
    assert "settings-changed" not in lt.run("check", "--json").kinds()
    assert lt.state()["settings"][MODELS]["video"][0]["modelKey"] == "m-two"


def test_acknowledging_covers_what_was_reported_not_what_changed_since(lt):
    _baseline(lt)
    lt.set_settings(MODELS, _models({"modelKey": "m-two", "modelName": "Two"}))
    lt.run("check", "--json")
    lt.set_settings(MODELS, _models({"modelKey": "m-four", "modelName": "Four"}))   # changed again, never shown
    lt.run("ack-settings")
    text = lt.run("check", "--json").finding("settings-changed")["text"]
    assert "m-four" in text, "a later change is shown, not swallowed by the earlier acknowledgement"


def test_acknowledging_with_nothing_reported_changes_nothing(lt):
    _baseline(lt)
    before = lt.state()
    ack = lt.run("ack-settings")
    assert ack.code == 0 and "nothing" in ack.out.lower()
    assert lt.state() == before


def test_a_channel_that_cannot_be_read_is_could_not_check_not_a_change(lt):
    _baseline(lt)
    lt.route("/api/www/landing-activities/getById?id=190", b"not json at all")
    result = lt.run("check", "--json")
    assert "settings" in result.detectors("could-not-check"), result.out
    assert "settings-changed" not in result.kinds()
