"""Document check for issue 95: references/image-sourcing.md names the Codex route (through the
ai-image-gen script) as the only source of generated images, and no other image service.

Stock-photo sources (Unsplash, Pexels, Pixabay) and the watermark steps are not generators and stay.
Run: python skills/builtin/xhs-note-creator/image-sourcing.test.py   (exit 0 = pass). tests/test_image_docs_codex_only.py
at the repo root checks the same file under pytest.
"""
from pathlib import Path
import sys

text = (Path(__file__).resolve().parent / "references" / "image-sourcing.md").read_text(encoding="utf-8")

required = {
    "names the Codex setting": "IMG_PROVIDER=codex",
    "names the script": "skills/shared/scripts/ai_image.py",
    "keeps Unsplash": "Unsplash",
    "keeps Pexels": "Pexels",
    "keeps Pixabay": "Pixabay",
    "keeps the watermark crop step": "裁剪去水印",
}
forbidden = ["Nano Banana", "Gemini Image", "Flux", "text-to-image 服务", "用户自备", "apimart"]
missing = [why for why, needle in required.items() if needle not in text]
named = [word for word in forbidden if word in text]
if missing or named:
    if missing:
        print("image-sourcing.md is missing:", "; ".join(missing))
    if named:
        print("image-sourcing.md still names:", "; ".join(named))
    sys.exit(1)
print("ok")
