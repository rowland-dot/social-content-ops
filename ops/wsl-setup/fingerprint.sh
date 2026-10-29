#!/usr/bin/env bash
# Prints one line per place that setup.sh touches: "<place> <hash of its content or listing>".
# Run it before and after a second setup run: identical output means the second run changed nothing.
#   bash ops/wsl-setup/fingerprint.sh
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=checks.sh
. "$HERE/checks.sh"

h() { sha256sum | cut -d' ' -f1; }
# names and sizes of every file under a folder, in a fixed order
listing() {
  [ -d "$1" ] || { echo "absent $1"; return 0; }
  find "$1" -type f 2>/dev/null | LC_ALL=C sort | while IFS= read -r f; do printf '%s %s\n' "$f" "$(stat -c %s "$f")"; done
}
filehash() { if [ -f "$1" ]; then h < "$1"; else echo absent; fi; }

printf 'dpkg %s\n' "$(dpkg-query -W -f='${Package} ${Version}\n' 2>/dev/null | LC_ALL=C sort | h)"
printf 'pip %s\n' "$("$PY" -m pip freeze 2>/dev/null | LC_ALL=C sort | h)"
printf 'openclaw-config %s\n' "$(filehash "$OC_CONFIG")"
printf 'models %s\n' "$({ listing "$MODEL_DIR"; listing "$REMBG_HOME"; listing "$(dirname "$RNNN_FILE")"; } | h)"
printf 'redbook-dir %s\n' "$(listing "$REDBOOK_DIR" | h)"
printf 'redbook-stub %s\n' "$(filehash "$REDBOOK_BIN")"
printf 'exclude %s\n' "$(filehash "$(exclude_file 2>/dev/null || echo /nonexistent)")"
printf 'libtv-bin %s\n' "$(filehash "$LIBTV_BIN")"
printf 'libtv-home %s\n' "$(listing "$HOME/.libtv" | h)"
printf 'display-font %s\n' "$(listing "$DISPLAY_FONT_DIR" | h)"
printf 'noto-fonts %s\n' "$(listing "$FONT_DIR" | h)"
# the places a vendor's own installer would write into (a PATH line in a shell profile, ~/.local/bin, an
# OpenClaw workspace notes file): none may ever change. Kept because LibTV's installer (issue 32) appends a PATH
# line to a shell profile unless told not to.
printf 'shell-profiles %s\n' "$(for f in .bashrc .profile .bash_profile .bash_login .zshrc .zprofile; do printf '%s %s\n' "$f" "$(filehash "$HOME/$f")"; done | h)"
printf 'local-bin %s\n' "$(listing "$HOME/.local/bin" | h)"
printf 'openclaw-workspaces %s\n' "$(for d in "$HOME"/.openclaw*/workspace; do listing "$d"; done | h)"
# the Remotion folder is thousands of files over the Windows mount; its top levels are what the installer decides
printf 'remotion %s\n' "$({ ls -1 "$REMOTION_DIR"; ls -1 "$REMOTION_DIR/node_modules"; ls -1 "$REMOTION_DIR/node_modules/@remotion"; } 2>/dev/null | h)"
