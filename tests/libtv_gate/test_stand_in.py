"""The stand-in LibTV server's own guarantees (issue 39): it never outlives its test, and its errors are the test's.

The seam is the `lt` fixture's teardown, so each case runs a small pytest session in a scratch folder with a copy
of this folder's conftest.py and judges the session: a stand-in handler still sleeping on a delayed reply must be
gone by the time the next test starts, and a handler that raises must fail the test that owns the server.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

CONFTEST = Path(__file__).with_name("conftest.py")

DELAYED_REPLY_THEN_NEXT_TEST = '''
import socket
import threading
import time


def test_a_reply_delayed_far_past_the_end_of_the_test(lt):
    lt.route("/slow", b"late", delay=30)
    client = socket.create_connection(("127.0.0.1", lt.server.server_address[1]))
    client.sendall(b"GET /slow HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n")
    deadline = time.time() + 5
    while "/slow" not in lt.requests() and time.time() < deadline:
        time.sleep(0.01)
    assert "/slow" in lt.requests(), "the handler never took the request"
    client.close()   # the client is gone, as the gate is when it gives up at its deadline


def test_zz_nothing_of_the_stand_in_is_left_running():
    alive = [t.name for t in threading.enumerate() if t is not threading.main_thread()]
    assert not alive, f"threads still running after the stand-in was torn down: {alive}"
'''

HANDLER_THAT_RAISES = '''
import urllib.request


def test_a_handler_that_raises(lt):
    lt.route("/boom", b"x")
    lt.server.routes["/boom"].body = "text where bytes belong"   # the handler's write raises TypeError
    try:
        urllib.request.urlopen(lt.server.base + "/boom", timeout=5).read()
    except Exception:
        pass   # what the client sees is not the point
'''


def _session(tmp_path: Path, test_source: str) -> tuple[subprocess.CompletedProcess, float]:
    folder = tmp_path / "session"
    folder.mkdir()
    shutil.copy(CONFTEST, folder / "conftest.py")
    (folder / "test_session.py").write_text(test_source, encoding="utf-8")
    started = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_session.py"],
        cwd=str(folder),
        capture_output=True,
        timeout=120,
    )
    return proc, time.time() - started


def test_a_delayed_reply_does_not_outlive_its_test(tmp_path):
    proc, seconds = _session(tmp_path, DELAYED_REPLY_THEN_NEXT_TEST)
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, out
    assert seconds < 20, f"teardown waited out the 30 second delay ({seconds:.1f} s)\n{out}"


def test_a_handler_that_raises_fails_the_test_that_owns_the_server(tmp_path):
    proc, _ = _session(tmp_path, HANDLER_THAT_RAISES)
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    assert proc.returncode != 0, f"a handler error went unreported:\n{out}"
    assert "/boom" in out, f"the failure does not name the request path:\n{out}"
