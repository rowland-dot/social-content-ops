#!/usr/bin/env bash
# Says whether any secret from a login-credential file occurs in the given files or folders.
# It prints only the secret's key name and the file's path, never a value or any part of one.
#
#   bash ops/wsl-setup/credential-leak-check.sh CREDENTIAL.json TARGET [TARGET ...]
#
# A secret is a string value of 20+ characters whose key name holds "token", "secret", "private" or
# "password" (expiry dates and public keys are not secrets). Targets are files or folders (searched all the
# way down). Exit status: 0 clean, 1 a secret was found, 2 the check itself could not run (no arguments, an
# unreadable credential file, one with no secret in it, a missing target) so it proves nothing.
set -u
[ $# -ge 2 ] || { echo "usage: credential-leak-check.sh CREDENTIAL.json TARGET [TARGET ...]" >&2; exit 2; }
exec python3 - "$@" <<'PY'
import json, os, re, sys

cred, targets = sys.argv[1], sys.argv[2:]
try:
    data = json.load(open(cred, encoding="utf-8"))
except (OSError, ValueError) as e:
    print("cannot read the credential file %s: %s" % (cred, type(e).__name__), file=sys.stderr)
    sys.exit(2)

SECRET_KEY = re.compile(r"token|secret|private|password", re.I)
NOT_SECRET = re.compile(r"expires|_at$|type", re.I)
secrets = {}  # dotted key path -> value (kept in memory only)

def walk(x, path):
    if isinstance(x, dict):
        for k, v in x.items():
            walk(v, path + [str(k)])
    elif isinstance(x, str) and len(x) >= 20 and path:
        key = path[-1]
        if SECRET_KEY.search(key) and not NOT_SECRET.search(key):
            secrets[".".join(path)] = x.encode("utf-8")

walk(data, [])
if not secrets:
    print("the credential file %s holds no secret value, so this check would see nothing" % cred, file=sys.stderr)
    sys.exit(2)

files = []
for t in targets:
    if os.path.isfile(t):
        files.append(t)
    elif os.path.isdir(t):
        for root, _, names in os.walk(t):
            files.extend(os.path.join(root, n) for n in names)
    else:
        print("target not found: %s" % t, file=sys.stderr)
        sys.exit(2)

leaks, unread = [], 0
for f in sorted(files):
    try:
        blob = open(f, "rb").read()
    except OSError:
        unread += 1
        continue
    for name, val in secrets.items():
        if val in blob:
            leaks.append((name, f))

for name, f in leaks:
    print("LEAKED: %s occurs in %s" % (name, f))
if leaks:
    sys.exit(1)
print("CLEAN: none of %d secret values occurs in %d files (%d could not be read)" % (len(secrets), len(files), unread))
PY
