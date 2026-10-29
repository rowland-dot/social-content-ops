#!/usr/bin/env bash
# Per-step checks for the WSL machine setup (see setup.sh). Each check prints lines that start with
# PASS, FAIL, SKIP or NOTE and the step name. A FAIL sets CHECK_FAILED=1.
#
# Standalone:  bash ops/wsl-setup/checks.sh [step ...]     (no step = all). Exit 1 if any check failed.
# Sourced by setup.sh, which runs a step's check right after the step.
#
# Settings (environment, all optional; the defaults are the real machine):
#   EASEL_VENV, EASEL_MODEL_DIR, REMBG_HOME, OPENCLAW_CONFIG, REDBOOK_DIR, REDBOOK_BIN, EASEL_FONT_DIR, NVM_DIR
#   LIBTV_BIN, LIBTV_ZIP_FILE (a local copy of LibTV's program package to install instead of downloading it),
#   LIBTV_GATEWAY_PATH, LIBTV_ZIP_SHA256 and LIBTV_SHA256 (the tests give them their stand-ins'; never set them
#   on the real machine)
#   EASEL_DISPLAY_FONT_DIR (where the display font is installed) and DISPLAY_FONT_SHA256 (the tests give it a
#   stand-in's; never set it on the real machine)
#   SETUP_CALL_CHECKS=0   skip the slow checks that drive the real programs (the tests use this; it prints SKIP)

CHK_HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$CHK_HERE/../.." && pwd)
VENV=${EASEL_VENV:-$ROOT/.venv}
PY=$VENV/bin/python
MODEL_DIR=${EASEL_MODEL_DIR:-$HOME/.cache/easel-models}
export REMBG_HOME=${REMBG_HOME:-$HOME/.rembg}
OC_CONFIG=${OPENCLAW_CONFIG:-$HOME/.openclaw-easel/openclaw.json}
REDBOOK_DIR=${REDBOOK_DIR:-/opt/redbook}
REDBOOK_BIN=${REDBOOK_BIN:-/usr/local/bin/redbook}
FONT_DIR=${EASEL_FONT_DIR:-/usr/share/fonts/opentype/noto}
CALL_CHECKS=${SETUP_CALL_CHECKS:-1}

# The only two pins, both from measured breaks (the rest takes the current release):
AV_PIN=17.1.0        # PyAV 19 refuses an argument faster-whisper 1.2.1 always passes (issue 07)
OCR_PIN=1.2.3        # the text-in-image engine skill-xhs-note-reader uses (issue 70): the release read and run on Easel's Python 3.14 on 2026-10-23
REDBOOK_PIN=0.8.2    # the version the read-only guard was tested against (issue 04)
# LibTV's closed CLI (issue 32) is pinned by the sha256 of the package it is downloaded in and again by the sha256
# of the one program inside it (77,667,686 bytes), both read and tested as release 1.1.3 on 2026-10-14. The
# address is versioned (cli/1.1.3/), so a different sha256 means the file there changed or the copy is wrong:
# it is refused, never accepted as "newer".
LIBTV_ZIP_SHA256=${LIBTV_ZIP_SHA256:-cf86f462c5aed60f95dca978cc91ece98c60bcfa27337da008ad59953c3ea7da}
LIBTV_SHA256=${LIBTV_SHA256:-e79ad52170556b44e957174f880c8a69057f668ddd0b9a4011524cac072c31f3}
# (the download address is in setup.sh, the only script that downloads it; ShellCheck lints each file alone)

export NVM_DIR=${NVM_DIR:-$HOME/.nvm}
WIN_MOUNT=${EASEL_WIN_MOUNT:-/mnt/}   # where WSL mounts the Windows drives; a Node found there is Windows Node

# nvm is only loaded by interactive shells, so load it here: this is what the OpenClaw gateway sees too
load_nvm() {
  [ -s "$NVM_DIR/nvm.sh" ] || return 0
  local restore=0
  case $- in *u*) restore=1; set +u ;; esac
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
  [ "$restore" = 1 ] && set -u
  return 0
}
load_nvm

CHECK_FAILED=0
STEP=setup
say() { printf '%s %s\n' "$1" "$2"; [ "$1" = FAIL ] && CHECK_FAILED=1; return 0; }
pass() { say PASS "$STEP: $1"; }
fail() { say FAIL "$STEP: $1"; }
note() { say NOTE "$STEP: $1"; }
# The engine saved in outputs/_harness/config.json (EASEL_AGENT_RUNTIME wins, as in easel/harnesses/store.py).
# None saved means OpenClaw, as before. Only the OpenClaw engine needs Easel's OpenClaw profile.
easel_engine() {
  local e=${EASEL_AGENT_RUNTIME:-}
  [ -n "$e" ] || e=$(sed -n 's/.*"runtime"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$ROOT/outputs/_harness/config.json" 2>/dev/null | head -1)
  printf '%s' "${e:-openclaw}" | tr 'A-Z' 'a-z' | tr -d ' '
}
openclaw_engine() { [ "$(easel_engine)" = openclaw ]; }
# an OpenClaw-only part left out of this run; setup.sh names SKIPPED in its closing line
SKIPPED=""
skip_openclaw() { say SKIP "$STEP: $1 skipped, OpenClaw is not the engine (engine: $(easel_engine))"; SKIPPED="$SKIPPED $STEP"; }
# slow checks drive the real programs; off only for the tests, and never silently
call_checks_on() {
  [ "$CALL_CHECKS" = 1 ] && return 0
  say SKIP "$STEP: slow check not run (SETUP_CALL_CHECKS=0)"; return 1
}

# Node, npm and npx must all be Linux programs, Node 24 or newer (OpenClaw needs 24.16+ on the 24 line).
# In WSL a missing Linux Node is silently replaced by the Windows one through interop, which installs
# Windows binaries on a Windows-mounted folder.
linux_node_ok() {
  local t p v
  for t in node npm npx; do
    p=$(command -v "$t" 2>/dev/null) || return 1
    case $p in "$WIN_MOUNT"*) return 1 ;; esac
  done
  v=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')
  [ -n "$v" ] && [ "$v" -ge 24 ] 2>/dev/null
}
check_node() {
  STEP=node
  if linux_node_ok; then pass "node, npm and npx are Linux programs ($(node -v), $(command -v node))"
  else fail "node, npm and npx are not all Linux programs at Node 24 or newer (node is: $(command -v node || echo none))"; fi
}

py_small_ok() { "$PY" -c 'import openpyxl, pdfplumber, fitz, zhconv, bs4, pytest' >/dev/null 2>&1; }
# none | cpu | cuda
torch_state() { "$PY" -c 'import torch; print("cpu" if torch.version.cuda is None else "cuda")' 2>/dev/null || echo none; }
whisper_ok() { "$PY" -c 'import whisper' >/dev/null 2>&1 && [ -x "$VENV/bin/whisper" ]; }
av_ok() { [ "$("$PY" -c 'import av; print(av.__version__)' 2>/dev/null)" = "$AV_PIN" ]; }
# the engine has no __version__, so the version is read from the package list (pip freeze: name==version)
ocr_ok() {
  "$PY" -c 'import rapidocr_onnxruntime' >/dev/null 2>&1 \
    && "$PY" -m pip list --format=freeze 2>/dev/null | grep -Eiq "^rapidocr[-_]onnxruntime(==| )$OCR_PIN\$"
}

check_python_packages() {
  STEP=python-packages
  local t tmp r
  if py_small_ok; then pass "openpyxl, pdfplumber, PyMuPDF (fitz), zhconv, beautifulsoup4 (bs4) and pytest import in the venv"
  else fail "one of openpyxl, pdfplumber, fitz, zhconv, bs4, pytest does not import in $VENV"; fi
  t=$(torch_state)
  case $t in
    cpu) pass "torch is the CPU build (no CUDA)" ;;
    cuda) fail "torch is a CUDA build; remove torch and the nvidia-* packages, then rerun" ;;
    *) fail "torch does not import" ;;
  esac
  if "$PY" -m pip list --format=freeze 2>/dev/null | grep -qi '^nvidia-'; then fail "nvidia-* packages are installed (the CUDA stack came in with torch)"
  else pass "no nvidia-* packages are installed"; fi
  if whisper_ok && "$VENV/bin/whisper" --help >/dev/null 2>&1; then pass "the whisper command runs from the venv"
  else fail "whisper does not import, or the whisper command is missing or fails in $VENV/bin"; fi
  if av_ok; then pass "PyAV is $AV_PIN (newer releases break faster-whisper 1.2.1)"
  else fail "PyAV is not $AV_PIN (is: $("$PY" -c 'import av; print(av.__version__)' 2>/dev/null || echo missing))"; fi
  if ocr_ok; then pass "the text-in-image engine rapidocr-onnxruntime $OCR_PIN imports in the venv"
  else fail "rapidocr-onnxruntime $OCR_PIN is not installed in $VENV"; fi
  call_checks_on || return 0
  # the engine on a real picture: render two Chinese words with the CJK font and read them back
  r=$("$PY" - "$FONT_DIR" <<'EOF' 2>&1 | tail -1
import glob, sys
from PIL import Image, ImageDraw, ImageFont
from rapidocr_onnxruntime import RapidOCR
font = (glob.glob(sys.argv[1] + "/NotoSansCJK-Regular*") or glob.glob("/usr/share/fonts/**/*CJK*Regular*", recursive=True))[0]
im = Image.new("RGB", (600, 160), "white")
ImageDraw.Draw(im).text((20, 30), "底妆教程", font=ImageFont.truetype(font, 64), fill="black")
im.save("/tmp/setup-ocr-check.png")
found, _ = RapidOCR()("/tmp/setup-ocr-check.png")
print("".join(item[1] for item in found or []))
EOF
)
  rm -f /tmp/setup-ocr-check.png
  if [ "$r" = 底妆教程 ]; then pass "the text-in-image engine reads Chinese text from a real picture"
  else fail "the text-in-image engine did not read a rendered picture: $r"; fi
  # the exact call that PyAV 19 broke: faster-whisper decoding a real audio file
  tmp=$(mktemp -d)
  ffmpeg -y -loglevel error -f lavfi -i sine=frequency=440:duration=1 "$tmp/tone.wav" 2>/dev/null
  r=$("$PY" -c 'import sys; from faster_whisper.audio import decode_audio; print(len(decode_audio(sys.argv[1])))' "$tmp/tone.wav" 2>&1 | tail -1)
  rm -rf "$tmp"
  if [ "${r:-0}" -gt 1000 ] 2>/dev/null; then pass "faster-whisper decodes a real audio clip ($r samples)"
  else fail "faster-whisper could not decode a real audio clip: $r"; fi
}

# --- speech models: the shared speech script loads a model with no network only from this folder ----
SPEECH_SIZES="base small large-v3"
speech_files() {
  case $1 in
    large-v3) echo "config.json model.bin preprocessor_config.json tokenizer.json vocabulary.json" ;;
    *) echo "config.json model.bin tokenizer.json vocabulary.txt" ;;
  esac
}
speech_min_bin() { case $1 in base) echo 100000000 ;; small) echo 400000000 ;; *) echo 2500000000 ;; esac; }  # real: 145 MB, 484 MB, 3.1 GB
# speech_file_ok SIZE FILE: present, non-empty, and a model.bin not cut off
speech_file_ok() {
  local f=$MODEL_DIR/faster-whisper-$1/$2 sz
  [ -s "$f" ] || return 1
  [ "$2" = model.bin ] || return 0
  sz=$(stat -c %s "$f"); [ "$sz" -ge "$(speech_min_bin "$1")" ]
}

check_speech_models() {
  STEP=speech-models
  local s f miss tmp clip log out n
  for s in $SPEECH_SIZES; do
    miss=""
    for f in $(speech_files "$s"); do speech_file_ok "$s" "$f" || miss="$miss $f"; done
    if [ -z "$miss" ]; then pass "$s: all files are in $MODEL_DIR/faster-whisper-$s ($(stat -c %s "$MODEL_DIR/faster-whisper-$s/model.bin") bytes of model)"
    else fail "$s: missing or cut off:$miss"; fi
  done
  call_checks_on || return 0
  # real consumer calls on a 12 second Chinese clip that ships with Easel, with the hub switched off
  tmp=$(mktemp -d); clip=$tmp/clip-zh.mp4
  ffmpeg -y -loglevel error -ss 2 -t 12 -i "$ROOT/assets/readme/videos/full/jilong-news.mp4" -c copy "$clip" 2>/dev/null
  [ -s "$clip" ] || { fail "the 12 second test clip could not be made, so transcription was not checked"; rm -rf "$tmp"; return 0; }
  for s in $SPEECH_SIZES; do
    out=$tmp/$s.srt
    log=$(HF_HUB_OFFLINE=1 "$PY" "$ROOT/skills/shared/scripts/asr.py" transcribe -i "$clip" -o "$out" --language zh --model "$s" 2>&1)
    n=$([ -s "$out" ] && "$PY" -c 'import re,sys; print(len(re.findall(r"[一-鿿]", open(sys.argv[1], encoding="utf-8").read())))' "$out" || echo 0)
    if [ -s "$out" ] && grep -q -- '-->' "$out" && [ "$n" -ge 5 ] && printf '%s' "$log" | grep -q '使用本地缓存模型'; then
      pass "$s: offline transcription gave an SRT with $n Chinese characters, and the log says it used the local model"
    else fail "$s: offline transcription failed (srt: $([ -s "$out" ] && echo yes || echo no), Chinese characters: $n) $(printf '%s' "$log" | tail -2 | tr '\n' ' ')"; fi
  done
  out=$tmp/noproxy.srt
  https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 "$PY" "$ROOT/skills/shared/scripts/asr.py" transcribe -i "$clip" -o "$out" --language zh --model base >/dev/null 2>&1
  if [ -s "$out" ] && grep -q -- '-->' "$out"; then pass "transcription works with a dead proxy and no offline flag, so nothing uses the network"
  else fail "transcription needs the network"; fi
  out=$tmp/dub.json
  HF_HUB_OFFLINE=1 "$PY" "$ROOT/skills/shared/scripts/asr.py" transcribe -i "$clip" --model base --format json -o "$out" >/dev/null 2>&1
  n=$([ -s "$out" ] && "$PY" -c 'import json,sys; print(len(json.load(open(sys.argv[1], encoding="utf-8")).get("segments", [])))' "$out" || echo 0)
  if [ "$n" -ge 1 ]; then pass "the dubbing checks' call (--model base --format json) returns $n segments"
  else fail "the dubbing checks' call (--model base --format json) returned no segments"; fi
  rm -rf "$tmp"
}

# --- RNNoise model for the shared audio script's strongest noise reduction (level 3) -----------------
RNNN_SIZE=297646
RNNN_FILE=$ROOT/skills/shared/scripts/models/sh.rnnn
RNNN_EXCLUDE=skills/shared/scripts/models/
exclude_file() {
  local p
  p=$(git -C "$ROOT" rev-parse --git-path info/exclude 2>/dev/null) || return 1
  case $p in /*) echo "$p" ;; *) echo "$ROOT/$p" ;; esac
}
rnnn_file_ok() { [ -f "$RNNN_FILE" ] && [ "$(stat -c %s "$RNNN_FILE")" = "$RNNN_SIZE" ]; }
rnnn_excluded() { local x; x=$(exclude_file) && [ -f "$x" ] && grep -qxF "$RNNN_EXCLUDE" "$x"; }

check_noise_model() {
  STEP=noise-model
  local tmp out
  if rnnn_file_ok; then pass "sh.rnnn ($RNNN_SIZE bytes) is beside the shared audio script"
  else fail "sh.rnnn is missing or the wrong size at $RNNN_FILE"; fi
  if rnnn_excluded; then pass "the models folder is in the local git exclude list"
  else fail "the models folder is not in the local git exclude list"; fi
  if [ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all -- skills/shared/scripts/models 2>/dev/null)" ]; then pass "git does not list the model as a new file"
  else fail "git lists the models folder as new files"; fi
  call_checks_on || return 0
  # the audio script's self-test never runs noise reduction, and without the model level 3 quietly runs
  # level 2 and still exits 0 -- so run level 3 with no model path and read what it says it did
  tmp=$(mktemp -d)
  ffmpeg -y -loglevel error -f lavfi -i 'sine=frequency=440:duration=3' -f lavfi -i 'anoisesrc=d=3:a=0.05' \
    -filter_complex 'amix=inputs=2:duration=first' "$tmp/noisy.wav" 2>/dev/null
  out=$("$PY" "$ROOT/skills/shared/scripts/audio_ops.py" denoise "$tmp/noisy.wav" -o "$tmp/clean.wav" --tier 3 2>&1)
  if printf '%s' "$out" | grep -q 'arnndn' && ! printf '%s' "$out" | grep -q 'WARN' && [ -s "$tmp/clean.wav" ]; then
    pass "level 3 noise reduction ran the neural filter (arnndn) with no fallback warning"
  else fail "level 3 noise reduction did not use the model: $(printf '%s' "$out" | head -3 | tr '\n' ' ')"; fi
  rm -rf "$tmp"
}

# --- background-removal models (rembg's own folder; the script's self-test uses u2netp, remove uses u2net) ---
REMBG_MODELS="u2net u2netp"
rembg_model_ok() { [ -s "$REMBG_HOME/models/$1/$1.onnx" ]; }

check_rembg_models() {
  STEP=rembg-models
  local m miss="" tmp src
  for m in $REMBG_MODELS; do rembg_model_ok "$m" || miss="$miss $m"; done
  if [ -z "$miss" ]; then pass "$REMBG_MODELS are in $REMBG_HOME/models"; else fail "missing from $REMBG_HOME/models:$miss"; fi
  call_checks_on || return 0
  # the script's own `check` never looks for a model and its self-test uses the small one, so run the
  # default model on a test image with the network cut: it must load from disk
  tmp=$(mktemp -d); src=$tmp/src.png
  "$PY" -c 'import sys; from PIL import Image, ImageDraw; im = Image.new("RGB", (256, 256), "white"); ImageDraw.Draw(im).ellipse((64, 64, 192, 192), fill=(220, 30, 30)); im.save(sys.argv[1])' "$src"
  if https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 \
       "$PY" "$ROOT/skills/shared/scripts/remove_bg.py" remove -i "$src" -o "$tmp/cut.png" >/dev/null 2>&1 \
     && "$PY" -c 'import sys; from PIL import Image; sys.exit(0 if Image.open(sys.argv[1]).convert("RGBA").getchannel("A").getextrema()[0] < 250 else 1)' "$tmp/cut.png"; then
    pass "the default model removes a background (transparent pixels) with the network cut"
  else fail "background removal with the default model failed with the network cut"; fi
  if https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 \
       "$PY" "$ROOT/skills/shared/scripts/remove_bg.py" selftest >/dev/null 2>&1; then pass "the background-removal self-test passes with the network cut"
  else fail "the background-removal self-test failed with the network cut"; fi
  rm -rf "$tmp"
}

# --- redbook (Xiaohongshu reader): the program in REDBOOK_DIR, only reachable through the guard stub ---
REDBOOK_GUARD=$ROOT/skills/builtin/skill-xhs-analyzer/scripts/redbook-guard.sh
redbook_stub_text() { printf '#!/usr/bin/env bash\nexec bash %s "$@"\n' "$REDBOOK_GUARD"; }
redbook_prog_ok() { [ "$("$REDBOOK_DIR/node_modules/.bin/redbook" --version 2>/dev/null)" = "$REDBOOK_PIN" ]; }
redbook_stub_ok() { [ -x "$REDBOOK_BIN" ] && [ "$(cat "$REDBOOK_BIN")" = "$(redbook_stub_text)" ]; }

check_redbook() {
  STEP=redbook
  local on_path out
  if redbook_prog_ok; then pass "redbook $REDBOOK_PIN is installed in $REDBOOK_DIR"
  else fail "redbook $REDBOOK_PIN is not installed in $REDBOOK_DIR (is: $("$REDBOOK_DIR/node_modules/.bin/redbook" --version 2>/dev/null || echo none))"; fi
  if redbook_stub_ok; then pass "$REDBOOK_BIN is the stub that runs the read-only guard"
  else fail "$REDBOOK_BIN is missing, not executable, or does not run the guard in this repo"; fi
  on_path=$(command -v redbook 2>/dev/null || true)
  if [ -n "$on_path" ] && [ "$on_path" != "$REDBOOK_BIN" ]; then fail "'redbook' on PATH is $on_path, not the guard"; fi
  # the program's own install script would link it into Claude Code's skills; a cookie file would be a login on disk
  if [ ! -e "$HOME/.claude/skills/redbook" ] && [ ! -L "$HOME/.claude/skills/redbook" ]; then pass "no redbook link in Claude Code's skills folder"
  else fail "there is a redbook link in Claude Code's skills folder"; fi
  if [ ! -e "$HOME/.redbook/cookies.json" ]; then pass "no cookie file on disk"
  else fail "there is a cookie file on disk ($HOME/.redbook/cookies.json); the login must only ever be held in memory"; fi
  if out=$(bash "$ROOT/skills/builtin/skill-xhs-analyzer/scripts/redbook-guard.test.sh" 2>&1); then pass "the guard's own tests pass"
  else fail "the guard's own tests fail: $(printf '%s' "$out" | grep '^FAIL' | head -3 | tr '\n' ' ')"; fi
  call_checks_on || return 0
  out=$(openclaw --profile easel skills info redbook 2>&1)
  if printf '%s' "$out" | grep -q 'Visible to model: yes' && ! printf '%s' "$out" | grep -q 'Needs setup'; then pass "OpenClaw lists the Xiaohongshu analyzer as ready and visible to the model"
  else fail "OpenClaw does not show the Xiaohongshu analyzer as ready (run Easel's agents/sync.sh, then start a new session)"; fi
}

# --- libtv (LibTV's closed CLI): one pinned program in /usr/local/bin, the report-off setting in the gateway's environment ---
# LibTV's own installer is never run: it takes whatever "latest" names, installs to ~/.libtv and appends a PATH line
# to a shell profile, none of which the gateway's PATH would see anyway. The login (credentials.json) is the owner's, by a
# browser approval; this script never does it.
LIBTV_BIN=${LIBTV_BIN:-/usr/local/bin/libtv}
LIBTV_ZIP_FILE=${LIBTV_ZIP_FILE:-}
LIBTV_GATEWAY_PATH=${LIBTV_GATEWAY_PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}   # what the running gateway process has, no profile involved
file_sha256() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
libtv_prog_ok() { [ -f "$LIBTV_BIN" ] && [ -x "$LIBTV_BIN" ] && [ "$(file_sha256 "$LIBTV_BIN")" = "$LIBTV_SHA256" ]; }
# the program reports every command (its command line with prompt text, exit code, error lines) to LibTV unless
# this is 1 in its environment; for calls made by the gateway's agent that environment is the OpenClaw config's env block
libtv_env_ok() {
  python3 -c 'import json,sys; sys.exit(0 if ((json.load(open(sys.argv[1])).get("env") or {}).get("vars") or {}).get("LIBTV_DISABLE_REPORT") == "1" else 1)' "$OC_CONFIG" 2>/dev/null
}

check_libtv() {
  STEP=libtv
  local got on_path bad="" f v
  if libtv_prog_ok; then pass "$LIBTV_BIN is the pinned program (sha256 ${LIBTV_SHA256:0:12}...)"
  else
    got=$(file_sha256 "$LIBTV_BIN")
    fail "$LIBTV_BIN is missing, not executable, or not the pinned program (its sha256: ${got:-none}; pinned: $LIBTV_SHA256)"
  fi
  on_path=$(env -i PATH="$LIBTV_GATEWAY_PATH" "$BASH" -c 'command -v libtv' 2>/dev/null || true)
  if [ "$on_path" = "$LIBTV_BIN" ]; then pass "the gateway's own PATH finds it at $on_path"
  else fail "the gateway's own PATH ($LIBTV_GATEWAY_PATH) does not find it at $LIBTV_BIN (finds: ${on_path:-nothing})"; fi
  for f in .bashrc .profile .bash_profile .bash_login .zshrc .zprofile; do
    [ -f "$HOME/$f" ] && grep -qi libtv "$HOME/$f" && bad="$bad ~/$f"
  done
  if [ -z "$bad" ]; then pass "no shell profile mentions libtv (LibTV's installer edits one)"
  else fail "a shell profile mentions libtv, so LibTV's own installer was run:$bad"; fi
  if [ ! -e "$HOME/.libtv/libtv" ]; then pass "no program in ~/.libtv (where LibTV's installer puts it)"
  else fail "there is a program at $HOME/.libtv/libtv, so LibTV's own installer was run"; fi
  if ! openclaw_engine; then skip_openclaw "the LIBTV_DISABLE_REPORT setting in the OpenClaw config"
  elif libtv_env_ok; then pass "the OpenClaw config sets LIBTV_DISABLE_REPORT=1 in the gateway's environment"
  else fail "the OpenClaw config does not set LIBTV_DISABLE_REPORT=1 in its env block ($OC_CONFIG), so the program would report every command to LibTV"; fi
  libtv_prog_ok || return 0
  call_checks_on || return 0
  # what the program says about itself is recorded, not pinned against; it runs with the report switched off and no input
  v=$(env LIBTV_DISABLE_REPORT=1 timeout 30 "$LIBTV_BIN" --version </dev/null 2>&1 | head -3 | tr '\n' ' ')
  if [ -n "$v" ]; then note "the program prints for --version: $v (the pinned release is 1.1.3; recorded, not a pin)"
  else fail "the program printed nothing for --version"; fi
}

# --- Remotion (video-production's renderer), installed by the SDK's own Linux installer --------------
VIDEO_SKILL=$ROOT/skills/builtin/video-production
SDK_DIR=$VIDEO_SKILL/vendor/video-pipeline-sdk
REMOTION_DIR=$SDK_DIR/deps/remotion
remotion_versions_ok() {
  local v nver npk
  v=$( cd "$REMOTION_DIR" 2>/dev/null && npx --no-install remotion versions 2>&1 )
  nver=$(printf '%s\n' "$v" | grep -c '^On version:')
  npk=$(printf '%s\n' "$v" | grep -cE '^- (@remotion/|remotion$)')
  [ "$npk" -ge 2 ] && [ "$nver" -eq 1 ] && printf '%s' "$v" | grep -q 'All packages have the correct version' \
    && ! printf '%s' "$v" | grep -qiE 'mismatch|wrong version|incorrect'
}
remotion_ok() {
  [ -d "$REMOTION_DIR/node_modules/@remotion/compositor-linux-x64-gnu" ] && remotion_versions_ok
}

check_remotion() {
  STEP=remotion
  local tmp out dur streams n W=1280 H=720 FPS=30 FRAMES=30
  if [ -d "$REMOTION_DIR/node_modules/@remotion/compositor-linux-x64-gnu" ]; then pass "the Linux x64 compositor is installed"
  else fail "the Linux x64 compositor (@remotion/compositor-linux-x64-gnu) is missing under $REMOTION_DIR/node_modules"; fi
  if remotion_versions_ok; then pass "remotion versions: the packages are at one version with no mismatch warning"
  else fail "remotion versions shows a mismatch, or no Remotion packages, or could not run"; fi
  call_checks_on || return 0
  # a one-scene composition rendered from a scratch folder outside the tracked tree
  tmp=$(mktemp -d); mkdir -p "$tmp/src"
  ln -s "$REMOTION_DIR/node_modules" "$tmp/node_modules"
  printf "import {registerRoot} from 'remotion';\nimport {Root} from './Root';\nregisterRoot(Root);\n" > "$tmp/src/index.ts"
  cat > "$tmp/src/Root.tsx" <<EOF
import React from 'react';
import {AbsoluteFill, Composition} from 'remotion';
const Scene: React.FC = () => (
  <AbsoluteFill style={{backgroundColor: '#1d3557', justifyContent: 'center', alignItems: 'center'}}>
    <div style={{color: 'white', fontSize: 72}}>render check</div>
  </AbsoluteFill>
);
export const Root: React.FC = () => (
  <Composition id="Check" component={Scene} durationInFrames={$FRAMES} fps={$FPS} width={$W} height={$H} />
);
EOF
  echo '{"compilerOptions":{"jsx":"react-jsx","module":"esnext","target":"es2020","moduleResolution":"bundler","strict":true,"skipLibCheck":true}}' > "$tmp/tsconfig.json"
  out=$tmp/render-check.mp4
  ( cd "$tmp" && npx --no-install remotion render src/index.ts Check "$out" >"$tmp/render.log" 2>&1 )
  if [ -s "$out" ]; then
    streams=$(ffprobe -v error -select_streams v -show_entries stream=codec_name,width,height -of csv=p=0 "$out" | sed 's/,$//' | tr '\n' ' ')
    n=$(ffprobe -v error -select_streams v -show_entries stream=index -of csv=p=0 "$out" | wc -l | tr -d ' ')
    dur=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 "$out" | sed 's/,$//')
    if [ "$streams" = "h264,$W,$H " ] && [ "$n" -eq 1 ] && awk -v d="$dur" -v n="$FRAMES" -v f="$FPS" 'BEGIN{x=d-n/f; if(x<0)x=-x; exit !(x<=1/f)}'; then
      pass "a one-scene composition renders to one H.264 stream at ${W}x${H}, ${dur}s long"
    else fail "the test render is wrong: streams='$streams' count=$n duration=$dur"; fi
  else fail "the test render produced no video: $(tail -3 "$tmp/render.log" | tr '\n' ' ')"; fi
  rm -rf "$tmp"
  if python3 "$VIDEO_SKILL/scripts/video_pipeline.py" doctor >/dev/null 2>&1; then pass "the skill's own setup check (video_pipeline.py doctor) exits 0"
  else fail "the skill's own setup check (video_pipeline.py doctor) fails"; fi
}

# --- Codex inside Linux (Easel's image and voice routes run on the owner's ChatGPT login through it) ------------
# The Windows copy of Codex is reachable from WSL but fails there, so one under the Windows mount does not count.
linux_codex_ok() {
  local p
  p=$(command -v codex 2>/dev/null) || return 1
  case $p in "$WIN_MOUNT"*) return 1 ;; esac
  codex --version >/dev/null 2>&1
}

check_codex() {
  STEP=codex
  if linux_codex_ok; then pass "Linux Codex runs ($(codex --version 2>&1 | head -1), $(command -v codex))"
  else fail "no working Linux Codex on PATH (found: $(command -v codex || echo none))"; return 0; fi
  # the login is a device approval on the ChatGPT page, which only the owner can give; this script never does it
  if codex login status >/dev/null 2>&1; then pass "Codex is logged in to ChatGPT"
  else note "Codex is not logged in to ChatGPT yet; that device login is the owner's one step and is not done by this script"; fi
}

# --- no Hugging Face login, token, cache or endpoint (anonymous file downloads only) -------------------
check_no_keys() {
  STEP=no-keys
  local bad="" f
  env | grep -qiE '^(HF_TOKEN|HUGGING_?FACE[A-Z_]*|HF_API[A-Z_]*|HF_ENDPOINT|EASEL_PROXY)=' && bad="$bad environment"
  for f in "$HOME/.cache/huggingface/token" "$HOME/.huggingface/token"; do [ -e "$f" ] && bad="$bad $f"; done
  [ -d "$HOME/.cache/huggingface" ] && bad="$bad $HOME/.cache/huggingface(hub cache; only plain file downloads are allowed)"
  for f in "$ROOT/.env" "$ROOT/.env.local"; do
    [ -f "$f" ] && grep -qiE 'hugging|^HF_|hf_[A-Za-z0-9]{20,}|api-inference|inference-endpoints' "$f" && bad="$bad $f"
  done
  if [ -z "$bad" ]; then pass "no Hugging Face token, account, endpoint or hub cache (.env, environment, home folder)"
  else fail "Hugging Face traces found:$bad"; fi
}

APT_PKGS="fonts-noto-cjk fonts-noto-cjk-extra fonts-noto-color-emoji poppler-utils"
pkg_installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'install ok installed'; }
# has_font FAMILY STYLE: is that weight in the system font list (the list the browser renderer reads)?
has_font() { fc-list :lang=zh family style 2>/dev/null | grep -Eq "^$1(,|:).*style=([^:]*,)?$2(,|\$)"; }

check_system_packages() {
  STEP=system-packages
  local p miss="" w f r
  for p in $APT_PKGS; do pkg_installed "$p" || miss="$miss $p"; done
  if [ -z "$miss" ]; then pass "installed: $APT_PKGS"; else fail "not installed:$miss"; fi
  miss=""
  # the card styles use sans Thin to Black and serif ExtraLight to Black; the base package has only Regular and Bold
  for w in Thin Light DemiLight Regular Medium Bold Black; do has_font "Noto Sans CJK SC" "$w" || miss="$miss sans-$w"; done
  for w in ExtraLight Light Regular Medium SemiBold Bold Black; do has_font "Noto Serif CJK SC" "$w" || miss="$miss serif-$w"; done
  has_font "Noto Sans Mono CJK SC" Regular || miss="$miss mono"
  fc-list 2>/dev/null | grep -q 'Noto Color Emoji' || miss="$miss emoji"
  if [ -z "$miss" ]; then pass "the font list has Noto Sans and Serif CJK SC in every weight the card styles use, the mono face and Noto Color Emoji"
  else fail "missing from the font list:$miss"; fi
  miss=""
  # about a dozen scripts open this fixed path instead of asking by name
  for f in NotoSansCJK-Regular.ttc NotoSansCJK-Bold.ttc; do [ -s "$FONT_DIR/$f" ] || miss="$miss $f"; done
  if [ -z "$miss" ]; then pass "the fixed font paths exist in $FONT_DIR"; else fail "missing in $FONT_DIR:$miss"; fi
  if command -v pdftotext >/dev/null 2>&1; then pass "the PDF reader (pdftotext) is on PATH"; else fail "pdftotext is not on PATH"; fi
  call_checks_on || return 0
  # Easel's own render self-test passes on empty boxes, so draw two different characters and compare:
  # a font that lacks them draws the same box for both.
  r=$("$PY" - "$FONT_DIR/NotoSansCJK-Regular.ttc" 2>&1 <<'PY'
import sys
from PIL import Image, ImageDraw, ImageFont
f = ImageFont.truetype(sys.argv[1], 64)
def draw(ch):
    im = Image.new("L", (96, 96), 0)
    ImageDraw.Draw(im).text((8, 8), ch, font=f, fill=255)
    return im.tobytes()
a, b, c = draw("字"), draw("中"), draw("\U0010FFFF")
print("real" if a != b and a != c and any(a) else "boxes")
PY
)
  if [ "$r" = real ]; then pass "Chinese characters draw as real, different glyphs (not empty boxes)"
  else fail "Chinese characters draw as empty boxes, or the drawing test could not run: $r"; fi
}

# --- display-font (issue 116): one free-licence Chinese display font beside the Noto fonts ----------------
# LXGW WenKai (霞鹜文楷) Medium, a regular-script face drawn from brush writing, so a typed A/B/C cover has a third
# letter form that is clearly neither Noto Serif nor Noto Sans. It is one file downloaded from the project's own
# GitHub release v1.530 (the address is in setup.sh, the only script that downloads it) and pinned by its sha256,
# read on 2026-10-28 from the downloaded file (25,800,076 bytes); GitHub's own digest for the asset is the same.
# Licence, checked 2026-10-28 in the project's OFL.txt at tag v1.530: SIL Open Font License 1.1, "Copyright 2021-2026
# LXGW (https://github.com/lxgw/LxgwWenKai)" with Reserved Font Names '霞鹜' and 'LXGW'. It allows commercial use,
# including text drawn into images; the reserved names matter only for a modified font, and this one is not modified.
# The address is versioned (v1.530), so a different sha256 means the file there changed or the copy is wrong: it is
# refused, never accepted as "newer". Installed system-wide because the gateway runs as root and the browser renderer
# reads the system font list; it gets a folder of its own, so no Noto file or apt-managed folder is written into.
DISPLAY_FONT_DIR=${EASEL_DISPLAY_FONT_DIR:-/usr/local/share/fonts/lxgw-wenkai}
DISPLAY_FONT_FILE=LXGWWenKai-Medium.ttf
DISPLAY_FONT_FAMILY="LXGW WenKai"
DISPLAY_FONT_SHA256=${DISPLAY_FONT_SHA256:-f4b8a34d1f838fe411540cb7c97b1c384ac9738a876c4104500bc42508b2312a}
display_font_ok() { [ -f "$DISPLAY_FONT_DIR/$DISPLAY_FONT_FILE" ] && [ "$(file_sha256 "$DISPLAY_FONT_DIR/$DISPLAY_FONT_FILE")" = "$DISPLAY_FONT_SHA256" ]; }
display_font_listed() { fc-list 2>/dev/null | grep -qF "$DISPLAY_FONT_FAMILY"; }

check_display_font() {
  STEP=display-font
  local got
  if display_font_ok; then pass "$DISPLAY_FONT_DIR/$DISPLAY_FONT_FILE is the pinned file (sha256 ${DISPLAY_FONT_SHA256:0:12}...)"
  else
    got=$(file_sha256 "$DISPLAY_FONT_DIR/$DISPLAY_FONT_FILE")
    fail "$DISPLAY_FONT_DIR/$DISPLAY_FONT_FILE is missing or not the pinned file (its sha256: ${got:-none}; pinned: $DISPLAY_FONT_SHA256)"
  fi
  if display_font_listed; then pass "the font list has the $DISPLAY_FONT_FAMILY family"
  else fail "the font list (fc-list) does not have the $DISPLAY_FONT_FAMILY family"; fi
}

check_search_deny() {
  STEP=search-deny
  openclaw_engine || { skip_openclaw "hiding web_search in the OpenClaw config"; return 0; }
  local verdict
  verdict=$(python3 - "$OC_CONFIG" <<'PY'
import json, sys
try:
    c = json.load(open(sys.argv[1]))
except Exception as e:
    print("FAIL cannot read the OpenClaw config: %s" % e); sys.exit(0)
t = c.get("tools") or {}
s = (t.get("web") or {}).get("search") or {}
bad = []
if "web_search" not in (t.get("deny") or []): bad.append("web_search is not in tools.deny")
if s.get("provider"): bad.append("a search provider is set: %r" % s["provider"])
if s.get("enabled") is False: bad.append("search.enabled is false, which turns Claude's own search off")
if any("key" in k.lower() for k in s): bad.append("there is an API key field in the search block")
print("FAIL " + "; ".join(bad) if bad else "PASS web_search is denied and Claude's own search is left on (no provider, not disabled, no key)")
PY
)
  say "${verdict%% *}" "$STEP: ${verdict#* }"
  call_checks_on || return 0
  # what the gateway actually hands the agent
  local ids n
  ids=$(openclaw --profile easel gateway call tools.effective --params '{"sessionKey":"agent:main:main"}' --json 2>&1 | python3 -c '
import sys, json
raw = sys.stdin.read()
try:
    o = json.loads(raw[raw.find("{"):])
except Exception:
    print(0); sys.exit(0)
ids = []
def walk(x):
    if isinstance(x, dict):
        if "id" in x and ("source" in x or "label" in x): ids.append(x["id"])
        for v in x.values(): walk(v)
    elif isinstance(x, list):
        for v in x: walk(v)
walk(o)
print(len(ids), " ".join(ids))
')
  n=${ids%% *}
  if [ -z "$n" ] || [ "$n" -lt 10 ]; then
    note "the gateway is not answering, so the tools it offers were not checked (start it and run checks.sh search-deny)"
  else
    case " $ids " in
      *" web_search "*) fail "the gateway still offers the managed web_search tool to the agent" ;;
      *) pass "the gateway does not offer web_search to the agent ($n tools listed)" ;;
    esac
  fi
}

# --- standalone ---------------------------------------------------------------------------------
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  steps=${*:-search-deny}
  for s in $steps; do "check_${s//-/_}"; done
  [ "$CHECK_FAILED" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
  exit "$CHECK_FAILED"
fi
