"""一次性: 打开收藏页, 捕获所有 mtop 响应供定稿解析 (Task 9)。

用法: python scripts/discover_favorites.py
产出: tests/fixtures/favorites.real.json = [{api, url, json}, ...] (gitignore)
然后看终端打印的 "疑似商品数据" 那条 api, 把对应 json 发给 Claude 定稿字段。
"""
from __future__ import annotations

from pathlib import Path

from xianyu_crawler.config import Settings
from xianyu_crawler.session import browser_session
from xianyu_crawler.discover import capture_mtop, summarize, dump

OUT = Path("tests/fixtures/favorites.real.json")


def main() -> None:
    settings = Settings()
    with browser_session(settings) as ctx:
        records = capture_mtop(ctx, settings.favorites_url)
    summarize(records)
    dump(records, OUT)


if __name__ == "__main__":
    main()
