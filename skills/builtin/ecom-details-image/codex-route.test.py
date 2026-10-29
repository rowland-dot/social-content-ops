"""Document check: ecom-details-image/SKILL.md must tell an agent that IMG_PROVIDER=codex makes
generate_image.py run on the Codex subscription (no key, PNG only, at most 4 per run), and that
a missing API key is then not a reason to stop.

Run: python skills/builtin/ecom-details-image/codex-route.test.py   (exit 0 = pass)
The executable behaviour tests are in tests/test_codex_image_route.py.
"""
from pathlib import Path
import sys

text = (Path(__file__).resolve().parent / "SKILL.md").read_text(encoding="utf-8")

required = {
    "names the switch": "IMG_PROVIDER=codex",
    "says no key is needed": "不需要任何 API key",
    "states the per-run limit": "最多 4 张",
    "says it never falls back to the paid mode": "**不会**回退",
    # issue 95: Codex is the only route; without the setting the agent stops and says so
    "rule 3 says what to tell the user when the setting is missing": "只告诉用户项目设置缺 `IMG_PROVIDER=codex`",
    "says not to look for another service": "不要去找别的出图服务",
}
# issue 95: no paid route, key setup or other image service may be named in this guide.
forbidden = ["apimart", "OpenAI 兼容", "OpenAI-compatible", "OPENAI_API_KEY", "IMG_API_KEY", "IMG_BASE_URL",
             "Nano Banana", "Gemini Image", "Flux", "交给用户自行运行"]
missing = [why for why, needle in required.items() if needle not in text]
named = [word for word in forbidden if word in text]
if missing or named:
    if missing:
        print("SKILL.md is missing:", "; ".join(missing))
    if named:
        print("SKILL.md still names:", "; ".join(named))
    sys.exit(1)
print("ok")
