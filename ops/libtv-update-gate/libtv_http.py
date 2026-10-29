"""Plain anonymous HTTP for the LibTV update gate. Standard library only; nothing here runs a program."""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = "libtv-update-gate/1 (read-only version check)"


class FetchError(Exception):
    """The answer could not be had at all (unreachable, timed out): the gate says so, never "no change"."""


@dataclass
class Response:
    status: int
    headers: dict[str, str] = field(default_factory=dict)  # names lower-cased
    body: bytes = b""


def request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, timeout: float = 8.0) -> Response:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = b"" if method == "HEAD" else resp.read()
            return Response(resp.status, {k.lower(): v for k, v in resp.headers.items()}, body)
    except urllib.error.HTTPError as err:  # an answer, just not a good one (404 and so on)
        body = b""
        if method != "HEAD":
            try:
                body = err.read()
            except OSError:
                pass
        return Response(err.code, {k.lower(): v for k, v in err.headers.items()}, body)
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise FetchError(f"{url}: {getattr(err, 'reason', err)}") from err


def download(url: str, dest: Path | None = None, *, timeout: float = 60.0) -> tuple[str, int, str]:
    """Fetch URL in full, always from the start (a half-finished file is never resumed), writing it to DEST when
    given. Returns (sha256, size, Last-Modified or "")."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    size = 0
    out = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            last_modified = resp.headers.get("Last-Modified", "")
            if dest is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                out = open(dest, "wb")
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                if out is not None:
                    out.write(chunk)
    except urllib.error.HTTPError as err:
        raise FetchError(f"{url}: HTTP {err.code}") from err
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise FetchError(f"{url}: {getattr(err, 'reason', err)}") from err
    finally:
        if out is not None:
            out.close()
    return digest.hexdigest(), size, last_modified
