"""Runs the WSL machine-setup script's own tests (ops/wsl-setup/setup.test.sh) under pytest, so CI runs them.

The bash test drives the real setup.sh and checks.sh in a scratch folder, with apt, curl, npm, nvm, pip,
openclaw and codex replaced by stand-ins. It needs Linux (or WSL) and bash; elsewhere it is skipped.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_SCRIPT = ROOT / "ops" / "wsl-setup" / "setup.test.sh"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the setup script is for Linux/WSL")
@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None, reason="needs bash and git")
def test_wsl_setup_script_behaviour():
    proc = subprocess.run(["bash", str(TEST_SCRIPT)], capture_output=True, text=True, cwd=ROOT, timeout=900)
    failures = [line for line in proc.stdout.splitlines() if line.startswith("FAIL")]
    assert proc.returncode == 0 and not failures, "\n".join(failures) or proc.stdout[-2000:] + proc.stderr[-2000:]
