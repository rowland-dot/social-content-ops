#!/usr/bin/env bash
# Tests for ops/easel-start/easel-start.sh. Run in Linux or WSL:  bash ops/easel-start/easel-start.test.sh
#
# The only seam is the script's command line: its exit status, what it says, and which outside programs it calls.
# The outside world is replaced by stand-ins on a private PATH (curl, explorer.exe, wslpath, Easel's own `easel`
# program, and Node's `node` / `openclaw`), so nothing real is started, stopped or opened. Node is reachable
# only through the fake home's .bashrc, exactly as nvm is on the real machine, so a script that runs its steps
# in a non-interactive shell cannot see it. The script is the real one, run in a scratch copy of the project.
# Exit status = number of failures.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SRC=${EASEL_START_SRC:-$HERE}   # folder holding the script and its window file; the mutation checks point it at a changed copy
T=$(mktemp -d "${TMPDIR:-/tmp}/easel-start-test-52.XXXXXX")
trap 'rm -rf "$T"' EXIT
FAILS=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }
# expect NAME CONDITION...  (the condition is a command; the test passes when it exits 0)
expect() { local n=$1; shift; if "$@"; then ok "$n"; else bad "$n"; fi; }
out_has()   { printf '%s\n' "$OUT" | grep -qF -- "$1"; }
out_lacks() { ! printf '%s\n' "$OUT" | grep -qF -- "$1"; }
calls_has()   { grep -qF -- "$1" "$W/calls.log"; }
calls_lacks() { ! grep -qF -- "$1" "$W/calls.log"; }
calls_count() { test "$(grep -cF -- "$1" "$W/calls.log")" = "$2"; }

mkshim() { cat > "$1"; chmod +x "$1"; }

# world NAME [flag...]  builds a fresh fake machine under $T/NAME and sets W and R.
# flags: web-up, web-starts (the window brings the web workspace up at once), web-slow (two seconds later), gw-up, gw-starts (a gateway start brings it up),
#        engine=claude|codex|api (saved in outputs/_harness/config.json; none saved = OpenClaw), no-engine-prog (the claude and codex programs are not on the path),
#        no-node (Node is not on the interactive shell's path), no-openclaw (Node is, openclaw is not), ping=ok|step1|step2|both|crash
world() {
  local name=$1; shift
  W=$T/$name; R=$W/root
  mkdir -p "$W"/{bin,nodebin,home} "$R/ops/easel-start" "$R/.venv/bin"
  : > "$W/calls.log"; echo ok > "$W/ping.mode"
  # the private PATH: only the real tools the script is expected to use
  local t p
  for t in bash env sed grep awk cat mkdir rm ls head tail sort date dirname basename mktemp tr wc cut sleep touch chmod ln id uname; do
    p=$(command -v "$t" 2>/dev/null) && ln -sf "$p" "$W/bin/$t"
  done
  for f in "$SRC"/easel-start.sh "$SRC"/easel-web-window.cmd; do [ -f "$f" ] && cp "$f" "$R/ops/easel-start/"; done
  local f
  for f in "$@"; do
    case $f in
      web-up) : > "$W/web.up" ;;
      web-starts) : > "$W/web.starts" ;;
      web-slow) : > "$W/web.slow" ;;
      gw-up) : > "$W/gw.up" ;;
      gw-starts) : > "$W/gw.starts" ;;
      no-node) : > "$W/no.node" ;;
      no-openclaw) : > "$W/no.openclaw" ;;
      ping=*) echo "${f#ping=}" > "$W/ping.mode" ;;
      engine=*) mkdir -p "$R/outputs/_harness"; printf '{\n  "runtime": "%s"\n}\n' "${f#engine=}" > "$R/outputs/_harness/config.json"
                echo "${f#engine=}" > "$W/engine" ;;
      no-engine-prog) : > "$W/no.engine.prog" ;;
    esac
  done
  # Node as nvm leaves it: on the path only for a shell that reads .bashrc
  mkshim "$W/nodebin/node" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  mkshim "$W/nodebin/openclaw" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  [ -e "$W/no.openclaw" ] && rm -f "$W/nodebin/openclaw"
  for t in claude codex; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$W/nodebin/$t"; chmod +x "$W/nodebin/$t"
    [ -e "$W/no.engine.prog" ] && rm -f "$W/nodebin/$t"
  done
  [ -e "$W/no.node" ] || printf 'export PATH="%s/nodebin:$PATH"\n' "$W" > "$W/home/.bashrc"
  # curl answers the web workspace's status address only while web.up exists, like a real server that is up
  mkshim "$W/bin/curl" <<'EOF'
#!/usr/bin/env bash
for a in "$@"; do case $a in http*) url=$a ;; esac; done
echo "curl $url" >> "$FAKE_W/calls.log"
[ -e "$FAKE_W/web.up" ] && exit 0
exit 22
EOF
  # explorer.exe opens the window file; like the real one it exits 1 even when it worked
  mkshim "$W/bin/explorer.exe" <<'EOF'
#!/usr/bin/env bash
echo "explorer.exe $*" >> "$FAKE_W/calls.log"
[ -e "$FAKE_W/web.starts" ] && : > "$FAKE_W/web.up"
# a slow start: the web workspace answers only two seconds after the window opened
[ -e "$FAKE_W/web.slow" ] && ( sleep 2; : > "$FAKE_W/web.up" ) >/dev/null 2>&1 &
exit 1
EOF
  mkshim "$W/bin/wslpath" <<'EOF'
#!/usr/bin/env bash
echo "wslpath $*" >> "$FAKE_W/calls.log"
printf 'C:\\fake\\%s\n' "$(basename "$2")"
EOF
  # anything that would stop a running Easel is recorded as forbidden
  for t in pkill killall taskkill.exe; do
    mkshim "$W/bin/$t" <<'EOF'
#!/usr/bin/env bash
echo "FORBIDDEN $(basename "$0") $*" >> "$FAKE_W/calls.log"
EOF
  done
  # Easel's own program, as far as the script sees it
  mkshim "$R/.venv/bin/easel" <<'EOF'
#!/usr/bin/env bash
echo "easel $*" >> "$FAKE_W/calls.log"
case "${1:-} ${2:-}" in
  "gateway status")
    if [ -e "$FAKE_W/gw.up" ]; then echo "[easel] Gateway running (PID 1423), profile: easel, port: 37289"
    else echo "[easel] Gateway not running (profile: easel, port: 37289)"; fi ;;
  "gateway start")
    [ -e "$FAKE_W/gw.starts" ] && : > "$FAKE_W/gw.up"
    if [ -e "$FAKE_W/gw.up" ]; then echo "[easel] Gateway started (PID 1423)"
    else echo "[easel] Gateway may not be ready yet — check: tail -f /tmp/easel-gateway.log"; fi ;;
  "gateway stop"|"gateway restart") echo "FORBIDDEN easel $*" >> "$FAKE_W/calls.log" ;;
  "ping ")
    # Claude Code, Codex and the API engine need no gateway and no openclaw program: Easel asks the engine itself
    if [ -e "$FAKE_W/engine" ]; then
      if [ "$(cat "$FAKE_W/ping.mode")" = ok ]; then echo; echo "$(cat "$FAKE_W/engine") 连通性测试通过"; exit 0; fi
      echo; echo "$(cat "$FAKE_W/engine") 连通性失败：请检查原生登录"; exit 1
    fi
    # the real ping crashes with a traceback when openclaw is missing
    command -v openclaw >/dev/null || { echo "Traceback (most recent call last):"; echo "FileNotFoundError: openclaw CLI not found"; exit 1; }
    ok=$(printf '\033[0;32mOK\033[0m'); fail=$(printf '\033[0;31mFAIL\033[0m')
    s1=$ok; s2=$ok; rc=0
    case "$(cat "$FAKE_W/ping.mode")" in
      step1) s1=$fail; rc=1 ;;
      step2) s2=$fail; rc=1 ;;
      both) s1=$fail; s2=$fail; rc=1 ;;
      crash) echo "Traceback (most recent call last):"; echo "RuntimeError: ping blew up"; exit 1 ;;
    esac
    echo "[easel] 连通性测试"; echo
    echo "  Step 1: Gateway healthz (localhost:37289)          $s1"
    [ "$s1" = "$fail" ] && echo "    └─ 端口来自 profile hash"
    echo "  Step 2: OpenClaw agent via Gateway (say PONG)      $s2"
    [ "$s2" = "$fail" ] && echo "    gateway timeout after 30s"
    exit $rc ;;
esac
exit 0
EOF
  export FAKE_W=$W
}

# run: the script, started from an unrelated folder, with only the private PATH and the fake home
run() {
  OUT=$(cd "$T" && env -i HOME="$W/home" PATH="$W/bin" FAKE_W="$W" EASEL_START_WAIT="${WAIT:-3}" \
        "$BASH" "$R/ops/easel-start/easel-start.sh" 2>&1)
  RC=$?
}

# ---- Easel already running: nothing is started, nothing is stopped ------------------------------------------
world running web-up gw-up
run
expect "already running: exit 0"                                  test "$RC" = 0
expect "already running: the verdict says Easel is ready"         out_has "EASEL READY"
expect "already running: no window is opened"                     calls_lacks "explorer.exe"
expect "already running: the gateway is not started again"        calls_lacks "easel gateway start"
expect "already running: the connection test runs once"           calls_count "easel ping" 1
expect "already running: nothing is stopped or restarted"         calls_lacks "FORBIDDEN"

# ---- Both parts down: the window is opened once, the gateway is started once --------------------------------
world cold web-starts gw-starts
run
expect "cold start: exit 0"                                       test "$RC" = 0
expect "cold start: the verdict says Easel is ready"              out_has "EASEL READY"
expect "cold start: one window is opened"                         calls_count "explorer.exe" 1
expect "cold start: the window file is the one that was opened"   calls_has "explorer.exe C:\\fake\\easel-web-window.cmd"
expect "cold start: the gateway is started once, by Easel's own command" calls_count "easel gateway start" 1
expect "cold start: the connection test runs once"                calls_count "easel ping" 1
expect "cold start: the web workspace's status address on 7860 is asked" calls_has "curl http://localhost:7860/api/status"
expect "cold start: nothing else is asked over the network"       \
  bash -c '! grep "^curl " "$1/calls.log" | grep -vqx "curl http://localhost:7860/api/status"' _ "$W"
expect "cold start: nothing is stopped or restarted"              calls_lacks "FORBIDDEN"

# ---- Web workspace up, gateway down: no second window, the gateway is started -------------------------------
world gwdown web-up gw-starts
run
expect "gateway down: exit 0"                                     test "$RC" = 0
expect "gateway down: no window is opened"                        calls_lacks "explorer.exe"
expect "gateway down: the gateway is started once"                calls_count "easel gateway start" 1

# ---- A web workspace that is slow to answer is waited for ---------------------------------------------------
world slow web-slow gw-up
WAIT=8 run
expect "slow web workspace: exit 0"                               test "$RC" = 0
expect "slow web workspace: still only one window"                calls_count "explorer.exe" 1

# ---- The web workspace never answers ------------------------------------------------------------------------
world webdead gw-up
WAIT=2 run
expect "web never answers: non-zero exit"                         test "$RC" != 0
expect "web never answers: the verdict names the web workspace and its address" out_has "web workspace did not answer on localhost:7860"
expect "web never answers: the verdict states the wait"           out_has "within 2 seconds"
expect "web never answers: no claim that Easel is ready"          out_lacks "EASEL READY"
expect "web never answers: the window was opened once, not again" calls_count "explorer.exe" 1
expect "web never answers: nothing is stopped or restarted"       calls_lacks "FORBIDDEN"

# ---- The gateway never comes up -----------------------------------------------------------------------------
world gwdead web-up
run
expect "gateway never up: non-zero exit"                          test "$RC" != 0
expect "gateway never up: the verdict names the gateway"          out_has "gateway did not come up"
expect "gateway never up: Easel's own words are shown"            out_has "Gateway may not be ready yet"
expect "gateway never up: no claim that Easel is ready"           out_lacks "EASEL READY"
expect "gateway never up: the connection test is not run"         calls_lacks "easel ping"
expect "gateway never up: nothing is stopped or restarted"        calls_lacks "FORBIDDEN"

# ---- The connection test fails ------------------------------------------------------------------------------
world ping1 web-up gw-up ping=step1
run
expect "ping step 1 fails: non-zero exit"                         test "$RC" != 0
expect "ping step 1 fails: the verdict names step 1 only"         out_has "ping failed at step 1 (the gateway's health check)."
expect "ping step 1 fails: Easel's own lines are shown"           out_has "Step 1: Gateway healthz (localhost:37289)"
expect "ping step 1 fails: including the hint under the failed step" out_has "端口来自 profile hash"
expect "ping step 1 fails: the colour codes are removed"          out_lacks "[0;31m"
expect "ping step 1 fails: no claim that Easel is ready"          out_lacks "EASEL READY"

world ping2 web-up gw-up ping=step2
run
expect "ping step 2 fails: non-zero exit"                         test "$RC" != 0
expect "ping step 2 fails: the verdict names step 2 only"         out_has "ping failed at step 2 (the agent's reply)."
expect "ping step 2 fails: Easel's own lines are shown"           out_has "gateway timeout after 30s"

world pingboth web-up gw-up ping=both
run
expect "both ping steps fail: the verdict names both"             out_has "ping failed at step 1 (the gateway's health check) and step 2 (the agent's reply)."

world pingcrash web-up gw-up ping=crash
run
expect "ping stops early: non-zero exit"                          test "$RC" != 0
expect "ping stops early: the verdict says no step was reported"  out_has "ping stopped before reporting a step (exit 1)."
expect "ping stops early: Easel's own lines are shown"            out_has "RuntimeError: ping blew up"

# ---- Node is missing: a plain message, and nothing is started -----------------------------------------------
world nonode web-starts gw-starts no-node
run
expect "no Node: non-zero exit"                                   test "$RC" != 0
expect "no Node: the verdict says Node or openclaw was not found" out_has "Node or the openclaw program was not found"
expect "no Node: no traceback reaches the reader"                 out_lacks "Traceback"
expect "no Node: no window is opened"                             calls_lacks "explorer.exe"
expect "no Node: the gateway is not started"                      calls_lacks "easel gateway"
expect "no Node: the connection test is not run"                  calls_lacks "easel ping"

world noclaw web-starts gw-starts no-openclaw
run
expect "Node present but no openclaw: non-zero exit"              test "$RC" != 0
expect "Node present but no openclaw: the same plain message"     out_has "Node or the openclaw program was not found"
expect "Node present but no openclaw: no traceback reaches the reader" out_lacks "Traceback"
expect "Node present but no openclaw: nothing is started"         calls_lacks "easel gateway"

# ---- Another engine is chosen (Claude Code or Codex): no OpenClaw program, no gateway --------------------------
for eng in claude codex; do
  world "$eng" web-starts engine=$eng no-openclaw
  run
  expect "$eng engine: exit 0 with no openclaw program"              test "$RC" = 0
  expect "$eng engine: the verdict says Easel is ready"              out_has "EASEL READY"
  expect "$eng engine: the verdict names the engine, not a gateway"  out_has "$eng engine answered the ping"
  expect "$eng engine: the verdict does not claim a gateway"         out_lacks "gateway up"
  expect "$eng engine: one window is opened"                         calls_count "explorer.exe" 1
  expect "$eng engine: the gateway is never asked about or started"  calls_lacks "easel gateway"
  expect "$eng engine: the connection test runs once"                calls_count "easel ping" 1
  expect "$eng engine: nothing is stopped or restarted"              calls_lacks "FORBIDDEN"
done

world api web-up engine=api no-openclaw no-engine-prog
run
expect "api engine: ready without any engine program or gateway"   bash -c '[ "$1" = 0 ] && ! grep -q "easel gateway" "$2/calls.log"' _ "$RC" "$W"

world engfail web-up engine=claude no-openclaw ping=step2
run
expect "engine ping fails: non-zero exit"                          test "$RC" != 0
expect "engine ping fails: the verdict names the engine"           out_has "ping failed on the claude engine."
expect "engine ping fails: the engine's own words are shown"       out_has "请检查原生登录"
expect "engine ping fails: no claim that Easel is ready"           out_lacks "EASEL READY"

world engnoprog web-starts engine=claude no-openclaw no-engine-prog
run
expect "engine program missing: non-zero exit"                     test "$RC" != 0
expect "engine program missing: the verdict names the program"     out_has "claude program was not found"
expect "engine program missing: no window, no ping"                bash -c '! grep -q "explorer.exe\|easel ping" "$1/calls.log"' _ "$W"

world ocsaved web-starts gw-starts engine=openclaw no-openclaw
run
expect "OpenClaw saved as the engine: still refuses without openclaw" out_has "Node or the openclaw program was not found"

echo
echo "failures: $FAILS"
exit $FAILS
