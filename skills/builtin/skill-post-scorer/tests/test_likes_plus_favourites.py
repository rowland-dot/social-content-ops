"""skill-post-scorer ranks the brand's own past posts by likes plus favourites (issue 83).

Seam: the `top` command line of scripts/score.py in this skill, run on a history file; the JSON it
prints is what the model reads.

Rules under test (The owner, 2026-10-28: "you should judget by combining like + fav as the total
impression score of a post"; issue 83 brief):
- the engagement score is likes + favourites, so comments no longer lift a post;
- the favourites field is accepted as favourites, favorites, collects, collected_count or 收藏;
- a post missing the favourites field counts them as 0;
- the reported formula says likes + favourites;
- the top-post rows show favourites.

Expected scores are literals worked out by hand from the posts below, never recomputed with the
scorer's own arithmetic.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "score.py"


def run_top(tmp_path: Path, posts: list, top_pct: float = 100) -> dict:
    history = tmp_path / "history.json"
    history.write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "top", "--input", str(history), "--top-pct", str(top_pct)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_many_favourites_outrank_more_comments(tmp_path):
    # Chatty: 100 likes + 200 comments, 50 favourites -> 150. Saved: 100 likes, 10 comments,
    # 400 favourites -> 500. Under likes + comments x 3 the chatty post would win (700 against 130).
    out = run_top(tmp_path, [
        {"title": "Chatty", "likes": 100, "comments": 200, "favourites": 50},
        {"title": "Saved", "likes": 100, "comments": 10, "favourites": 400},
    ], top_pct=50)
    assert [p["title"] for p in out["top_posts"]] == ["Saved"]
    assert out["top_posts"][0]["engagement_score"] == 500
    assert out["summary"]["top_threshold_score"] == 500


def test_missing_favourites_counts_as_zero(tmp_path):
    # 40 likes, 20 comments, no favourites field at all -> 40, not 100.
    out = run_top(tmp_path, [{"title": "No favourites field", "likes": 40, "comments": 20}])
    assert out["top_posts"][0]["engagement_score"] == 40
    assert out["top_posts"][0]["favourites"] in (None, 0)


@pytest.mark.parametrize("alias", ["favourites", "favorites", "collects", "collected_count", "收藏"])
def test_favourites_field_aliases_are_accepted(tmp_path, alias):
    out = run_top(tmp_path, [
        {"title": "Plain", "likes": 10},
        {"title": "Aliased", "likes": 5, alias: 20},
    ])
    assert [p["title"] for p in out["top_posts"]] == ["Aliased", "Plain"]
    assert out["top_posts"][0]["engagement_score"] == 25
    assert out["top_posts"][0]["favourites"] == 20


def test_reported_formula_says_likes_plus_favourites(tmp_path):
    out = run_top(tmp_path, [{"title": "Only", "likes": 1, "favourites": 1}])
    formula = out["summary"]["engagement_formula"]
    assert "likes + favourites" in formula
    assert "评论" not in formula
