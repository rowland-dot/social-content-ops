"""The owner's answers to the gate, and what a yes writes.

A yes books a ready-filled issue in `.scratch/easel-setup-gaps/issues/`. It moves no pin, installs nothing and
touches no vendored file: that is the booked issue's work, done through the issue pipeline after triage.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from libtv_candidate import program_bytes
from libtv_detect import Finding, Pin, Report
from libtv_report import PACKAGES, candidate_dir
from libtv_state import Store

ISSUES_DIR = Path(".scratch") / "easel-setup-gaps" / "issues"
SOURCE_NOTE = Path("docs") / "vendored" / "libtv-cli-source.md"
GATE_COMMAND = "python ops/libtv-update-gate/libtv_gate.py"


def apply_answers(report: Report, state: dict) -> None:
    """A new version the owner has booked or declined stops being offered; one whose files are unstable is never offered."""
    booked, declined, unstable = state.get("booked", {}), set(state.get("declined", [])), state.get("unstable", {})
    kept = []
    for finding in report.findings:
        if finding.kind == "new-version":
            version = finding.extra["version"]
            if version in booked:
                report.info.append(f"LibTV {version} is booked as {booked[version]['issue']}; the pin moves in that issue.")
                continue
            if version in declined:
                report.info.append(f"LibTV {version} was declined; it is shown again only if the channel moves past it.")
                continue
            if version in unstable:
                finding = Finding(
                    "candidate-unstable",
                    f"LibTV {version}: its files differ between two fetches, so it is not offered for approval.",
                    {"version": version},
                )
        kept.append(finding)
    report.findings = kept


def decline(store: Store, version: str) -> str:
    state = store.load()
    declined = state.setdefault("declined", [])
    if version not in declined:
        declined.append(version)
    store.save(state)
    return f"Declined LibTV {version}: it is not shown again unless the version channel moves past it."


def next_issue_number(issues: Path) -> int:
    numbers = [int(m.group(1)) for p in issues.glob("*.md") if (m := re.match(r"(\d+)-", p.name))]
    return max(numbers, default=0) + 1


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _note_section(root: Path) -> str:
    try:
        text = (root / SOURCE_NOTE).read_text(encoding="utf-8")
    except OSError:
        return f"(`{SOURCE_NOTE.as_posix()}` could not be read; its \"Moving to a newer version\" section is the list.)"
    parts = text.split("## Moving to a newer version", 1)
    if len(parts) < 2:
        return f"(`{SOURCE_NOTE.as_posix()}` has no \"Moving to a newer version\" section.)"
    body = parts[1].split("\n## ", 1)[0].strip()
    return "\n".join("> " + line if line else ">" for line in body.splitlines())


def issue_text(pin: Pin, store: Store, root: Path, version: str, report_text: str) -> str:
    cdir = candidate_dir(store, version)
    program_zip = (cdir / PACKAGES[1]).read_bytes()
    skill_zip = (cdir / PACKAGES[0]).read_bytes()
    inner = program_bytes(cdir / PACKAGES[1]) or b""
    kept = store.pinned_copy(pin.version)
    paid = report_text.split("## Paid-run section", 1)
    paid_block = "## Paid-run section" + paid[1].rstrip() if len(paid) == 2 else "## Paid-run section: not found in the report"
    report_body = paid[0].rstrip()
    if kept.is_file():
        rollback = (
            f"Revert the pin change in git, then run the setup step from the kept, checked copy of the pinned package "
            f"(it does not depend on LibTV keeping old folders up):\n\n"
            f"    LIBTV_ZIP_FILE=<the kept copy, {kept}> bash ops/wsl-setup/setup.sh --only libtv\n"
        )
    else:
        rollback = (
            f"No kept copy of the pinned {pin.version} package exists yet. Before the move, run "
            f"`{GATE_COMMAND} keep-pin` so a rollback does not depend on LibTV keeping old folders up; then "
            f"revert the pin change in git and run `LIBTV_ZIP_FILE=<that copy> bash ops/wsl-setup/setup.sh --only libtv`.\n"
        )
    return f"""Status: needs-triage

## Action

Move Easel's pinned LibTV CLI from {pin.version} to {version}, as one change: the two pins, the download address, the
vendored skill files and the notes that record them. Written ready-filled by the LibTV update gate (issue 37) after the owner's
yes through the question tool. The gate read files only: it installed nothing, ran no LibTV program and used no login.

## Pins and files to move

- `LIBTV_ZIP_SHA256` in `ops/wsl-setup/checks.sh`: {pin.program_zip_sha256} -> {_sha(program_zip)} (the program package)
- `LIBTV_SHA256` in `ops/wsl-setup/checks.sh`: {pin.program_sha256} -> {_sha(inner)} (the program inside it)
- `LIBTV_URL` in `ops/wsl-setup/setup.sh`: {pin.files_base.rstrip('/')}/cli/{pin.version}/libtv-linux-x64.zip -> {pin.files_base.rstrip('/')}/cli/{version}/libtv-linux-x64.zip
- the vendored skill folder `skills/builtin/libtv-cli/references/vendor/`: replaced by the files of the {version} skill
  package (package sha256 {_sha(skill_zip)}), and `docs/vendored/libtv-cli-{pin.version}-files.sha256` renamed and
  rewritten for {version}
- `docs/vendored/libtv-cli-source.md`, and the tests that pin the old values

What the source note says moves together:

{_note_section(root)}

{paid_block}

## Rollback

{rollback}
## The report

{report_body}
"""


def write_issue(pin: Pin, store: Store, root: Path, version: str, report_text: str) -> Path:
    issues = root / "work" / ISSUES_DIR
    issues.mkdir(parents=True, exist_ok=True)
    path = issues / f"{next_issue_number(issues):02d}-libtv-update-to-{version}.md"
    path.write_text(issue_text(pin, store, root, version, report_text), encoding="utf-8")
    return path
