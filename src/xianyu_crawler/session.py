"""Playwright 会话: 载入 storage_state + 登录校验。"""
from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from .anti_detect import pick_profile

HOME = "https://www.goofish.com/"
DEFAULT_STATE = "data/storage_state.json"


@contextmanager
def browser_session(settings, state_path: str = DEFAULT_STATE):
    """有/无登录态均可启动; 退出时刷新保存登录态。"""
    profile = pick_profile()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=settings.headless,
            args=["--disable-blink-features=AutomationControlled"],   # 降低被识别为自动化
        )
        ctx = browser.new_context(
            storage_state=state_path if Path(state_path).exists() else None,
            user_agent=profile["user_agent"],
            viewport=profile["viewport"],
            locale="zh-CN",
        )
        ctx.add_init_script(                       # 抹掉 navigator.webdriver, 减少风控
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        try:
            yield ctx
        finally:
            try:
                Path(state_path).parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=state_path)
            finally:
                browser.close()


def is_logged_in(page) -> bool:
    """登录校验(保守): 访问首页, 若被重定向到登录/passport 页则判未登录。
    保守判定避免误报(宁可漏判也不频繁误发重登邮件)。"""
    page.goto(HOME)
    page.wait_for_timeout(2000)
    u = page.url.lower()
    return not any(k in u for k in ("login", "passport", "havana", "sign"))
