"""Publish-log growth attribution: platform names, time zones, brands, missing metrics.

Seams (from issue 12's acceptance criteria): analyze.analyze_growth / analyze.main,
calendar_ops.record_publish (which writes publish-log through log.py), log.py stat.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CST = timezone(timedelta(hours=8))


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def analyze():
    return load("easel_analyze", "skills/builtin/skill-publish-analytics/scripts/analyze.py")


@pytest.fixture
def calendar_ops(monkeypatch):
    monkeypatch.delenv("EASEL_CALENDAR_AUTORECORD", raising=False)
    monkeypatch.delenv("EASEL_PROFILE", raising=False)
    monkeypatch.delenv("EASEL_ROOT", raising=False)
    return load("easel_calendar_ops", "skills/shared/scripts/calendar_ops.py")


def entry(platform, published_at, profile="", **metrics):
    return {
        "id": 1, "title": "t", "platform": platform, "type": "图文",
        "published_at": published_at, "profile": profile, "tags": [],
        "initial_metrics": {"views": None, "likes": None, "comments": None,
                            "shares": None, **metrics},
    }


def snap(platform, recorded_at, followers, profile=""):
    return {"platform": platform, "recorded_at": recorded_at,
            "followers": followers, "profile": profile}


def growth_row(analyze, entries, snapshots):
    rows = analyze.analyze_growth(entries, {"snapshots": snapshots})["ranking"]
    assert len(rows) == len(entries)
    return rows[0]


# --- Chinese platform name in the publish log, English code in the snapshots -----------

def test_growth_matches_chinese_platform_name_to_english_code(analyze):
    row = growth_row(
        analyze,
        [entry("小红书", "2026-07-02T20:00:00")],
        [snap("xiaohongshu", "2026-07-02", 1000), snap("xiaohongshu", "2026-07-03", 1200)],
    )
    assert row["delta_24h"] == 200


def test_growth_matches_english_code_in_log_to_chinese_name_in_snapshot(analyze):
    row = growth_row(
        analyze,
        [entry("douyin", "2026-07-02T20:00:00")],
        [snap("抖音", "2026-07-02", 50), snap("抖音", "2026-07-03", 80)],
    )
    assert row["delta_24h"] == 30


# --- time with a time zone vs time without one ----------------------------------------

def test_growth_publish_time_with_zone_against_snapshot_dates_without(analyze):
    # 17:00 UTC on 2 July is 01:00 on 3 July in China, so the 3 July snapshot (1200)
    # is the "before" figure and the 4 July snapshot (1500) the "within 24h" figure.
    row = growth_row(
        analyze,
        [entry("xiaohongshu", "2026-07-02T17:00:00+00:00")],
        [snap("xiaohongshu", "2026-07-02", 1000), snap("xiaohongshu", "2026-07-03", 1200),
         snap("xiaohongshu", "2026-07-04", 1500)],
    )
    assert row["delta_24h"] == 300


def test_growth_snapshot_time_with_zone_against_publish_time_without(analyze):
    row = growth_row(
        analyze,
        [entry("xiaohongshu", "2026-07-02T20:00:00")],
        [snap("xiaohongshu", "2026-07-02T00:00:00+08:00", 1000),
         snap("xiaohongshu", "2026-07-03T00:00:00+08:00", 1200)],
    )
    assert row["delta_24h"] == 200


# --- brand tag on automatically saved posts -------------------------------------------

def publish_log(tmp_path):
    return json.loads((tmp_path / "outputs/_analytics/publish-log.json")
                      .read_text(encoding="utf-8"))["entries"]


def test_record_publish_tags_the_brand_in_the_publish_log(calendar_ops, tmp_path, monkeypatch):
    monkeypatch.setenv("EASEL_ROOT", str(tmp_path))  # the log writer reads this
    assert calendar_ops.record_publish("xiaohongshu", "燕麦蛋白笔记", profile="Northwind",
                                       data_path=tmp_path / "_schedule.json")
    [logged] = publish_log(tmp_path)
    assert logged["profile"] == "Northwind"


def test_record_publish_takes_the_brand_from_the_environment(calendar_ops, tmp_path, monkeypatch):
    monkeypatch.setenv("EASEL_ROOT", str(tmp_path))
    monkeypatch.setenv("EASEL_PROFILE", "Orchard")
    assert calendar_ops.record_publish("xiaohongshu", "笔记",
                                       data_path=tmp_path / "_schedule.json")
    [logged] = publish_log(tmp_path)
    assert logged["profile"] == "Orchard"


def test_per_brand_growth_counts_only_that_brands_posts(calendar_ops, analyze, tmp_path,
                                                        monkeypatch, capsys):
    """Whole flow: two brands on Xiaohongshu publish through the real recorder."""
    monkeypatch.setenv("EASEL_ROOT", str(tmp_path))
    schedule = tmp_path / "_schedule.json"
    for brand, title in (("Northwind", "a"), ("Northwind", "b"), ("Orchard", "c")):
        assert calendar_ops.record_publish("xiaohongshu", title, profile=brand, data_path=schedule)

    today = datetime.now(CST).date()
    before, after = today - timedelta(days=1), today + timedelta(days=1)
    followers = {"Northwind": (100, 150), "Orchard": (500, 520)}
    snapshots = [
        {"profile": brand, "platform": "xiaohongshu", "recorded_at": str(day), "followers": n}
        for brand, (low, high) in followers.items()
        for day, n in ((before, low), (after, high))
    ]
    follower_log = tmp_path / "follower-log.json"
    follower_log.write_text(json.dumps({"snapshots": snapshots}), encoding="utf-8")
    data = tmp_path / "outputs/_analytics/publish-log.json"

    for brand, posts, delta in (("Northwind", 2, 50), ("Orchard", 1, 20)):
        analyze.main(["--data", str(data), "--follower-log", str(follower_log),
                      "--profile", brand, "growth"])
        out = json.loads(capsys.readouterr().out)
        assert out["summary"]["total"] == posts
        ranking = out["mode_D_growth"]["ranking"]
        assert [r["delta_24h"] for r in ranking] == [delta] * posts


# --- missing likes and views are left out of averages, not counted as zero ------------

def test_engagement_average_skips_posts_with_no_measured_metrics(analyze):
    entries = [entry("xiaohongshu", "2026-07-02T20:00:00", likes=100),
               entry("xiaohongshu", "2026-07-03T20:00:00")]
    [row] = analyze.analyze_types(entries)["by_type"]
    assert row["avg_engagement_score"] == 100.0
    assert analyze.analyze_types(entries)["winners"]["engagement_score"] == "图文"


def test_a_group_with_nothing_measured_has_no_engagement_average(analyze):
    entries = [entry("xiaohongshu", "2026-07-02T20:00:00")]
    [row] = analyze.analyze_types(entries)["by_type"]
    assert row["avg_engagement_score"] is None
    assert analyze.analyze_types(entries)["winners"]["engagement_score"] is None


def test_publish_log_stat_skips_posts_with_no_measured_metrics(tmp_path, capsys):
    log = load("easel_publish_log", "skills/builtin/skill-publish-log/scripts/log.py")
    path = tmp_path / "publish-log.json"
    path.write_text(json.dumps({"entries": [
        entry("小红书", "2026-07-02T20:00:00", likes=100),
        entry("小红书", "2026-07-03T20:00:00"),
    ]}), encoding="utf-8")
    log.cmd_stat(argparse.Namespace(data=str(path), by="platform", platform=None, profile=None,
                                    since=None, until=None, keyword=None, min_n=10))
    out = json.loads(capsys.readouterr().out)
    assert out["avg_engagement_score_by_group"] == {"小红书": 100.0}
