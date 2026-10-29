"""The approval page checks written beside the skills (issue 51), run here because CI does not collect *.test.py files.

They live in skills/builtin/video-script/storyboard-approval-page.test.py, because the edit guard for skill folders
wants a check file beside the skill it guards.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS_FILE = ROOT / "skills" / "builtin" / "video-script" / "storyboard-approval-page.test.py"


def test_the_approval_page_skill_checks_run_here_because_ci_does_not_collect_dot_test_dot_py_files():
    spec = importlib.util.spec_from_file_location("storyboard_approval_page_skill_text", CHECKS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = [getattr(module, name) for name in dir(module) if name.startswith("test_")]
    assert len(checks) >= 6  # the file really has its checks, so an empty pass cannot happen
    for check in checks:
        check()
