#!/usr/bin/env python3
"""Says whether a folder holds exactly the files of LibTV's skill package, byte for byte.

    python3 ops/wsl-setup/libtv-vendor-compare.py SOURCE FOLDER

SOURCE is LibTV's own package (libtv-cli-skill.zip) or a sha256sum-style list of it
(docs/vendored/libtv-cli-1.1.3-files.sha256: "<sha256>  <relative path>" per line).
FOLDER is the vendored copy (skills/builtin/libtv-cli/references/vendor).

Exit status: 0 the same files with the same bytes; 1 a file is missing, extra or changed (each is named);
2 the comparison could not run (unreadable source, no files in the source, no such folder), which proves nothing.
"""

import hashlib
import sys
import zipfile
from pathlib import Path


def cannot(why):
    print("cannot compare: " + why, file=sys.stderr)
    sys.exit(2)


def read_source(source):
    """{relative path: sha256} for everything the package holds."""
    if not source.is_file():
        cannot("no such source file: %s" % source)
    try:
        if zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as z:
                return {i.filename: hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.is_dir()}
        want = {}
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, name = line.split("  ", 1)
                want[name] = digest
        return want
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        cannot("the source %s is unreadable (%s)" % (source, type(e).__name__))


def main(argv):
    if len(argv) != 3:
        cannot("usage: libtv-vendor-compare.py SOURCE FOLDER")
    source, folder = Path(argv[1]), Path(argv[2])
    want = read_source(source)
    if not want:
        cannot("the source %s lists no files, so every folder would look wrong or empty alike" % source)
    if not folder.is_dir():
        cannot("no such folder: %s" % folder)
    have = {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file()
    }
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    changed = sorted(n for n in set(want) & set(have) if want[n] != have[n])
    for n in missing:
        print("MISSING: %s" % n)
    for n in extra:
        print("EXTRA: %s" % n)
    for n in changed:
        print("CHANGED: %s" % n)
    if missing or extra or changed:
        print("DIFFERENT: %d missing, %d extra, %d changed" % (len(missing), len(extra), len(changed)))
        return 1
    print("SAME: %d files, byte for byte" % len(want))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
