"""读取"收藏"列表为 Item (R2 的数据源)。

接口: mtop.taobao.idle.web.favor.item.list
商品: data.items[] (扁平, 字段干净: id/title/price/city/freeShip/userNick)
分页: data.nextPage; 滚动触发懒加载, 拦截每页响应。
"""
from __future__ import annotations

from .models import Item
from .parsing import to_price, guess_condition
from .anti_detect import human_scroll

# 收藏列表页(用户确认); 可经 Settings.favorites_url / XIANYU_FAVORITES_URL 覆盖
FAVORITES_URL = "https://www.goofish.com/collection"
FAVOR_API = "mtop.taobao.idle.web.favor.item.list"


def _has_next_page(raw: dict) -> bool:
    return bool(((raw or {}).get("data") or {}).get("nextPage"))


def _dead_state(d: dict) -> tuple[bool, str | None]:
    """从收藏项判定死链(已售/已删除/已下架)。itemStatus==-1 为主信号。"""
    if d.get("itemDeleted"):
        return True, "已删除"
    if d.get("itemStatus") not in (0, "0", None):     # -1 等
        return True, "已售出"
    if d.get("offline") not in (0, "0", None, False):
        return True, "已下架"
    return False, None


def parse_favorites_json(raw: dict) -> list[Item]:
    out: list[Item] = []
    seen: set[str] = set()
    arr = (((raw or {}).get("data") or {}).get("items")) or []
    for el in arr:
        d = el if isinstance(el, dict) else {}
        iid = d.get("id")
        title = d.get("title")
        price = to_price(d.get("price"))
        if not iid or not title or price is None or str(iid) in seen:
            continue
        seen.add(str(iid))
        loc = d.get("city") or d.get("province") or d.get("area")
        nick = d.get("userNick")
        uid = d.get("userId")
        fs = d.get("freeShip")
        pic = d.get("picUrl")
        dead, dead_reason = _dead_state(d)
        out.append(Item(
            item_id=str(iid),
            title=str(title),
            price=price,
            url=f"https://www.goofish.com/item?id={iid}",
            location=str(loc) if isinstance(loc, str) else None,
            seller_nick=str(nick) if nick else None,
            seller_id=str(uid) if uid else None,
            free_shipping=bool(fs) if fs is not None else None,
            condition=guess_condition(str(title)),
            reduce_price=to_price(d.get("reducePrice")),  # "收藏后降价" ¥
            pic_url=str(pic) if isinstance(pic, str) else None,
            dead=dead,
            dead_reason=dead_reason,
            raw=d,
        ))
    return out


def read_favorites(ctx, url: str = FAVORITES_URL, max_pages: int = 5) -> list[Item]:
    captured: list[dict] = []
    page = ctx.new_page()

    def _on_response(resp) -> None:
        if f"{FAVOR_API}/" in resp.url:
            try:
                captured.append(resp.json())
            except Exception:
                pass

    page.on("response", _on_response)
    try:
        page.goto(url)
        page.wait_for_timeout(4000)
        n = len(captured)
        for _ in range(max(0, max_pages - 1)):
            if captured and not _has_next_page(captured[-1]):
                break
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            human_scroll(page, steps=2)
            page.wait_for_timeout(2500)
            if len(captured) == n:
                break
            n = len(captured)
    finally:
        page.close()

    out: list[Item] = []
    seen: set[str] = set()
    for raw in captured:
        for it in parse_favorites_json(raw):
            if it.item_id not in seen:
                seen.add(it.item_id)
                out.append(it)
    return out
