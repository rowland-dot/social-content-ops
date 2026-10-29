"""Building the candidate report: download a newer LibTV version twice, read it as files, say what it changes."""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "shared" / "scripts"))
from private_work import missing_message, private_file  # noqa: E402

from libtv_candidate import (
    GENERATION_WORDS,
    SELF_CHANGE,
    diff_commands,
    diff_docs,
    installer_channels,
    is_listed,
    listed_paid_commands,
    paid_candidates,
    program_bytes,
    program_versions,
    read_commands,
    zip_members,
)
from libtv_detect import Context, VERSION_CHANNEL
from libtv_http import FetchError, download
from libtv_state import Store

PACKAGES = ("libtv-cli-skill.zip", "libtv-linux-x64.zip")
VENDOR_DIR = Path("skills") / "builtin" / "libtv-cli" / "references" / "vendor"
PATCH_LINES_SHOWN = 40
DOC_LINES_SHOWN = 12


def candidate_dir(store: Store, version: str) -> Path:
    return store.path / "candidates" / version


def _ticks(path: tuple[str, ...]) -> str:
    return "`" + " ".join(path) + "`"


def _vendored_docs(root: Path) -> dict[str, bytes] | None:
    folder = root / VENDOR_DIR
    if not folder.is_dir():
        return None
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def fetch_twice(ctx: Context, store: Store, version: str) -> tuple[bool, dict, str]:
    """Download both packages of VERSION into the store, each twice. Returns (stable, facts, message)."""
    cdir = candidate_dir(store, version)
    facts: dict[str, dict] = {}
    unstable: dict[str, list[str]] = {}
    for name in PACKAGES:
        url = f"{ctx.pin.files_base.rstrip('/')}/cli/{version}/{name}"
        try:
            sha, size, last_modified = download(url, cdir / name, timeout=ctx.download_timeout)
            again, _size, _lm = download(url, None, timeout=ctx.download_timeout)
        except FetchError as err:
            shutil.rmtree(cdir, ignore_errors=True)
            if "HTTP 404" in str(err):
                return False, {}, f"LibTV {version} is not published: {url} answers HTTP 404."
            return False, {}, f"Could not fetch LibTV {version}: {err}"
        facts[name] = {"sha256": sha, "size": size, "last_modified": last_modified}
        if again != sha:
            unstable[name] = [sha, again]
    if unstable:
        shutil.rmtree(cdir, ignore_errors=True)
        lines = [f"LibTV {version}: the bytes differ between two fetches, so this version is not offered for approval."]
        lines += [f"- {n}: first fetch sha256 {a}, second fetch sha256 {b}" for n, (a, b) in unstable.items()]
        lines.append("A file at a versioned address should never change between two requests. Nothing was installed.")
        return False, {"unstable": unstable}, "\n".join(lines)
    return True, facts, ""


def build_report(ctx: Context, store: Store, root: Path, version: str, facts: dict) -> str:
    cdir = candidate_dir(store, version)
    skill_members = zip_members((cdir / PACKAGES[0]).read_bytes())
    program = program_bytes(cdir / PACKAGES[1])
    out: list[str] = [
        f"# LibTV {version}: what it would change",
        f"Read from files only: nothing was run, installed or logged in to. Pinned now: {ctx.pin.version}.",
        "",
        "## Files",
    ]
    for name in PACKAGES:
        f = facts[name]
        out.append(f"- {name}: {f['size']} bytes, sha256 {f['sha256']}, Last-Modified {f['last_modified'] or 'not given'}")
    versions: list[str] = []
    if program is None:
        out.append("- The program package holds no libtv-linux-x64/libtv program.")
    else:
        out.append(f"- The program inside: {len(program)} bytes, sha256 {hashlib.sha256(program).hexdigest()}")
        versions = program_versions(program)
        note = f" (does not match the published version {version})" if versions and version not in versions else ""
        out.append(f"- Version strings found in the program: {', '.join(versions) or 'none found'}{note}")

    channels = installer_channels(skill_members)
    if not channels:
        out.append(f"- The candidate's installer names no version channel (the pin follows channel {VERSION_CHANNEL}).")
    else:
        for channel in channels:
            flag = "the channel the pin follows" if channel == VERSION_CHANNEL else f"NOT {VERSION_CHANNEL}, the channel the pin follows"
            out.append(f"- The candidate's installer names channel {channel} ({flag}).")

    out += ["", "## Commands (read from the program's embedded source, by full command path)"]
    cmd_diff = None
    base_zip = store.pinned_copy(ctx.pin.version)
    if not base_zip.is_file():
        out.append("Not built: no kept copy of the pinned package to compare with. Run `keep-pin` first.")
    else:
        old = read_commands(program_bytes(base_zip) or b"")
        new = read_commands(program or b"")
        if old is None or new is None:
            which = "pinned" if old is None else "candidate"
            out.append(f"Not built: no command tree could be read from the {which} program.")
        else:
            cmd_diff = diff_commands(old, new)
            lines = []
            for p in cmd_diff.added:   # a new command's options are listed with it, not one line each
                opts = ", ".join(new[p])
                lines.append(f"- Added command {_ticks(p)}" + (f" (options: {opts})" if opts else ""))
            lines += [f"- Removed command {_ticks(p)}" for p in cmd_diff.removed]
            lines += [f"- Added option `{' '.join(p)} {flag}`" for p, flag in cmd_diff.options_added if p in old]
            lines += [f"- Removed option `{' '.join(p)} {flag}`" for p, flag in cmd_diff.options_removed if p in new]
            out += lines or ["No command changes."]

    out += ["", "## Documents (compared with the vendored copy)"]
    base_docs = _vendored_docs(root)
    if base_docs is None:
        out.append("Not built: the vendored folder is missing, so every document counts as added.")
        base_docs = {}
    docs = diff_docs(base_docs, skill_members)
    for label, names in (("Added", docs.added), ("Removed", docs.removed), ("Changed", docs.changed)):
        if names:
            out.append(f"{label}: {', '.join(names)}")
    if not (docs.added or docs.removed or docs.changed):
        out.append("No document changes.")
    full_patch = []
    for name, patch in docs.patches.items():
        full_patch += patch
        out += ["", f"### {name}", "```diff", *patch[:PATCH_LINES_SHOWN]]
        if len(patch) > PATCH_LINES_SHOWN:
            out.append(f"... {len(patch) - PATCH_LINES_SHOWN} more lines in docs.diff")
        out.append("```")
    (cdir / "docs.diff").write_text("\n".join(full_patch) + "\n", encoding="utf-8")

    risky = [(n, line) for n, line in docs.added_lines if SELF_CHANGE.search(line)]
    out.append("")
    if risky:
        out.append(f"Self-update or install instructions in added document lines ({len(risky)}):")
        out += [f"- {n}: {line.strip()[:200]}" for n, line in risky[:DOC_LINES_SHOWN]]
    else:
        out.append("Self-update or install instructions in added document lines: none")

    out += [""] + paid_section(root, cmd_diff, docs)
    return "\n".join(out)


def paid_section(root: Path, cmd_diff, docs) -> list[str]:
    candidates = paid_candidates(cmd_diff) if cmd_diff is not None else []
    mentions = [(n, line) for n, line in docs.added_lines if GENERATION_WORDS.search(line)]
    rules = private_file("CLAUDE.md", root)
    try:
        listed = listed_paid_commands(rules.read_text(encoding="utf-8")) if rules else None
    except OSError:
        listed = None
    if candidates:
        head = ["## Paid-run section"]
        for path, flag in candidates:
            what = f"Added command {_ticks(path)}" if flag is None else f"Added option `{' '.join(path)} {flag}`"
            if listed is None:
                verdict = (missing_message("The list of paid LibTV commands") if rules is None
                           else "CLAUDE.md's list could not be read.")
            elif is_listed((path, flag), listed):
                verdict = "On CLAUDE.md's list."
            else:
                verdict = "NOT on CLAUDE.md's list: add it before approving this version."
            head.append(f"- {what}: can start a generation. {verdict}")
    elif cmd_diff is None:
        head = ["## Paid-run section: not built (the command comparison was not built)"]
    else:
        head = ["## Paid-run section: none in the command tree",
                "No added command or option that can start a generation was found (read by name)."]
    if mentions:
        head.append(f"Added document lines that mention generating ({len(mentions)}):")
        head += [f"- {n}: {line.strip()[:200]}" for n, line in mentions[:DOC_LINES_SHOWN]]
    return head
