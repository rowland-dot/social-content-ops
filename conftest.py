"""Fixtures shared by test files in more than one folder.

Kept at the repository root on purpose: pytest runs here with --import-mode=importlib, where a
second `tests/conftest.py` clashes with the one in skills/builtin/skill-wechat-publisher/tests
(both are packages named `tests`) and stops collection of the whole suite.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

RENDER_CARD = Path(__file__).resolve().parent / "skills/shared/scripts/render_card.py"


@pytest.fixture(autouse=True)
def isolate_web_outputs(request, tmp_path_factory, monkeypatch):
    if not request.node.path.is_relative_to(Path(__file__).parent / "tests"):
        return
    outputs = tmp_path_factory.mktemp("isolated-web-outputs")
    for name in ("app", "web.app"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "OUTPUTS_DIR"):
            monkeypatch.setattr(module, "OUTPUTS_DIR", outputs)


@pytest.fixture(scope="module")
def chromium(tmp_path_factory):
    """Skip the tests that really render when this machine cannot start Chromium.

    CI installs the playwright package but not the Chromium download, so rendering a trivial page
    exits 3 there ("无法启动 chromium ... playwright install"; the same exit 3 covers a missing
    playwright package). The script's own --selftest cannot be the probe: it turns that exit 3
    into its own exit 1. Anything other than exit 3, including a render that fails some other way,
    is not a reason to skip: the tests then run and report the real fault. Tests that never open a
    browser (the flag-conflict refusal) do not ask for this fixture and keep running everywhere.
    """
    folder = tmp_path_factory.mktemp("chromium-probe")
    page = folder / "probe.html"
    page.write_text("<!doctype html><meta charset='utf-8'><body>probe</body>", encoding="utf-8")
    probe = subprocess.run([sys.executable, str(RENDER_CARD), "--wait", "0", "--html", str(page),
                            "--out", str(folder / "probe.png")],
                           capture_output=True, text=True, timeout=120)
    if probe.returncode == 3:
        first = next((line for line in probe.stderr.splitlines() if line.strip()), "no message")
        pytest.skip(f"Chromium cannot be started here, so cards cannot be rendered "
                    f"(render_card.py exit 3: {first[:160]})")
