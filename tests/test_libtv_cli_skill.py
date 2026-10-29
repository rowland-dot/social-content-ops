"""LibTV's official CLI skill (libtv-cli 1.1.3) as an Easel wrapper skill, issue 32.

Seams (the issue's Agent Brief key interfaces and acceptance criteria): the real validator
function, the real skill-library function in web/app.py, the vendored package folder compared
with its recorded per-file checksums (and, when the downloaded package is on this machine, with
the package itself) through the compare script's command line, where the setup script keeps the
download address and where the checks file keeps the pins, and the written rules.
LibTV's own files sit unchanged under references/vendor/; SKILL.md is Easel's wrapper.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import web.app as web

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "builtin" / "libtv-cli"
VENDOR_DIR = SKILL_DIR / "references" / "vendor"
MANIFEST = ROOT / "docs" / "vendored" / "libtv-cli-1.1.3-files.sha256"
NOTE = ROOT / "docs" / "vendored" / "libtv-cli-source.md"
COMPARE = ROOT / "ops" / "wsl-setup" / "libtv-vendor-compare.py"
SETUP_DIR = ROOT / "ops" / "wsl-setup"
SPEC = ROOT / "docs" / "specs" / "2026-10-12-easel-replatform-spec.md"
PKG_ZIP = (
    ROOT / ".scratch" / "easel-setup-gaps" / "evidence" / "32-libtv-probe" / "reopen-2026-10-14"
    / "1.1.3-libtv-cli-skill.zip"
)

PKG_SHA256 = "b3277d4a07bb1c28442e12db3023bdd9634b64ab23f26e3bf7ad9bf2d3c84072"
PROGRAM_ZIP_SHA256 = "cf86f462c5aed60f95dca978cc91ece98c60bcfa27337da008ad59953c3ea7da"
PROGRAM_SHA256 = "e79ad52170556b44e957174f880c8a69057f668ddd0b9a4011524cac072c31f3"
PROGRAM_URL = "https://liblibai-web-static.liblib.cloud/cli/1.1.3/libtv-linux-x64.zip"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _validator():
    spec = importlib.util.spec_from_file_location("validate_skills", ROOT / "scripts" / "validate_skills.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compare(source: Path, folder: Path):
    return subprocess.run(
        [sys.executable, str(COMPARE), str(source), str(folder)], capture_output=True, text=True, timeout=120
    )


def _copy_vendor(tmp_path: Path) -> Path:
    dest = tmp_path / "vendor-copy"
    shutil.copytree(VENDOR_DIR, dest)
    return dest


# ---- LibTV's own files, byte for byte ------------------------------------------------------------


def test_manifest_lists_the_44_files_of_package_1_1_3():
    lines = [ln for ln in _text(MANIFEST).splitlines() if ln.strip()]
    assert len(lines) == 44
    assert all(re.fullmatch(r"[0-9a-f]{64}  \S.*", ln) for ln in lines)


def test_vendored_folder_matches_the_manifest_byte_for_byte():
    proc = _compare(MANIFEST, VENDOR_DIR)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "44 files" in proc.stdout


@pytest.mark.skipif(not PKG_ZIP.is_file(), reason="the downloaded package is in the local evidence folder only")
def test_vendored_folder_matches_the_downloaded_package_itself():
    assert hashlib.sha256(PKG_ZIP.read_bytes()).hexdigest() == PKG_SHA256
    proc = _compare(PKG_ZIP, VENDOR_DIR)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "44 files" in proc.stdout


def test_compare_script_sees_a_changed_file(tmp_path):
    copy = _copy_vendor(tmp_path)
    target = copy / "commands" / "account.md"
    target.write_bytes(target.read_bytes() + b" ")
    proc = _compare(MANIFEST, copy)
    assert proc.returncode == 1
    assert "commands/account.md" in proc.stdout


def test_compare_script_sees_an_extra_and_a_missing_file(tmp_path):
    copy = _copy_vendor(tmp_path)
    (copy / "extra.md").write_text("x", encoding="utf-8")
    proc = _compare(MANIFEST, copy)
    assert proc.returncode == 1 and "extra.md" in proc.stdout
    (copy / "extra.md").unlink()
    (copy / "commands" / "group.md").unlink()
    proc = _compare(MANIFEST, copy)
    assert proc.returncode == 1 and "commands/group.md" in proc.stdout


def test_compare_script_cannot_run_is_not_a_pass(tmp_path):
    empty = tmp_path / "empty.sha256"
    empty.write_text("", encoding="utf-8")
    # exit 2 alone proves nothing (Python itself exits 2 for a missing script): the script must say why
    for source, folder in ((empty, VENDOR_DIR), (MANIFEST, tmp_path / "no-such-folder"), (tmp_path / "no-such-source", VENDOR_DIR)):
        proc = _compare(source, folder)
        assert proc.returncode == 2 and "cannot compare" in proc.stderr, proc.stderr


# ---- Easel's skill contract --------------------------------------------------------------------


def test_shipped_header_alone_fails_the_contract_check_for_the_three_known_reasons(tmp_path):
    shipped = tmp_path / "libtv-cli"
    shipped.mkdir()
    shutil.copy(VENDOR_DIR / "SKILL.md", shipped / "SKILL.md")
    errors = _validator().validate(shipped / "SKILL.md")
    joined = "\n".join(errors)
    assert "missing required keys: layer" in joined
    assert "invalid layer" in joined
    assert "description must state when the skill should trigger" in joined


def test_skill_contract_validator_accepts_the_wrapper():
    assert _validator().validate(SKILL_DIR / "SKILL.md") == []


def test_skill_library_lists_it_under_produce_with_the_wrappers_description():
    listed = [s for s in web.get_skills() if s["name"] == "libtv-cli"]
    assert len(listed) == 1
    skill = listed[0]
    assert skill["layer"] == "produce"
    assert "libtv" in skill["description"].lower() and skill["description"].strip()


def test_vendor_skill_is_not_a_second_skill_in_the_library():
    assert sum(1 for s in web.get_skills() if "libtv" in s["name"].lower()) == 1


def test_wrapper_sends_the_agent_to_the_vendor_files_and_keeps_updates_to_the_setup_script():
    text = _text(SKILL_DIR / "SKILL.md")
    assert "`references/vendor/SKILL.md`" in text
    # the one Easel rule: LibTV's text asks the agent to install, update and edit; only the setup script does
    assert "ops/wsl-setup/setup.sh" in text
    for vendor_script in ("install-libtv-cli.sh", "install-libtv-cli.ps1", "install-libtv-cli.bat", "scripts/install.md"):
        assert vendor_script in text, f"the wrapper does not name the vendor's {vendor_script}"


def test_wrapper_adds_no_paid_run_rule_of_its_own():
    # the paid-run rule lives in CLAUDE.md and Easel's agent rules; the wrapper has no approval rule of its own
    text = _text(SKILL_DIR / "SKILL.md")
    assert "question tool" not in text.lower() and "yes" not in text.lower()


# ---- the setup script keeps the address, the checks file keeps the pins ------------------------


def test_download_address_lives_in_the_script_that_reads_it_and_is_versioned():
    checks = _text(SETUP_DIR / "checks.sh")
    setup = _text(SETUP_DIR / "setup.sh")
    assert not re.search(r"^LIBTV_URL=", checks, re.M), "checks.sh does not assign the address"
    assert re.search(rf"^LIBTV_URL={re.escape(PROGRAM_URL)}$", setup, re.M)
    assert setup.index("LIBTV_URL=") > setup.index('. "$HERE/checks.sh"'), "assigned after checks.sh is sourced"
    assert "/cli/1.1.3/" in PROGRAM_URL


def test_pins_stay_in_the_checks_file():
    checks = _text(SETUP_DIR / "checks.sh")
    assert f"LIBTV_ZIP_SHA256=${{LIBTV_ZIP_SHA256:-{PROGRAM_ZIP_SHA256}}}" in checks
    assert f"LIBTV_SHA256=${{LIBTV_SHA256:-{PROGRAM_SHA256}}}" in checks


def test_setup_step_never_uses_the_vendor_installer():
    setup = _text(SETUP_DIR / "setup.sh")
    checks = _text(SETUP_DIR / "checks.sh")
    assert "install-libtv-cli" not in setup and "install-libtv-cli" not in checks
    assert "LIBTV_DISABLE_REPORT" in checks


# ---- the written record ------------------------------------------------------------------------


def test_source_note_records_the_pins_and_where_everything_goes():
    note = _text(NOTE)
    for needle in (
        PKG_SHA256,
        PROGRAM_ZIP_SHA256,
        PROGRAM_SHA256,
        "1.1.3",
        "api2.liblib.art/api/www/landing-activities/getById?id=240",
        "/usr/local/bin/libtv",
        "credentials.json",
        "LIBTV_DISABLE_REPORT",
        "no licence",
        "libtv-cli-1.1.3-files.sha256",
    ):
        assert needle in note, f"the source note does not say: {needle}"




