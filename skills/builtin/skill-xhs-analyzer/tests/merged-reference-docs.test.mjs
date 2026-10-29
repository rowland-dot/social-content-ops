// The analyzer's two reference documents carry both the reader-guard wording (issue 69) and the
// likes-plus-favourites ranking note (issue 83) after the two changes are merged, with no
// leftover merge markers.
//
// Run:  node --test tests/merged-reference-docs.test.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (name) =>
  readFileSync(new URL(`../references/${name}`, import.meta.url), "utf8");

for (const name of ["commands.md", "modules.md"]) {
  test(`${name} has no merge markers`, () => {
    const text = read(name);
    assert.ok(!/^(<<<<<<<|=======$|>>>>>>>)/m.test(text), "merge markers left in " + name);
  });
}

test("commands.md keeps the guard wording and the ranking rename note for account-report", () => {
  const text = read("commands.md");
  assert.ok(text.includes("守卫拒绝 `--file`、多个账号、`--max-pages` 大于 1 和 `--all`"));
  assert.ok(text.includes("`topByLikesPlusFavourites` = 点赞 + 收藏最高的笔记"));
});

test("modules.md keeps the one-account guard wording and the ranking rename note", () => {
  const text = read("modules.md");
  assert.ok(text.includes("一次一个账号；`--file`、多个账号被守卫拒绝"));
  assert.ok(text.includes("守卫拒绝 `--all` 和 `--max-pages` 大于 1"));
  assert.ok(text.includes("`topByLikesPlusFavourites` 按点赞 + 收藏排名"));
});
