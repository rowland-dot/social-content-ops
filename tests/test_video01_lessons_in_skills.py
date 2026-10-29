"""The video 01 lessons (issue 43) are written into the video skills, in the lines the agent reads.

The checks live beside the skills, in skills/builtin/auto-short-video/video01-lessons.test.py, because the edit guard
for skill folders wants a check file there. pytest does not collect *.test.py files by name, so CI runs them from here.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS_FILE = ROOT / "skills" / "builtin" / "auto-short-video" / "video01-lessons.test.py"


def test_the_video01_lesson_checks_run_here_because_ci_does_not_collect_dot_test_dot_py_files():
    spec = importlib.util.spec_from_file_location("video01_lessons_skill_text", CHECKS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = [getattr(module, name) for name in dir(module) if name.startswith("test_")]
    assert len(checks) >= 20  # the file really has its checks, so an empty pass cannot happen
    for check in checks:
        check()
