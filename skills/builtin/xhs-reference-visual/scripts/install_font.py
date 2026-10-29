#!/usr/bin/env python3
"""Install ONE free Chinese font on demand (issue 119), for a photo-scene post whose A/B/C typeface options need it.

    python3 install_font.py --font-url <pinned address of one .ttf/.otf/.ttc> \
        --license-url <pinned address of that font's own licence file> --post "<the post this is for>"

What it refuses (nothing is installed, the reason is printed, exit 1):
  - an address that is not pinned to a commit sha or a version tag (a branch such as main or master moves);
  - a licence file that is not the SIL Open Font License 1.1 or the Apache License 2.0 (a project's own "free for
    commercial use" statement, or no licence file, goes to the owner);
  - anything that is not a single .ttf / .otf / .ttc file;
  - a different file already installed under the same name.
What it does: downloads the font and its licence fresh, writes both and a source note (address, sha256, licence,
date, post) into /usr/local/share/fonts/on-demand/<font>/, refreshes the font cache for that folder only, and prints the
family name and the file name to put in typed-styling.json. Run twice with the same address it says "already done" and
downloads nothing. It never touches any other folder, the Noto fonts, LXGW WenKai or an apt package.

The install root is the setting EASEL_ONDEMAND_FONT_ROOT (or --root); xhs-note-creator's text_on_image.py reads the same
setting to find the font by its bare file name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

DEFAULT_ROOT = "/usr/local/share/fonts/on-demand"
MAX_BYTES = 60 * 1024 * 1024
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
FONT_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"ttcf", b"true")

_SHA = r"[0-9a-f]{40}"
# shortcut: a tag is told from a branch only by its shape (digits and dots, e.g. v1.330 or Name-v1.330); a branch named
# like a version would pass. Upgrade to a GitHub API check if a font ever comes from such a repository.
_TAG = r"(?:[A-Za-z][\w-]*-)?v?\d+(?:\.\d+)+"
PINNED = [
    re.compile(rf"https://raw\.githubusercontent\.com/[\w.-]+/[\w.-]+/(?:{_SHA}|{_TAG})/[^?#]+"),
    re.compile(rf"https://github\.com/[\w.-]+/[\w.-]+/raw/(?:{_SHA}|{_TAG})/[^?#]+"),
    re.compile(rf"https://github\.com/[\w.-]+/[\w.-]+/releases/download/{_TAG}/[^/?#]+"),
]
# shortcut: the licence is recognised by its title text, not by comparing the whole file; a file that names one of
# the two titles but changes its terms would pass. Upgrade to a hash list of the official texts if that ever matters.
LICENSES = [
    ("SIL Open Font License 1.1", re.compile(r"sil open font license,? version 1\.1"), "OFL.txt"),
    ("Apache License 2.0", re.compile(r"apache license,? version 2\.0"), "LICENSE.txt"),
]
ALLOWED = "the SIL Open Font License 1.1 or the Apache License 2.0"


class Refused(Exception):
    """The install was stopped; nothing was installed."""


def fetch_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - the address was checked as pinned https
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Refused(f"{url} is larger than {MAX_BYTES // (1024 * 1024)} MB")
    return data


def refresh_font_cache(folder: Path) -> None:
    subprocess.run(["fc-cache", "-f", str(folder)], check=True, capture_output=True, timeout=300)


def family_name(font_path: Path) -> str | None:
    try:
        out = subprocess.run(["fc-list", "-f", "%{file}\t%{family}\n"], capture_output=True, text=True, timeout=120).stdout
    except OSError:
        return None
    for line in out.splitlines():
        file, _, family = line.partition("\t")
        if file == str(font_path):
            return family.split(",")[0].strip()
    return None


def _require_pinned(label: str, url: str) -> None:
    if not url:
        raise Refused(f"no {label} address was given")
    if not any(p.fullmatch(url) for p in PINNED) or ".." in urllib.parse.urlsplit(url).path:
        raise Refused(
            f"the {label} address is not pinned: {url}. Use a GitHub raw or release address with a commit sha or a "
            "version tag in it (not main or master), because a branch can change under the install.")


def _font_file_name(url: str) -> str:
    name = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])
    if not name.lower().endswith(FONT_SUFFIXES):
        raise Refused(f"{url} is not a single .ttf, .otf or .ttc file (one font file per call)")
    if not re.fullmatch(r"[\w.\[\]-]+", name):
        raise Refused(f"the font file name {name!r} has characters this command will not write")
    return name


def _licence_of(text: bytes) -> tuple[str, str]:
    flat = re.sub(r"\s+", " ", text.decode("utf-8", errors="replace").lower())
    for name, pattern, file_name in LICENSES:
        if pattern.search(flat):
            return name, file_name
    raise Refused(f"the font's own licence file is not {ALLOWED}. Fonts under any other licence (including a project's "
                  "own free-for-commercial-use statement) are not installed; ask the owner.")


def install_font(font_url: str, license_url: str, post: str, root, fetch=fetch_url, refresh=refresh_font_cache,
                 family=family_name, today: str | None = None) -> dict:
    root = Path(root)
    _require_pinned("font", font_url)
    _require_pinned("licence", license_url)
    file_name = _font_file_name(font_url)
    folder = root / re.sub(r"[^a-z0-9]+", "-", Path(file_name).stem.lower()).strip("-")
    target = folder / file_name

    # Already installed from this address and untouched since: nothing to download.
    note_path = folder / "source.json"
    if target.is_file() or note_path.is_file():
        try:
            note = json.loads(note_path.read_text(encoding="utf-8"))
            same = (note["address"] == font_url and target.is_file()
                    and hashlib.sha256(target.read_bytes()).hexdigest() == note["sha256"])
        except (OSError, ValueError, KeyError):
            same = False
        if not same:
            raise Refused(f"{target} is already there and is not the file at {font_url}; it is left untouched. "
                          "Remove it by hand first if it should be replaced.")
        return {"status": "already done", "folder": folder, "font_file": file_name, "family": family(target)}

    try:
        license_bytes = fetch(license_url)
    except OSError as err:
        raise Refused(f"the font's licence file could not be downloaded from {license_url} ({err}); a font with no "
                      "licence file is not installed") from err
    license_name, license_file = _licence_of(license_bytes)
    font_bytes = fetch(font_url)
    if not font_bytes.startswith(FONT_MAGIC):
        raise Refused(f"{font_url} did not download as a font file (it does not start like a .ttf, .otf or .ttc)")

    folder.mkdir(parents=True, exist_ok=True)
    (folder / license_file).write_bytes(license_bytes)
    target.write_bytes(font_bytes)
    note_path.write_text(json.dumps({
        "address": font_url, "sha256": hashlib.sha256(font_bytes).hexdigest(), "license": license_name,
        "license_address": license_url, "date": today or date.today().isoformat(), "post": post,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    warning = None
    try:
        refresh(folder)
    except (OSError, subprocess.SubprocessError) as err:
        warning = f"the font cache was not refreshed ({err}); the font file is in place and text_on_image.py can still use it"
    return {"status": "installed", "folder": folder, "font_file": file_name, "family": family(target), "warning": warning}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install one free Chinese font on demand (issue 119).")
    ap.add_argument("--font-url", required=True, help="pinned address of one .ttf/.otf/.ttc file")
    ap.add_argument("--license-url", default="", help="pinned address of that font's own licence file")
    ap.add_argument("--post", required=True, help="the post this font is installed for (recorded in the source note)")
    ap.add_argument("--root", default=os.environ.get("EASEL_ONDEMAND_FONT_ROOT", DEFAULT_ROOT))
    args = ap.parse_args(argv)
    try:
        result = install_font(args.font_url, args.license_url, args.post, args.root)
    except Refused as why:
        print(f"REFUSED: {why}", file=sys.stderr)
        return 1
    print(f"{result['status']}: {result['folder'] / result['font_file']}")
    print(f"family: {result['family'] or '(fc-list does not list it yet)'}")
    print(f"font_file for typed-styling.json: {result['font_file']}")
    if result.get("warning"):
        print(f"WARN: {result['warning']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
