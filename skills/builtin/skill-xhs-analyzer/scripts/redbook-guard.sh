#!/usr/bin/env bash
# The `redbook` command on this machine (WSL). Installed as /usr/local/bin/redbook; the real
# program lives in /opt/redbook and is only reachable through here.
#
# Why it exists: the program has post/comment/reply/like/collect commands and can save the login
# cookie to disk, and nothing in it stops either. The owner's conditions for borrowing the favsense
# account (2026-10-12): read only, favsense idle, one read at a time, at most 100 reads a day,
# stop at the first platform safety signal, cookie values never on disk. This file is where
# those hold, so the agent's good behaviour is not the only thing standing in the way.
#
# The cookie comes fresh for every call from the scanning browser (xhs-cdp-cookies.mjs, run on
# Windows) and exists only in this process's environment.
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REAL=${REDBOOK_REAL_BIN:-/opt/redbook/node_modules/.bin/redbook}
STATE=${REDBOOK_GUARD_STATE_DIR:-/root/.local/state/redbook-guard}
CAP=${REDBOOK_DAILY_CAP:-100}
GAP=${REDBOOK_MIN_GAP_SEC:-15}
HELPER=${REDBOOK_COOKIE_HELPER:-}

umask 077
say() { echo "redbook-guard: $*" >&2; }
# One line per call, never arguments or cookies: the record of what actually reached the program.
record() { mkdir -p "$STATE" && echo "$(date '+%F %T') $1 $2" >> "$STATE/calls.log"; }
refuse() { record refused "$1"; say "refused '$1': $2"; exit 64; }

READS="search read comments user user-posts account-report topics feed health whoami"
# Issue 69: the program fetches many pages inside one call with no delay (and in parallel), but the
# guard only spaces and counts the call. These stay refused; the same work is separate, spaced calls.
SPACED="Do it as separate calls, one note or one page each (read, comments, user, user-posts): each is counted and spaced 15 seconds apart."
# Two steps that are not the program's own commands (issue 70), both under the same lock and tripped check:
#   fetch-file URL DEST        one file from the platform's file servers (no login cookie, not a read)
#   diandian NOTE-URL OUT-FILE the 点点 summary of one note, through the scanning browser (counted as a read)
STEPS="fetch-file diandian"
# What the platform shows when it has stopped trusting the account.
SIGNALS='NeedVerify|captcha|验证码|300012|300031|访问频繁|Session expired|No .a1. cookie|IP.*(blocked|封)'
# trip HIT WHAT: stop everything until the owner has looked
trip() {
  echo "$(date '+%F %T') signal '$1' on: $2" > "$STATE/tripped"
  record signal "$2"
  say "tripped on '$1'. Stopping all reads; tell the owner now, do not retry."
}

# --- 1. what is being asked -------------------------------------------------------------
sub=""
for a in "$@"; do
  case "$a" in
    --cookie-string|--cookie-string=*|--cookie-source|--cookie-source=*|--chrome-profile|--chrome-profile=*)
      refuse "$a" "cookies come only from the scanning browser, never from the command line." ;;
    -*) ;;
    *) [ -z "$sub" ] && sub=$a ;;
  esac
done

needs_cookie=1
case "${1:-}" in
  ""|--help|-h|--version|-V|help) needs_cookie=0 ;;
esac
[ "$sub" = render ] && needs_cookie=0

if [ "$needs_cookie" = 1 ]; then
  case "$sub" in
    analyze-viral|viral-template)
      refuse "$sub" "it fetches the note, its comment pages, the author's posts and the author's profile in one call with no delay, which the guard can neither space nor count. $SPACED" ;;
  esac
  # --all pages through everything in one call. account-report is one account, one page per call.
  for a in "$@"; do
    [ "$a" = --all ] && refuse "$sub" "--all fetches every page in one call with no delay, which the guard can neither space nor count. $SPACED"
  done
  if [ "$sub" = account-report ]; then
    n=0; pages=1; argv=("$@")
    for ((i = 0; i < ${#argv[@]}; i++)); do
      case "${argv[$i]}" in
        --max-pages) pages=${argv[$((i + 1))]:-}; i=$((i + 1)) ;;
        --max-pages=*) pages=${argv[$i]#*=} ;;
        # the value-taking options of the real program (redbook 0.8.2 `account-report --help`) that are not refused above
        --month|--delay|--platform|--xsec-token|--xsec-source) i=$((i + 1)) ;;
        --file|--file=*) refuse "$sub" "--file lists many accounts and fetches them all in one call. Give one account per call. $SPACED" ;;
        -*) ;;
        *) n=$((n + 1)) ;;
      esac
    done
    [ "$pages" = 1 ] || refuse "$sub" "--max-pages above 1 fetches several pages in one call with no delay. $SPACED"
    # n counts the word account-report itself, so 2 = one account.
    [ "$n" -le 2 ] || refuse "$sub" "several accounts fetch in one call with no delay. Give one account per call. $SPACED"
  fi
  case " $READS $STEPS " in
    *" $sub "*) ;;
    *) refuse "${sub:-?}" "this install is read only. Allowed: $READS $STEPS. Posting, commenting, replying, liking, collecting, saving cookies and anything else go back to the owner." ;;
  esac
fi

# The two steps take their arguments as $2 and $3 and are checked before anything is locked or fetched.
FILE_RE='^https?://([A-Za-z0-9-]+\.)*(xhscdn|xiaohongshu)\.com/[^[:space:]]+$'
NOTE_RE='^https?://(www\.)?xiaohongshu\.com/(discovery/item|explore)/[A-Za-z0-9_-]+([/?#].*)?$'
case "$sub" in
  fetch-file)
    [ "${1:-}" = fetch-file ] && [[ ${2:-} =~ $FILE_RE ]] && [ -n "${3:-}" ] \
      || refuse fetch-file "usage: fetch-file URL DEST, and URL must be an http(s) address on xhscdn.com or xiaohongshu.com." ;;
  diandian)
    [ "${1:-}" = diandian ] && [[ ${2:-} =~ $NOTE_RE ]] && [ -n "${3:-}" ] \
      || refuse diandian "usage: diandian NOTE-URL OUT-FILE, and NOTE-URL must be the note's full xiaohongshu.com address (follow short links with 'read' first)." ;;
esac

if ! command -v node >/dev/null 2>&1; then
  export NVM_DIR=${NVM_DIR:-/root/.nvm}
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh" >/dev/null 2>&1 || true
fi

if [ "$needs_cookie" = 0 ]; then
  exec "$REAL" "$@"
fi

# --- 2. one at a time, under the daily cap, not after a safety signal ---------------------
mkdir -p "$STATE"
exec 9>"$STATE/lock"
flock -w 600 9 || { say "another read is still running after 10 minutes; not starting a second one."; exit 69; }

if [ -f "$STATE/tripped" ]; then
  record tripped-refused "$sub"
  say "tripped: $(cat "$STATE/tripped"). The platform raised a safety signal earlier; no more reads until the owner has looked. Tell the owner, do not retry. (The owner clears it by deleting $STATE/tripped.)"
  exit 66
fi

# --- 2a. a file download: the lock and the tripped check above, nothing else ----------------
# It goes to the platform's file servers and carries no login cookie, so it is not a read: it is not
# counted against the daily cap, does not wait for the spacing clock and does not reset it. A safety
# signal on the downloader's error stream, or in a small text answer where a picture should be, trips
# the guard exactly as a read does.
# REDBOOK_DOWNLOAD_CMD: a command that takes the address and the destination (tests).
if [ "$sub" = fetch-file ]; then
  dest=$3
  errf="$STATE/dl-err.$$"
  record ok fetch-file
  if [ -n "${REDBOOK_DOWNLOAD_CMD:-}" ]; then
    "$REDBOOK_DOWNLOAD_CMD" "$2" "$dest" 2>"$errf"; rc=$?
  else
    curl -fsSL --max-time "${REDBOOK_DOWNLOAD_TIMEOUT_SEC:-120}" -o "$dest" -- "$2" 2>"$errf"; rc=$?
  fi
  hit=$(grep -E -i -o "$SIGNALS" "$errf" | head -1)
  if [ -z "$hit" ] && [ -f "$dest" ] && [ "$(stat -c %s "$dest")" -lt 65536 ]; then
    hit=$(grep -a -E -i -o "$SIGNALS" "$dest" | head -1)
  fi
  cat "$errf" >&2
  rm -f "$errf"
  if [ -n "$hit" ]; then trip "$hit" fetch-file; rm -f "$dest"; [ "$rc" -eq 0 ] && rc=1
  elif [ "$rc" -ne 0 ]; then rm -f "$dest"; fi
  exit "$rc"
fi

today=$(date +%F)
countfile="$STATE/count-$today"
used=$(cat "$countfile" 2>/dev/null || echo 0)
if [ "$used" -ge "$CAP" ]; then
  record cap-reached "$sub"
  say "daily cap reached: $used of $CAP reads used today ($today). Stop until tomorrow."
  exit 65
fi

# --- 2b. xhslink.com short links become the note's full address ---------------------------
# The program keeps a whole short link as the note id and sends a malformed request (issue 71).
# So for the commands that take a note link, each short link is followed ONE hop here: no login
# cookie, xhslink.com only, the redirect target is read and not visited. This is not a read of
# Xiaohongshu, so it does not count against the daily cap or reset the spacing clock; it runs
# after the lock, tripped and cap checks above and before any cookie is fetched.
# REDBOOK_SHORTLINK_RESOLVER: a command that takes the link and prints the redirect target (tests).
RESOLVER=${REDBOOK_SHORTLINK_RESOLVER:-}
RTIMEOUT=${REDBOOK_RESOLVE_TIMEOUT_SEC:-10}
SHORT_RE='^https?://([A-Za-z0-9-]+\.)*xhslink\.com([/?#]|$)'
args=("$@")
case "$sub" in
  read|comments)
    for i in "${!args[@]}"; do
      link=${args[$i]}
      [[ $link =~ $SHORT_RE ]] || continue
      if [ -n "$RESOLVER" ]; then
        target=$(timeout "$RTIMEOUT" "$RESOLVER" "$link" 2>/dev/null)
      else
        target=$(timeout "$RTIMEOUT" curl -s -o /dev/null --max-time "$RTIMEOUT" -w '%{redirect_url}' "$link" 2>/dev/null)
      fi
      target=${target%$'\r'}
      if [[ ! $target =~ $NOTE_RE ]]; then
        record resolve-failed "$sub"
        say "could not follow the short link '$link' to a note address (got '${target:-nothing}'). Nothing was sent to Xiaohongshu and no read was used. Open the link in a browser and give the full note address instead."
        exit 67
      fi
      record resolved "$sub"
      args[$i]=$target
    done ;;
esac

# --- 3. cookie, fresh, memory only --------------------------------------------------------
errf="$STATE/helper-err.$$"
if [ -n "$HELPER" ]; then
  cookie=$("$HELPER" 2>"$errf"); hrc=$?
else
  NODE_WIN="/mnt/c/Program Files/nodejs/node.exe"
  cookie=$("$NODE_WIN" "$(wslpath -w "$HERE/xhs-cdp-cookies.mjs")" 2>"$errf"); hrc=$?
fi
cookie=${cookie%$'\r'}
if [ "$hrc" -ne 0 ] || [ -z "$cookie" ]; then
  record no-cookie "$sub"
  say "no cookie, nothing was sent to Xiaohongshu (helper exit $hrc): $(tr -d '\r' < "$errf" | head -3)"
  rm -f "$errf"
  say "Do not retry in a loop; tell the owner."
  # the 点点 step tells "someone else is using the account right now" (3) from every other failure
  [ "$sub" = diandian ] && [ "$hrc" -eq 3 ] && exit 71
  exit 70
fi
rm -f "$errf"

# --- 4. spacing, then the read ----------------------------------------------------------
if [ -f "$STATE/last-run" ]; then
  last=$(cat "$STATE/last-run" 2>/dev/null || echo 0)
  wait=$(( last + GAP * 1000 - $(date +%s%N | cut -b1-13) ))
  [ "$wait" -gt 0 ] && sleep "$(( wait / 1000 )).$(printf %03d $(( wait % 1000 )))"
fi
echo $(( used + 1 )) > "$countfile"
record ok "$sub"

outf="$STATE/out.$$"; errf="$STATE/err.$$"
if [ "$sub" = diandian ]; then
  # The chat is driven in the scanning browser, which already holds the login, so the driver is given
  # no cookie. It prints the finished reply on stdout; the reply is kept only if the driver succeeded
  # and the page showed no safety signal. REDBOOK_DIANDIAN_DRIVER: a command that takes the note address (tests).
  if [ -n "${REDBOOK_DIANDIAN_DRIVER:-}" ]; then
    "$REDBOOK_DIANDIAN_DRIVER" "$2" >"$outf" 2>"$errf"; rc=$?
  else
    NODE_WIN="/mnt/c/Program Files/nodejs/node.exe"
    "$NODE_WIN" "$(wslpath -w "$HERE/xhs-diandian-driver.mjs")" "$2" >"$outf" 2>"$errf"; rc=$?
  fi
else
  REDBOOK_COOKIE_STRING=$cookie REDBOOK_PLATFORM=xhs REDBOOK_COOKIE_FILE='' "$REAL" "${args[@]}" >"$outf" 2>"$errf"
  rc=$?
fi
date +%s%N | cut -b1-13 > "$STATE/last-run"
[ "$sub" = diandian ] || cat "$outf"
cat "$errf" >&2

# --- 5. a platform safety signal stops everything until the owner looks -------------------------
# -i: the program capitalises its messages ("Captcha required: ..."), so match without regard to case.
# The 点点 reply is read by people and can mention a captcha; only the driver's own error stream counts for it.
hit=$(grep -E -i -o "$SIGNALS" "$errf" | head -1)
[ -z "$hit" ] && [ "$rc" -ne 0 ] && [ "$sub" != diandian ] && hit=$(grep -E -i -o "$SIGNALS" "$outf" | head -1)
[ -n "$hit" ] && trip "$hit" "$sub"
if [ "$sub" = diandian ]; then
  if [ "$rc" -eq 0 ] && [ -z "$hit" ]; then mv "$outf" "$3"; else rm -f "$3"; [ "$rc" -eq 0 ] && rc=1; fi
fi
rm -f "$outf" "$errf"
exit "$rc"
