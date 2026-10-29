"""What the LibTV update gate looks at, and what it concludes. Read-only: it fetches, it never installs or runs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from libtv_http import FetchError, download, request
from libtv_settings import CHANNELS, summarize

DEFAULT_API_BASE = "https://api2.liblib.art"
VERSION_CHANNEL = "240"
GET_BY_ID = "/api/www/landing-activities/getById?id="


class PinError(Exception):
    """The repo's pin could not be read; the gate refuses rather than guess what is pinned."""


@dataclass
class Pin:
    version: str
    files_base: str  # the file server's address up to (not including) /cli/<version>/
    program_zip_sha256: str
    program_sha256: str


def read_pin(root: Path) -> Pin:
    """The pinned version and its two sha256 values, read from setup.sh and checks.sh (never written)."""
    try:
        setup = (root / "ops" / "wsl-setup" / "setup.sh").read_text(encoding="utf-8")
        checks = (root / "ops" / "wsl-setup" / "checks.sh").read_text(encoding="utf-8")
    except OSError as err:
        raise PinError(f"cannot read the pin: {err}") from err
    url = re.search(r"^LIBTV_URL=(\S+)$", setup, re.M)
    m = re.match(r"(.+)/cli/(\d+\.\d+\.\d+)/libtv-linux-x64\.zip$", url.group(1)) if url else None
    if not m:
        raise PinError("cannot read the pin: no versioned LIBTV_URL in ops/wsl-setup/setup.sh")

    def sha(name: str) -> str:
        env = os.environ.get(name)  # checks.sh lets the environment override its pins; so does the gate
        if env:
            return env
        found = re.search(rf"^{name}=\$\{{{name}:-([0-9a-f]{{64}})\}}", checks, re.M)
        if not found:
            raise PinError(f"cannot read the pin: no {name} in ops/wsl-setup/checks.sh")
        return found.group(1)

    return Pin(m.group(2), m.group(1), sha("LIBTV_ZIP_SHA256"), sha("LIBTV_SHA256"))


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


@dataclass
class Finding:
    kind: str
    text: str
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, **self.extra}


@dataclass
class Report:
    pinned: str
    channel: str | None = None
    findings: list[Finding] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    folders_above_pin: list[str] = field(default_factory=list)  # versions whose folder exists; sorted out after all detectors ran
    new_baselines: dict = field(default_factory=dict)  # pinned-file facts seen for the first time; saved by the caller
    settings_baseline: dict | None = None  # the run-time settings on the very first check
    settings_pending: dict | None = None   # the run-time settings as they stood when a change was reported
    settings_in_step: bool = False         # the settings equal the acknowledged snapshot

    def as_dict(self) -> dict:
        return {
            "pinned": self.pinned,
            "channel": self.channel,
            "findings": [f.as_dict() for f in self.findings],
            "info": self.info,
        }


@dataclass
class Context:
    pin: Pin
    api_base: str
    timeout: float
    state: dict = field(default_factory=dict)  # what the store held when the check began (read only here)
    deep: bool = False
    download_timeout: float = 120.0

    def api(self, path: str, headers: dict | None = None):
        return request(self.api_base.rstrip("/") + path, headers=headers, timeout=self.timeout)

    def files(self, path: str, method: str = "GET"):
        return request(self.pin.files_base.rstrip("/") + path, method=method, timeout=self.timeout)

    def channel_object(self, channel_id: str):
        """The JSON a channel carries in data.linkUrl: an object for most, a list for the voices channel."""
        resp = self.api(GET_BY_ID + channel_id)
        if resp.status != 200:
            raise FetchError(f"channel {channel_id} answered HTTP {resp.status}")
        try:
            outer = json.loads(resp.body.decode("utf-8"))
            payload = json.loads(outer["data"]["linkUrl"])
        except (ValueError, KeyError, TypeError) as err:
            raise FetchError(f"channel {channel_id} answered something unreadable") from err
        if not isinstance(payload, (dict, list)):
            raise FetchError(f"channel {channel_id} answered something unreadable")
        return payload

    def channel_payload(self, channel_id: str) -> dict:
        """A channel whose payload must be an object (the version channel and the notice channel)."""
        payload = self.channel_object(channel_id)
        if not isinstance(payload, dict):
            raise FetchError(f"channel {channel_id} answered something unreadable")
        return payload


def detect_version(ctx: Context, report: Report) -> None:
    """The version channel (240) is the authority; the old latest/manifest.json is reported as information only."""
    payload = ctx.channel_payload(VERSION_CHANNEL)
    channel = str(payload.get("version", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", channel):
        raise FetchError(f"channel {VERSION_CHANNEL} names no readable version")
    report.channel = channel
    pinned = ctx.pin.version
    if version_tuple(channel) > version_tuple(pinned):
        report.findings.append(
            Finding(
                "new-version",
                f"LibTV publishes {channel}; Easel is pinned to {pinned}.",
                {"version": channel, "action": "book-or-decline"},
            )
        )
    elif version_tuple(channel) < version_tuple(pinned):
        report.findings.append(
            Finding("channel-behind-pin", f"LibTV's version channel names {channel}, older than the pinned {pinned}.")
        )
    else:
        report.info.append(f"The version channel names {channel}, the pinned version: no update.")
    try:
        manifest = ctx.files("/cli/latest/manifest.json")
        if manifest.status == 200:
            name = json.loads(manifest.body.decode("utf-8")).get("version")
            report.info.append(f"The old cli/latest/manifest.json names {name} (information only; the channel decides).")
    except (FetchError, ValueError, AttributeError):
        pass


def detect_folders(ctx: Context, report: Report) -> None:
    """Does the folder of the next patch, minor or major version above the pin exist on the file server?"""
    major, minor, patch = version_tuple(ctx.pin.version)
    for version in (f"{major}.{minor}.{patch + 1}", f"{major}.{minor + 1}.0", f"{major + 1}.0.0"):
        if ctx.files(f"/cli/{version}/libtv-cli-skill.zip", method="HEAD").status == 200:
            report.folders_above_pin.append(version)


def detect_notice(ctx: Context, report: Report) -> None:
    """LibTV's broadcast notice channel: reported word for word when it is enabled or carries any message."""
    payload = ctx.channel_payload("217")
    message = str(payload.get("message") or "")
    enabled = bool(payload.get("enable"))
    if enabled or message.strip():
        report.findings.append(
            Finding("notice", f'LibTV\'s notice channel says (enabled: {str(enabled).lower()}): "{message}"', {"message": message})
        )
    else:
        report.info.append("LibTV's notice channel is off and empty.")


CANARY_PATH = "/api/www/account/list"
CANARY_BASELINE_MSG = "未登录"


def detect_canary(ctx: Context, report: Report) -> None:
    """Ask the program's own route, as the program does and with no login. A logged-out answer is a stable
    baseline; LibTV's one known retirement answered code 0 with a message and no data, which the program itself
    would pass through as an empty success."""
    resp = ctx.api(CANARY_PATH, headers={"X-from-client": "cli"})
    raw = resp.body.decode("utf-8", "replace")
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if resp.status == 200 and isinstance(data, dict):
        if data.get("code") == 401 and data.get("msg") == CANARY_BASELINE_MSG:
            report.info.append("The canary route answers the not-logged-in baseline (code 401): nothing unusual.")
            return
        message = data.get("message") or data.get("msg")
        if data.get("code") == 0 and not data.get("data") and message:
            report.findings.append(
                Finding(
                    "upgrade-demand",
                    f'LibTV answered a call that needs no login with a message and no data, the shape of its old-skill '
                    f'retirement. It says: "{message}"',
                    {"message": message},
                )
            )
            return
    report.findings.append(
        Finding(
            "canary-other",
            f"The canary route answered differently from the not-logged-in baseline (HTTP {resp.status}): {raw[:500]}",
            {"status": resp.status},
        )
    )


def detect_settings(ctx: Context, report: Report) -> None:
    """Report only (The owner's ruling): diff the run-time settings against the snapshot he last acknowledged."""
    payloads = {channel_id: ctx.channel_object(channel_id) for channel_id in CHANNELS}
    snapshot = ctx.state.get("settings")
    if not snapshot:
        report.settings_baseline = payloads
        report.info.append(f"Recorded a baseline of {len(payloads)} run-time settings channels; changes are reported from now on.")
        return
    lines = []
    for channel_id in CHANNELS:
        lines += summarize(channel_id, snapshot.get(channel_id, type(payloads[channel_id])()), payloads[channel_id])
    if lines:
        report.settings_pending = payloads
        report.findings.append(
            Finding(
                "settings-changed",
                "LibTV changed settings the program downloads at run time (no program update involved): " + " | ".join(lines),
                {"action": "acknowledge", "changes": lines},
            )
        )
    else:
        report.settings_in_step = True


def pinned_file_paths(pin: Pin) -> list[str]:
    return [f"/cli/{pin.version}/libtv-linux-x64.zip", f"/cli/{pin.version}/libtv-cli-skill.zip"]


def detect_pinned_files(ctx: Context, report: Report) -> None:
    """The pinned version sits at a versioned address, so its files should never change. Compare what LibTV
    publishes there now (size and date, by a HEAD request) with what was recorded; with --deep, re-hash the
    program package against the pin."""
    recorded = ctx.state.get("pinned_files", {})
    for path in pinned_file_paths(ctx.pin):
        resp = ctx.files(path, method="HEAD")
        if resp.status != 200:
            report.findings.append(
                Finding("pinned-files-changed", f"LibTV's pinned file {path} now answers HTTP {resp.status}.", {"path": path})
            )
            continue
        now = {"size": int(resp.headers.get("content-length", -1)), "last_modified": resp.headers.get("last-modified", "")}
        before = recorded.get(path)
        if before is None:
            report.new_baselines[path] = now
            continue
        changes = []
        if before["size"] != now["size"]:
            changes.append(f"size {before['size']} -> {now['size']} bytes")
        if before["last_modified"] != now["last_modified"]:
            changes.append(f"Last-Modified {before['last_modified']} -> {now['last_modified']}")
        if changes:
            report.findings.append(
                Finding(
                    "pinned-files-changed",
                    f"LibTV changed its pinned file {path} since it was recorded: {'; '.join(changes)}.",
                    {"path": path},
                )
            )
    if ctx.deep:
        path = pinned_file_paths(ctx.pin)[0]
        got, _size, _lm = download(ctx.pin.files_base.rstrip("/") + path, None, timeout=ctx.download_timeout)
        if got == ctx.pin.program_zip_sha256:
            report.info.append(f"The pinned program package {path} matches the pin (sha256 {got[:12]}...).")
        else:
            report.findings.append(
                Finding(
                    "pinned-files-changed",
                    f"The pinned program package {path} now has sha256 {got}, not the pinned {ctx.pin.program_zip_sha256}.",
                    {"path": path},
                )
            )


def settle_folders(report: Report) -> None:
    """A folder above the pin that the version channel does not name is worth saying; one it names is the update."""
    for version in report.folders_above_pin:
        if report.channel is not None and version != report.channel:
            report.findings.append(
                Finding(
                    "unlisted-version",
                    f"LibTV has a folder for {version} that its version channel ({report.channel}) does not name.",
                    {"version": version},
                )
            )
