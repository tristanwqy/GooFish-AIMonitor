"""Playwright 会话: 载入 storage_state + 登录校验。"""
from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

from .anti_detect import pick_profile

HOME = "https://www.goofish.com/"


@contextmanager
def browser_session(settings, state_path: str | None = None):
    """有/无登录态均可启动; 退出时刷新保存登录态。

    state_path 默认锚定到 settings.data_dir/storage_state.json —— 必须与扫码登录
    (login_runner 存登录态的位置)一致。不要用相对 CWD 的 "data/storage_state.json":
    打包成桌面应用后进程 CWD 不是数据目录, 相对路径会读不到登录态, 于是每轮抓取都被
    判为"未登录"→ 直接按 login_expired 退出 → 收藏夹空、一个推荐都没有。
    """
    if state_path is None:
        state_path = str(Path(settings.data_dir) / "storage_state.json")
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
