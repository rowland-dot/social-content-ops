import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import login_state
import tmall_login as tl

class Ctx:
    def __init__(self, seq): self.seq = list(seq)
    def cookies(self): return self.seq.pop(0) if len(self.seq) > 1 else self.seq[0]

def test_login_is_judged_by_the_taobao_login_cookies():
    assert tl.is_logged_in([{"name": "unb", "value": "123"}]) is True
    assert tl.is_logged_in([{"name": "unb", "value": ""}, {"name": "x", "value": "1"}]) is False

def test_profile_dir_is_the_tmall_folder_under_the_shared_profile_root(tmp_path):
    assert tl.profile_dir(tmp_path) == tmp_path / "TmallProfile"

def test_waiting_reports_window_login_then_success(tmp_path):
    status = tmp_path / "tmall.status.json"; clock = iter(range(0, 1000))
    ctx = Ctx([[], [], [{"name": "lgc", "value": "a"}]])
    ok = tl.wait_for_login(ctx, str(status), timeout=60, poll=1, clock=lambda: next(clock), sleep=lambda s: None)
    assert ok is True and login_state.read_status(str(status))["state"] == "success"

def test_waiting_gives_up_after_the_limit_and_says_expired(tmp_path):
    status = tmp_path / "tmall.status.json"; clock = iter(range(0, 1000))
    ok = tl.wait_for_login(Ctx([[]]), str(status), timeout=5, poll=1, clock=lambda: next(clock), sleep=lambda s: None)
    assert ok is False and login_state.read_status(str(status))["state"] == "expired"

def test_the_window_login_message_tells_ro_what_to_do(tmp_path):
    status = tmp_path / "s.json"; clock = iter(range(0, 10))
    tl.wait_for_login(Ctx([[]]), str(status), timeout=1, poll=1, clock=lambda: next(clock), sleep=lambda s: None)
    # the first status written while waiting is the window prompt; it is overwritten by expired, so check the constant
    assert "扫描" in tl.WINDOW_MESSAGE and "淘宝" in tl.WINDOW_MESSAGE
