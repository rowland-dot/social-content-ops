"""LibTV update gate (issue 37): a free, read-only check of whether LibTV has published something Easel has not seen.

    python ops/libtv-update-gate/libtv_gate.py check [--json] [--deep]   what LibTV changed; installs nothing
    python ops/libtv-update-gate/libtv_gate.py candidate VERSION         what a newer version would change
    python ops/libtv-update-gate/libtv_gate.py book VERSION              after the owner's yes: write a ready-filled issue
    python ops/libtv-update-gate/libtv_gate.py decline VERSION           after the owner's no: stop offering that version
    python ops/libtv-update-gate/libtv_gate.py ack-settings              the owner has seen the run-time settings change
    python ops/libtv-update-gate/libtv_gate.py keep-pin                  keep a checked copy of the pinned package
    python ops/libtv-update-gate/libtv_gate.py hook                      the SessionStart note (.claude/settings.json)

It reads LibTV's public answers with no login. It never installs, never runs the `libtv` program and never
touches the pins: those move only in a booked issue, after the owner's yes. See docs/vendored/libtv-cli-source.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "skills" / "shared" / "scripts"))
from private_work import missing_message, work_dir  # noqa: E402

from libtv_answers import apply_answers, decline, write_issue  # noqa: E402
from libtv_detect import (  # noqa: E402
    DEFAULT_API_BASE,
    Context,
    Finding,
    PinError,
    Report,
    detect_canary,
    detect_folders,
    detect_notice,
    detect_pinned_files,
    detect_settings,
    detect_version,
    pinned_file_paths,
    read_pin,
    settle_folders,
)
from libtv_hook import note  # noqa: E402
from libtv_http import FetchError, download  # noqa: E402
from libtv_report import build_report, candidate_dir, fetch_twice  # noqa: E402
from libtv_state import Store  # noqa: E402

DETECTORS = (
    ("version", detect_version),
    ("folders", detect_folders),
    ("notice", detect_notice),
    ("canary", detect_canary),
    ("pinned-files", detect_pinned_files),
    ("settings", detect_settings),
)
VERSION = re.compile(r"\d+\.\d+\.\d+")


def out(text: str) -> None:
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.flush()


# ---- the check -------------------------------------------------------------------------------------------------


def run_detectors(ctx: Context, report: Report, deadline: float) -> None:
    """Each detector on its own thread. One that fails or does not answer in time is "could not check", never "fine"."""
    pool = ThreadPoolExecutor(max_workers=len(DETECTORS))
    futures = {pool.submit(fn, ctx, report): name for name, fn in DETECTORS}
    done, not_done = wait(futures, timeout=deadline)
    for future in done:
        try:
            future.result()
        except FetchError as err:
            report.findings.append(
                Finding("could-not-check", f"Could not check {futures[future]}: {err}", {"detector": futures[future]})
            )
    for future in not_done:
        name = futures[future]
        report.findings.append(Finding("could-not-check", f"Could not check {name}: no answer in time.", {"detector": name}))
    pool.shutdown(wait=False, cancel_futures=True)
    settle_folders(report)
    order = ("The version", "The old", "LibTV's notice", "The canary", "The pinned", "Recorded")   # threads finish in any order
    report.info.sort(key=lambda line: next((i for i, p in enumerate(order) if line.startswith(p)), len(order)))


def check_report(ctx: Context, store: Store, deadline: float) -> Report:
    """Run every detector, save what a check learns on its own, and drop what the owner has already answered."""
    ctx.state = store.load()
    report = Report(pinned=ctx.pin.version)
    run_detectors(ctx, report, deadline)
    persist(report, store)
    apply_answers(report, store.load())
    return report


def persist(report: Report, store: Store) -> None:
    """Save what a check learned that is not an answer from the owner: first-time baselines, and the settings as reported."""
    state = store.load()
    before = json.dumps(state, sort_keys=True)
    files = state.setdefault("pinned_files", {})
    for path, facts in report.new_baselines.items():
        files.setdefault(path, facts)
    if report.settings_baseline is not None and "settings" not in state:
        state["settings"] = report.settings_baseline
    if report.settings_pending is not None:
        state["settings_pending"] = report.settings_pending
    if report.settings_in_step:
        state.pop("settings_pending", None)
    if json.dumps(state, sort_keys=True) != before:
        store.save(state)


def render(report: Report) -> str:
    lines = [f"LibTV update gate. Pinned: {report.pinned}. Version channel: {report.channel or 'unknown'}."]
    lines += [f"- {f.text}" for f in report.findings]
    lines += [f"  {i}" for i in report.info]
    return "\n".join(lines)


def cmd_check(ctx: Context, store: Store, as_json: bool) -> None:
    report = check_report(ctx, store, float(os.environ.get("LIBTV_GATE_DEADLINE", "30")))
    out(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if as_json else render(report))


def cmd_hook(root: Path, store: Store) -> None:
    """The SessionStart note. It always exits 0, says "could not check" rather than "no update", and ends in time."""
    try:
        pin = read_pin(root)
    except PinError as err:
        out(json.dumps({"systemMessage": f"LibTV update gate could not read its pin: {err}"}, ensure_ascii=False))
        return
    ctx = Context(
        pin,
        os.environ.get("LIBTV_GATE_API_BASE", DEFAULT_API_BASE),
        float(os.environ.get("LIBTV_GATE_TIMEOUT", "4")),
    )
    report = check_report(ctx, store, float(os.environ.get("LIBTV_GATE_DEADLINE", "10")))
    message = note(report)
    if message:
        out(json.dumps(message, ensure_ascii=False))


# ---- a newer version -------------------------------------------------------------------------------------------


def candidate_report(ctx: Context, store: Store, root: Path, version: str, rebuild: bool = False) -> tuple[int, str]:
    """The report on LibTV VERSION, built once per version. Downloads into the store; installs nothing."""
    state = store.load()
    report_file = candidate_dir(store, version) / "report.md"
    if not rebuild and report_file.is_file() and version in state.get("candidates", {}):
        return 0, report_file.read_text(encoding="utf-8").rstrip()
    stable, facts, message = fetch_twice(ctx, store, version)
    if not stable:
        if "unstable" in facts:
            state.setdefault("unstable", {})[version] = facts["unstable"]
            store.save(state)
        return 1, message
    text = build_report(ctx, store, root, version, facts)
    report_file.write_text(text + "\n", encoding="utf-8")
    state.setdefault("candidates", {})[version] = {"report": str(report_file)}
    state.get("unstable", {}).pop(version, None)
    store.save(state)
    return 0, text


def cmd_candidate(ctx: Context, store: Store, root: Path, version: str, rebuild: bool) -> int:
    code, text = candidate_report(ctx, store, root, version, rebuild)
    out(text)
    return code


def cmd_book(ctx: Context, store: Store, root: Path, version: str) -> int:
    """The owner said yes: write the ready-filled issue. No pin, installed program or vendored file is touched."""
    state = store.load()
    if version in state.get("booked", {}):
        out(f"LibTV {version} is already booked: {state['booked'][version]['issue']}")
        return 0
    if version in state.get("unstable", {}):
        out(f"LibTV {version} is not offered: its files differ between two fetches. Nothing was booked.")
        return 1
    if work_dir(root) is None:
        out(missing_message("Booking an issue") + " Nothing was booked.")
        return 1
    code, text = candidate_report(ctx, store, root, version)
    if code != 0:
        out(text)
        return code
    issue = write_issue(ctx.pin, store, root, version, text)
    state = store.load()
    state.setdefault("booked", {})[version] = {"issue": issue.relative_to(root).as_posix()}
    store.save(state)
    out(f"Booked LibTV {version} as {issue.relative_to(root).as_posix()} (Status: needs-triage). No pin, program or vendored file was changed.")
    return 0


def cmd_decline(store: Store, version: str) -> None:
    out(decline(store, version))


def cmd_ack_settings(store: Store) -> None:
    """The owner's acknowledgement: the settings as last reported become the snapshot later checks compare with."""
    state = store.load()
    pending = state.pop("settings_pending", None)
    if not pending:
        out("Nothing to acknowledge: no run-time settings change is waiting.")
        return
    state["settings"] = pending
    store.save(state)
    out("Acknowledged: the run-time settings as last reported are now the snapshot later checks compare with.")


# ---- the kept copy of the pin ---------------------------------------------------------------------------------


def wsl_path(p: Path) -> str:
    """How WSL names a Windows path (the setup step runs in WSL); a Linux path stays as it is."""
    text = str(p)
    if len(text) > 2 and text[1] == ":":
        return "/mnt/" + text[0].lower() + text[2:].replace("\\", "/")
    return text


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cmd_keep_pin(ctx: Context, store: Store) -> int:
    """Keep a checked copy of the pinned program package, so a rollback does not depend on LibTV's old folders."""
    pin = ctx.pin
    dest = store.pinned_copy(pin.version)
    path = pinned_file_paths(pin)[0]
    url = pin.files_base.rstrip("/") + path
    rollback = f"LIBTV_ZIP_FILE={wsl_path(dest)} bash ops/wsl-setup/setup.sh --only libtv"
    if dest.is_file() and file_sha256(dest) == pin.program_zip_sha256:
        out(f"Pinned package already kept and checked: {dest}")
        out(f"Rollback route: revert the pin change, then run (in WSL): {rollback}")
        return 0
    part = dest.with_name(dest.name + ".part")
    try:
        got, size, last_modified = download(url, part, timeout=ctx.download_timeout)
    except FetchError as err:
        part.unlink(missing_ok=True)
        out(f"Could not fetch the pinned package: {err}")
        return 1
    if got != pin.program_zip_sha256:
        part.unlink(missing_ok=True)
        out(f"Refused: {url} has sha256 {got}, not the pinned {pin.program_zip_sha256}. Nothing was kept.")
        return 1
    os.replace(part, dest)
    state = store.load()
    state.setdefault("pinned_files", {})[path] = {"size": size, "last_modified": last_modified}
    store.save(state)
    out(f"Kept the checked pinned package ({size} bytes, sha256 {got[:12]}...): {dest}")
    out(f"Rollback route: revert the pin change, then run (in WSL): {rollback}")
    return 0


# ---- the command line ------------------------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="libtv_gate.py", description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=str(HERE.parents[1]), help="the repo whose pin is read")
    parser.add_argument("--store", default=None, help="where the gate keeps its own files (outside git)")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="detect what LibTV has changed; installs nothing")
    check.add_argument("--json", action="store_true")
    check.add_argument("--deep", action="store_true", help="also download the pinned program package and re-hash it")
    sub.add_parser("keep-pin", help="keep a checked copy of the pinned program package for rollback")
    sub.add_parser("ack-settings", help="The owner has seen the reported run-time settings change: advance the snapshot")
    sub.add_parser("hook", help="the note a Claude Code session gets when it opens in this project")
    cand = sub.add_parser("candidate", help="show what a newer LibTV version would change, built from its files")
    cand.add_argument("version")
    cand.add_argument("--rebuild", action="store_true", help="build the report again even if it was built before")
    for name, help_text in (("book", "The owner said yes: write a ready-filled issue"), ("decline", "The owner said no: stop offering it")):
        sub.add_parser(name, help=help_text).add_argument("version")
    args = parser.parse_args(argv)
    if getattr(args, "version", None) is not None and not VERSION.fullmatch(args.version):
        print(f"not a version number: {args.version}", file=sys.stderr)
        return 2

    root = Path(args.root)
    store = Store(Path(args.store) if args.store else Path(os.environ.get("LIBTV_GATE_STORE") or root / ".scratch" / "libtv-update-gate"))
    code = 0
    if args.command == "hook":
        cmd_hook(root, store)
    else:
        try:
            pin = read_pin(root)
        except PinError as err:
            print(str(err), file=sys.stderr)
            return 2
        ctx = Context(
            pin,
            os.environ.get("LIBTV_GATE_API_BASE", DEFAULT_API_BASE),
            float(os.environ.get("LIBTV_GATE_TIMEOUT", "8")),
            deep=getattr(args, "deep", False),
            download_timeout=float(os.environ.get("LIBTV_GATE_DOWNLOAD_TIMEOUT", "120")),
        )
        if args.command == "check":
            cmd_check(ctx, store, args.json)
        elif args.command == "keep-pin":
            code = cmd_keep_pin(ctx, store)
        elif args.command == "ack-settings":
            cmd_ack_settings(store)
        elif args.command == "candidate":
            code = cmd_candidate(ctx, store, root, args.version, args.rebuild)
        elif args.command == "book":
            code = cmd_book(ctx, store, root, args.version)
        elif args.command == "decline":
            cmd_decline(store, args.version)
    sys.stdout.flush()
    os._exit(code)  # a request that never answers must not hold the process open


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
