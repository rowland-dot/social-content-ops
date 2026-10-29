#!/usr/bin/env bash
# Tests for redbook-guard.sh, run in WSL: bash redbook-guard.test.sh
# Fakes stand in at the outside boundaries only: the redbook program, the cookie helper and the
# short-link resolver (so no test reaches Xiaohongshu or xhslink.com).
# Exit status = number of failures.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GUARD=$HERE/redbook-guard.sh
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
FAILS=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }

cat > "$T/fake-redbook" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$T/real-calls"
[ -n "\${REDBOOK_COOKIE_STRING:-}" ] && echo "cookie-env-set" >> "$T/real-env"
echo "platform=\${REDBOOK_PLATFORM:-unset}" >> "$T/real-env"
if [ "\${FAKE_MODE:-ok}" = trip ]; then echo "Error: NeedVerify captcha" >&2; exit 1; fi
# FAKE_ERR / FAKE_OUT: print exactly this line on the error / normal stream and exit with FAKE_RC.
# Used with lines copied verbatim from what the real program prints.
[ -n "\${FAKE_ERR:-}" ] && { printf '%s\n' "\$FAKE_ERR" >&2; exit "\${FAKE_RC:-1}"; }
[ -n "\${FAKE_OUT:-}" ] && { printf '%s\n' "\$FAKE_OUT"; exit "\${FAKE_RC:-0}"; }
echo '{"ok":true}'
EOF
cat > "$T/fake-helper-ok" <<EOF
#!/usr/bin/env bash
echo run >> "$T/helper-calls"
echo "a1=SENTINEL_A1_9f3c; web_session=SENTINEL_WS_7c2d"
EOF
cat > "$T/fake-helper-busy" <<EOF
#!/usr/bin/env bash
echo run >> "$T/helper-calls"
echo "busy: favsense is running" >&2
exit 3
EOF
# Stand-in for the one request that follows an xhslink.com short link. Prints the address the
# short link redirects to; RESOLVER_MODE picks a failure instead.
cat > "$T/fake-resolver" <<EOF
#!/usr/bin/env bash
echo "\$1" >> "$T/resolver-calls"
code=\${1%%[?#]*}; code=\${code%/}; code=\${code##*/}
case "\${RESOLVER_MODE:-ok}" in
  ok)      echo "https://www.xiaohongshu.com/discovery/item/note-\$code?source=webshare&xhsshare=pc_web&xsec_token=tok-\$code&xsec_source=pc_share" ;;
  fail)    echo "curl: (6) Could not resolve host" >&2; exit 6 ;;
  empty)   exit 0 ;;
  notnote) echo "https://www.xiaohongshu.com/login?redirectPath=x" ;;
  slow)    sleep 5; echo "https://www.xiaohongshu.com/discovery/item/note-\$code" ;;
esac
EOF
# Stand-in for the one request that downloads a file from the platform's file servers. Receives the address and
# the destination. DL_MODE picks a failure; the two signal modes print / contain what the platform shows on a captcha.
cat > "$T/fake-download" <<EOF2
#!/usr/bin/env bash
echo "\$1 \$2" >> "$T/download-calls"
case "\${DL_MODE:-ok}" in
  ok)            echo IMG-BYTES > "\$2" ;;
  fail)          echo "curl: (22) The requested URL returned error: 404" >&2; exit 22 ;;
  signal-stderr) echo "curl: (22) Captcha required" >&2; exit 22 ;;
  signal-body)   echo "请完成验证码 captcha" > "\$2" ;;
esac
EOF2
# Stand-in for the browser driver of the 点点 chat. It receives the note address and prints the reply on stdout.
cat > "$T/fake-driver" <<EOF2
#!/usr/bin/env bash
echo "\$1" >> "$T/driver-calls"
[ -n "\${REDBOOK_COOKIE_STRING:-}" ] && echo cookie-env-set >> "$T/driver-env"
case "\${DD_MODE:-ok}" in
  ok)     echo "DIANDIAN-REPLY 这篇笔记讲了三个做法" ;;
  signal) echo "safety-signal: captcha" >&2; exit 2 ;;
  signal-but-ok) echo "DIANDIAN-REPLY half a reply"; echo "safety-signal: captcha" >&2 ;;
  fail)   echo "driver: the chat input never appeared" >&2; exit 1 ;;
esac
EOF2
chmod +x "$T"/fake-*

g() {
  REDBOOK_REAL_BIN="$T/fake-redbook" REDBOOK_COOKIE_HELPER="${HELPER:-$T/fake-helper-ok}" \
  REDBOOK_GUARD_STATE_DIR="$T/state" REDBOOK_MIN_GAP_SEC="${GAP:-0}" REDBOOK_DAILY_CAP="${CAP:-100}" \
  REDBOOK_SHORTLINK_RESOLVER="$T/fake-resolver" REDBOOK_RESOLVE_TIMEOUT_SEC="${RESOLVE_TIMEOUT:-10}" \
  REDBOOK_DOWNLOAD_CMD="$T/fake-download" REDBOOK_DIANDIAN_DRIVER="$T/fake-driver" \
    bash "$GUARD" "$@"
}
reset() { rm -rf "$T/state" "$T/real-calls" "$T/real-env" "$T/helper-calls" "$T/resolver-calls" "$T/download-calls" "$T/driver-calls" "$T/driver-env" "$T/reply.txt"; }
count() { [ -f "$1" ] && wc -l < "$1" | tr -d ' ' || echo 0; }

echo "== write commands are refused before anything else happens =="
for c in post comment reply batch-reply like collect auth publish favorites nonsense; do
  reset
  g $c "x" >"$T/out" 2>&1; rc=$?
  if [ $rc -eq 64 ] && grep -qi refused "$T/out" && [ ! -e "$T/real-calls" ] && [ ! -e "$T/helper-calls" ]; then ok "refused: $c"; else bad "refused: $c (rc=$rc)"; fi
done
reset
g search x --cookie-string "a1=1; web_session=2" >"$T/out" 2>&1; rc=$?
[ $rc -eq 64 ] && [ ! -e "$T/real-calls" ] && ok "refused: caller-supplied cookie" || bad "refused: caller-supplied cookie (rc=$rc)"

echo "== one call, one fetch: commands that fetch many pages in one call are refused (issue 69) =="
# Refused = exit 64, program never run, no cookie fetched, no read counted.
refused_fast() {
  local label=$1; shift
  reset
  g "$@" >"$T/out" 2>&1; rc=$?
  if [ $rc -eq 64 ] && grep -qi refused "$T/out" && [ ! -e "$T/real-calls" ] && [ ! -e "$T/helper-calls" ] && ! ls "$T"/state/count-* >/dev/null 2>&1; then ok "refused: $label"; else bad "refused: $label (rc=$rc, program=$(count "$T/real-calls"), helper=$(count "$T/helper-calls"))"; fi
}
NOTE="https://www.xiaohongshu.com/explore/plainid?xsec_token=zz"
refused_fast "viral-template" viral-template "$NOTE" "$NOTE" "$NOTE" --json
refused_fast "analyze-viral" analyze-viral "$NOTE" --json
reset
g viral-template "$NOTE" >"$T/out" 2>&1
grep -q "read" "$T/out" && grep -q "comments" "$T/out" && ok "refusal names the spaced alternative" || bad "refusal names the spaced alternative"
# --all pages through everything in one call; --max-pages above 1, --file and several accounts do the same.
refused_fast "comments --all" comments "$NOTE" --all --json
refused_fast "health --all" health --all --json
refused_fast "user-posts --all" user-posts someuser --all --json
refused_fast "account-report --all" account-report acct1 --all --json
refused_fast "account-report --max-pages 2" account-report acct1 --max-pages 2 --json
refused_fast "account-report --max-pages=2" account-report acct1 --max-pages=2
refused_fast "account-report --file" account-report --file accounts.txt --json
refused_fast "account-report with two accounts" account-report acct1 acct2 --json
refused_fast "--all before the command word" --all comments "$NOTE"
# One note, one page, one account still reaches the program exactly as before.
passes() {
  local label=$1; shift
  reset
  g "$@" >/dev/null 2>&1; rc=$?
  if [ $rc -eq 0 ] && [ "$(count "$T/real-calls")" = 1 ]; then ok "passes: $label"; else bad "passes: $label (rc=$rc, program=$(count "$T/real-calls"))"; fi
}
passes "comments, one page" comments "$NOTE" --json
passes "health" health --json
passes "user-posts, one page" user-posts someuser --json
passes "account-report, one account" account-report acct1 --json
passes "account-report, one account, --max-pages 1" account-report acct1 --max-pages 1 --json
passes "account-report, one account, --month" account-report acct1 --month 2026-09 --json
# Every option of the real account-report (redbook 0.8.2, `account-report --help`) that takes a value is not an account.
passes "account-report, one account, --delay" account-report acct1 --delay 3000 --json
passes "account-report, one account, --platform" account-report acct1 --platform xhs --json
passes "account-report, one account, --xsec-token" account-report acct1 --xsec-token tok123 --json
passes "account-report, one account, --xsec-source" account-report acct1 --xsec-source pc_search --json
passes "account-report, one account, all value options before the account" account-report --platform xhs --xsec-token tok123 --xsec-source pc_search --month 2026-09 --delay 3000 acct1 --json
refused_fast "account-report, two accounts around a value option" account-report acct1 --platform xhs acct2 --json
# The refusals of issue 69 and the two steps of issue 70 live in one allowed list: the list shown on a refusal
# names fetch-file and diandian, and no longer offers the two commands that fetch many pages in one call.
reset
g nonsense >"$T/out" 2>&1
if grep -q "Allowed:" "$T/out" && grep -q "fetch-file" "$T/out" && grep -q "diandian" "$T/out" && ! grep -q "viral-template" "$T/out" && ! grep -q "analyze-viral" "$T/out"; then ok "allowed list names the two steps and not the many-page commands"; else bad "allowed list names the two steps and not the many-page commands: $(cat "$T/out")"; fi

echo "== a read passes, the cookie is only in memory =="
reset
g search "燕麦蛋白" --json >"$T/out" 2>&1; rc=$?
[ $rc -eq 0 ] && ok "search runs" || bad "search runs (rc=$rc)"
[ "$(count "$T/real-calls")" = 1 ] && ok "program called once" || bad "program called once"
grep -q cookie-env-set "$T/real-env" 2>/dev/null && ok "program received the cookie in its environment" || bad "program received the cookie in its environment"
grep -q "platform=xhs" "$T/real-env" 2>/dev/null && ok "platform pinned to the mainland site" || bad "platform pinned to the mainland site"
if grep -rq "SENTINEL" "$T/out" "$T/state" 2>/dev/null; then bad "cookie value leaked to output or state"; else ok "cookie value not in output or state"; fi
if grep -rl "SENTINEL" "$T" 2>/dev/null | grep -v fake-helper-ok >/dev/null; then bad "cookie value written to a file"; else ok "cookie value not written to any file"; fi

echo "== offline commands need no cookie =="
reset
g --version >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ "$(count "$T/real-calls")" = 1 ] && [ ! -e "$T/helper-calls" ] && ok "--version runs the program without fetching a cookie" || bad "--version without a cookie (rc=$rc)"

echo "== helper says no (favsense busy) =="
reset
HELPER="$T/fake-helper-busy" g search x --json >"$T/out" 2>&1; rc=$?
[ $rc -ne 0 ] && [ ! -e "$T/real-calls" ] && grep -q "busy" "$T/out" && ok "program not run, reason shown" || bad "program not run, reason shown (rc=$rc)"

echo "== daily cap =="
reset
CAP=2 g whoami >/dev/null 2>&1; CAP=2 g whoami >/dev/null 2>&1
CAP=2 g whoami >"$T/out" 2>&1; rc=$?
[ $rc -ne 0 ] && [ "$(count "$T/real-calls")" = 2 ] && grep -qi "cap" "$T/out" && ok "third read refused at cap 2" || bad "third read refused at cap 2 (rc=$rc, calls=$(count "$T/real-calls"))"

echo "== one platform safety signal stops everything =="
reset
FAKE_MODE=trip g search x --json >/dev/null 2>&1
g search y --json >"$T/out" 2>&1; rc=$?
[ $rc -ne 0 ] && [ "$(count "$T/real-calls")" = 1 ] && grep -qi "tripped" "$T/out" && ok "next read refused after a captcha signal" || bad "next read refused after a captcha signal (rc=$rc)"
rm -f "$T"/state/tripped
g search z --json >/dev/null 2>&1; [ "$(count "$T/real-calls")" = 2 ] && ok "runs again only after the marker is cleared" || bad "runs again only after the marker is cleared"

echo "== the real program's own lines, in any letter case =="
# $1 label, $2 the line printed. $3: err (default) = error stream, exit 1; out = normal stream, exit 1; out_ok = normal stream, exit 0.
read_then_next() {
  reset
  case "${3:-err}" in
    out)    FAKE_OUT="$2" FAKE_RC=1 g search x --json >/dev/null 2>&1 ;;
    out_ok) FAKE_OUT="$2" FAKE_RC=0 g search x --json >/dev/null 2>&1 ;;
    *)      FAKE_ERR="$2" g search x --json >/dev/null 2>&1 ;;
  esac
  g search y --json >"$T/out" 2>&1; rc=$?
}
trips() {
  read_then_next "$@"
  if [ -e "$T/state/tripped" ] && [ $rc -eq 66 ] && [ "$(count "$T/real-calls")" = 1 ]; then ok "trips: $1"; else bad "trips: $1 (rc=$rc, calls=$(count "$T/real-calls"))"; fi
}
stays_open() {
  read_then_next "$@"
  if [ ! -e "$T/state/tripped" ] && [ $rc -eq 0 ] && [ "$(count "$T/real-calls")" = 2 ]; then ok "does not trip: $1"; else bad "does not trip: $1 (rc=$rc, calls=$(count "$T/real-calls"))"; fi
}
trips "captcha, the program's real line" "Error: Captcha required: type=217, uuid=e24400a2-8b8c-4229-bdcd-698cda65a5bf"
trips "captcha inside the multi-account report" "Failed 5a1b: Captcha required: type=217, uuid=u"
trips "CAPTCHA upper case" "Error: CAPTCHA required"
trips "needverify lower case" "Error: needverify"
trips "SESSION EXPIRED upper case" "Error: SESSION EXPIRED"
trips "ip BLOCKED mixed case" "Error: ip BLOCKED by the platform"
trips "missing a1 cookie, other case" "Error: no 'A1' COOKIE"
trips "300012 in an API error" "Error: API error 300012"
trips "captcha on the normal stream of a failed read" "Captcha required: type=217, uuid=u" out
stays_open "a successful read that mentions a captcha in its text" "Captcha required is what the post says" out_ok
stays_open "a failure that is not a safety signal" "Error: Signature verification failed (code 300015)"

echo "== spacing between reads =="
reset
GAP=3 g whoami >/dev/null 2>&1
s=$(date +%s); GAP=3 g whoami >/dev/null 2>&1; e=$(date +%s)
[ $((e - s)) -ge 2 ] && ok "second read waited for the gap (3s configured)" || bad "second read waited for the gap ($((e - s))s of 3)"

echo "== every call leaves a one-line record (the evidence that nothing but reads went out) =="
reset
g post "x" >/dev/null 2>&1; g search "y" --json >/dev/null 2>&1; CAP=1 g whoami >/dev/null 2>&1
log="$T/state/calls.log"
grep -q " refused post$" "$log" 2>/dev/null && ok "refusal recorded" || bad "refusal recorded"
grep -q " ok search$" "$log" 2>/dev/null && ok "read recorded" || bad "read recorded"
grep -q " cap-reached whoami$" "$log" 2>/dev/null && ok "cap stop recorded" || bad "cap stop recorded"
grep -q "SENTINEL" "$log" 2>/dev/null && bad "record holds no cookie" || ok "record holds no cookie"

echo "== xhslink.com short links are followed to the note address before the program runs =="
SHORT=http://xhslink.com/o/AbCdEf123
FULL="https://www.xiaohongshu.com/discovery/item/note-AbCdEf123?source=webshare&xhsshare=pc_web&xsec_token=tok-AbCdEf123&xsec_source=pc_share"
for c in read comments; do
  reset
  g $c "$SHORT" --json >/dev/null 2>&1; rc=$?
  if [ $rc -eq 0 ] && [ "$(cat "$T/real-calls" 2>/dev/null)" = "$c $FULL --json" ]; then ok "$c gets the full note address, not the short link"; else bad "$c gets the full note address (rc=$rc, program got: $(cat "$T/real-calls" 2>/dev/null))"; fi
done
reset
g read https://www.xiaohongshu.com/explore/plainid?xsec_token=zz >/dev/null 2>&1
[ ! -e "$T/resolver-calls" ] && [ "$(cat "$T/real-calls")" = "read https://www.xiaohongshu.com/explore/plainid?xsec_token=zz" ] && ok "a full address passes through, no resolver call" || bad "a full address passes through, no resolver call"
reset
g search "$SHORT" >/dev/null 2>&1
[ ! -e "$T/resolver-calls" ] && [ "$(cat "$T/real-calls")" = "search $SHORT" ] && ok "search text is not treated as a note link" || bad "search text is not treated as a note link"

echo "== a short link that cannot be resolved stops before any request =="
for m in fail empty notnote slow; do
  reset
  g read x >/dev/null 2>&1                                   # one real read first, so the count is 1
  rm -f "$T/real-calls" "$T/helper-calls"
  RESOLVER_MODE=$m RESOLVE_TIMEOUT=1 g read "$SHORT" --json >"$T/out" 2>&1; rc=$?
  used=$(cat "$T"/state/count-* 2>/dev/null)
  if [ $rc -ne 0 ] && grep -q "$SHORT" "$T/out" && [ ! -e "$T/helper-calls" ] && [ ! -e "$T/real-calls" ] && [ "$used" = 1 ]; then ok "unresolvable ($m): named in the message, no cookie, no program, count unchanged"; else bad "unresolvable ($m) (rc=$rc, used=$used, helper=$(count "$T/helper-calls"), program=$(count "$T/real-calls"))"; fi
done

echo "== a tripped guard does not even resolve =="
reset
FAKE_MODE=trip g search x --json >/dev/null 2>&1
g read "$SHORT" >"$T/out" 2>&1; rc=$?
[ $rc -eq 66 ] && [ ! -e "$T/resolver-calls" ] && ok "tripped: short link not resolved" || bad "tripped: short link not resolved (rc=$rc)"

echo "== each resolution leaves one line in the record, never a cookie =="
reset
g read "$SHORT" >/dev/null 2>&1
[ "$(grep -c ' resolved read$' "$T/state/calls.log" 2>/dev/null)" = 1 ] && ok "one record line per resolution" || bad "one record line per resolution"
grep -q "SENTINEL" "$T/state/calls.log" 2>/dev/null && bad "resolution record holds no cookie" || ok "resolution record holds no cookie"
reset
RESOLVER_MODE=fail g read "$SHORT" >/dev/null 2>&1
grep -q ' resolve-failed read$' "$T/state/calls.log" 2>/dev/null && ok "failed resolution recorded" || bad "failed resolution recorded"

echo "== file downloads (fetch-file): the guard's lock and tripped check, no cookie, one record line, xhscdn/xiaohongshu only =="
IMG='https://sns-webpic-qc.xhscdn.com/202610/abc123/img1!nd_dft'
DEST=$T/dl/01.jpg
mkdir -p "$T/dl"
reset
g fetch-file "$IMG" "$DEST" >"$T/out" 2>&1; rc=$?
if [ $rc -eq 0 ] && [ "$(cat "$T/download-calls" 2>/dev/null)" = "$IMG $DEST" ] && grep -q IMG-BYTES "$DEST" 2>/dev/null; then ok "fetch-file runs the downloader with the address and the destination"; else bad "fetch-file runs the downloader (rc=$rc, calls: $(cat "$T/download-calls" 2>/dev/null))"; fi
[ ! -e "$T/helper-calls" ] && ok "fetch-file fetches no cookie" || bad "fetch-file fetches no cookie"
if [ -z "$(ls "$T"/state/count-* 2>/dev/null)" ]; then ok "fetch-file does not count against the daily cap"; else bad "fetch-file does not count against the daily cap"; fi
[ "$(grep -c ' ok fetch-file$' "$T/state/calls.log" 2>/dev/null)" = 1 ] && ok "fetch-file leaves exactly one record line" || bad "fetch-file leaves exactly one record line ($(grep -c fetch-file "$T/state/calls.log" 2>/dev/null) lines)"
if grep -rq "SENTINEL\|xsec_token" "$T/state" "$T/out" 2>/dev/null; then bad "fetch-file record holds no cookie or access code"; else ok "fetch-file record holds no cookie or access code"; fi
rm -f "$DEST"
reset
CAP=1 g whoami >/dev/null 2>&1
CAP=1 g fetch-file "$IMG" "$DEST" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && [ -s "$DEST" ] && ok "a download still runs after the daily cap of reads is used up" || bad "a download still runs after the daily cap is used up (rc=$rc)"
rm -f "$DEST"
for u in https://evil.example.com/a.jpg file:///etc/passwd "http://xhscdn.com.evil.example/a.jpg" "ftp://sns-webpic-qc.xhscdn.com/a.jpg"; do
  reset
  g fetch-file "$u" "$DEST" >"$T/out" 2>&1; rc=$?
  if [ $rc -eq 64 ] && [ ! -e "$T/download-calls" ] && [ ! -e "$DEST" ]; then ok "fetch-file refuses $u"; else bad "fetch-file refuses $u (rc=$rc)"; fi
done
reset
FAKE_MODE=trip g search x --json >/dev/null 2>&1
g fetch-file "$IMG" "$DEST" >"$T/out" 2>&1; rc=$?
if [ $rc -eq 66 ] && [ ! -e "$T/download-calls" ] && grep -qi tripped "$T/out" && grep -q ' tripped-refused fetch-file$' "$T/state/calls.log"; then ok "tripped: fetch-file refused, downloader not started, recorded"; else bad "tripped: fetch-file refused (rc=$rc)"; fi
reset
DL_MODE=fail g fetch-file "$IMG" "$DEST" >"$T/out" 2>&1; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$DEST" ] && [ ! -e "$T/state/tripped" ]; then ok "a failed download is an error, not a safety signal"; else bad "a failed download is an error (rc=$rc)"; fi
for m in signal-stderr signal-body; do
  reset
  DL_MODE=$m g fetch-file "$IMG" "$DEST" >"$T/out" 2>&1; rc=$?
  g search y --json >"$T/out2" 2>&1; rc2=$?
  if [ $rc -ne 0 ] && [ -e "$T/state/tripped" ] && [ ! -e "$DEST" ] && [ $rc2 -eq 66 ] && [ "$(count "$T/real-calls")" = 0 ]; then ok "safety signal in a download ($m): guard tripped, file removed, later reads refused"; else bad "safety signal in a download ($m) (rc=$rc, later rc=$rc2)"; fi
done
reset
mkdir -p "$T/state"
( flock 8; sleep 3 ) 8>"$T/state/lock" &
sleep 0.5
s=$(date +%s); g fetch-file "$IMG" "$DEST" >/dev/null 2>&1; e=$(date +%s)
wait
[ $((e - s)) -ge 2 ] && [ -s "$DEST" ] && ok "fetch-file waits for the guard's lock while a read is running" || bad "fetch-file waits for the guard's lock ($((e - s))s)"

echo "== 点点 summary (diandian): counted, spaced, refused when tripped or capped or favsense busy, driver never started then =="
NOTEURL="https://www.xiaohongshu.com/explore/6aabad9400000000110328e1?xsec_token=tok-secret&xsec_source=pc_search"
REPLY=$T/reply.txt
reset
g diandian "$NOTEURL" "$REPLY" >"$T/out" 2>&1; rc=$?
if [ $rc -eq 0 ] && [ "$(cat "$T/driver-calls" 2>/dev/null)" = "$NOTEURL" ] && grep -q "DIANDIAN-REPLY" "$REPLY" 2>/dev/null; then ok "diandian runs the driver on the note address and keeps its reply"; else bad "diandian runs the driver (rc=$rc, driver got: $(cat "$T/driver-calls" 2>/dev/null))"; fi
[ "$(count "$T/helper-calls")" = 1 ] && ok "diandian asks the cookie helper whether the account is free" || bad "diandian asks the cookie helper once ($(count "$T/helper-calls"))"
[ "$(cat "$T"/state/count-* 2>/dev/null)" = 1 ] && ok "diandian counts as one read against the daily cap" || bad "diandian counts as one read (count: $(cat "$T"/state/count-* 2>/dev/null))"
[ "$(grep -c ' ok diandian$' "$T/state/calls.log" 2>/dev/null)" = 1 ] && ok "diandian leaves exactly one record line" || bad "diandian leaves exactly one record line"
if grep -q cookie-env-set "$T/driver-env" 2>/dev/null; then bad "the driver is not given the cookie"; else ok "the driver is not given the cookie"; fi
if grep -rq "SENTINEL\|tok-secret" "$T/state" "$T/out" 2>/dev/null; then bad "diandian record holds no cookie or access code"; else ok "diandian record holds no cookie or access code"; fi
reset
CAP=1 g whoami >/dev/null 2>&1
CAP=1 g diandian "$NOTEURL" "$REPLY" >"$T/out" 2>&1; rc=$?
if [ $rc -eq 65 ] && [ ! -e "$T/driver-calls" ] && [ ! -e "$REPLY" ] && grep -q ' cap-reached diandian$' "$T/state/calls.log"; then ok "cap reached: diandian refused, driver never started"; else bad "cap reached: diandian refused (rc=$rc)"; fi
reset
FAKE_MODE=trip g search x --json >/dev/null 2>&1
g diandian "$NOTEURL" "$REPLY" >"$T/out" 2>&1; rc=$?
if [ $rc -eq 66 ] && [ ! -e "$T/driver-calls" ] && grep -q ' tripped-refused diandian$' "$T/state/calls.log"; then ok "tripped: diandian refused, driver never started"; else bad "tripped: diandian refused (rc=$rc)"; fi
reset
HELPER="$T/fake-helper-busy" g diandian "$NOTEURL" "$REPLY" >"$T/out" 2>&1; rc=$?
if [ $rc -eq 71 ] && [ ! -e "$T/driver-calls" ] && grep -q "busy" "$T/out" && [ -z "$(ls "$T"/state/count-* 2>/dev/null)" ]; then ok "favsense or an SOP scan busy: diandian stops (exit 71), driver never started, no read counted"; else bad "favsense busy: diandian stops (rc=$rc)"; fi
for u in "http://xhslink.com/o/AbCdEf123" "https://example.com/explore/abc" "总结 this please" ""; do
  reset
  g diandian "$u" "$REPLY" >"$T/out" 2>&1; rc=$?
  if [ $rc -eq 64 ] && [ ! -e "$T/driver-calls" ] && [ ! -e "$T/helper-calls" ]; then ok "diandian refuses '$u' (not a note address)"; else bad "diandian refuses '$u' (rc=$rc)"; fi
done
reset
DD_MODE=signal g diandian "$NOTEURL" "$REPLY" >"$T/out" 2>&1; rc=$?
g search y --json >"$T/out2" 2>&1; rc2=$?
if [ $rc -ne 0 ] && [ -e "$T/state/tripped" ] && [ ! -e "$REPLY" ] && [ $rc2 -eq 66 ]; then ok "safety signal on the 点点 page: guard tripped, no reply kept, later reads refused"; else bad "safety signal on the 点点 page (rc=$rc, later rc=$rc2)"; fi
reset
DD_MODE=signal-but-ok g diandian "$NOTEURL" "$REPLY" >"$T/out" 2>&1; rc=$?
if [ -e "$T/state/tripped" ] && [ ! -e "$REPLY" ]; then ok "a safety signal with a clean exit still trips the guard and keeps no reply"; else bad "a safety signal with a clean exit (rc=$rc)"; fi
reset
DD_MODE=fail g diandian "$NOTEURL" "$REPLY" >"$T/out" 2>&1; rc=$?
if [ $rc -ne 0 ] && [ ! -e "$REPLY" ] && [ ! -e "$T/state/tripped" ] && [ "$(cat "$T"/state/count-* 2>/dev/null)" = 1 ]; then ok "a driver failure that is not a safety signal: error, no reply kept, not tripped, the read stays counted"; else bad "a driver failure (rc=$rc)"; fi
reset
GAP=3 g whoami >/dev/null 2>&1
s=$(date +%s); GAP=3 g diandian "$NOTEURL" "$REPLY" >/dev/null 2>&1; e=$(date +%s)
[ $((e - s)) -ge 2 ] && ok "diandian waits out the guard's spacing after a read" || bad "diandian waits out the spacing ($((e - s))s of 3)"
reset
mkdir -p "$T/state"
( flock 8; sleep 3 ) 8>"$T/state/lock" &
sleep 0.5
s=$(date +%s); g diandian "$NOTEURL" "$REPLY" >/dev/null 2>&1; e=$(date +%s)
wait
[ $((e - s)) -ge 2 ] && [ -s "$REPLY" ] && ok "diandian waits for the guard's lock while a read is running" || bad "diandian waits for the guard's lock ($((e - s))s)"

echo "failures: $FAILS"
exit $FAILS
