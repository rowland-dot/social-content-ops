#!/usr/bin/env bash
# Tests for ops/wsl-setup/setup.sh and checks.sh. Run in Linux or WSL:  bash ops/wsl-setup/setup.test.sh
#
# The outside world is replaced by stand-ins on a private PATH: apt, curl, npm, nvm, the venv's pip,
# openclaw, codex and the video SDK's own installer. Everything else is the real script, run on real
# files in a scratch folder. The slow checks that drive the real programs (transcription, a Remotion
# render, a noise-reduction run) are switched off here and run on the live machine instead.
# Exit status = number of failures.
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/wsl-setup-test-27.XXXXXX")
trap 'rm -rf "$T"' EXIT
FAILS=0
ok()  { echo "PASS  $1"; }
bad() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }
# expect NAME CONDITION...  (condition is a command; passes when it exits 0)
expect() { local n=$1; shift; if "$@"; then ok "$n"; else bad "$n"; fi; }
has()    { grep -q -- "$1" "$2"; }
# unimportable NAME...: take a stand-in package away so that importing it fails, whatever the host python has installed
# (deleting the stand-in file is not enough: the real package of that name may sit behind it, as on CI)
unimportable() { local m; for m in "$@"; do echo 'raise ImportError("removed by the test")' > "$W/site/$m.py"; done; }
hasF()   { grep -qF -- "$1" "$2"; }
lacks()  { ! grep -qF -- "$1" "$2"; }

mkshim() { cat > "$W/bin/$1"; chmod +x "$W/bin/$1"; }

# mklibtv TAG VERSION: the text of a stand-in for LibTV's closed program (it answers `--version`)
mklibtv() {
  printf '#!/usr/bin/env bash\n# %s\n' "$1"
  printf 'case "${1:-}" in --version) echo "libtv version %s (disable-report=${LIBTV_DISABLE_REPORT:-unset})";; esac\nexit 0\n' "$2"
}
# mkpkg ZIP MEMBER SOURCE: a zip like LibTV's program package, holding SOURCE under the name MEMBER
mkpkg() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys, zipfile
zip_path, member, source = sys.argv[1:4]
with zipfile.ZipFile(zip_path, "w") as z:
    z.writestr("libtv-linux-x64/", "")
    info = zipfile.ZipInfo(member)
    info.external_attr = 0o100755 << 16
    z.writestr(info, open(source, "rb").read())
PY
}

# world NAME  -> builds a fresh fake machine under $T/NAME and sets W
world() {
  W=$T/$1; mkdir -p "$W"/{bin,home,site,fonts,opt,local,nvm,tmp}
  : > "$W/calls.log"; : > "$W/dpkg.list"
  # private PATH: only the real tools the scripts need, so nothing on the host leaks in
  for t in bash env sed grep awk cat mkdir mv cp rm ls stat head tail sort date dirname basename mktemp tr wc cut \
           sha256sum find id git python3 diff chmod ln sleep touch tee uname xargs truncate readlink realpath \
           comm uniq tar gzip ffmpeg ffprobe install timeout; do
    p=$(command -v "$t" 2>/dev/null) && ln -sf "$p" "$W/bin/$t"
  done
  PY3=$(command -v python3)
  # the repo as setup.sh sees it: our scripts copied in, the Easel files it points at stubbed
  R=$W/root
  mkdir -p "$R/ops/wsl-setup" "$R/skills/shared/scripts" "$R/.venv/bin" \
           "$R/skills/builtin/skill-xhs-analyzer/scripts" \
           "$R/skills/builtin/video-production/vendor/video-pipeline-sdk/deps/remotion" \
           "$R/skills/builtin/video-production/scripts"
  for f in setup.sh checks.sh fingerprint.sh; do [ -f "$HERE/$f" ] && cp "$HERE/$f" "$R/ops/wsl-setup/$f"; done
  ( cd "$R" && git init -q . )
  printf '#!/usr/bin/env bash\nexit 0\n' > "$R/skills/builtin/skill-xhs-analyzer/scripts/redbook-guard.sh"
  printf '#!/usr/bin/env bash\necho "fake guard tests"\nexit 0\n' > "$R/skills/builtin/skill-xhs-analyzer/scripts/redbook-guard.test.sh"
  echo '{}' > "$R/skills/builtin/video-production/vendor/video-pipeline-sdk/deps/remotion/package.json"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$R/skills/builtin/video-production/scripts/video_pipeline.py"
  printf '# stand-in\n' > "$R/skills/shared/scripts/audio_ops.py"
  printf '# stand-in\n' > "$R/skills/shared/scripts/remove_bg.py"
  cat > "$R/skills/builtin/video-production/vendor/video-pipeline-sdk/deps/bootstrap.sh" <<'EOF'
#!/usr/bin/env bash
# stand-in for the SDK's installer: like the real one, it skips when node_modules exists
echo "bootstrap.sh" >> "$FAKE_W/calls.log"
d=$(cd "$(dirname "$0")" && pwd)/remotion
case "$(command -v node)" in /mnt/*|"") echo "bootstrap ran without Linux node" >> "$FAKE_W/calls.log" ;; esac
[ -d "$d/node_modules" ] && { echo "node_modules exists, skipping"; exit 0; }
mkdir -p "$d/node_modules/@remotion/compositor-linux-x64-gnu" "$d/node_modules/.bin"
echo "npm ci exit=0"
EOF
  # the venv: real python3 with a private folder of stand-in packages on its path
  cat > "$R/.venv/bin/python" <<EOF
#!/usr/bin/env bash
if [ "\${1:-}" = -m ] && [ "\${2:-}" = pip ]; then
  shift 2
  case "\${1:-}" in
    install)
      shift; echo "pip install \$*" >> "\$FAKE_W/calls.log"
      skip=0
      for a in "\$@"; do
        [ \$skip = 1 ] && { skip=0; continue; }
        case \$a in
          --index-url|--extra-index-url) skip=1 ;;
          -*) ;;
          *) n=\${a%%==*}; v=1.0; case \$a in *==*) v=\${a##*==} ;; esac
             case \$n in PyMuPDF) m=fitz;; beautifulsoup4) m=bs4;; openai-whisper) m=whisper;; rapidocr-onnxruntime) m=rapidocr_onnxruntime;; *) m=\$n;; esac
             printf '__version__ = "%s"\n' "\$v" > "\$FAKE_W/site/\$m.py"
             case \$n in torch) printf '__version__ = "2.14.1+cpu"\nclass version:\n    cuda = None\n' > "\$FAKE_W/site/torch.py" ;; esac
             case \$n in openai-whisper) printf '#!/usr/bin/env bash\nexit 0\n' > "\$FAKE_W/root/.venv/bin/whisper"; chmod +x "\$FAKE_W/root/.venv/bin/whisper" ;; esac
             echo "\$n \$v" >> "\$FAKE_W/pip.list" ;;
        esac
      done ;;
    list|freeze) cat "\$FAKE_W/pip.list" 2>/dev/null ;;
  esac
  exit 0
fi
exec env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="\$FAKE_W/site" "$PY3" "\$@"
EOF
  chmod +x "$R/.venv/bin/python"
  printf '__version__ = "0.2.1"\n' > "$W/site/easel.py"      # Easel's own installer has run,
  printf '__version__ = "19.0.1"\n' > "$W/site/av.py"        # and put in the newest PyAV, which breaks speech
  { echo "easel 0.2.1"; echo "av 19.0.1"; } > "$W/pip.list"
  # rembg, as Easel's installer leaves it: installed, models not yet downloaded. new_session fetches one.
  cat > "$W/site/rembg.py" <<'EOF'
import os
def new_session(name):
    with open(os.path.join(os.environ["FAKE_W"], "calls.log"), "a") as f:
        f.write("rembg new_session %s\n" % name)
    d = os.path.join(os.environ["REMBG_HOME"], "models", name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, name + ".onnx"), "w").write("x")
EOF
  # the places a vendor's own installer would write into (shell profiles, the default OpenClaw workspace) and
  # Easel's own agent workspace: each holds a file, so the fingerprint's lines for them can be shown to see a change
  printf 'export EDITOR=vi\n' > "$W/home/.bashrc"; echo '# profile' > "$W/home/.profile"
  mkdir -p "$W/home/.openclaw/workspace" "$W/home/.openclaw-easel/workspace"
  printf 'tools notes\n' > "$W/home/.openclaw/workspace/TOOLS.md"; echo agent > "$W/home/.openclaw-easel/workspace/AGENTS.md"
  # the OpenClaw profile exists, with an unrelated tool already denied and an unrelated search setting
  mkdir -p "$W/home/.openclaw-easel"
  cat > "$W/home/.openclaw-easel/openclaw.json" <<'EOF'
{"agents": {"defaults": {"model": "claude-cli/opus"}}, "tools": {"profile": "full", "deny": ["exec_remote"]}}
EOF
  # LibTV's closed program as the file server hands it over: a good package, and a different (older) one served
  # from the same kind of address; the program is a stand-in that answers --version
  mklibtv good 1.1.3 > "$W/libtv.good"; mklibtv stale 1.0.2 > "$W/libtv.stale"
  mkpkg "$W/libtv-pkg.good.zip" libtv-linux-x64/libtv "$W/libtv.good"
  mkpkg "$W/libtv-pkg.stale.zip" libtv-linux-x64/libtv "$W/libtv.stale"
  LTV_ZIP_SHA=$(sha256sum "$W/libtv-pkg.good.zip" | cut -d' ' -f1)
  LTV_SHA=$(sha256sum "$W/libtv.good" | cut -d' ' -f1)
  cp "$W/libtv-pkg.good.zip" "$W/libtv.served"
  # the display font as the release server hands it over: the good file, and a different one served from the same address
  printf 'stand-in font file\n' > "$W/font.good"; printf 'a different stand-in font file\n' > "$W/font.stale"
  DF_SHA=$(sha256sum "$W/font.good" | cut -d' ' -f1)
  cp "$W/font.good" "$W/font.served"
  make_shims
  export FAKE_W=$W
}

make_shims() {
  mkshim apt-get <<'EOF'
#!/usr/bin/env bash
echo "apt-get $*" >> "$FAKE_W/calls.log"
if [ "${1:-}" = install ]; then
  shift
  for a in "$@"; do
    case $a in
      -*) ;;
      *) echo "$a" >> "$FAKE_W/dpkg.list"
         case $a in
           poppler-utils) printf '#!/usr/bin/env bash\nexit 0\n' > "$FAKE_W/bin/pdftotext"; chmod +x "$FAKE_W/bin/pdftotext" ;;
           fonts-noto-cjk) for f in Regular Bold; do echo x > "$FAKE_W/fonts/NotoSansCJK-$f.ttc"; done ;;
         esac ;;
    esac
  done
fi
exit 0
EOF
  mkshim dpkg-query <<'EOF'
#!/usr/bin/env bash
pkg=""
for a in "$@"; do case $a in -*) ;; *) pkg=$a ;; esac; done
[ -z "$pkg" ] && { sed 's/$/ 1.0/' "$FAKE_W/dpkg.list"; exit 0; }
if grep -qx "$pkg" "$FAKE_W/dpkg.list"; then printf 'install ok installed'; exit 0; fi
echo "dpkg-query: no packages found matching $pkg" >&2; exit 1
EOF
  mkshim fc-cache <<'EOF'
#!/usr/bin/env bash
echo "fc-cache $*" >> "$FAKE_W/calls.log"
# remembers what each folder it was told to scan held, so fc-list can list a font only after a scan of its folder
for a in "$@"; do [ -d "$a" ] && ls "$a" >> "$FAKE_W/fc-scanned"; done
exit 0
EOF
  mkshim fc-list <<'EOF'
#!/usr/bin/env bash
grep -qx fonts-noto-cjk-extra "$FAKE_W/dpkg.list" && {
  for s in Thin Light DemiLight Medium Black; do echo "Noto Sans CJK SC,Noto Sans CJK SC $s:style=$s,Regular"; done
  echo "Noto Sans CJK SC:style=Regular"; echo "Noto Sans CJK SC:style=Bold"
  for s in ExtraLight Light Medium SemiBold Black; do echo "Noto Serif CJK SC,Noto Serif CJK SC $s:style=$s,Regular"; done
  echo "Noto Serif CJK SC:style=Regular"; echo "Noto Serif CJK SC:style=Bold"
  echo "Noto Sans Mono CJK SC:style=Regular"; echo "Noto Sans Mono CJK SC:style=Bold"
}
grep -qx fonts-noto-color-emoji "$FAKE_W/dpkg.list" && echo "Noto Color Emoji:style=Regular"
grep -qx LXGWWenKai-Medium.ttf "$FAKE_W/fc-scanned" 2>/dev/null && echo "LXGW WenKai,LXGW WenKai Medium:style=Medium,Regular"
exit 0
EOF
  mkshim curl <<'EOF'
#!/usr/bin/env bash
out=""; url=""; hdr=""
echo "$*" >> "$FAKE_W/curl-args.log"
while [ $# -gt 0 ]; do
  case $1 in
    -o) out=$2; shift ;;
    -D) hdr=$2; shift ;;
    -C|--retry) shift ;;
    -*) ;;
    *) url=$1 ;;
  esac
  shift
done
echo "curl $url" >> "$FAKE_W/calls.log"
[ -n "$hdr" ] && printf 'HTTP/1.1 200 OK\r\nLast-Modified: %s\r\n\r\n' "${FAKE_LAST_MODIFIED:-Sun, 09 Aug 2026 06:20:00 GMT}" > "$hdr"
case $url in
  *nvm-sh/nvm*install.sh)
    cat <<'NVM'
mkdir -p "$NVM_DIR"
cat > "$NVM_DIR/nvm.sh" <<'NVMSH'
nvm() {
  case "$1" in
    install)
      echo "nvm install $2" >> "$FAKE_W/calls.log"
      d="$NVM_DIR/versions/node/v24.0.0/bin"; mkdir -p "$d"
      for t in node npm npx; do cp "$FAKE_W/bin/.$t" "$d/$t"; done ;;
  esac
}
for d in "$NVM_DIR"/versions/node/*/bin; do [ -d "$d" ] && PATH="$d:$PATH"; done
NVMSH
NVM
    exit 0 ;;
esac
[ -z "$out" ] && exit 0
mkdir -p "$(dirname "$out")"
case $url in
  *faster-whisper-base/*model.bin)     truncate -s 145217532 "$out" ;;
  *faster-whisper-small/*model.bin)    truncate -s 483546902 "$out" ;;
  *faster-whisper-large-v3/*model.bin) truncate -s 3087284237 "$out" ;;
  *sh.rnnn)                            truncate -s 297646 "$out" ;;
  *libtv-linux-x64.zip)                cp "$FAKE_W/libtv.served" "$out" ;;
  *LXGWWenKai-Medium.ttf)              cp "$FAKE_W/font.served" "$out" ;;
  *) echo x > "$out" ;;
esac
exit 0
EOF
  # node, npm, npx: kept as hidden originals so the nvm stand-in can "install" them
  cat > "$W/bin/.node" <<'EOF'
#!/usr/bin/env bash
[ "${1:-}" = -v ] && echo "${FAKE_NODE_VERSION:-v24.0.0}"
exit 0
EOF
  cat > "$W/bin/.npm" <<'EOF'
#!/usr/bin/env bash
echo "npm $*" >> "$FAKE_W/calls.log"
case "${1:-}" in
  install)
    case " $* " in
      *" -g "*) for a in "$@"; do case $a in @openai/codex*) printf '#!/usr/bin/env bash\ncase "$1$2" in --version) echo "codex-cli 0.0.0-fake";; loginstatus) echo "Not logged in"; exit 1;; esac\nexit 0\n' > "$(dirname "$0")/codex"; chmod +x "$(dirname "$0")/codex";; esac; done ;;
      *) for a in "$@"; do case $a in @lucasygu/redbook@*)
           ver=${a##*@}; mkdir -p node_modules/.bin
           printf '#!/usr/bin/env bash\necho %s\n' "$ver" > node_modules/.bin/redbook; chmod +x node_modules/.bin/redbook
           echo '{}' > package.json ;; esac; done ;;
    esac ;;
esac
exit 0
EOF
  cat > "$W/bin/.npx" <<'EOF'
#!/usr/bin/env bash
if [ "$*" = "--no-install remotion versions" ] && [ -d node_modules/@remotion ]; then
  printf 'On version: 4.0.503\n- remotion\n- @remotion/cli\nAll packages have the correct version.\n'; exit 0; fi
exit 1
EOF
  chmod +x "$W/bin/.node" "$W/bin/.npm" "$W/bin/.npx"
  mkshim openclaw <<'EOF'
#!/usr/bin/env bash
cfg=$OPENCLAW_CONFIG
case "$*" in
  *"config set tools.deny"*)
    echo "openclaw $*" >> "$FAKE_W/calls.log"
    python3 - "$cfg" "$6" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); c.setdefault("tools", {})["deny"] = json.loads(sys.argv[2])
json.dump(c, open(sys.argv[1], "w"))
PY
    ;;
  *"config set env.vars."*)
    echo "openclaw $*" >> "$FAKE_W/calls.log"
    python3 - "$cfg" "$5" "$6" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); c.setdefault("env", {}).setdefault("vars", {})[sys.argv[2].split("env.vars.", 1)[1]] = json.loads(sys.argv[3])
json.dump(c, open(sys.argv[1], "w"))
PY
    ;;
  *"skills info redbook"*) echo "Visible to model: yes" ;;
  *"gateway call"*) echo "gateway not running" >&2; exit 1 ;;
esac
exit 0
EOF
}

# the environment for every run of a script under test. Optional knobs, set by a test before the call:
#   CALLCHK=1 (let the slow checks run), EXTRA_PATH and WINMNT (a program found under a fake Windows mount),
#   T_ZIPSHA and T_SHA (the program package's and the program's pinned sha256: unset = the good stand-in's,
#   empty = the real pin), T_ZIPFILE (a local package file), T_GWPATH (the gateway's PATH)
in_world() {
  ( cd "$W/root" && env -i PATH="${EXTRA_PATH:-}$W/bin" HOME="$W/home" FAKE_W="$W" TMPDIR="$W/tmp" \
      SETUP_SUDO="" SETUP_CALL_CHECKS="${CALLCHK:-0}" NVM_DIR="$W/nvm" EASEL_WIN_MOUNT="${WINMNT:-/mnt/}" \
      EASEL_MODEL_DIR="$W/home/.cache/easel-models" REMBG_HOME="$W/home/.rembg" \
      OPENCLAW_CONFIG="$W/home/.openclaw-easel/openclaw.json" REDBOOK_DIR="$W/opt/redbook" \
      REDBOOK_BIN="$W/local/redbook" EASEL_FONT_DIR="$W/fonts" \
      LIBTV_BIN="$W/local/libtv" LIBTV_ZIP_SHA256="${T_ZIPSHA-$LTV_ZIP_SHA}" LIBTV_SHA256="${T_SHA-$LTV_SHA}" \
      EASEL_DISPLAY_FONT_DIR="$W/dfonts" DISPLAY_FONT_SHA256="${T_FONTSHA-$DF_SHA}" \
      LIBTV_ZIP_FILE="${T_ZIPFILE:-}" LIBTV_GATEWAY_PATH="${T_GWPATH:-$W/local}" FAKE_LAST_MODIFIED="${FAKE_LAST_MODIFIED:-}" \
      "$@" )
}
run_setup() {
  OUT=$W/out.txt
  in_world bash ops/wsl-setup/setup.sh "$@" > "$OUT" 2>&1
  RC=$?
  [ "${VERBOSE:-}" = 1 ] && sed 's/^/    | /' "$OUT"
}
# the checks on their own, without the install step
run_check() {
  OUT=$W/out.txt
  in_world bash ops/wsl-setup/checks.sh "$@" > "$OUT" 2>&1
  RC=$?
  [ "${VERBOSE:-}" = 1 ] && sed 's/^/    | /' "$OUT"
}
# fp: what setup.sh touches, as fingerprint.sh prints it
fp() { in_world bash ops/wsl-setup/fingerprint.sh 2>&1; }
calls() { cat "$W/calls.log"; }
ncalls() { wc -l < "$W/calls.log" | tr -d ' '; }

# ---------------------------------------------------------------------------------------------------
echo "== node: a Linux Node (24 or newer), never the Windows one reached through WSL =="
world node1
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
run_setup --only node
expect "a machine with Linux Node already has it: says so, exits 0" bash -c 'grep -q "^already done: node" "$1" && grep -q "^PASS node" "$1"' _ "$OUT"
expect "nothing was installed"                      test "$(ncalls)" = 0

world node2
run_setup --only node
expect "no Node at all: exits 0"                    test "$RC" = 0
expect "nvm was fetched, then Node 24 installed"    bash -c 'a=$(grep -n "nvm-sh/nvm" "$1/calls.log" | head -1 | cut -d: -f1); b=$(grep -n "nvm install 24" "$1/calls.log" | head -1 | cut -d: -f1); [ -n "$a" ] && [ -n "$b" ] && [ "$b" -gt "$a" ]' _ "$W"
expect "its own check prints PASS"                  has "^PASS node" "$OUT"
n1=$(ncalls)
run_setup --only node
expect "second run says already done"               has "^already done: node" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world node3
mkdir -p "$W/winmnt/bin"; for t in node npm npx; do cp "$W/bin/.$t" "$W/winmnt/bin/$t"; done
EXTRA_PATH="$W/winmnt/bin:" WINMNT="$W/winmnt/" run_setup --only node
expect "a Node found under the Windows mount is refused and Linux Node installed instead" bash -c 'grep -q "nvm install 24" "$1/calls.log" && grep -q "^PASS node" "$2"' _ "$W" "$OUT"
unset EXTRA_PATH WINMNT

world node4
for t in npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
printf '#!/usr/bin/env bash\n[ "${1:-}" = -v ] && echo v20.11.0\n' > "$W/bin/node"; chmod +x "$W/bin/node"
run_setup --only node
expect "Node older than 24 is replaced"             bash -c 'grep -q "nvm install 24" "$1/calls.log"' _ "$W"

echo "== python-packages: skill packages, CPU-only PyTorch before whisper, PyAV pinned last =="
world py1
run_setup --only python-packages
expect "first run exits 0"                          test "$RC" = 0
expect "the small packages went in first"           bash -c 'head -1 "$1/calls.log" | grep -q "pip install openpyxl pdfplumber PyMuPDF zhconv beautifulsoup4 pytest"' _ "$W"
expect "torch came from PyTorch's CPU index"        hasF "pip install torch --index-url https://download.pytorch.org/whl/cpu" "$W/calls.log"
expect "PyTorch went in before openai-whisper, PyAV pin after both" bash -c 'l=$(grep -n "" "$1/calls.log"); t=$(echo "$l" | grep "install torch" | cut -d: -f1); w=$(echo "$l" | grep "openai-whisper" | cut -d: -f1); a=$(echo "$l" | grep "av==17.1.0" | cut -d: -f1); [ -n "$t" ] && [ "$t" -lt "$w" ] && [ "$w" -lt "$a" ]' _ "$W"
expect "openai-whisper itself comes from the normal index" bash -c 'grep -qx "pip install openai-whisper" "$1/calls.log"' _ "$W"
expect "the text-in-image engine is installed at the pinned version" hasF "pip install rapidocr-onnxruntime==1.2.3" "$W/calls.log"
expect "the engine went in before the PyAV pin"     bash -c 'l=$(grep -n "" "$1/calls.log"); o=$(echo "$l" | grep "rapidocr-onnxruntime==1.2.3" | cut -d: -f1); a=$(echo "$l" | grep "av==17.1.0" | cut -d: -f1); [ -n "$o" ] && [ "$o" -lt "$a" ]' _ "$W"
expect "no check FAILs"                             bash -c '! grep -q "^FAIL" "$1"' _ "$OUT"
expect "the check says the engine is there"         bash -c 'grep -q "^PASS python-packages.*rapidocr-onnxruntime 1.2.3" "$1"' _ "$OUT"
expect "the check says the CPU build and the pin"   bash -c 'grep -q "^PASS python-packages.*CPU" "$1" && grep -q "^PASS python-packages.*17.1.0" "$1"' _ "$OUT"
n1=$(ncalls)
run_setup --only python-packages
expect "second run says already done"               has "^already done: python-packages" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world py2
run_setup --only python-packages
printf '__version__ = "19.0.1"\n' > "$W/site/av.py"       # something upgraded PyAV later
: > "$W/calls.log"
run_setup --only python-packages
expect "a drifted PyAV is put back, and nothing else is reinstalled" bash -c '[ "$(wc -l < "$1/calls.log")" = 1 ] && grep -q "pip install av==17.1.0" "$1/calls.log"' _ "$W"

world py4
run_setup --only python-packages
sed -i 's/^rapidocr-onnxruntime .*/rapidocr-onnxruntime 1.2.1/' "$W/pip.list"   # something moved the engine to another release
: > "$W/calls.log"
run_setup --only python-packages
expect "a drifted engine is put back to the pin, and nothing else is reinstalled" bash -c '[ "$(wc -l < "$1/calls.log")" = 1 ] && grep -q "pip install rapidocr-onnxruntime==1.2.3" "$1/calls.log"' _ "$W"

world py3
printf '__version__ = "2.0.0"\nclass version:\n    cuda = "13.0"\n' > "$W/site/torch.py"
run_setup --only python-packages
expect "a CUDA build of torch is reported, not silently kept" has "^FAIL python-packages.*torch" "$OUT"
expect "the script exits non-zero"                  test "$RC" != 0
expect "and torch is not reinstalled over it"       bash -c '! grep -q "install torch" "$1/calls.log"' _ "$W"

echo "== speech-models: faster-whisper base, small, large-v3 by plain file download =="
world sp1
run_setup --only speech-models
expect "first run exits 0"                          test "$RC" = 0
expect "13 files fetched (4 + 4 + 5)"               test "$(grep -c '^curl ' "$W/calls.log")" = 13
expect "from huggingface.co's file server, per model" bash -c 'for s in base small large-v3; do grep -q "^curl https://huggingface.co/Systran/faster-whisper-$s/resolve/main/model.bin" "$1/calls.log" || exit 1; done' _ "$W"
expect "large-v3 also gets preprocessor_config.json" hasF "faster-whisper-large-v3/resolve/main/preprocessor_config.json" "$W/calls.log"
expect "every file is in the Easel model folder"    bash -c 'd="$1/home/.cache/easel-models"; for f in faster-whisper-base/vocabulary.txt faster-whisper-small/tokenizer.json faster-whisper-large-v3/vocabulary.json faster-whisper-large-v3/preprocessor_config.json; do [ -s "$d/$f" ] || exit 1; done' _ "$W"
expect "no half-finished download left behind"      bash -c '! find "$1/home" -name "*.part" | grep -q .' _ "$W"
expect "no Hugging Face hub cache was created"      test ! -e "$W/home/.cache/huggingface"
expect "each size has its own PASS"                 bash -c '[ "$(grep -c "^PASS speech-models" "$1")" -ge 3 ]' _ "$OUT"
n1=$(ncalls)
run_setup --only speech-models
expect "second run says already done"               has "^already done: speech-models" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world sp2
run_setup --only speech-models
: > "$W/calls.log"
truncate -s 1000 "$W/home/.cache/easel-models/faster-whisper-small/model.bin"   # a cut-off download
rm "$W/home/.cache/easel-models/faster-whisper-base/tokenizer.json"
run_setup --only speech-models
expect "only the cut-off model and the missing file are fetched again" bash -c '[ "$(grep -c "^curl " "$1/calls.log")" = 2 ] && grep -q "faster-whisper-small/resolve/main/model.bin" "$1/calls.log" && grep -q "faster-whisper-base/resolve/main/tokenizer.json" "$1/calls.log"' _ "$W"
expect "and it ends all PASS"                       has "^ALL PASS" "$OUT"

echo "== noise-model: the RNNoise model beside the audio script, kept out of git locally =="
world nm1
run_setup --only noise-model
EXC=$W/root/.git/info/exclude
expect "first run exits 0"                          test "$RC" = 0
expect "the model came from the address the audio script prints" hasF "curl https://github.com/GregorR/rnnoise-models/raw/master/somnolent-hogwash-2018-09-01/sh.rnnn" "$W/calls.log"
expect "it is beside the shared audio script, full size" test "$(stat -c %s "$W/root/skills/shared/scripts/models/sh.rnnn")" = 297646
expect "the folder is in the local exclude list, once" test "$(grep -cxF 'skills/shared/scripts/models/' "$EXC")" = 1
expect "git does not list the model as untracked"   bash -c '[ -z "$(git -C "$1/root" status --porcelain --untracked-files=all -- skills/shared/scripts/models)" ]' _ "$W"
expect "no check FAILs"                             bash -c '! grep -q "^FAIL" "$1"' _ "$OUT"
n1=$(ncalls); s1=$(sha256sum "$EXC" | cut -d' ' -f1)
run_setup --only noise-model
expect "second run says already done"               has "^already done: noise-model" "$OUT"
expect "second run fetches nothing and leaves the exclude list byte for byte alone" bash -c '[ "$(wc -l < "$1/calls.log" | tr -d " ")" = "$2" ] && [ "$(sha256sum "$3" | cut -d" " -f1)" = "$4" ]' _ "$W" "$n1" "$EXC" "$s1"

world nm2
mkdir -p "$W/root/skills/shared/scripts/models"; truncate -s 297646 "$W/root/skills/shared/scripts/models/sh.rnnn"
run_setup --only noise-model
expect "a model already there is kept: only the exclude line is added" bash -c '! grep -q "^curl" "$1/calls.log" && grep -qxF "skills/shared/scripts/models/" "$2"' _ "$W" "$W/root/.git/info/exclude"

world nm3
mkdir -p "$W/root/skills/shared/scripts/models"; truncate -s 100 "$W/root/skills/shared/scripts/models/sh.rnnn"
printf 'skills/shared/scripts/models/\n' >> "$W/root/.git/info/exclude"
run_setup --only noise-model
expect "a cut-off model is fetched again, an existing exclude line is not repeated" bash -c '[ "$(grep -c "^curl" "$1/calls.log")" = 1 ] && [ "$(grep -cxF "skills/shared/scripts/models/" "$2")" = 1 ]' _ "$W" "$W/root/.git/info/exclude"

echo "== rembg-models: the background-removal models u2net and u2netp, fetched by rembg itself =="
world rb1
run_setup --only rembg-models
expect "first run exits 0"                          test "$RC" = 0
expect "rembg fetched both models itself"           bash -c 'grep -q "rembg new_session u2net$" "$1/calls.log" && grep -q "rembg new_session u2netp$" "$1/calls.log"' _ "$W"
expect "both are in rembg's model folder"           bash -c '[ -s "$1/home/.rembg/models/u2net/u2net.onnx" ] && [ -s "$1/home/.rembg/models/u2netp/u2netp.onnx" ]' _ "$W"
expect "its own check prints PASS and no FAIL"      bash -c 'grep -q "^PASS rembg-models" "$1" && ! grep -q "^FAIL" "$1"' _ "$OUT"
n1=$(ncalls)
run_setup --only rembg-models
expect "second run says already done"               has "^already done: rembg-models" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world rb2
mkdir -p "$W/home/.rembg/models/u2net"; echo x > "$W/home/.rembg/models/u2net/u2net.onnx"
run_setup --only rembg-models
expect "only the missing model is fetched"          bash -c '[ "$(grep -c "^rembg new_session" "$1/calls.log")" = 1 ] && grep -q "new_session u2netp$" "$1/calls.log"' _ "$W"

world rb3
unimportable rembg
run_setup --only rembg-models
expect "rembg missing from the venv is a FAIL, not a crash" has "^FAIL rembg-models" "$OUT"
expect "and the script exits non-zero"              test "$RC" != 0

echo "== redbook: the Xiaohongshu reader, install scripts skipped, only reachable through the read-only guard =="
GUARD_STUB() { printf '#!/usr/bin/env bash\nexec bash %s/skills/builtin/skill-xhs-analyzer/scripts/redbook-guard.sh "$@"\n' "$1"; }
world rd1
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
run_setup --only redbook
expect "first run exits 0"                          test "$RC" = 0
expect "pinned 0.8.2, install scripts skipped"      hasF "npm install --ignore-scripts --no-audit --no-fund @lucasygu/redbook@0.8.2" "$W/calls.log"
expect "installed in the program folder"            test -x "$W/opt/redbook/node_modules/.bin/redbook"
expect "the command on PATH is a stub that runs the guard from this repo" bash -c '[ -x "$1/local/redbook" ] && [ "$(cat "$1/local/redbook")" = "$2" ]' _ "$W" "$(GUARD_STUB "$W/root")"
expect "no link in Claude Code's skills folder and no cookie file" bash -c '[ ! -e "$1/home/.claude/skills/redbook" ] && [ ! -e "$1/home/.redbook/cookies.json" ]' _ "$W"
expect "the guard's own tests ran and passed"       has "^PASS redbook:.*guard" "$OUT"
expect "no check FAILs"                             bash -c '! grep -q "^FAIL" "$1"' _ "$OUT"
n1=$(ncalls)
run_setup --only redbook
expect "second run says already done"               has "^already done: redbook" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world rd2
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
run_setup --only redbook
printf '#!/usr/bin/env bash\necho 0.8.1\n' > "$W/opt/redbook/node_modules/.bin/redbook"
: > "$W/calls.log"
run_setup --only redbook
expect "a different installed version is replaced by the pinned one" bash -c '[ "$(grep -c "^npm install" "$1/calls.log")" = 1 ] && grep -q "redbook@0.8.2" "$1/calls.log"' _ "$W"

world rd3
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
run_setup --only redbook
printf '#!/usr/bin/env bash\nexec bash /somewhere/else/redbook-guard.sh "$@"\n' > "$W/local/redbook"
: > "$W/calls.log"
run_setup --only redbook
expect "a stub pointing at another folder is rewritten, with no reinstall" bash -c '[ ! -s "$1/calls.log" ] && [ "$(cat "$1/local/redbook")" = "$2" ]' _ "$W" "$(GUARD_STUB "$W/root")"

world rd4
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
run_setup --only redbook
mkdir -p "$W/home/.redbook"; echo '{}' > "$W/home/.redbook/cookies.json"
run_setup --only redbook
expect "a cookie file on disk is a FAIL"            has "^FAIL redbook:.*cookie" "$OUT"
printf '#!/usr/bin/env bash\nexit 3\n' > "$W/root/skills/builtin/skill-xhs-analyzer/scripts/redbook-guard.test.sh"
rm -rf "$W/home/.redbook"
run_setup --only redbook
expect "failing guard tests are a FAIL"             has "^FAIL redbook:.*guard" "$OUT"

echo "== libtv: LibTV's closed CLI, pinned by sha256 (package and program), placed where the gateway finds it, nothing else touched =="
LT_URL=https://liblibai-web-static.liblib.cloud/cli/1.1.3/libtv-linux-x64.zip
KEEP='^(shell-profiles|local-bin|openclaw-workspaces|libtv-home) '      # the fingerprint lines that must never move
cfg_env() { python3 -c 'import json,sys; v=((json.load(open(sys.argv[1])).get("env") or {}).get("vars") or {}).get("LIBTV_DISABLE_REPORT"); print(v)' "$W/home/.openclaw-easel/openclaw.json"; }
world lt1
FPK1=$(fp | grep -E "$KEEP" | sha256sum)
run_check libtv
expect "the check fails first on a machine without the program" bash -c 'grep -q "^FAIL libtv" "$1" && [ "$2" != 0 ]' _ "$OUT" "$RC"
run_setup --only libtv
expect "first run exits 0"                          test "$RC" = 0
expect "the install branch ran, then the check passed" bash -c 'grep -q "^doing: libtv" "$1" && grep -q "^PASS libtv" "$1" && ! grep -q "^FAIL" "$1"' _ "$OUT"
expect "it downloaded the package once, from the versioned address" bash -c '[ "$(grep -c "^curl " "$1/calls.log")" = 1 ] && grep -qxF "curl $2" "$1/calls.log"' _ "$W" "$LT_URL"
expect "the package is fetched fresh, never resumed from a half-finished file" bash -c 'grep -qF "$2" "$1/curl-args.log" && ! grep -q -e " -C " -e "^-C " "$1/curl-args.log"' _ "$W" "$LT_URL"
expect "the program (not the package) is in place, executable, and is the checked build" bash -c '[ -x "$1/local/libtv" ] && cmp -s "$1/local/libtv" "$1/libtv.good"' _ "$W"
expect "the gateway's PATH finds it"                has "^PASS libtv:.*gateway" "$OUT"
expect "no download or unpacked file is left in the temp folder" bash -c '[ -z "$(ls -A "$1/tmp")" ]' _ "$W"
expect "no shell profile, local-bin, .libtv folder or OpenClaw workspace changed" test "$(fp | grep -E "$KEEP" | sha256sum)" = "$FPK1"
expect "the .libtv folder in the home folder was never created (LibTV's own installer puts the program there)" test ! -e "$W/home/.libtv"
expect "the gateway's own environment gets LIBTV_DISABLE_REPORT=1 from the OpenClaw config" test "$(cfg_env)" = 1
expect "the config's other settings survive"        python3 -c "import json,sys; c=json.load(open(sys.argv[1])); sys.exit(0 if c['tools']['deny']==['exec_remote'] and c['tools']['profile']=='full' else 1)" "$W/home/.openclaw-easel/openclaw.json"
n1=$(ncalls); FPD1=$(fp | sha256sum)
run_setup --only libtv
expect "second run says already done"               has "^already done: libtv" "$OUT"
expect "second run downloads and sets nothing"      test "$(ncalls)" = "$n1"
expect "second run changes nothing the fingerprint covers" test "$(fp | sha256sum)" = "$FPD1"

world lt2
STALE_ZIP_SHA=$(sha256sum "$W/libtv-pkg.stale.zip" | cut -d' ' -f1)
cp "$W/libtv-pkg.stale.zip" "$W/libtv.served"; FAKE_LAST_MODIFIED="Mon, 08 Jun 2026 05:00:00 GMT"
run_setup --only libtv
expect "a package with the wrong sha256 is refused, exit non-zero" bash -c 'grep -q "^FAIL libtv" "$1" && [ "$2" != 0 ]' _ "$OUT" "$RC"
expect "nothing was installed and the config was not touched" bash -c '[ ! -e "$1/local/libtv" ] && ! grep -q openclaw "$1/calls.log"' _ "$W"
expect "the refusal prints the sha256 and the Last-Modified it received" bash -c 'grep -qF "$2" "$1" && grep -qF "Mon, 08 Jun 2026 05:00:00 GMT" "$1"' _ "$OUT" "$STALE_ZIP_SHA"
expect "the refused download was not kept"          bash -c '[ -z "$(ls -A "$1/tmp")" ]' _ "$W"
unset FAKE_LAST_MODIFIED

world lt3
cp "$W/libtv.stale" "$W/local/libtv"; chmod +x "$W/local/libtv"
run_setup --only libtv
expect "a different program already in place is replaced by the checked one" bash -c '[ "$2" = 0 ] && cmp -s "$1/local/libtv" "$1/libtv.good"' _ "$W" "$RC"
cp "$W/libtv.stale" "$W/local/libtv"; cp "$W/libtv-pkg.stale.zip" "$W/libtv.served"
run_setup --only libtv
expect "and when the download is wrong too, the program in place is left exactly as it was" bash -c '[ "$2" != 0 ] && cmp -s "$1/local/libtv" "$1/libtv.stale"' _ "$W" "$RC"

world lt4
cp "$W/libtv-pkg.good.zip" "$W/given.zip"
T_ZIPFILE=$W/given.zip run_setup --only libtv
expect "a local package named by the setting is installed with no download" bash -c '[ "$2" = 0 ] && ! grep -q "^curl" "$1/calls.log" && cmp -s "$1/local/libtv" "$1/libtv.good"' _ "$W" "$RC"
world lt5
cp "$W/libtv-pkg.stale.zip" "$W/given.zip"
T_ZIPFILE=$W/given.zip run_setup --only libtv
expect "a local package with the wrong sha256 is refused, and no download is tried instead" bash -c '[ "$2" != 0 ] && ! grep -q "^curl" "$1/calls.log" && [ ! -e "$1/local/libtv" ] && grep -q "^FAIL libtv" "$3"' _ "$W" "$RC" "$OUT"

world lt6
run_setup --only libtv
CALLCHK=1 run_check libtv
expect "the check records what the program prints for --version, without re-pinning" bash -c 'grep -q "^NOTE libtv:.*libtv version 1.1.3" "$1" && ! grep -q "^FAIL" "$1"' _ "$OUT"
expect "the check runs the program with the report switched off" has "^NOTE libtv:.*disable-report=1" "$OUT"

world lt7
run_setup --only libtv
echo 'export PATH="$HOME/.libtv:$PATH"   # libtv' >> "$W/home/.bashrc"
run_check libtv
expect "a shell profile that mentions libtv (LibTV's own installer ran) is a FAIL" has "^FAIL libtv:.*profile" "$OUT"
world lt8
run_setup --only libtv
mkdir -p "$W/home/.libtv"; cp "$W/libtv.good" "$W/home/.libtv/libtv"
run_check libtv
expect "a program in ~/.libtv (LibTV's own installer ran) is a FAIL" has "^FAIL libtv:.*\.libtv" "$OUT"
world lt9
run_setup --only libtv
T_GWPATH=/nonexistent run_check libtv
expect "a program the gateway's PATH does not reach is a FAIL" has "^FAIL libtv:.*gateway" "$OUT"

world lt10
run_setup --only libtv
python3 - "$W/home/.openclaw-easel/openclaw.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); c["env"]["vars"]["LIBTV_DISABLE_REPORT"] = "0"
json.dump(c, open(sys.argv[1], "w"))
PY
run_check libtv
expect "the report switched back on in the gateway's environment is a FAIL" has "^FAIL libtv:.*LIBTV_DISABLE_REPORT" "$OUT"
run_setup --only libtv
expect "and a rerun puts it right, without downloading again" bash -c '[ "$(grep -c "^curl " "$1/calls.log")" = 1 ] && [ "$2" = 1 ]' _ "$W" "$(cfg_env)"

world lt11
cp "$W/libtv.good" "$W/local/libtv"; chmod +x "$W/local/libtv"
run_setup --only libtv
expect "the right program but no report setting: only the setting is added, nothing is downloaded" bash -c '[ "$2" = 0 ] && ! grep -q "^curl" "$1/calls.log" && grep -q "config set env.vars.LIBTV_DISABLE_REPORT" "$1/calls.log" && [ "$3" = 1 ]' _ "$W" "$RC" "$(cfg_env)"

world lt12
mkpkg "$W/odd.zip" "other/thing" "$W/libtv.good"
cp "$W/odd.zip" "$W/libtv.served"
T_ZIPSHA=$(sha256sum "$W/odd.zip" | cut -d' ' -f1) run_setup --only libtv
expect "a package with the right sha256 but no libtv program inside is refused, nothing installed" bash -c '[ "$2" != 0 ] && [ ! -e "$1/local/libtv" ] && grep -q "^FAIL libtv" "$3"' _ "$W" "$RC" "$OUT"
world lt13
cp "$W/libtv-pkg.stale.zip" "$W/libtv.served"
T_ZIPSHA=$(sha256sum "$W/libtv-pkg.stale.zip" | cut -d' ' -f1) run_setup --only libtv
expect "a package whose program is not the pinned program is refused, nothing installed" bash -c '[ "$2" != 0 ] && [ ! -e "$1/local/libtv" ] && grep -q "^FAIL libtv" "$3"' _ "$W" "$RC" "$OUT"

# the kept copy of the pinned package (issue 37): the update gate's keep-pin saves the checked package, and a rollback
# runs the setup step from it with no download. The gate fetches from a stand-in file server on a loopback port.
GATE=$HERE/../libtv-update-gate/libtv_gate.py
world ltk1
LTK_PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
mkdir -p "$W/serve/cli/1.1.3" "$W/gaterepo/ops/wsl-setup"
cp "$W/libtv-pkg.good.zip" "$W/serve/cli/1.1.3/libtv-linux-x64.zip"
cp "$HERE/setup.sh" "$HERE/checks.sh" "$W/gaterepo/ops/wsl-setup/"
sed -i "s#^LIBTV_URL=.*#LIBTV_URL=http://127.0.0.1:$LTK_PORT/cli/1.1.3/libtv-linux-x64.zip#" "$W/gaterepo/ops/wsl-setup/setup.sh"
python3 -m http.server "$LTK_PORT" --bind 127.0.0.1 --directory "$W/serve" > "$W/http.log" 2>&1 &
LTK_PID=$!
for _ in $(seq 1 50); do python3 -c 'import socket,sys; socket.create_connection(("127.0.0.1", int(sys.argv[1])), 0.2)' "$LTK_PORT" 2>/dev/null && break; sleep 0.1; done
NO_PROXY=127.0.0.1 LIBTV_ZIP_SHA256=$LTV_ZIP_SHA LIBTV_SHA256=$LTV_SHA \
  python3 "$GATE" --root "$W/gaterepo" --store "$W/store" keep-pin > "$W/keep.txt" 2>&1
KEEP_RC=$?
kill "$LTK_PID" 2>/dev/null; wait "$LTK_PID" 2>/dev/null
KEPT=$W/store/pinned/1.1.3/libtv-linux-x64.zip
expect "the gate's keep-pin keeps the checked package from the file server" bash -c '[ "$2" = 0 ] && cmp -s "$1" "$3"' _ "$KEPT" "$KEEP_RC" "$W/libtv-pkg.good.zip"
expect "it prints the rollback command for the setup step" has "LIBTV_ZIP_FILE=.*setup.sh --only libtv" "$W/keep.txt"
cp "$W/libtv.stale" "$W/local/libtv"; chmod +x "$W/local/libtv"      # a newer program is in place; roll back
T_ZIPFILE=$KEPT run_setup --only libtv
expect "the setup step installs the pinned program from the kept copy with no download" bash -c '[ "$2" = 0 ] && ! grep -q "^curl" "$1/calls.log" && cmp -s "$1/local/libtv" "$1/libtv.good"' _ "$W" "$RC"
expect "and the step's own check passes"            has "^PASS libtv" "$OUT"

# the real packages, when the checked copies are on this machine (the evidence folder is not in git)
EVL=$HERE/../../work/.scratch/easel-setup-gaps/evidence/32-libtv-probe/reopen-2026-10-14
if [ -f "$EVL/1.1.3-libtv-linux-x64.zip" ] && [ -f "$EVL/libtv-linux-x64.zip.1" ]; then
  world ltr1
  T_ZIPSHA="" T_SHA="" T_ZIPFILE="$EVL/libtv-linux-x64.zip.1" run_setup --only libtv
  expect "the real 1.0.2 package is refused against the real pins, nothing installed" bash -c '[ "$2" != 0 ] && [ ! -e "$1/local/libtv" ] && grep -q "^FAIL libtv" "$3"' _ "$W" "$RC" "$OUT"
  world ltr2
  T_ZIPSHA="" T_SHA="" T_ZIPFILE="$EVL/1.1.3-libtv-linux-x64.zip" run_setup --only libtv
  expect "the real 1.1.3 package passes both real pins and the program is installed" bash -c '[ "$2" = 0 ] && [ -x "$1/local/libtv" ] && grep -q "^PASS libtv" "$3"' _ "$W" "$RC" "$OUT"
  expect "the installed file is the real program (sha256 from the source note)" bash -c '[ "$(sha256sum "$1/local/libtv" | cut -d" " -f1)" = e79ad52170556b44e957174f880c8a69057f668ddd0b9a4011524cac072c31f3 ]' _ "$W"
else
  echo "SKIP  the real-package cases (the checked copies are not in work/.scratch/easel-setup-gaps/evidence/32-libtv-probe)"
fi

echo "== remotion: the video renderer, installed by the SDK's own installer under Linux Node =="
RM=skills/builtin/video-production/vendor/video-pipeline-sdk/deps/remotion
world rm1
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
run_setup --only remotion
expect "first run exits 0"                          test "$RC" = 0
expect "the SDK's own installer ran once"           test "$(grep -c '^bootstrap.sh' "$W/calls.log")" = 1
expect "it ran under Linux Node"                    bash -c '! grep -q "without Linux node" "$1/calls.log"' _ "$W"
expect "the Linux compositor is there"              test -d "$W/root/$RM/node_modules/@remotion/compositor-linux-x64-gnu"
expect "its own check prints PASS and no FAIL"      bash -c 'grep -q "^PASS remotion" "$1" && ! grep -q "^FAIL" "$1"' _ "$OUT"
n1=$(ncalls)
run_setup --only remotion
expect "second run says already done"               has "^already done: remotion" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world rm2
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
mkdir -p "$W/root/$RM/node_modules/@remotion/compositor-win32-x64-msvc"     # what a run under Windows Node leaves behind
run_setup --only remotion
expect "a broken install is cleared and redone (the SDK's installer would skip it)" bash -c 'grep -q "^bootstrap.sh" "$1/calls.log" && [ -d "$1/root/$2/node_modules/@remotion/compositor-linux-x64-gnu" ] && [ ! -d "$1/root/$2/node_modules/@remotion/compositor-win32-x64-msvc" ]' _ "$W" "$RM"

world rm3
run_setup --only remotion
expect "no Linux Node: refused, the installer is not run" bash -c '! grep -q "bootstrap" "$1/calls.log"' _ "$W"
expect "and the script exits non-zero"              test "$RC" != 0

echo "== codex: the Linux Codex program; its ChatGPT login stays the owner's step =="
world cx1
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
run_setup --only codex
expect "first run exits 0"                          test "$RC" = 0
expect "installed globally under Linux Node"        hasF "npm install -g @openai/codex" "$W/calls.log"
expect "the version check passes"                   has "^PASS codex:.*codex-cli" "$OUT"
expect "an unfinished login is a NOTE for the owner, not a FAIL" bash -c 'grep -q "^NOTE codex:.*login" "$1" && ! grep -q "^FAIL" "$1"' _ "$OUT"
n1=$(ncalls)
run_setup --only codex
expect "second run says already done"               has "^already done: codex" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world cx2
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
printf '#!/usr/bin/env bash\ncase "$1$2" in --version) echo "codex-cli 9.9";; loginstatus) echo "Logged in using ChatGPT";; esac\nexit 0\n' > "$W/bin/codex"; chmod +x "$W/bin/codex"
run_setup --only codex
expect "an existing logged-in Codex is kept, and the login is a PASS" bash -c '! grep -q "^curl\|^npm" "$1/calls.log" && grep -q "^PASS codex:.*logged in" "$2" && ! grep -q "^NOTE" "$2"' _ "$W" "$OUT"

world cx3
for t in node npm npx; do cp "$W/bin/.$t" "$W/bin/$t"; done
mkdir -p "$W/winmnt/bin"; printf '#!/usr/bin/env bash\necho "codex-cli windows"\n' > "$W/winmnt/bin/codex"; chmod +x "$W/winmnt/bin/codex"
EXTRA_PATH="$W/winmnt/bin:" WINMNT="$W/winmnt/" run_setup --only codex
expect "a Codex found under the Windows mount does not count" bash -c 'grep -q "npm install -g @openai/codex" "$1/calls.log"' _ "$W"
unset EXTRA_PATH WINMNT

world cx4
run_setup --only codex
expect "no Linux Node: refused, nothing installed"  bash -c '! grep -q "^npm" "$1/calls.log" && [ "$2" != 0 ]' _ "$W" "$RC"

echo "== no-keys: no Hugging Face login, token, cache or endpoint anywhere =="
world nk1
run_setup --only no-keys
expect "a clean machine passes"                     bash -c 'grep -q "^PASS no-keys" "$1" && ! grep -q "^FAIL" "$1"' _ "$OUT"
mkdir -p "$W/home/.cache/huggingface"
run_setup --only no-keys
expect "a Hugging Face hub cache is a FAIL"         has "^FAIL no-keys:.*cache" "$OUT"
rmdir "$W/home/.cache/huggingface"; echo 'HF_TOKEN=hf_abcdefghijklmnopqrstuvwxyz' > "$W/root/.env"
run_setup --only no-keys
expect "a Hugging Face token in .env is a FAIL"     has "^FAIL no-keys:.*\.env" "$OUT"
echo 'SEEDANCE_API_KEY=abc' > "$W/root/.env"
run_setup --only no-keys
expect "other keys in .env (the Seedance one the owner allowed) are not this check's business" bash -c '! grep -q "^FAIL" "$1"' _ "$OUT"

echo "== preconditions: refuse, list everything missing, change nothing =="
world pre1
unimportable easel
rm "$W/home/.openclaw-easel/openclaw.json"
run_setup
expect "exits 2"                                    test "$RC" = 2
expect "names the missing Python environment"       has "Python environment" "$OUT"
expect "names the missing OpenClaw profile"         has "OpenClaw profile" "$OUT"
expect "changed nothing"                            test "$(ncalls)" = 0
run_setup --only nonsense
expect "an unknown step is refused"                 test "$RC" = 2
run_setup --list
expect "--list prints the 13 steps"                 test "$(grep -c . "$OUT")" = 13

echo "== whole run, from a bare machine, then again =="
world full1
run_setup
expect "first run exits 0"                          test "$RC" = 0
expect "it ends ALL PASS"                           has "^ALL PASS" "$OUT"
expect "every step did its work (none said already done)" bash -c '! grep -q "^already done: \(node\|system-packages\|display-font\|python-packages\|speech-models\|noise-model\|rembg-models\|search-deny\|redbook\|libtv\|remotion\|codex\)" "$1"' _ "$OUT"
expect "Node came first: before the SDK installer, redbook and Codex" bash -c 'l=$(grep -n "" "$1/calls.log"); n=$(echo "$l" | grep "nvm install" | cut -d: -f1); for p in "bootstrap.sh" "redbook@" "openai/codex"; do x=$(echo "$l" | grep -m1 "$p" | cut -d: -f1); [ -n "$x" ] && [ "$n" -lt "$x" ] || exit 1; done' _ "$W"
expect "the login note for the owner is shown"             has "^NOTE codex:.*login" "$OUT"
FP1=$(fp | sha256sum)
expect "the fingerprint names every place the script touches" bash -c 'f=$(cat); for s in dpkg pip openclaw-config models redbook-dir redbook-stub exclude remotion libtv-bin libtv-home display-font noto-fonts shell-profiles local-bin openclaw-workspaces; do echo "$f" | grep -q "^$s " || { echo "no $s"; exit 1; }; done' < <(fp)
n1=$(ncalls)
run_setup
expect "second run exits 0 and ends ALL PASS"       bash -c '[ "$1" = 0 ] && grep -q "^ALL PASS" "$2"' _ "$RC" "$OUT"
expect "second run says already done for all 13 steps" test "$(grep -c '^already done:' "$OUT")" = 13
expect "second run touched nothing"                 test "$(ncalls)" = "$n1"
FP2=$(fp | sha256sum)
expect "the fingerprint of everything the script touches is unchanged" test "$FP1" = "$FP2"
# an instrument that cannot see a change proves nothing: change each place once and look for the difference
sees() { # NAME, then the command that changes the place and the command that puts it back
  local name=$1 do_=$2 undo=$3 before after
  before=$(fp | sha256sum); eval "$do_"; after=$(fp | sha256sum); eval "$undo"
  if [ "$before" != "$after" ]; then ok "the fingerprint sees a change in $name"; else bad "the fingerprint is blind to $name"; fi
}
EXC=$W/root/.git/info/exclude
sees "the OpenClaw config"    'cp -p "$W/home/.openclaw-easel/openclaw.json" "$W/bak"; echo " " >> "$W/home/.openclaw-easel/openclaw.json"'                'mv "$W/bak" "$W/home/.openclaw-easel/openclaw.json"'
sees "the installed packages" 'cp -p "$W/dpkg.list" "$W/bak"; echo zz >> "$W/dpkg.list"' 'mv "$W/bak" "$W/dpkg.list"'
sees "the pip packages"       'cp -p "$W/pip.list" "$W/bak"; echo "zz 1" >> "$W/pip.list"' 'mv "$W/bak" "$W/pip.list"'
sees "a speech model file"    'cp -p "$W/home/.cache/easel-models/faster-whisper-base/config.json" "$W/bak"; echo y >> "$W/home/.cache/easel-models/faster-whisper-base/config.json"'               'mv "$W/bak" "$W/home/.cache/easel-models/faster-whisper-base/config.json"'
sees "a background-removal model" 'cp -p "$W/home/.rembg/models/u2net/u2net.onnx" "$W/bak"; echo y >> "$W/home/.rembg/models/u2net/u2net.onnx"'         'mv "$W/bak" "$W/home/.rembg/models/u2net/u2net.onnx"'
sees "the redbook folder"     'touch "$W/opt/redbook/extra"'                          'rm "$W/opt/redbook/extra"'
sees "the redbook stub"       'cp -p "$W/local/redbook" "$W/bak"; echo "# x" >> "$W/local/redbook"'       'mv "$W/bak" "$W/local/redbook"'
sees "the exclude list"       'cp -p "$EXC" "$W/bak"; echo x >> "$EXC"'             'mv "$W/bak" "$EXC"'
sees "the Remotion folder"    'mkdir "$W/root/'"$RM"'/node_modules/extra"'          'rmdir "$W/root/'"$RM"'/node_modules/extra"'
sees "the libtv program"      'cp -p "$W/local/libtv" "$W/bak"; echo "# x" >> "$W/local/libtv"' 'mv "$W/bak" "$W/local/libtv"'
sees "a file in ~/.libtv"     'mkdir -p "$W/home/.libtv"; touch "$W/home/.libtv/credentials.json"' 'rm -rf "$W/home/.libtv"'
sees "the display font folder" 'touch "$W/dfonts/extra.ttf"' 'rm "$W/dfonts/extra.ttf"'
sees "the Noto font folder"   'touch "$W/fonts/extra.ttc"' 'rm "$W/fonts/extra.ttc"'
sees "a shell profile"        'cp -p "$W/home/.bashrc" "$W/bak"; echo x >> "$W/home/.bashrc"' 'mv "$W/bak" "$W/home/.bashrc"'
sees "a file in ~/.local/bin" 'mkdir -p "$W/home/.local/bin"; touch "$W/home/.local/bin/some-program"' 'rm -rf "$W/home/.local"'
sees "the default OpenClaw workspace" 'cp -p "$W/home/.openclaw/workspace/TOOLS.md" "$W/bak"; echo x >> "$W/home/.openclaw/workspace/TOOLS.md"' 'mv "$W/bak" "$W/home/.openclaw/workspace/TOOLS.md"'
sees "Easel's agent workspace" 'echo x > "$W/home/.openclaw-easel/workspace/new.md"' 'rm "$W/home/.openclaw-easel/workspace/new.md"'
expect "and the undo left it as it was"             test "$(fp | sha256sum)" = "$FP2"

echo "== search-deny: hide the dead managed search tool, keep what is already denied =="
world deny1
run_setup --only search-deny
expect "first run exits 0"                          test "$RC" = 0
expect "tools.deny gains web_search"                python3 -c "import json,sys; d=json.load(open(sys.argv[1]))['tools']['deny']; sys.exit(0 if 'web_search' in d else 1)" "$W/home/.openclaw-easel/openclaw.json"
expect "an entry already denied is kept"            python3 -c "import json,sys; d=json.load(open(sys.argv[1]))['tools']['deny']; sys.exit(0 if 'exec_remote' in d else 1)" "$W/home/.openclaw-easel/openclaw.json"
expect "the profile setting is untouched"           python3 -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))['tools']['profile']=='full' else 1)" "$W/home/.openclaw-easel/openclaw.json"
expect "its own check prints PASS"                  has "^PASS search-deny" "$OUT"
n1=$(ncalls)
run_setup --only search-deny
expect "second run exits 0"                         test "$RC" = 0
expect "second run says already done"               has "^already done: search-deny" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world deny2
python3 - "$W/home/.openclaw-easel/openclaw.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); c["tools"]["deny"] = ["web_search", "exec_remote", "added_later"]
json.dump(c, open(sys.argv[1], "w"))
PY
run_setup --only search-deny
expect "an entry someone added later survives a rerun" python3 -c "import json,sys; d=json.load(open(sys.argv[1]))['tools']['deny']; sys.exit(0 if d==['web_search','exec_remote','added_later'] else 1)" "$W/home/.openclaw-easel/openclaw.json"

world deny3
python3 - "$W/home/.openclaw-easel/openclaw.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); c["tools"]["web"] = {"search": {"provider": "duckduckgo"}}
json.dump(c, open(sys.argv[1], "w"))
PY
run_setup --only search-deny
expect "a managed search provider makes the check FAIL" has "^FAIL search-deny" "$OUT"
expect "and the script exits non-zero"                  test "$RC" != 0

# ---------------------------------------------------------------------------------------------------
echo "== system-packages: Chinese and emoji fonts, PDF reader =="
world fonts1
run_setup --only system-packages
expect "first run exits 0"                          test "$RC" = 0
expect "all four packages were installed"           bash -c 'for p in fonts-noto-cjk fonts-noto-cjk-extra fonts-noto-color-emoji poppler-utils; do grep -qx $p "$1/dpkg.list" || exit 1; done' _ "$W"
expect "the font cache was refreshed after"         bash -c 'a=$(grep -n "apt-get install" "$1/calls.log" | head -1 | cut -d: -f1); b=$(grep -n "fc-cache" "$1/calls.log" | head -1 | cut -d: -f1); [ -n "$a" ] && [ -n "$b" ] && [ "$b" -gt "$a" ]' _ "$W"
expect "font weights, fixed paths and PDF tool all PASS" bash -c '[ "$(grep -c "^PASS system-packages" "$1")" -ge 4 ]' _ "$OUT"
expect "no FAIL line"                               bash -c '! grep -q "^FAIL" "$1"' _ "$OUT"
n1=$(ncalls)
run_setup --only system-packages
expect "second run says already done"               has "^already done: system-packages" "$OUT"
expect "second run changes nothing"                 test "$(ncalls)" = "$n1"

world fonts2
echo fonts-noto-cjk >> "$W/dpkg.list"; for f in Regular Bold; do echo x > "$W/fonts/NotoSansCJK-$f.ttc"; done
run_setup --only system-packages
expect "a partly installed machine installs only what is missing" bash -c 'l=$(grep "apt-get install" "$1/calls.log"); case $l in *" fonts-noto-cjk "*|*" fonts-noto-cjk") exit 1;; *fonts-noto-cjk-extra*poppler*|*poppler*) exit 0;; *) exit 1;; esac' _ "$W"

world fonts3
run_setup --only system-packages
rm -f "$W/fonts/NotoSansCJK-Bold.ttc"
run_setup --only system-packages
expect "a missing fixed font path is a FAIL (packages alone are not enough)" has "^FAIL system-packages" "$OUT"
expect "and the script exits non-zero"              test "$RC" != 0

echo "== display-font: LXGW WenKai Medium (issue 116), pinned by sha256, added beside the Noto fonts and nothing else touched =="
DF_URL=https://github.com/lxgw/LxgwWenKai/releases/download/v1.530/LXGWWenKai-Medium.ttf
DF_REAL_PIN=f4b8a34d1f838fe411540cb7c97b1c384ac9738a876c4104500bc42508b2312a
KEEPF='^(dpkg|noto-fonts|shell-profiles|local-bin|openclaw-workspaces|libtv-bin|libtv-home) '   # lines that must not move
world df1
run_setup --only system-packages            # the Noto fonts and the apt packages are in place first
run_check display-font
expect "the check fails first on a machine without the font" bash -c 'grep -q "^FAIL display-font" "$1" && [ "$2" != 0 ]' _ "$OUT" "$RC"
FPF1=$(fp | grep -E "$KEEPF" | sha256sum); n0=$(ncalls)
run_setup --only display-font
expect "first run exits 0"                          test "$RC" = 0
expect "the install branch ran, then the check passed" bash -c 'grep -q "^doing: display-font" "$1" && grep -q "^PASS display-font" "$1" && ! grep -q "^FAIL" "$1"' _ "$OUT"
expect "it made exactly two calls: one download from the versioned release address, then a scan of the font folder alone" bash -c 'got=$(tail -n +$(($2 + 1)) "$1/calls.log"); [ "$got" = "$(printf "curl %s\nfc-cache -f %s" "$3" "$1/dfonts")" ]' _ "$W" "$n0" "$DF_URL"
expect "the download is fresh, never resumed"       bash -c 'grep -qF "$2" "$1/curl-args.log" && ! grep -q -e " -C " -e "^-C " "$1/curl-args.log"' _ "$W" "$DF_URL"
expect "the font file is in its own folder, under its release name, the checked file" bash -c 'cmp -s "$1/dfonts/LXGWWenKai-Medium.ttf" "$1/font.good" && [ "$(ls "$1/dfonts")" = LXGWWenKai-Medium.ttf ]' _ "$W"
expect "the check says the family is in the font list" has "^PASS display-font:.*LXGW WenKai" "$OUT"
expect "no download is left in the temp folder"     bash -c '[ -z "$(ls -A "$1/tmp")" ]' _ "$W"
expect "the Noto fonts, the apt packages and every other fingerprint line are untouched" test "$(fp | grep -E "$KEEPF" | sha256sum)" = "$FPF1"
run_check system-packages
expect "the system-packages check still passes"     bash -c 'grep -q "^PASS system-packages" "$1" && ! grep -q "^FAIL" "$1" && [ "$2" = 0 ]' _ "$OUT" "$RC"
n1=$(ncalls); FPD1=$(fp | sha256sum)
run_setup --only display-font
expect "second run says already done"               has "^already done: display-font" "$OUT"
expect "second run downloads and scans nothing"     test "$(ncalls)" = "$n1"
expect "second run changes nothing the fingerprint covers" test "$(fp | sha256sum)" = "$FPD1"

world df2
run_setup --only system-packages
cp "$W/font.stale" "$W/font.served"; DF_STALE_SHA=$(sha256sum "$W/font.stale" | cut -d' ' -f1); n0=$(ncalls)
run_setup --only display-font
expect "a download with the wrong sha256 is refused, exit non-zero" bash -c 'grep -q "^FAIL display-font" "$1" && [ "$2" != 0 ]' _ "$OUT" "$RC"
expect "nothing was installed and the font cache was not scanned" bash -c '[ -z "$(ls -A "$1/dfonts" 2>/dev/null)" ] && ! tail -n +$(($2 + 1)) "$1/calls.log" | grep -q fc-cache' _ "$W" "$n0"
expect "the refusal prints the sha256 it got, the pinned one and says nothing was installed" bash -c 'grep -qF "$2" "$1" && grep -qF "$3" "$1" && grep -q "Nothing was installed" "$1"' _ "$OUT" "$DF_STALE_SHA" "$DF_SHA"
expect "the refused download was not kept"          bash -c '[ -z "$(ls -A "$1/tmp")" ]' _ "$W"

world df3
cp "$W/font.stale" "$W/font.served"
T_FONTSHA="" run_setup --only display-font
expect "against the real pin, a stand-in file is refused and the real pin is named" bash -c '[ "$2" != 0 ] && grep -qF "$3" "$1" && [ -z "$(ls -A "$4/dfonts" 2>/dev/null)" ]' _ "$OUT" "$RC" "$DF_REAL_PIN" "$W"

world df4
mkdir -p "$W/dfonts"; cp "$W/font.stale" "$W/dfonts/LXGWWenKai-Medium.ttf"
run_check display-font
expect "a different file under the font's name is a FAIL, not a pass" has "^FAIL display-font" "$OUT"
run_setup --only display-font
expect "a different file already in place is replaced by the checked one" bash -c '[ "$2" = 0 ] && cmp -s "$1/dfonts/LXGWWenKai-Medium.ttf" "$1/font.good"' _ "$W" "$RC"
cp "$W/font.stale" "$W/dfonts/LXGWWenKai-Medium.ttf"; cp "$W/font.stale" "$W/font.served"
run_setup --only display-font
expect "and when the download is wrong too, the file in place is left exactly as it was" bash -c '[ "$2" != 0 ] && cmp -s "$1/dfonts/LXGWWenKai-Medium.ttf" "$1/font.stale"' _ "$W" "$RC"

world df5
mkdir -p "$W/dfonts"; cp "$W/font.good" "$W/dfonts/LXGWWenKai-Medium.ttf"       # the right file, but the font list was never refreshed
run_setup --only display-font
expect "the right file that the font list does not show: only the cache is refreshed, nothing is downloaded" bash -c '[ "$2" = 0 ] && ! grep -q "^curl" "$1/calls.log" && grep -qxF "fc-cache -f $1/dfonts" "$1/calls.log" && grep -q "^PASS display-font:.*LXGW WenKai" "$3"' _ "$W" "$RC" "$OUT"

echo
echo "failures: $FAILS"
exit $FAILS
