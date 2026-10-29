#!/usr/bin/env bash
# Lists every file under profiles/ that git is ignoring, one path per line.
# Easel ignores every client profile folder, so a file added with force stays tracked but a NEW file Easel
# writes there (an asset, a whole new client) is silently left out of git. This reports those files.
#
#   bash ops/profile-check/profile-ignored-check.sh [REPO]     (REPO defaults to the current folder)
#
# The list is git's own report of ignored, untracked files, so tracked files and the template never appear and
# Easel's ignore rules are not re-implemented here. Exit status: 0 nothing ignored, 1 at least one file listed,
# 2 the check could not look (not a git repository), so it proves nothing.
set -u
repo=${1:-.}
top=$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null) || { echo "not a git repository: $repo" >&2; exit 2; }
# -z keeps non-ASCII names (素材清单.md) as themselves instead of git's quoted octal form.
list=$(git -C "$top" ls-files -z --others --ignored --exclude-standard -- profiles | tr '\0' '\n') || exit 2
[ -z "$list" ] && exit 0
printf '%s\n' "$list"
exit 1
