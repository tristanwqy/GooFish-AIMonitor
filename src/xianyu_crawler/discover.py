"""发现式抓包: 捕获页面所有 mtop 响应, 帮助定稿解析字段 (Task 9)。

闲鱼 web 走 mtop 网关(h5api.m.goofish.com)。首屏会发若干 mtop 调用,
真正的数据接口需从全部响应中按"商品数据可能性"挑出。
"""
from __future__ import annotations

import json
from pathlib import Path

from .anti_detect import human_scroll
from .parsing import items_from_json


def capture_mtop(ctx, url: str, scrolls: int = 6, wait_ms: int = 6000) -> list[dict]:
    """打开 url, 捕获所有 mtop/h5api 响应, 返回 [{api, url, json}]。"""
    records: list[dict] = []

    def _on_response(resp) -> None:
        u = resp.url
        if "h5api" not in u and "mtop" not in u:
            return
        try:
            body = resp.json()
        except Exception:
            return
        api = u.split("/h5/", 1)[-1].split("/", 1)[0] if "/h5/" in u else u
        records.append({"api": api, "url": u, "json": body})

    page = ctx.new_page()
    page.on("response", _on_response)
    try:
        page.goto(url)
        page.wait_for_timeout(wait_ms)
        human_scroll(page, steps=scrolls)
        page.wait_for_timeout(2000)
    finally:
        page.close()
    return records


def _pricey_nodes(o: object) -> int:
    """粗略计数: 含 'price' 字样 key 的 dict 数 → 商品数据的强信号。"""
    cnt = 0
    if isinstance(o, dict):
        if any("price" in str(k).lower() for k in o):
            cnt += 1
        for v in o.values():
            cnt += _pricey_nodes(v)
    elif isinstance(o, list):
        for v in o:
            cnt += _pricey_nodes(v)
    return cnt


def summarize(records: list[dict]) -> None:
    print(f"captured {len(records)} mtop responses:")
    for r in records:
        body = r["json"]
        size = len(json.dumps(body, ensure_ascii=False))
        pricey = _pricey_nodes(body)
        heur = len(items_from_json(body)) if isinstance(body, dict) else 0
        flag = "  <-- 疑似商品数据" if pricey >= 3 else ""
        print(f"  api={r['api']}  size={size}  pricey_nodes={pricey}  heuristic_items={heur}{flag}")


def dump(records: list[dict], out: str | Path) -> None:
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved ->", p)
