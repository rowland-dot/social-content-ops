#!/usr/bin/env python3
# skills/shared/scripts/tmall_login.py
"""tmall_login.py: The owner's own Taobao login, saved for Easel's Tmall reading. One QR scan in a visible window, then reused with no window.

Commands: login (visible window, waits for the scan), status (cookies only, no network)."""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import login_state  # noqa: E402

LOGIN_URL = "https://login.taobao.com/member/login.jhtml"
COOKIES = ("unb", "_nk_", "lgc")
ARGS = ["--no-proxy-server", "--disable-blink-features=AutomationControlled"]
WINDOW_MESSAGE = "请用手机淘宝扫描窗口里的二维码登录（只需这一次）"

def profile_dir(base=None) -> Path:
    root = Path(base).expanduser() if base else Path.home() / ".easel-browser-profiles"
    return root / "TmallProfile"

def is_logged_in(cookies) -> bool:
    return any(c.get("name") in COOKIES and c.get("value") for c in cookies)

def wait_for_login(context, status_file, *, timeout=300, poll=1.0, clock=time.monotonic, sleep=time.sleep) -> bool:
    login_state.write_status(status_file, "window_login", WINDOW_MESSAGE)
    deadline = clock() + timeout
    while clock() < deadline:
        if is_logged_in(context.cookies()):
            login_state.write_status(status_file, "success", "已登录")
            return True
        sleep(poll)
    login_state.write_status(status_file, "expired", "超时未扫码；重新运行 tmall_login.py login，再用手机淘宝扫一次")
    return False

def _context(p, headless: bool, base=None):
    d = profile_dir(base); d.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(str(d), headless=headless, args=ARGS,
                                                viewport={"width": 1280, "height": 900}, locale="zh-CN")

def cmd_login(a) -> int:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _context(p, headless=False, base=a.profile_base)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        ok = wait_for_login(ctx, a.status_file, timeout=a.timeout)
        ctx.close()
    return 0 if ok else 1

def cmd_status(a) -> int:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _context(p, headless=True, base=a.profile_base)
        ok = is_logged_in(ctx.cookies()); ctx.close()
    print("logged in (cookies present; expiry is only found out on a visit)" if ok else "not logged in")
    return 0 if ok else 1

def main(argv=None) -> int:
    login_state.configure_stdio()
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("login", cmd_login), ("status", cmd_status)):
        p = sub.add_parser(name); p.add_argument("--profile-base"); p.add_argument("--status-file", default="outputs/_login/tmall.status.json")
        p.add_argument("--timeout", type=int, default=300); p.set_defaults(func=fn)
    a = ap.parse_args(argv)
    return a.func(a)

if __name__ == "__main__":
    sys.exit(main())
