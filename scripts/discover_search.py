"""一次性: 登录态下搜索关键词, 捕获所有 mtop 响应供定稿解析 (Task 9)。

用法: python scripts/discover_search.py "iPhone 15"
产出: tests/fixtures/search.real.json = [{api, url, json}, ...] (gitignore)
然后看终端打印的 "疑似商品数据" 那条 api, 把对应 json 发给 Claude 定稿字段。
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

from xianyu_crawler.config import Settings
from xianyu_crawler.session import browser_session
from xianyu_crawler.discover import capture_mtop, summarize, dump

OUT = Path("tests/fixtures/search.real.json")


def main(keyword: str) -> None:
    with browser_session(Settings()) as ctx:
        records = capture_mtop(ctx, f"https://www.goofish.com/search?q={quote(keyword)}")
    summarize(records)
    dump(records, OUT)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "iPhone")
