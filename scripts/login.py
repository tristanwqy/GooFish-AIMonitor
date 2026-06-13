"""首次扫码登录: 有头启动 → 手动扫码 → 保存 storage_state。

用法: python scripts/login.py
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

STATE = Path("data/storage_state.json")
LOGIN_URL = "https://www.goofish.com/"


def main() -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()
        page.goto(LOGIN_URL)
        print(">> 请在浏览器中完成扫码登录, 登录成功后回到终端按回车...")
        input()
        ctx.storage_state(path=str(STATE))
        print(f">> 已保存登录态到 {STATE}")
        browser.close()


if __name__ == "__main__":
    main()
