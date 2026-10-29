#!/usr/bin/env bash
# Rebuilds, on a fresh or rebuilt WSL Ubuntu, the machine setup that was done by hand on 2026-10-12
# so that Easel works again without repeating the audit. Safe to run twice: each step checks first and
# says "already done", or does its work; then the step's own check prints PASS or FAIL.
#
#   bash ops/wsl-setup/setup.sh               run every step
#   bash ops/wsl-setup/setup.sh --only a,b    run only these steps
#   bash ops/wsl-setup/setup.sh --list        print the step names
#
# Run it as the user the Easel gateway runs as (root here), AFTER Easel's own installer (setup.sh at the
# repo root) has run: it needs Easel's .venv and its OpenClaw profile. It changes none of Easel's tracked
# files. No API key, account or paid service is involved; Hugging Face is only anonymous file downloads.
# The libtv step installs LibTV's program only; the owner's login to it (a browser approval) is not done here.
#
# Exit status: 0 when every check passed, 1 when any failed, 2 when a precondition is missing.
# Settings and the two pins live in checks.sh.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=checks.sh
. "$HERE/checks.sh"

# Where do_libtv downloads LibTV's program package from: a versioned address, so the file there does not change
# under the pin. The two sha256 pins that decide what is accepted are in checks.sh.
LIBTV_URL=https://liblibai-web-static.liblib.cloud/cli/1.1.3/libtv-linux-x64.zip

# What do_python_packages installs when py_small_ok (checks.sh) fails, and where do_noise_model downloads the RNNoise model from.
PY_SMALL_PKGS="openpyxl pdfplumber PyMuPDF zhconv beautifulsoup4 pytest"
RNNN_URL=https://github.com/GregorR/rnnoise-models/raw/master/somnolent-hogwash-2018-09-01/sh.rnnn

# Where do_display_font downloads the display font from: a versioned release address, so the file there does not change
# under the pin (the sha256 pin, licence and release note are in checks.sh).
DISPLAY_FONT_URL=https://github.com/lxgw/LxgwWenKai/releases/download/v1.530/LXGWWenKai-Medium.ttf

STEPS="node system-packages display-font python-packages speech-models noise-model rembg-models search-deny redbook libtv remotion codex no-keys"
SUDO=${SETUP_SUDO-$([ "$(id -u)" = 0 ] || echo sudo)}
as_root() { if [ -n "$SUDO" ]; then $SUDO env "PATH=$PATH" "$@"; else "$@"; fi; }

# --- preconditions: refuse, and list everything that is missing, before changing anything ---------
preflight() {
  local miss=""
  [ "$(uname -s)" = Linux ] || miss="$miss\n  - this is not Linux; run it inside WSL"
  [ -x "$PY" ] && "$PY" -c 'import easel' 2>/dev/null \
    || miss="$miss\n  - Easel's Python environment is missing or has no easel in it ($VENV); run Easel's own installer first"
  [ -f "$OC_CONFIG" ] || miss="$miss\n  - Easel's OpenClaw profile is missing ($OC_CONFIG); run Easel's own installer first"
  command -v git >/dev/null 2>&1 || miss="$miss\n  - git is not installed"
  if [ -n "$miss" ]; then
    printf 'Cannot start. Missing:%b\n' "$miss"
    return 1
  fi
}

# --- steps ----------------------------------------------------------------------------------------
have_node() { linux_node_ok; }
do_node() {
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash || return 1
  fi
  load_nvm
  nvm install 24 && nvm alias default 24 >/dev/null && nvm use 24 >/dev/null
  load_nvm
}

have_system_packages() {
  local p
  for p in $APT_PKGS; do pkg_installed "$p" || return 1; done
}
do_system_packages() {
  local p miss=""
  for p in $APT_PKGS; do pkg_installed "$p" || miss="$miss $p"; done
  as_root apt-get update -qq || return 1
  # shellcheck disable=SC2086  # $miss is a list of package names
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y $miss || return 1
  as_root fc-cache -f
}

# display_font_install: one file, downloaded fresh, checked, then placed in its own folder. Nothing is installed on a
# different sha256, and no other font or package is touched.
display_font_install() {
  local tmp got
  tmp=$(mktemp -d) || return 1
  # a fresh download, never resumed: a half-finished file must not be mistaken for the font
  curl -fL --retry 3 -o "$tmp/font" "$DISPLAY_FONT_URL" || { echo "the download of the display font failed"; rm -rf "$tmp"; return 1; }
  got=$(file_sha256 "$tmp/font")
  if [ "$got" != "$DISPLAY_FONT_SHA256" ]; then
    echo "refused: the display font's sha256 is ${got:-unreadable}, not the pinned $DISPLAY_FONT_SHA256."
    echo "The download address is versioned (v1.530), so this is a changed file or a wrong local copy. Nothing was installed."
    rm -rf "$tmp"; return 1
  fi
  as_root mkdir -p "$DISPLAY_FONT_DIR" && as_root install -m 644 "$tmp/font" "$DISPLAY_FONT_DIR/$DISPLAY_FONT_FILE"
  local rc=$?
  rm -rf "$tmp"
  return $rc
}

have_display_font() { display_font_ok && display_font_listed; }
do_display_font() {
  display_font_ok || display_font_install || return 1
  # only the font's own folder is scanned: no other font's cache entry is rebuilt
  as_root fc-cache -f "$DISPLAY_FONT_DIR"
}

PIP() { "$PY" -m pip "$@"; }
have_python_packages() { py_small_ok && [ "$(torch_state)" = cpu ] && whisper_ok && ocr_ok && av_ok; }
do_python_packages() {
  # order matters: PyTorch before openai-whisper (or pip pulls the multi-GB CUDA build), PyAV pin last
  # (anything installed before it can move PyAV)
  # shellcheck disable=SC2086  # a list of package names
  py_small_ok || PIP install $PY_SMALL_PKGS || return 1
  case "$(torch_state)" in
    none) PIP install torch --index-url https://download.pytorch.org/whl/cpu || return 1 ;;
    cuda) echo "a CUDA build of torch is installed; remove torch and the nvidia-* packages, then rerun"; return 1 ;;
  esac
  whisper_ok || PIP install openai-whisper || return 1
  # the free local text-in-image engine (issue 70); it runs on the onnxruntime and opencv already in the venv
  ocr_ok || PIP install "rapidocr-onnxruntime==$OCR_PIN" || return 1
  av_ok || PIP install "av==$AV_PIN"
}

# fetch URL DEST: a plain anonymous download. It resumes, and a half-finished file never has the final name.
fetch() {
  mkdir -p "$(dirname "$2")" && curl -fL --retry 3 -C - -o "$2.part" "$1" && mv "$2.part" "$2"
}

have_speech_models() {
  local s f
  for s in $SPEECH_SIZES; do for f in $(speech_files "$s"); do speech_file_ok "$s" "$f" || return 1; done; done
}
do_speech_models() {
  local s f d
  for s in $SPEECH_SIZES; do
    d=$MODEL_DIR/faster-whisper-$s
    for f in $(speech_files "$s"); do
      speech_file_ok "$s" "$f" && continue
      rm -f "$d/$f" "$d/$f.part"     # a cut-off file is fetched again from the start
      fetch "https://huggingface.co/Systran/faster-whisper-$s/resolve/main/$f" "$d/$f" || return 1
    done
  done
}

have_noise_model() { rnnn_file_ok && rnnn_excluded; }
do_noise_model() {
  local x
  if ! rnnn_file_ok; then
    rm -f "$RNNN_FILE" "$RNNN_FILE.part"
    fetch "$RNNN_URL" "$RNNN_FILE" || return 1
  fi
  if ! rnnn_excluded; then
    # the local exclude list (not Easel's .gitignore) is how our untracked downloads stay out of git
    x=$(exclude_file) || { echo "$ROOT is not a git checkout"; return 1; }
    mkdir -p "$(dirname "$x")"
    printf '\n# Easel model downloads (issue 26)\n%s\n' "$RNNN_EXCLUDE" >> "$x"
  fi
}

have_rembg_models() {
  local m
  for m in $REMBG_MODELS; do rembg_model_ok "$m" || return 1; done
}
do_rembg_models() {
  local m
  for m in $REMBG_MODELS; do
    rembg_model_ok "$m" && continue
    # rembg's own download: it checks the file as it goes, and puts it where rembg will look
    "$PY" -c 'import sys; from rembg import new_session; new_session(sys.argv[1])' "$m" || {
      echo "rembg could not fetch $m (is rembg installed in $VENV? Easel's installer installs it)"; return 1; }
  done
}

need_linux_node() {
  linux_node_ok && return 0
  echo "Linux Node 24 or newer is required first (step: node); found: $(command -v node || echo none)"
  return 1
}

have_redbook() { redbook_prog_ok && redbook_stub_ok; }
do_redbook() {
  need_linux_node || return 1
  if ! redbook_prog_ok; then
    # --ignore-scripts: the program's own install script would link it into Claude Code's skills folder
    as_root mkdir -p "$REDBOOK_DIR" || return 1
    ( cd "$REDBOOK_DIR" && as_root npm install --ignore-scripts --no-audit --no-fund "@lucasygu/redbook@$REDBOOK_PIN" ) || return 1
  fi
  if ! redbook_stub_ok; then
    as_root mkdir -p "$(dirname "$REDBOOK_BIN")" || return 1
    redbook_stub_text | as_root tee "$REDBOOK_BIN" >/dev/null || return 1
    as_root chmod 755 "$REDBOOK_BIN"
  fi
}

# libtv_refuse WHAT GOT PINNED LASTMODIFIED: nothing is installed when a sha256 is not the pinned one
libtv_refuse() {
  echo "refused: the $1's sha256 is ${2:-unreadable}, not the pinned $3."
  echo "The download address is versioned (cli/1.1.3/), so this is a changed file or a wrong local copy. Last-Modified received: ${4:-none (local file or no header)}. Nothing was installed."
}
# libtv_install_program: LibTV's package, checked, then the one program inside it, checked, then placed on the gateway's path.
# No unzip on this machine, and none needed: python reads the one member by its exact name. Nothing LibTV ships is run.
libtv_install_program() {
  local tmp src hdr got lm rc
  tmp=$(mktemp -d) || return 1
  if [ -n "$LIBTV_ZIP_FILE" ]; then
    [ -f "$LIBTV_ZIP_FILE" ] || { echo "LIBTV_ZIP_FILE is not a file: $LIBTV_ZIP_FILE"; rm -rf "$tmp"; return 1; }
    src=$LIBTV_ZIP_FILE; hdr=/dev/null
  else
    src=$tmp/libtv.zip; hdr=$tmp/headers
    # a fresh download, never resumed: a half-finished file must not be mistaken for the package
    curl -fL --retry 3 -D "$hdr" -o "$src" "$LIBTV_URL" || { echo "the download of the libtv package failed"; rm -rf "$tmp"; return 1; }
  fi
  got=$(file_sha256 "$src")
  if [ "$got" != "$LIBTV_ZIP_SHA256" ]; then
    lm=$(sed -n 's/^[Ll]ast-[Mm]odified: *//p' "$hdr" 2>/dev/null | tr -d '\r' | tail -1)
    libtv_refuse package "$got" "$LIBTV_ZIP_SHA256" "$lm"
    rm -rf "$tmp"; return 1
  fi
  python3 - "$src" "$tmp/libtv" <<'PY' || { echo "the package holds no libtv-linux-x64/libtv program. Nothing was installed."; rm -rf "$tmp"; return 1; }
import sys, zipfile
try:
    with zipfile.ZipFile(sys.argv[1]) as z:
        data = z.read("libtv-linux-x64/libtv")
except (KeyError, zipfile.BadZipFile):
    sys.exit(1)
with open(sys.argv[2], "wb") as f:
    f.write(data)
PY
  got=$(file_sha256 "$tmp/libtv")
  if [ "$got" != "$LIBTV_SHA256" ]; then
    libtv_refuse program "$got" "$LIBTV_SHA256" ""
    rm -rf "$tmp"; return 1
  fi
  as_root mkdir -p "$(dirname "$LIBTV_BIN")" && as_root install -m 755 "$tmp/libtv" "$LIBTV_BIN"
  rc=$?
  rm -rf "$tmp"
  return $rc
}

have_libtv() { libtv_prog_ok && libtv_env_ok; }
do_libtv() {
  libtv_prog_ok || libtv_install_program || return 1
  if ! libtv_env_ok; then
    command -v openclaw >/dev/null 2>&1 || { echo "openclaw is not on PATH; run Easel's own installer first"; return 1; }
    # one key only: the rest of the config's env block (and everything else in it) stays as it is. OpenClaw
    # reloads its config after the write; that the agent's own shell then has the variable is shown by asking
    # the agent (printenv), not by reading the gateway process's start-up environment.
    openclaw --profile easel config set env.vars.LIBTV_DISABLE_REPORT '"1"' --strict-json || return 1
  fi
}

have_remotion() { remotion_ok; }
do_remotion() {
  need_linux_node || return 1
  # the SDK's installer skips when node_modules exists, broken or not (a run under Windows Node leaves
  # Windows binaries behind), so a broken one is cleared first. It is a derived folder, rebuilt from the lock file.
  if [ -d "$REMOTION_DIR/node_modules" ] && ! remotion_ok; then rm -rf "${REMOTION_DIR:?}/node_modules"; fi
  bash "$SDK_DIR/deps/bootstrap.sh"
  remotion_ok   # the installer exits 0 whatever happened; only the result says
}

have_codex() { linux_codex_ok; }
do_codex() {
  need_linux_node || return 1
  npm install -g @openai/codex
}

# a check with nothing to install: it only looks
have_no_keys() { return 0; }
do_no_keys() { return 0; }

have_search_deny() {
  python3 -c 'import json,sys; sys.exit(0 if "web_search" in ((json.load(open(sys.argv[1])).get("tools") or {}).get("deny") or []) else 1)' "$OC_CONFIG" 2>/dev/null
}
do_search_deny() {
  command -v openclaw >/dev/null 2>&1 || { echo "openclaw is not on PATH; run Easel's own installer first"; return 1; }
  local merged
  # add to the list, never replace it: other denied tools must survive a rerun
  merged=$(python3 - "$OC_CONFIG" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
d = list((c.get("tools") or {}).get("deny") or [])
if "web_search" not in d:
    d.append("web_search")
print(json.dumps(d))
PY
) || return 1
  openclaw --profile easel config set tools.deny "$merged" --strict-json
}

# --- runner ---------------------------------------------------------------------------------------
only=""
while [ $# -gt 0 ]; do
  case $1 in
    --only) only=${2:-}; shift ;;
    --list) echo "$STEPS" | tr ' ' '\n'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
selected=$STEPS
[ -n "$only" ] && selected=${only//,/ }
for s in $selected; do
  case " $STEPS " in *" $s "*) ;; *) echo "unknown step: $s (steps: $STEPS)" >&2; exit 2 ;; esac
done

preflight || exit 2
for s in $selected; do
  fn=${s//-/_}
  printf '== %s ==\n' "$s"
  if "have_$fn"; then
    echo "already done: $s"
  else
    echo "doing: $s"
    "do_$fn" || echo "step failed: $s"
  fi
  "check_$fn"
done
echo
if [ "$CHECK_FAILED" = 0 ]; then echo "ALL PASS"; else echo "SOME CHECKS FAILED"; fi
exit "$CHECK_FAILED"
