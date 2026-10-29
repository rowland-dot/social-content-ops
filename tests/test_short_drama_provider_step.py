"""Issue 53: short-drama step 16 no longer reads the video provider from the shell.

The checks live beside the skill, in skills/builtin/short-drama/provider-step.test.py, because the edit guard for
skill folders wants a check file there. pytest does not collect *.test.py files by name, so CI runs them from here.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS_FILE = ROOT / "skills" / "builtin" / "short-drama" / "provider-step.test.py"


def test_the_short_drama_provider_step_checks_run_here_because_ci_does_not_collect_dot_test_dot_py_files():
    spec = importlib.util.spec_from_file_location("short_drama_provider_step", CHECKS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = [getattr(module, name) for name in dir(module) if name.startswith("test_")]
    assert len(checks) == 3  # the file really has its checks, so an empty pass cannot happen
    for check in checks:
        check()
