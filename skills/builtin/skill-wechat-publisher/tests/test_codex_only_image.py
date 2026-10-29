"""Issue 95: the publisher's image core runs only on the Codex subscription.

Without IMG_PROVIDER=codex, and for an explicit paid provider, detectProvider() throws a message that
names the Codex setting and no key. The fuller behaviour tests (no request reaches a stand-in paid
API) are in tests/test_codex_image_route.py at the repo root.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "scripts" / "baoyu_image_gen_core.ts"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not on PATH")


@pytest.mark.parametrize("provider", ["null", '"openai"', '"gemini-proxy"'])
def test_detect_provider_refuses_a_paid_route_when_the_codex_setting_is_missing(tmp_path, provider):
    script = tmp_path / "check.mjs"
    script.write_text(
        f'import * as core from "{CORE.as_posix()}";\n'
        f'try {{ console.log(core.detectProvider({{provider: {provider}}})); }} '
        'catch (e) { console.log("ERR:" + e.message); }\n', encoding="utf-8")
    env = {**os.environ, "IMG_PROVIDER": "", "OPENAI_API_KEY": "sk-not-real",
           "GEMINI_PROXY_API_KEY": "sk-not-real"}
    r = subprocess.run([NODE, str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert "ERR:" in r.stdout and "IMG_PROVIDER=codex" in r.stdout, r.stdout + r.stderr
    assert "OPENAI_API_KEY" not in r.stdout and "GEMINI_PROXY_API_KEY" not in r.stdout
