"""The private work folder is found in one place (issue 136).

Seam: `skills/shared/scripts/private_work.py`, the one module that says where `work/` is and what to tell
a reader when it is missing. Every public piece of code that needs a private file asks it. Expected values
are literals; the project root is a throwaway folder.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("private_work", REPO / "skills/shared/scripts/private_work.py")
pw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pw)


def test_the_work_folder_is_the_work_folder_inside_the_project(tmp_path):
    (tmp_path / "work").mkdir()
    assert pw.work_dir(tmp_path) == tmp_path / "work"


def test_a_project_without_the_work_folder_has_none(tmp_path):
    assert pw.work_dir(tmp_path) is None


def test_a_file_inside_the_work_folder_is_found_by_its_path_under_it(tmp_path):
    (tmp_path / "work" / "docs").mkdir(parents=True)
    (tmp_path / "work" / "docs" / "a.md").write_text("x", encoding="utf-8")
    assert pw.private_file("docs/a.md", tmp_path) == tmp_path / "work" / "docs" / "a.md"


def test_a_file_that_is_not_in_the_work_folder_is_not_found(tmp_path):
    (tmp_path / "work").mkdir()
    assert pw.private_file("docs/a.md", tmp_path) is None


def test_the_missing_message_says_in_plain_words_what_is_missing_and_that_nothing_crashed():
    text = pw.missing_message("The paid-command list")
    assert text.startswith("The paid-command list lives in the private work folder (work/)")
    assert "is not here" in text and "Nothing was read from it" in text
