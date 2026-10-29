"""The candidate report on LibTV's real packages (issue 37), when the checked copies are on this machine.

The evidence folder is git-ignored, so these cases skip on a fresh clone and in CI; the synthetic cases in
test_candidate.py cover the same behaviour there. Real neighbouring versions are used:
- skill documents 1.1.2 against 1.1.3 (LibTV's two packages hold byte-identical documents), and 1.0.2 against 1.1.3;
- the program 1.0.2 against 1.1.3, where `workspace` is the added command group.
The stand-in serves the real 1.1.3 files under a made-up newer folder, so "1.1.3" inside the program reads as a
mismatch with the published folder, which the report is expected to say.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "work" / ".scratch" / "easel-setup-gaps" / "evidence" / "32-libtv-probe" / "reopen-2026-10-14"
)
SKILL_113 = EVIDENCE / "1.1.3-libtv-cli-skill.zip"
SKILL_112 = EVIDENCE / "1.1.2-libtv-cli-skill.zip"
SKILL_102 = EVIDENCE / "libtv-cli-skill.zip.1"
PROGRAM_113 = EVIDENCE / "1.1.3-libtv-linux-x64.zip"
PROGRAM_102 = EVIDENCE / "libtv-linux-x64.zip.1"

pytestmark = pytest.mark.skipif(
    not all(p.is_file() for p in (SKILL_113, SKILL_112, SKILL_102, PROGRAM_113, PROGRAM_102)),
    reason="the real packages are in the local evidence folder only",
)

SKILL_ZIP_SHA = "b3277d4a07bb1c28442e12db3023bdd9634b64ab23f26e3bf7ad9bf2d3c84072"
PROGRAM_ZIP_SHA = "cf86f462c5aed60f95dca978cc91ece98c60bcfa27337da008ad59953c3ea7da"
PROGRAM_SHA = "e79ad52170556b44e957174f880c8a69057f668ddd0b9a4011524cac072c31f3"


def _docs_of(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}


def _set_up(lt, docs_zip: Path):
    """pinned: the real 1.0.2 program (kept copy) and the documents of DOCS_ZIP; published as 1.1.4: the real 1.1.3 files"""
    lt.write_vendor(_docs_of(docs_zip))
    kept = lt.store / "pinned" / "1.1.3" / "libtv-linux-x64.zip"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(PROGRAM_102.read_bytes())
    lt.publish("1.1.4", program_zip_bytes=PROGRAM_113.read_bytes(), skill_zip_bytes=SKILL_113.read_bytes())
    lt.set_channel("1.1.4")


def test_real_1_1_2_documents_against_real_1_1_3_are_identical_and_the_program_adds_workspace(lt):
    _set_up(lt, SKILL_112)
    result = lt.run("candidate", "1.1.4", timeout=300)
    assert result.code == 0, result.out + result.err
    out = result.out
    assert "No document changes" in out
    for path in ("workspace", "workspace create", "workspace list", "workspace update", "workspace use", "workspace unuse"):
        line = next((ln for ln in out.splitlines() if ln.startswith(f"- Added command `{path}`")), None)
        assert line, f"`{path}` is not reported as added:\n{out}"
    assert "- Added option `project create --workspace`" in out
    assert "28385926" in out and PROGRAM_ZIP_SHA in out and SKILL_ZIP_SHA in out and PROGRAM_SHA in out
    assert "77667686" in out
    assert "Version strings found in the program: 1.1.3" in out
    assert "does not match the published version 1.1.4" in out
    assert "Paid-run section: none in the command tree" in out


def test_real_1_0_2_documents_against_real_1_1_3_list_the_new_and_changed_files(lt):
    _set_up(lt, SKILL_102)
    out = lt.run("candidate", "1.1.4", timeout=300).out
    added = next(ln for ln in out.splitlines() if ln.startswith("Added:"))
    assert "commands/workspace.md" in added and "examples/workflow/workspace-setup.md" in added
    changed = next(ln for ln in out.splitlines() if ln.startswith("Changed:"))
    assert "SKILL.md" in changed and "commands/node.md" in changed and "scripts/install.md" in changed
    assert "channel 240" in out, "the installer in the real package follows the same channel as the pin"
    assert "Self-update or install instructions in added document lines (" in out, "the install scripts changed"
