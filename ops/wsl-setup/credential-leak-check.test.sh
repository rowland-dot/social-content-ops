#!/usr/bin/env bash
# Tests for ops/wsl-setup/credential-leak-check.sh. Run in Linux or WSL:  bash ops/wsl-setup/credential-leak-check.test.sh
# The credential is a stand-in file in the shape the dreamina program writes; nothing real is read.
# Exit status = number of failures.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CHECK=$HERE/credential-leak-check.sh
T=$(mktemp -d "${TMPDIR:-/tmp}/credleak-test-33.XXXXXX")
trap 'rm -rf "$T"' EXIT
FAILS=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }
expect() { local n=$1; shift; if "$@"; then ok "$n"; else bad "$n"; fi; }

ACCESS=AcCeSs-0123456789abcdefghijklmnopqrstuvwxyz-XYZ
REFRESH=ReFrEsH-0123456789abcdefghijklmnopqrstuvwxyz-QRS
PRIV=PrIvAtEkEyBaSe64-0123456789abcdefghijklmnopqrstuvwxyz==
cat > "$T/cred.json" <<EOF
{"client_key": "short-client-key", "login_expires_at": "2026-10-14T06:42:43+11:00",
 "access_token": "$ACCESS", "refresh_token": "$REFRESH", "token_expires_at": "2026-10-14 07:36:01.123456789 +1100 AEDT",
 "device_key": {"Algorithm": "ECDSA-P256", "PublicKeyBase64": "PuBlIc-0123456789abcdefghijklmnopqrstuvwxyz", "PrivateKeyBase64": "$PRIV"},
 "user_info": {"user_id": 7100000000000000}}
EOF
mkdir -p "$T/clean" "$T/dirty"
printf 'user_credit ok, total_credit: 140\nexpires 2026-10-14 07:36:01\n' > "$T/clean/chat.log"
printf '{"role":"assistant","text":"the balance is 140"}\n' > "$T/clean/transcript.jsonl"
printf 'GET /user_info Authorization: Bearer %s\n' "$ACCESS" > "$T/dirty/gateway.log"
printf 'device key %s\n' "$PRIV" > "$T/dirty/other.txt"

run() { OUT=$("$CHECK" "$@" 2>&1); RC=$?; }

run "$T/cred.json" "$T/clean"
expect "files without any secret: exit 0 and says clean"        bash -c '[ "$1" = 0 ] && printf "%s" "$2" | grep -qi "^CLEAN"' _ "$RC" "$OUT"
expect "a clean run says how many secrets and files it looked at" bash -c 'printf "%s" "$1" | grep -qE "3 secret.*2 file"' _ "$OUT"

run "$T/cred.json" "$T/clean" "$T/dirty"
expect "a file holding the access token: exit 1"                 test "$RC" = 1
expect "it names the file"                                       bash -c 'printf "%s" "$1" | grep -q "gateway.log"' _ "$OUT"
expect "it names which secret, by key"                           bash -c 'printf "%s" "$1" | grep -q "access_token"' _ "$OUT"
expect "it names the file holding the private key too"           bash -c 'printf "%s" "$1" | grep -q "other.txt" && printf "%s" "$1" | grep -q "PrivateKeyBase64"' _ "$OUT"
expect "it does not name a clean file"                           bash -c '! printf "%s" "$1" | grep -q "chat.log"' _ "$OUT"
expect "no secret value, or part of one, is ever printed"        bash -c 'for v in "$2" "$3" "$4"; do printf "%s" "$1" | grep -qF "${v:0:12}" && exit 1; done; exit 0' _ "$OUT" "$ACCESS" "$REFRESH" "$PRIV"

run "$T/cred.json" "$T/dirty/gateway.log"
expect "a single file as the target works"                       test "$RC" = 1

printf 'Authorization: Bearer %s\n' "$REFRESH" > "$T/dirty/sub.log"
mkdir -p "$T/deep/a/b"; cp "$T/dirty/sub.log" "$T/deep/a/b/x.log"
run "$T/cred.json" "$T/deep"
expect "a folder is searched all the way down"                   bash -c '[ "$1" = 1 ] && printf "%s" "$2" | grep -q "refresh_token"' _ "$RC" "$OUT"

run "$T/cred.json" "$T/does-not-exist"
expect "a target that is not there is a usage error (exit 2), not a clean result" test "$RC" = 2
run "$T/no-such-credential.json" "$T/clean"
expect "an unreadable credential file is exit 2, not a clean result" test "$RC" = 2
echo '{"nothing": "secret"}' > "$T/empty.json"
run "$T/empty.json" "$T/clean"
expect "a credential file with no secret in it is exit 2 (the instrument would see nothing)" test "$RC" = 2
run
expect "no arguments: usage, exit 2"                             test "$RC" = 2

echo
echo "failures: $FAILS"
exit $FAILS
