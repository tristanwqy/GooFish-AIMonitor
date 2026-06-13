"""搜索: 跑搜索页 → 拦截 mtop 搜索接口 JSON → 翻页加载 → 解析为 Item。

watch.keywords 是**一个**搜索词的若干词块, 用空格拼成一条 query 搜一次(不是逐词分搜)。
接口: mtop.taobao.idlemtopsearch.pc.search
商品: data.resultList[].data.item.main.exContent (+ detailParams / clickParam.args)
分页: data.resultInfo.hasNextPage; 滚动触发懒加载下一页, 拦截每页响应。
"""
from __future__ import annotations

from urllib.parse import quote

from .config import Watch
from .models import Item
from .parsing import to_price, guess_condition, to_dt_ms
from .anti_detect import human_scroll

SEARCH_URL = "https://www.goofish.com/search"
SEARCH_API = "mtop.taobao.idlemtopsearch.pc.search"


def _has_next_page(raw: dict) -> bool:
    info = (((raw or {}).get("data") or {}).get("resultInfo")) or {}
    return bool(info.get("hasNextPage"))


def parse_search_json(raw: dict) -> list[Item]:
    out: list[Item] = []
    seen: set[str] = set()
    result_list = (((raw or {}).get("data") or {}).get("resultList")) or []
    for el in result_list:
        main = (((el or {}).get("data") or {}).get("item") or {}).get("main") or {}
        ex = main.get("exContent") or {}
        dp = ex.get("detailParams") or {}
        args = (main.get("clickParam") or {}).get("args") or {}
        iid = ex.get("itemId") or dp.get("itemId") or args.get("item_id")
        title = ex.get("title") or dp.get("title")
        # 精确价用 soldPrice/args.price; exContent.price 是 "¥2.89万" 样式串, 不可用
        price = to_price(dp.get("soldPrice") or args.get("price") or args.get("displayPrice"))
        if not iid or not title or price is None or str(iid) in seen:
            continue
        seen.add(str(iid))
        tag = str(args.get("tag") or "").lower()
        tagname = str(args.get("tagname") or "")
        area = ex.get("area")
        nick = ex.get("userNickName") or dp.get("userNick")
        sid = args.get("seller_id")
        pic = ex.get("picUrl")
        out.append(Item(
            item_id=str(iid),
            title=str(title),
            price=price,
            url=f"https://www.goofish.com/item?id={iid}",
            location=str(area) if isinstance(area, str) else None,
            seller_nick=str(nick) if nick else None,
            seller_id=str(sid) if sid else None,
            free_shipping=("freeship" in tag) or ("包邮" in tagname),
            condition=guess_condition(str(title)),
            pic_url=str(pic) if isinstance(pic, str) else None,
            publish_time=to_dt_ms(args.get("publishTime")),
            raw=main if isinstance(main, dict) else None,
        ))
    return out


def search(ctx, watch: Watch, max_pages: int = 3, search_url: str = SEARCH_URL) -> list[Item]:
    captured: list[dict] = []
    page = ctx.new_page()

    def _on_response(resp) -> None:
        if f"{SEARCH_API}/" in resp.url:
            try:
                captured.append(resp.json())
            except Exception:
                pass

    page.on("response", _on_response)
    try:
        query = " ".join(k.strip() for k in watch.keywords if k.strip())  # 多词块拼一条 query
        page.goto(f"{search_url}?q={quote(query)}")
        page.wait_for_timeout(4000)
        n = len(captured)
        for _ in range(max(0, max_pages - 1)):
            if captured and not _has_next_page(captured[-1]):
                break
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            human_scroll(page, steps=2)
            page.wait_for_timeout(2500)
            if len(captured) == n:        # 滚动未触发新页 → 停
                break
            n = len(captured)
    finally:
        page.close()

    out: list[Item] = []
    seen: set[str] = set()
    for raw in captured:
        for it in parse_search_json(raw):
            if it.item_id not in seen:
                seen.add(it.item_id)
                out.append(it)
    return out
