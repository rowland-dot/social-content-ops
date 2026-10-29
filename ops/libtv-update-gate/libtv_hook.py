"""The note a Claude Code session gets when it opens in this project.

Plain hook output reaches Claude but not necessarily the owner, so the note is JSON with two parts: `systemMessage`, one
short line for the owner, and `additionalContext`, what Claude needs in order to put the question to him.
"""

from __future__ import annotations

from libtv_answers import GATE_COMMAND
from libtv_detect import Finding, Report

NEEDS_ANSWER = ("new-version", "settings-changed")


def _short(finding: Finding, pinned: str) -> str:
    kind, extra = finding.kind, finding.extra
    if kind == "new-version":
        return f"LibTV published {extra['version']} (pinned: {pinned}); Claude will show what it changes and ask you."
    if kind == "candidate-unstable":
        return f"LibTV {extra['version']} is not offered: its files differ between two fetches."
    if kind == "settings-changed":
        return f"LibTV changed {len(extra.get('changes', []))} run-time settings (no program update); Claude will show them and ask you."
    if kind == "could-not-check":
        return f"could not check {extra.get('detector', 'LibTV')}"
    return finding.text[:240]


def system_message(report: Report) -> str:
    failed = [f for f in report.findings if f.kind == "could-not-check"]
    others = [f for f in report.findings if f.kind != "could-not-check"]
    parts = [_short(f, report.pinned) for f in others]
    if failed and not others and report.channel is None:
        reason = failed[0].text.split(": ", 1)[-1]
        parts.append(f"could not check LibTV ({reason})")
    elif failed:
        parts.append("could not check " + ", ".join(f.extra.get("detector", "?") for f in failed))
    return "LibTV update gate: " + " | ".join(parts)


def additional_context(report: Report) -> str:
    lines = [
        "LibTV update gate. A read-only check ran when this session opened: it installed nothing, ran no LibTV "
        "program and used no login. Findings:",
    ]
    lines += [f"- {f.text}" for f in report.findings]
    lines += ["", "What to do with them:"]
    versions = [f.extra["version"] for f in report.findings if f.kind == "new-version"]
    for v in versions:
        lines += [
            f"- New version {v}. Run `{GATE_COMMAND} candidate {v}` (from the repo root) and show the owner, in plain words, "
            f"what the report says the documents, the commands and the paid runs change. Then ask him through the "
            f"question tool: book the update as an issue, not now, or decline this version. On \"book\" run "
            f"`{GATE_COMMAND} book {v}`; on \"decline\" run `{GATE_COMMAND} decline {v}`; on \"not now\" do nothing "
            f"(this note comes back at the next session).",
        ]
    if any(f.kind == "settings-changed" for f in report.findings):
        lines.append(
            f"- Changed run-time settings. Tell the owner what changed, then ask him through the question tool to acknowledge. "
            f"On yes run `{GATE_COMMAND} ack-settings`. This is report-only; nothing is changed on LibTV's side or ours."
        )
    if any(f.kind not in NEEDS_ANSWER for f in report.findings):
        lines.append(
            "- The other findings (a LibTV notice, an upgrade demand, an unusual canary answer, a changed pinned file, "
            "a version folder the channel does not name, a check that could not run) are for the owner to know about. "
            "They come back at every session until the cause is gone; there is nothing to acknowledge."
        )
    lines += [
        "- Never run the libtv program (pinned or candidate), never install anything and never change the pins or the "
        "vendored files. A booked issue does that, after triage.",
        "- In a headless or dispatched session, with no the owner to ask, never book, decline or acknowledge anything; ask "
        "only after the owner answers in a session where he is present, and mention the finding only if it matters to the work.",
        "- Only after the owner answers through the question tool does a book, decline or acknowledge command run.",
    ]
    return "\n".join(lines)


def note(report: Report) -> dict | None:
    if not report.findings:
        return None
    return {
        "systemMessage": system_message(report),
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": additional_context(report)},
    }
