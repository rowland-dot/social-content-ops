"""Red/green check for issue 119: scripts/install_font.py installs one free Chinese font, on demand, only from a pinned
address and only when the font's own licence file is the SIL Open Font License 1.1 or the Apache License 2.0.

Run: python skills/builtin/xhs-reference-visual/install-font.test.py   (exit 0 = pass). Nothing touches the network or
this PC's fonts: the install root is a temporary folder and the downloader, the font-cache refresh and the family lookup
are stand-ins. tests/test_xhs_reference_visual_skill.py runs this file too, which is how CI collects it.

Seam (the issue's "Agreed seams", 1): the install command, as the function install_font() and the command line.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "scripts" / "install_font.py"

failures = []


def check(ok, message):
    if not ok:
        failures.append(message)


if not SCRIPT.is_file():
    print("FAIL the install command does not exist: skills/builtin/xhs-reference-visual/scripts/install_font.py")
    sys.exit(1)

spec = importlib.util.spec_from_file_location("install_font", SCRIPT)
install_font = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install_font)

PIN = "6d49995f5d8f1c7d476760a580ffb89ce1e52c5d"
OTHER_PIN = "0123456789abcdef0123456789abcdef01234567"
BASE = f"https://raw.githubusercontent.com/google/fonts/{PIN}/ofl/zcoolkuaile"
FONT_URL = f"{BASE}/ZCOOLKuaiLe-Regular.ttf"
LICENSE_URL = f"{BASE}/OFL.txt"
FONT_A = b"\x00\x01\x00\x00" + b"stand-in font A"
FONT_B = b"\x00\x01\x00\x00" + b"stand-in font B"
OFL = ("Copyright 2020 The ZCOOL KuaiLe Project Authors\n\n"
       "This Font Software is licensed under the SIL Open Font License, Version 1.1.\n"
       "This license is copied below, and is also available with a FAQ at: https://openfontlicense.org\n\n"
       "SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007\n").encode()
APACHE = b"                                 Apache License\n                           Version 2.0, January 2004\n"
CUSTOM = "本字体免费商用，无需授权，但不得转售字体文件。".encode()


class Net:
    """A stand-in downloader: serves what it is given, records every address asked for, 404s anything else."""

    def __init__(self, files):
        self.files, self.calls = dict(files), []

    def __call__(self, url):
        self.calls.append(url)
        if url not in self.files:
            raise OSError(f"404 Not Found: {url}")
        return self.files[url]


class Cache:
    """A stand-in for the font-cache refresh: records which folders it was asked to refresh."""

    def __init__(self):
        self.folders = []

    def __call__(self, folder):
        self.folders.append(Path(folder))


def family_of(path):
    return "Stand-In Family"


def tree(root):
    """Every file under root with its bytes, to see exactly what a run changed."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


def new_root():
    root = Path(tempfile.mkdtemp(prefix="install-font-")) / "on-demand"
    return root


def run(root, net, cache=None, font_url=FONT_URL, license_url=LICENSE_URL, post="Northwind November post 03"):
    cache = cache if cache is not None else Cache()
    try:
        result = install_font.install_font(font_url, license_url, post, root, fetch=net, refresh=cache,
                                           family=family_of, today="2026-10-28")
        return result, None, cache
    except install_font.Refused as why:
        return None, str(why), cache


# 1. an OFL font installs into its own folder with its licence and a source note; fc-cache is asked for that folder only
root = new_root()
untouched = root / "lxgw-wenkai" / "LXGWWenKai-Medium.ttf"  # a font that is already there must not change
untouched.parent.mkdir(parents=True)
untouched.write_bytes(b"already installed")
before = tree(root)
net = Net({FONT_URL: FONT_A, LICENSE_URL: OFL})
result, why, cache = run(root, net)
check(why is None, f"an OFL font on a pinned address was refused: {why}")
if why is None:
    folder = root / "zcoolkuaile-regular"
    after = tree(root)
    added = sorted(set(after) - set(before))
    check(added == ["zcoolkuaile-regular/OFL.txt", "zcoolkuaile-regular/ZCOOLKuaiLe-Regular.ttf",
                    "zcoolkuaile-regular/source.json"],
          f"the font folder holds {added}, not the font, its licence and the source note")
    check({k: v for k, v in after.items() if k in before} == before, "a file outside the font's own folder changed")
    check(after.get("zcoolkuaile-regular/ZCOOLKuaiLe-Regular.ttf") == FONT_A, "the installed file is not the downloaded font")
    check(after.get("zcoolkuaile-regular/OFL.txt") == OFL, "the licence file beside the font is not the downloaded licence")
    note = json.loads(after.get("zcoolkuaile-regular/source.json", b"{}"))
    check(note.get("address") == FONT_URL, f"the source note's address is {note.get('address')!r}")
    check(note.get("sha256") == hashlib.sha256(FONT_A).hexdigest(), f"the source note's sha256 is {note.get('sha256')!r}")
    check(note.get("license") == "SIL Open Font License 1.1", f"the source note's licence is {note.get('license')!r}")
    check(note.get("license_address") == LICENSE_URL, f"the source note's licence address is {note.get('license_address')!r}")
    check(note.get("date") == "2026-10-28", f"the source note's date is {note.get('date')!r}")
    check(note.get("post") == "Northwind November post 03", f"the source note's post is {note.get('post')!r}")
    check(cache.folders == [folder], f"the font cache was refreshed for {cache.folders}, not for the font's folder only")
    check(result.get("status") == "installed", f"the first run reports {result.get('status')!r}, not installed")
    check(result.get("font_file") == "ZCOOLKuaiLe-Regular.ttf", f"the file name to put in typed-styling.json is {result.get('font_file')!r}")
    check(result.get("family") == "Stand-In Family", f"the family name reported is {result.get('family')!r}")
    check(sorted(net.calls) == sorted([FONT_URL, LICENSE_URL]), f"one font and its licence were downloaded, got {net.calls}")

    # 2. the same font again: already done, nothing downloaded, nothing changed
    net2 = Net({FONT_URL: FONT_A, LICENSE_URL: OFL})
    again, why2, _ = run(root, net2)
    check(why2 is None and again.get("status") == "already done", f"the second run said {why2 or again.get('status')!r}, not already done")
    check(net2.calls == [], f"the second run downloaded {net2.calls}")
    check(tree(root) == after, "the second run changed a file")

    # 3. a different file under the same name (another commit): refused, the installed font left as it was
    other_url = f"https://raw.githubusercontent.com/google/fonts/{OTHER_PIN}/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf"
    other_license = f"https://raw.githubusercontent.com/google/fonts/{OTHER_PIN}/ofl/zcoolkuaile/OFL.txt"
    net3 = Net({other_url: FONT_B, other_license: OFL})
    _, why3, _ = run(root, net3, font_url=other_url, license_url=other_license)
    check(why3 is not None, "a different file under the same name was installed over the first")
    check(why3 is None or "ZCOOLKuaiLe-Regular.ttf" in why3, f"the refusal does not say which file clashes: {why3}")
    check(tree(root) == after, "the refused run changed a file")

# 4. an Apache 2.0 licence is accepted and recorded as such
root = new_root()
apache_license = f"{BASE}/LICENSE.txt"
result, why, _ = run(root, Net({FONT_URL: FONT_A, apache_license: APACHE}), license_url=apache_license)
check(why is None, f"an Apache 2.0 font was refused: {why}")
if why is None:
    note = json.loads((root / "zcoolkuaile-regular" / "source.json").read_text(encoding="utf-8"))
    check(note.get("license") == "Apache License 2.0", f"the Apache font's licence is recorded as {note.get('license')!r}")
    check((root / "zcoolkuaile-regular" / "LICENSE.txt").read_bytes() == APACHE, "the Apache licence file is not beside the font")

# 5. a custom "免费商用" licence text and a missing licence are both refused, with nothing installed and the reason printed
root = new_root()
for label, files, license_url in (
        ("a custom 免费商用 licence text", {FONT_URL: FONT_A, LICENSE_URL: CUSTOM}, LICENSE_URL),
        ("a licence address that does not exist", {FONT_URL: FONT_A}, LICENSE_URL),
        ("no licence address at all", {FONT_URL: FONT_A}, ""),
        ("an empty licence file", {FONT_URL: FONT_A, LICENSE_URL: b""}, LICENSE_URL)):
    cache = Cache()
    _, why, cache = run(root, Net(files), cache=cache, license_url=license_url)
    check(why, f"{label} was not refused")
    check(not root.exists() or not tree(root), f"{label}: something was installed: {sorted(tree(root))}")
    check(cache.folders == [], f"{label}: the font cache was refreshed")
_, why, _ = run(root, Net({FONT_URL: FONT_A, LICENSE_URL: CUSTOM}))
check(why and "Open Font License" in why and "Apache" in why, f"the licence refusal does not name the two allowed licences: {why}")

# 6. an address that is not pinned (a branch) is refused before anything is downloaded
root = new_root()
for label, url in (("main", f"https://raw.githubusercontent.com/google/fonts/main/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf"),
                   ("master", f"https://raw.githubusercontent.com/google/fonts/master/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf"),
                   ("refs/heads/main", "https://raw.githubusercontent.com/google/fonts/refs/heads/main/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf"),
                   ("plain http", f"http://raw.githubusercontent.com/google/fonts/{PIN}/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf"),
                   ("another host", f"https://example.com/{PIN}/ZCOOLKuaiLe-Regular.ttf")):
    net = Net({url: FONT_A, LICENSE_URL: OFL})
    _, why, _ = run(root, net, font_url=url)
    check(why, f"the {label} font address was not refused")
    check(net.calls == [], f"the {label} font address was refused only after downloading {net.calls}")
    check(not root.exists() or not tree(root), f"the {label} font address left files behind")
main_license = "https://raw.githubusercontent.com/google/fonts/main/ofl/zcoolkuaile/OFL.txt"
net = Net({FONT_URL: FONT_A, main_license: OFL})
_, why, _ = run(root, net, license_url=main_license)
check(why and net.calls == [], "a licence address on main was not refused before downloading")
release = "https://github.com/lxgw/LxgwWenKai/releases/download/v1.330/LXGWWenKai-Medium.ttf"
release_license = "https://raw.githubusercontent.com/lxgw/LxgwWenKai/v1.330/OFL.txt"
result, why, _ = run(new_root(), Net({release: FONT_A, release_license: OFL}), font_url=release, license_url=release_license)
check(why is None, f"a release address with a version tag was refused: {why}")

# 7. only a single .ttf / .otf / .ttc file: an archive address, or a download that is not a font, is refused
root = new_root()
for label, url, body in (("a zip", f"{BASE}/ZCOOLKuaiLe.zip", FONT_A),
                         ("a woff2", f"{BASE}/ZCOOLKuaiLe.woff2", FONT_A),
                         ("a web page saved as .ttf", FONT_URL, b"<html>Not Found</html>")):
    _, why, _ = run(root, Net({url: body, LICENSE_URL: OFL}), font_url=url)
    check(why, f"{label} was not refused")
    check(not root.exists() or not tree(root), f"{label}: something was installed")
for suffix, magic in ((".otf", b"OTTO"), (".ttc", b"ttcf")):
    url = f"{BASE}/Some-Regular{suffix}"
    result, why, _ = run(new_root(), Net({url: magic + b"stand-in", LICENSE_URL: OFL}), font_url=url)
    check(why is None, f"a single {suffix} file was refused: {why}")

# 8. the command line: an address on main is refused with exit 1 and the reason on screen, with no network and nothing installed
root = new_root()
env = {**os.environ, "EASEL_ONDEMAND_FONT_ROOT": str(root)}
proc = subprocess.run(
    [sys.executable, str(SCRIPT), "--font-url", "https://raw.githubusercontent.com/google/fonts/main/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf",
     "--license-url", "https://raw.githubusercontent.com/google/fonts/main/ofl/zcoolkuaile/OFL.txt", "--post", "Northwind November post 03"],
    capture_output=True, text=True, timeout=60, env=env)
check(proc.returncode == 1, f"the command line exited {proc.returncode} on an address on main, not 1")
check("REFUSED" in proc.stderr and "main" in proc.stderr, f"the command line did not print why: {proc.stderr.strip()[-300:]}")
check(not root.exists() or not tree(root), "the command line installed something from an address on main")

for line in failures:
    print("FAIL", line)
print("PASS" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
