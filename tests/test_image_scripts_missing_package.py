"""Missing-package behaviour of the three shared image scripts.

remove_bg.py, img_enhance.py and meme_ops.py must answer a missing library with one
"ERROR:" line on stderr that names the package and the pip command, then exit 3 -- never a
raw Python traceback.

Each case runs the real script through runpy with sys.argv set (the same entry the command
line uses) while the library is hidden by putting None into sys.modules. Exceptions that
would reach the shell as a traceback are turned into exit 1 plus the word "Traceback" in
stderr, which is what a real process would show.

remove_bg remove/selftest are only ever run with a library hidden: unhidden they would
download a ~170 MB model.
"""
from __future__ import annotations

import io
import re
import runpy
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/shared/scripts"


def _hide(monkeypatch, *names: str) -> None:
    """Make `import <name>` fail. Cached submodules are dropped so a fresh import really runs."""
    for key in list(sys.modules):
        if any(key == n or key.startswith(n + ".") for n in names):
            monkeypatch.delitem(sys.modules, key, raising=False)
    for n in names:
        monkeypatch.setitem(sys.modules, n, None)


def _fresh_rembg_without_onnxruntime(monkeypatch) -> None:
    """Hide onnxruntime only. rembg stays importable but is dropped from the module cache so its
    real import-time behaviour runs: it prints a hint and calls sys.exit(1)."""
    for key in list(sys.modules):
        if key == "rembg" or key.startswith("rembg."):
            monkeypatch.delitem(sys.modules, key, raising=False)
    monkeypatch.setitem(sys.modules, "onnxruntime", None)


def _run(monkeypatch, script: str, *argv: str):
    """Run scripts/<script> as __main__; return (exit_code, stdout, stderr)."""
    monkeypatch.setattr(sys, "argv", [script, *argv])
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with redirect_stdout(out), redirect_stderr(err):
        try:
            runpy.run_path(str(SCRIPTS / script), run_name="__main__")
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        except BaseException:  # an uncaught error is a traceback and exit 1 in a real process
            code = 1
            traceback.print_exc(file=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def png(tmp_path) -> Path:
    """A real input image. Made before any library is hidden."""
    from PIL import Image

    p = tmp_path / "in.png"
    Image.new("RGB", (64, 64), (120, 40, 200)).save(p)
    return p


def _assert_install_message(code: int, out: str, err: str, package: str) -> None:
    assert "Traceback" not in out + err, f"raw traceback leaked:\n{err}"
    assert code == 3, f"expected exit 3, got {code}\nstderr:\n{err}"
    # the message is the script's own ERROR line, naming the package and how to install it
    assert re.search(rf"^ERROR:[^\n]*{package}", err, re.M), f"no ERROR line naming {package}:\n{err}"
    assert "pip install" in err, f"no pip install hint:\n{err}"


# ---- remove_bg ----------------------------------------------------------------

def test_remove_bg_remove_without_rembg(monkeypatch, png, tmp_path):
    _hide(monkeypatch, "rembg")
    code, out, err = _run(monkeypatch, "remove_bg.py", "remove", "-i", str(png), "-o", str(tmp_path / "o.png"))
    _assert_install_message(code, out, err, "rembg")


def test_remove_bg_remove_without_onnxruntime(monkeypatch, png, tmp_path):
    # rembg itself calls sys.exit(1) while importing when onnxruntime is absent
    _fresh_rembg_without_onnxruntime(monkeypatch)
    code, out, err = _run(monkeypatch, "remove_bg.py", "remove", "-i", str(png), "-o", str(tmp_path / "o.png"))
    _assert_install_message(code, out, err, "onnxruntime")


def test_remove_bg_selftest_without_rembg(monkeypatch):
    _hide(monkeypatch, "rembg")
    code, out, err = _run(monkeypatch, "remove_bg.py", "selftest")
    _assert_install_message(code, out, err, "rembg")


def test_remove_bg_check_without_onnxruntime_reports_every_dependency(monkeypatch):
    _fresh_rembg_without_onnxruntime(monkeypatch)
    code, out, err = _run(monkeypatch, "remove_bg.py", "check")
    assert "Traceback" not in out + err, err
    for name in ("rembg", "onnxruntime", "Pillow"):
        assert re.search(rf"^[✅❌] {name}", out, re.M), f"check printed no line for {name}:\n{out}\n{err}"
    assert re.search(r"^❌ onnxruntime", out, re.M), out
    assert code == 3, f"expected exit 3, got {code}\n{out}\n{err}"


# ---- img_enhance --------------------------------------------------------------

def test_img_enhance_enhance_without_pillow(monkeypatch, png, tmp_path):
    _hide(monkeypatch, "PIL")
    code, out, err = _run(monkeypatch, "img_enhance.py", "enhance", "-i", str(png), "-o", str(tmp_path / "o.png"))
    _assert_install_message(code, out, err, "Pillow")


def test_img_enhance_selftest_without_pillow(monkeypatch):
    _hide(monkeypatch, "PIL")
    code, out, err = _run(monkeypatch, "img_enhance.py", "selftest")
    _assert_install_message(code, out, err, "Pillow")


def test_img_enhance_denoise_without_opencv_still_skips_and_succeeds(monkeypatch, png, tmp_path):
    _hide(monkeypatch, "cv2")
    dest = tmp_path / "o.png"
    code, out, err = _run(monkeypatch, "img_enhance.py", "enhance", "-i", str(png), "-o", str(dest),
                          "--denoise", "--scale", "1")
    assert code == 0, f"exit {code}\n{out}\n{err}"
    assert dest.is_file()


def test_img_enhance_with_everything_present_writes_output(monkeypatch, png, tmp_path):
    dest = tmp_path / "o.png"
    code, out, err = _run(monkeypatch, "img_enhance.py", "enhance", "-i", str(png), "-o", str(dest))
    assert code == 0, f"exit {code}\n{out}\n{err}"
    assert dest.is_file()


# ---- meme_ops -----------------------------------------------------------------

def test_meme_ops_make_without_pillow(monkeypatch, png, tmp_path):
    _hide(monkeypatch, "PIL")
    code, out, err = _run(monkeypatch, "meme_ops.py", "make", "-i", str(png), "-o", str(tmp_path / "o.png"),
                          "--top", "hi")
    _assert_install_message(code, out, err, "Pillow")


def test_meme_ops_selftest_without_pillow(monkeypatch):
    _hide(monkeypatch, "PIL")
    code, out, err = _run(monkeypatch, "meme_ops.py", "selftest")
    _assert_install_message(code, out, err, "Pillow")


def test_meme_ops_with_everything_present_writes_output(monkeypatch, png, tmp_path):
    dest = tmp_path / "o.png"
    code, out, err = _run(monkeypatch, "meme_ops.py", "make", "-i", str(png), "-o", str(dest), "--top", "hi")
    assert code == 0, f"exit {code}\n{out}\n{err}"
    assert dest.is_file()
