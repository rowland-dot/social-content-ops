"""ai_image.py 的 Agnes AI 辅助函数测试（issue #51）。

Agnes 没有 /images/edits 与 /images/variations：文生图 / 图生图 / 变体统一打
/images/generations，输入图放 extra_body.image，size 用档位（1K/2K/3K/4K）+
独立 ratio，n>1 必须客户端循环。

issue 95：本项目的图片只走 Codex 订阅，没有 IMG_PROVIDER=codex 时 text2img / img2img /
variations 在任何请求之前就停下（见 tests/test_codex_image_route.py）。原来经三个子命令
检查 Agnes 请求形状的测试因此删掉了——那条路线不会再运行；这里只留不发请求的纯函数测试
（域名识别、尺寸换算），为的是上游同步时这些函数仍然对得上。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_SCRIPTS = PROJECT_ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

import ai_image  # noqa: E402


# ── provider 检测 ─────────────────────────────────────────

@pytest.mark.parametrize("base", [
    "https://api.agnes-ai.cn/v1",
    "https://AGNES-AI.CN/v1",
])
def test_detect_provider_matches_agnes_host(base: str) -> None:
    assert ai_image.detect_provider(base) == "agnes"


@pytest.mark.parametrize("base", [
    "https://api.openai.com/v1",
    "https://token.lightvela.com/v1",
    "https://api.apimart.ai/v1",
])
def test_detect_provider_defaults_openai(base: str) -> None:
    assert ai_image.detect_provider(base) == "openai"


# ── size 归一 ────────────────────────────────────────────

def test_split_size_pixel_maps_to_tier_and_ratio() -> None:
    assert ai_image.agnes_split_size("1024x1024", "2k") == ("1K", "1:1")
    assert ai_image.agnes_split_size("1920x1080", "2k") == ("2K", "16:9")
    assert ai_image.agnes_split_size("3840x2160", "1k") == ("3K", "16:9")


def test_split_size_ratio_uses_resolution_tier() -> None:
    assert ai_image.agnes_split_size("16:9", "2k") == ("2K", "16:9")
    assert ai_image.agnes_split_size("1:1", "1k") == ("1K", "1:1")


def test_split_size_unknown_pixel_fails() -> None:
    with pytest.raises(SystemExit):
        ai_image.agnes_split_size("not-a-size", "2k")


def test_split_size_unlisted_pixel_is_reduced() -> None:
    # 官方未列的精确尺寸（如 1920x1080）按边长推档位、按最大公约数化简比例。
    assert ai_image.agnes_split_size("1920x1080", "2k") == ("2K", "16:9")
    assert ai_image.agnes_split_size("800x600", "1k") == ("1K", "4:3")


# ── detect_provider 域名匹配的防误判（审计补） ──────────────────

def test_detect_provider_rejects_lookalike_domains():
    """含 agnes 字母序列的无关域名不得误判成 Agnes（子串匹配的历史 bug）。"""
    for url in ("https://api.stagneschurch.com/v1", "https://api.magnes.com/v1",
                "https://notagnes.example.com/v1"):
        assert ai_image.detect_provider(url) == "openai", url


def test_detect_provider_accepts_known_agnes_domains():
    for url in ("https://api.agnes-ai.cn/v1", "https://apihub.agnes-ai.com/v1",
                "https://x.agnes-ai.cn/v1"):
        assert ai_image.detect_provider(url) == "agnes", url
