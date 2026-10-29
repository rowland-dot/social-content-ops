"""Issue 125, seam 2: creation_guide.py finds an account's creation guide where its profile is."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "shared" / "scripts" / "creation_guide.py"


def run(*args, env_extra=None):
    env = {**os.environ, "EASEL_PROFILE_DIRS": "", **(env_extra or {})}
    return subprocess.run([sys.executable, str(SCRIPT), "check", *args],
                          capture_output=True, text=True, env=env, cwd=ROOT)


def test_guide_in_profiles_folder_is_named_with_its_date(tmp_path):
    guide = tmp_path / "acme-test" / "creation-guide.md"
    guide.parent.mkdir()
    guide.write_text("# Guide\n", encoding="utf-8")
    os.utime(guide, (1761696000, 1761696000))  # 2025-10-29 00:00 UTC
    r = run("--brand", "acme-test", "--profiles-dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert str(guide) in r.stdout
    assert re.search(r"2025-10-29", r.stdout)


def test_missing_guide_stops_the_agent_and_offers_the_template(tmp_path):
    (tmp_path / "acme-test").mkdir()
    r = run("--brand", "acme-test", "--profiles-dir", str(tmp_path))
    assert r.returncode == 2
    out = r.stdout + r.stderr
    assert "no creation guide" in out.lower()
    assert "profiles/_template/creation-guide.md" in out
    assert "stop" in out.lower() and "draw and write nothing" in out.lower()


def test_guide_of_a_profile_mapped_outside_the_repository(tmp_path):
    outside = tmp_path / "kb" / "profile"
    outside.mkdir(parents=True)
    (outside / "creation-guide.md").write_text("# Guide\n", encoding="utf-8")
    r = run("--brand", "acme-test", env_extra={"EASEL_PROFILE_DIRS": f"acme-test={outside}"})
    assert r.returncode == 0, r.stderr
    assert str(outside / "creation-guide.md") in r.stdout


# ---- seam 1: the template and the guides of the repository-held accounts ----------------------

PROFILES = ROOT / "profiles"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_template_guide_has_an_images_and_a_posts_part_and_holds_no_client_material():
    text = read(PROFILES / "_template" / "creation-guide.md")
    assert "## Images" in text and "## Posts" in text
    assert text.index("## Images") < text.index("## Posts")
    assert "Tmall" not in text
    assert "creation-guide.md" in read(PROFILES / "_template" / "README.md")


def test_an_account_whose_guide_was_made_from_the_template_is_found(tmp_path):
    guide = tmp_path / "northwind" / "creation-guide.md"
    guide.parent.mkdir()
    guide.write_text(read(PROFILES / "_template" / "creation-guide.md"), encoding="utf-8")
    r = run("--brand", "northwind", "--profiles-dir", str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert str(guide) in r.stdout
