"""`skills/shared/scripts/zhihu_answer.py` 发布结果判定的行为测试。

被测缺陷：脚本点完发布按钮后，只要页面地址含 "question" 就报成功。知乎问题页
地址永远含它，登录页的回跳参数（next=%2Fquestion%2F...）也含它，所以没发出去
的回答也会读成「已发布」，下一步还会往发布日志里写一条假记录。

契约：真发（--exec）时，只有「点击后页面落在同一问题下、且回答 id 不是输入地址
里原有的那个」才算 verified；其余一律 success=False，命令行退出码非 0。

接缝只有两个：公开函数 `publish_answer`（用假的 Playwright，不开浏览器、不联网）
和命令行入口 `main`。浏览器是系统边界，假的只替它；脚本自己的函数一概不 mock。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts" / "zhihu_answer.py"

# 故意用与任何默认值/示例都不相同的 id，免得判定写成「恰好等于某个常量」也能蒙混过关。
QID = "398172645"
OTHER_QID = "552210987"
THEIR_AID = "7741001"
NEW_AID = "9930582"

QUESTION = f"https://www.zhihu.com/question/{QID}"


class _Element:
    def __init__(self, text: str = ""):
        self._text = text

    def inner_text(self) -> str:
        return self._text

    def is_visible(self) -> bool:
        return True


class _Locator:
    @property
    def first(self):
        return self

    def wait_for(self, **_kw):
        pass

    def dispatch_event(self, *_a, **_kw):
        pass

    def focus(self):
        pass

    def scroll_into_view_if_needed(self):
        pass


class _Keyboard:
    def press(self, *_a, **_kw):
        pass

    def type(self, *_a, **_kw):
        pass


class _Page:
    """已登录、编辑器能打开、发布按钮能点的知乎问题页；点发布后地址变成 final_url。"""

    def __init__(self, final_url: str):
        self._final_url = final_url
        self.url = ""
        self.keyboard = _Keyboard()

    def goto(self, url, **_kw):
        self.url = url

    def wait_for_timeout(self, _ms):
        pass

    def wait_for_selector(self, *_a, **_kw):
        pass

    def query_selector(self, selector):
        if "SignContainer" in selector:  # 登录检查：已登录，没有登录框
            return None
        return _Element("某个知乎问题")  # 标题 / 编辑器

    def locator(self, _selector):
        return _Locator()

    def evaluate(self, script, _arg=None):
        if "发布回答" in script and "dispatchEvent" in script:  # 点发布按钮
            self.url = self._final_url
            return "发布回答"
        if "编辑回答" in script:  # 是否「已答过」检查
            return False
        return None  # el.click() 之类


class _Context:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        pass


@pytest.fixture
def zhihu():
    spec = importlib.util.spec_from_file_location("zhihu_answer_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def browser_ends_at(monkeypatch):
    """用法：browser_ends_at(final_url) —— 装上假 Playwright，点发布后浏览器停在 final_url。"""

    def install(final_url: str) -> None:
        page = _Page(final_url)

        class _Chromium:
            def launch_persistent_context(self, *_a, **_kw):
                return _Context(page)

        class _Playwright:
            chromium = _Chromium()

        @contextmanager
        def sync_playwright():
            yield _Playwright()

        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.sync_playwright = sync_playwright
        pkg = types.ModuleType("playwright")
        pkg.sync_api = sync_api
        monkeypatch.setitem(sys.modules, "playwright", pkg)
        monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    return install


def _publish(zhihu, question_url=QUESTION):
    return zhihu.publish_answer(question_url, "回答正文", dry_run=False)


# ---- publish_answer：五种结局 ------------------------------------------------

def test_still_on_the_question_page_is_not_confirmed(zhihu, browser_ends_at):
    browser_ends_at(QUESTION)
    result = _publish(zhihu)
    assert result["success"] is False
    assert result["outcome"] == "unverified"


def test_sign_in_redirect_is_login_required_even_though_next_mentions_question(zhihu, browser_ends_at):
    browser_ends_at(f"https://www.zhihu.com/signin?next=%2Fquestion%2F{QID}")
    result = _publish(zhihu)
    assert result["success"] is False
    assert result["outcome"] == "login_required"


def test_new_answer_under_the_same_question_is_verified(zhihu, browser_ends_at):
    answer_url = f"{QUESTION}/answer/{NEW_AID}"
    browser_ends_at(answer_url)
    result = _publish(zhihu)
    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert result["url"] == answer_url


def test_answer_under_a_different_question_is_not_ours(zhihu, browser_ends_at):
    browser_ends_at(f"https://www.zhihu.com/question/{OTHER_QID}/answer/{NEW_AID}")
    result = _publish(zhihu)
    assert result["success"] is False


def test_answer_address_given_as_input_is_not_evidence_of_our_post(zhihu, browser_ends_at):
    theirs = f"{QUESTION}/answer/{THEIR_AID}"
    browser_ends_at(theirs)
    result = _publish(zhihu, question_url=theirs)
    assert result["success"] is False
    assert result["outcome"] == "unverified"


def test_input_with_trailing_slash_query_and_fragment_still_matches_the_question(zhihu, browser_ends_at):
    browser_ends_at(f"{QUESTION}/answer/{NEW_AID}")
    result = _publish(zhihu, question_url=f"{QUESTION}/?utm_source=share#anchor")
    assert result["success"] is True
    assert result["outcome"] == "verified"


def test_new_answer_beside_a_pasted_answer_address_is_verified(zhihu, browser_ends_at):
    browser_ends_at(f"{QUESTION}/answer/{NEW_AID}")
    result = _publish(zhihu, question_url=f"{QUESTION}/answer/{THEIR_AID}")
    assert result["success"] is True
    assert result["outcome"] == "verified"


def test_dry_run_still_reports_success_without_touching_the_editor(zhihu, browser_ends_at):
    browser_ends_at(QUESTION)
    result = zhihu.publish_answer(QUESTION, "回答正文", dry_run=True)
    assert result["success"] is True
    assert result["dry_run"] is True


# ---- 命令行：退出码跟着 success --------------------------------------------

def _run_cli(zhihu, monkeypatch, tmp_path, capsys):
    content = tmp_path / "answer.md"
    content.write_text("回答正文", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["zhihu_answer.py", "--question", QUESTION, "--content-file", str(content), "--exec"],
    )
    with pytest.raises(SystemExit) as exit_info:
        zhihu.main()
    printed = json.loads(capsys.readouterr().out)
    return exit_info.value.code, printed


def test_cli_exits_nonzero_when_the_post_is_not_confirmed(zhihu, browser_ends_at, monkeypatch, tmp_path, capsys):
    browser_ends_at(QUESTION)
    code, printed = _run_cli(zhihu, monkeypatch, tmp_path, capsys)
    assert code not in (0, None)
    assert printed["success"] is False
    assert printed["outcome"] == "unverified"


def test_cli_exits_zero_when_the_post_is_verified(zhihu, browser_ends_at, monkeypatch, tmp_path, capsys):
    browser_ends_at(f"{QUESTION}/answer/{NEW_AID}")
    code, printed = _run_cli(zhihu, monkeypatch, tmp_path, capsys)
    assert code == 0
    assert printed["outcome"] == "verified"
