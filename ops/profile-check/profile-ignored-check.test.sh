#!/usr/bin/env bash
# Tests for ops/profile-check/profile-ignored-check.sh. Run in Linux, WSL or Git Bash:
#   bash ops/profile-check/profile-ignored-check.test.sh
# Each test builds a throwaway git repository whose ignore rules for profiles are copied from this project's own
# .gitignore, so the test breaks if Easel's rules and the check ever stop agreeing. Nothing real is read or changed.
# Exit status = number of failures.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
CHECK=$HERE/profile-ignored-check.sh
T=$(mktemp -d "${TMPDIR:-/tmp}/profcheck-test-40.XXXXXX")
trap 'rm -rf "$T"' EXIT
FAILS=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }
expect() { local n=$1; shift; if "$@"; then ok "$n"; else bad "$n"; fi; }

# The project's own rules for profile folders (three lines today). An empty copy would make every test vacuous.
grep -E '^!?profiles/' "$ROOT/.gitignore" > "$T/rules.txt"
expect "the project's .gitignore still has its three profile rules to copy" test "$(wc -l < "$T/rules.txt" | tr -d ' ')" = 3

R=$T/repo
mkdir -p "$R/profiles/_template" "$R/profiles/acme/assets"
git -C "$R" init -q
git -C "$R" config user.email t@example.invalid
git -C "$R" config user.name test
git -C "$R" config core.autocrlf false
cp "$T/rules.txt" "$R/.gitignore"
printf 'template rule\n' > "$R/profiles/_template/persona.md"
printf 'persona\n' > "$R/profiles/acme/persona.md"
git -C "$R" add .gitignore profiles/_template/persona.md
git -C "$R" add -f profiles/acme/persona.md
git -C "$R" commit -q -m base

run() { OUT=$(bash "$CHECK" "$@" 2>/dev/null); RC=$?; }

run "$R"
expect "only tracked files and the template: prints nothing"      test -z "$OUT"
expect "only tracked files and the template: exit 0"              test "$RC" = 0

printf 'edit\n' >> "$R/profiles/acme/persona.md"
run "$R"
expect "an edited tracked profile file is never listed"           test -z "$OUT"
expect "an edited tracked profile file: exit 0"                   test "$RC" = 0

printf 'new\n' > "$R/profiles/_template/extra.md"
run "$R"
expect "a new file in the template folder is never listed"        test -z "$OUT"
expect "a new file in the template folder: exit 0"                test "$RC" = 0

printf 'x' > "$R/profiles/acme/assets/photo.jpg"
printf 'x' > "$R/profiles/acme/素材清单.md"
run "$R"
expect "new files in a client profile: exit 1"                    test "$RC" = 1
expect "the new image is listed, one path per line"               bash -c 'printf "%s\n" "$1" | grep -qx "profiles/acme/assets/photo.jpg"' _ "$OUT"
expect "a Chinese file name is listed as itself, not escaped"     bash -c 'printf "%s\n" "$1" | grep -qx "profiles/acme/素材清单.md"' _ "$OUT"
expect "exactly the two new files are listed"                     test "$(printf '%s\n' "$OUT" | wc -l | tr -d ' ')" = 2
expect "the tracked file is not listed"                           bash -c '! printf "%s\n" "$1" | grep -q "persona.md"' _ "$OUT"

git -C "$R" add -f profiles/acme
run "$R"
expect "after they are added with force: prints nothing"          test -z "$OUT"
expect "after they are added with force: exit 0"                  test "$RC" = 0

# A file ignored somewhere other than profiles/ is not this check's business.
printf 'scratch\n' >> "$R/.gitignore"; printf 'x' > "$R/scratch"
run "$R"
expect "an ignored file outside profiles/ is not listed"          test -z "$OUT"

# A check that cannot look must not report a clean result.
mkdir -p "$T/not-a-repo"
run "$T/not-a-repo"
expect "a folder that is not a git repository is exit 2, not clean" test "$RC" = 2

echo
echo "failures: $FAILS"
exit $FAILS
