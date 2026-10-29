// Xiaohongshu analyzer ranks posts by likes plus favourites (issue 83).
//
// Run after `npm run build`:  node --test tests/
//
// Seams: topReportNote (the top-post pick behind the account report), computeViralScore (the
// single-note score's engagement band) and analyzeViral / formatViralAnalysis (what the
// author-baseline block says it compares). All three are read from the built dist/ files.
//
// Rule under test (The owner, 2026-10-28: "you should judget by combining like + fav as the total
// impression score of a post"). The band thresholds keep their current numbers, 500 / 1000 /
// 5000 / 10000 likes, now applied to likes + favourites. Expected values are literals, never
// recomputed with the code's own arithmetic.

import assert from "node:assert/strict";
import test from "node:test";

import {
  analyzeComments,
  analyzeContent,
  analyzeHook,
  analyzeViral,
  computeEngagement,
  computeRelativePerformance,
  computeViralScore,
  formatViralAnalysis,
} from "../dist/lib/analyze.js";
import { topReportNote } from "../dist/lib/top-notes.js";

function note(title, likes, collects, comments = 0, shares = 0) {
  return { title, likes, comments, collects, shares, totalEngagement: likes + comments + collects + shares };
}

test("top post is the one with the most likes plus favourites, not the most likes", () => {
  const notes = [
    note("Most likes", 100, 0),
    note("Most likes plus favourites", 60, 80),
  ];
  assert.equal(topReportNote(notes).title, "Most likes plus favourites");
});

test("the separate total-engagement ranking is kept", () => {
  const notes = [
    note("Likes plus favourites leader", 100, 100),
    note("Comment-heavy", 10, 10, 500),
  ];
  assert.equal(topReportNote(notes, "totalEngagement").title, "Comment-heavy");
});

function bandFor(liked, collected) {
  const engagement = computeEngagement({
    liked_count: liked,
    collected_count: collected,
    comment_count: 0,
    share_count: 0,
  });
  const score = computeViralScore(
    analyzeHook("x"),
    engagement,
    computeRelativePerformance(0, [], 0),
    analyzeContent(""),
    analyzeComments([]),
  );
  return score.breakdown.engagement;
}

test("viral score engagement band reads likes plus favourites against 500 / 1000 / 5000 / 10000", () => {
  assert.equal(bandFor(400, 99), 4); // 499 stays in the lowest band
  assert.equal(bandFor(400, 100), 8); // 500 reaches the first band
  assert.equal(bandFor(600, 400), 12); // 1000
  assert.equal(bandFor(3000, 2000), 16); // 5000
  assert.equal(bandFor(6000, 4000), 20); // 10000
  assert.equal(bandFor(300, 0), 4); // likes alone below 500 is unchanged
});

test("author-baseline block says it compares likes only", () => {
  const thisNote = {
    title: "Probe",
    desc: "body",
    type: "normal",
    user: { nickname: "someone", user_id: "u1" },
    interact_info: { liked_count: 200, collected_count: 900, comment_count: 0, share_count: 0 },
  };
  const authorPosts = [
    { interact_info: { liked_count: 50 } },
    { interact_info: { liked_count: 80 } },
  ];
  const result = analyzeViral("n1", thisNote, [], authorPosts, 1000);
  assert.equal(result.relative.measure, "likes");
  assert.ok(formatViralAnalysis(result).includes("likes only"));
});
