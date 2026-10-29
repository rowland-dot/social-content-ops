"""Document check: ai-image-gen/SKILL.md must tell an agent how to use the Codex subscription
route (IMG_PROVIDER=codex) and its limits, so nobody fills in a paid API key instead.

Run: python skills/builtin/ai-image-gen/codex-route.test.py   (exit 0 = pass)
The named file is not collected by pytest on purpose; the executable behaviour tests are in
tests/test_codex_image_route.py.
"""
from pathlib import Path
import sys

text = (Path(__file__).resolve().parent / "SKILL.md").read_text(encoding="utf-8")

required = {
    "names the switch": "IMG_PROVIDER=codex",
    "says no key is needed": "不需要 API key",
    "states the per-run limit": "最多 4 张",
    "says it never falls back to the paid mode": "**不会**回退",
    "says PNG only": "只产出 PNG",
    "says img2img takes a product image plus style references": "第 1 张是商品图",
    "states the three-image limit": "最多 3 张",
    "keeps the style-reference wording": "不带它的商品、人物、手、文字",
    # issue 92: the brand's own model, as its own role and its own option
    "names the identity option": "--identity-image",
    "names the identity role": "身份参考",
    "states the new total": "共最多 4 张",
    "allows one identity image only": "至多 1 张",
    # issue 114: the identity image can stand alone for a card with no pack
    "says it can be given alone": "也可以单独给 `--identity-image`（不给 `--image`）",
    "says no product or pack is drawn": "不画商品和包装",
    # issue 115: an approved card as the base image, its own role and its own option
    "names the base-image option": "--base-image",
    "names the base-image role": "底图",
    "allows one base image only": "至多 1 张",
    "states the total with a base image": "共最多 5 张",
    "says only what the prompt names changes": "只改提示词点名的地方",
    "says it needs a product image": "商品图，不能没有",
    # issue 95: Codex is the only route; without the setting the agent stops and says so
    "says what to tell the user when the setting is missing": "只告诉用户项目设置缺 `IMG_PROVIDER=codex`",
    "says not to look for another service": "不要去找别的出图服务",
}
# issue 95: no paid route and no other image service may be named in this guide.
forbidden = ["apimart", "OpenAI 兼容", "OpenAI-compatible", "OPENAI_API_KEY", "IMG_API_KEY", "IMG_BASE_URL",
             "Nano Banana", "Gemini Image", "Flux", "用户自备"]
missing = [why for why, needle in required.items() if needle not in text]
named = [word for word in forbidden if word in text]
if missing or named:
    if missing:
        print("SKILL.md is missing:", "; ".join(missing))
    if named:
        print("SKILL.md still names:", "; ".join(named))
    sys.exit(1)
print("ok")
