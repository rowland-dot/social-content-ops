"""Document check for issue 95: the guides an agent reads about making images send it to the Codex
subscription route and nowhere else.

Fails while ai-image-gen's SKILL.md, ecom-details-image's SKILL.md or the Xiaohongshu image-sourcing
guide still name a paid image route or another image service. Stock-photo sources (Unsplash, Pexels,
Pixabay) and the watermark steps are not generators and must stay.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BUILTIN = REPO / "skills/builtin"
AI_IMAGE_GEN = BUILTIN / "ai-image-gen/SKILL.md"
ECOM = BUILTIN / "ecom-details-image/SKILL.md"
SOURCING = BUILTIN / "xhs-note-creator/references/image-sourcing.md"

# Literal names from the issue, plus the key variables that only a paid setup needs.
FORBIDDEN = [
    r"apimart", r"OpenAI 兼容", r"OpenAI-compatible", r"OPENAI_API_KEY", r"IMG_API_KEY", r"IMG_BASE_URL",
    r"Nano Banana", r"Gemini Image", r"Flux", r"\bSD\b", r"text-to-image 服务", r"用户自备",
]


@pytest.mark.parametrize("path", [AI_IMAGE_GEN, ECOM, SOURCING], ids=lambda p: p.parent.name + "/" + p.name)
def test_the_guide_names_no_paid_route_and_no_other_image_service(path):
    text = path.read_text(encoding="utf-8")
    found = [pattern for pattern in FORBIDDEN if re.search(pattern, text)]
    assert not found, f"{path.relative_to(REPO)} still names: {found}"


@pytest.mark.parametrize("path", [AI_IMAGE_GEN, ECOM, SOURCING], ids=lambda p: p.parent.name + "/" + p.name)
def test_the_guide_names_the_codex_setting(path):
    assert "IMG_PROVIDER=codex" in path.read_text(encoding="utf-8")


def test_the_sourcing_guide_keeps_the_stock_photo_sources_and_the_watermark_steps():
    text = SOURCING.read_text(encoding="utf-8")
    for kept in ("Unsplash", "Pexels", "Pixabay", "裁剪去水印"):
        assert kept in text, kept


def test_the_sourcing_guide_points_generated_images_at_the_ai_image_gen_script():
    assert "skills/shared/scripts/ai_image.py" in SOURCING.read_text(encoding="utf-8")


@pytest.mark.parametrize("skill", ["ai-image-gen", "ecom-details-image"])
def test_the_skills_own_codex_route_document_check_still_passes(skill):
    r = subprocess.run([sys.executable, str(BUILTIN / skill / "codex-route.test.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
