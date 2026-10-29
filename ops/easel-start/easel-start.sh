#!/usr/bin/env bash
# Brings Easel up on this PC and says plainly whether each part answered. Run in WSL:
#   bash ops/easel-start/easel-start.sh
# It never stops, restarts or kills anything: stopping Easel ends whatever job it is running.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
WAIT=${EASEL_START_WAIT:-90}   # seconds to wait for the web workspace to answer

fail() { echo "EASEL NOT READY: $1"; [ $# -gt 1 ] && printf '%s\n' "$2"; exit 1; }

# nvm loads Node only in an interactive shell, so every Easel command runs in one
node_shell() { ROOT=$ROOT bash -ic 'cd "$ROOT" && '"$1"; }

web_up() { curl -sf --max-time 3 -o /dev/null "http://localhost:7860/api/status"; }

# checked first because `easel ping` crashes with a Python traceback when openclaw is missing
node_shell 'command -v node >/dev/null && command -v openclaw >/dev/null' 2>/dev/null ||
  fail "Node or the openclaw program was not found in an interactive WSL shell (nvm loads Node only there), so Easel cannot start or be tested."

# a window that outlives this script's caller: explorer.exe opens the .cmd (its exit status says nothing: it is 1 even when it worked)
web_up || explorer.exe "$(wslpath -w "$HERE/easel-web-window.cmd")"

# Easel's own gateway command is the only place that knows the gateway's port
case $(node_shell '.venv/bin/easel gateway status' 2>&1) in
  *"Gateway running"*) ;;
  *)
    started=$(node_shell '.venv/bin/easel gateway start' 2>&1)
    case $(node_shell '.venv/bin/easel gateway status' 2>&1) in
      *"Gateway running"*) ;;
      *) fail "gateway did not come up." "$started" ;;
    esac ;;
esac

for ((i = 0; i < WAIT; i++)); do web_up && break; sleep 1; done
web_up || fail "web workspace did not answer on localhost:7860 within $WAIT seconds."

ping_out=$(node_shell '.venv/bin/easel ping' 2>&1); rc=$?
if [ $rc -ne 0 ]; then
  ping_out=$(printf '%s\n' "$ping_out" | sed 's/\x1b\[[0-9;]*m//g')   # colour codes
  bad=""
  printf '%s\n' "$ping_out" | grep -q 'Step 1.*FAIL' && bad="step 1 (the gateway's health check)"
  printf '%s\n' "$ping_out" | grep -q 'Step 2.*FAIL' && bad="${bad:+$bad and }step 2 (the agent's reply)"
  if [ -n "$bad" ]; then fail "ping failed at $bad." "$ping_out"
  else fail "ping stopped before reporting a step (exit $rc)." "$ping_out"; fi
fi
echo "EASEL READY: web workspace on localhost:7860, gateway up, ping passed both steps."
