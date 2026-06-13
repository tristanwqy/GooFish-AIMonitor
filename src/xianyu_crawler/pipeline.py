"""编排一次 run: R1(选品收藏) + R2(降价监控)。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .config import Settings, Watch
from .price_monitor import detect_drop
from .filter import matches
from .storage import repo
from . import search as _search_mod
from . import favorites_list as _fav_mod
from . import favorite as _favorite_mod


# 间接层: 便于测试 monkeypatch (替换掉真实浏览器交互)
def _search(ctx, watch, settings):
    return _search_mod.search(ctx, watch, settings.search_max_pages)


def _read_favorites(ctx, settings):
    return _fav_mod.read_favorites(ctx, settings.favorites_url, settings.favorites_max_pages)


def _add_favorite(ctx, item, settings):
    return _favorite_mod.add_favorite(ctx, item, settings)


def run_search(ctx, session: Session, settings: Settings, watches: list[Watch]) -> int:
    """R1: 搜索 → 过滤 → 点想要(单 watch 限量)。返回新增收藏数。"""
    added = 0
    for w in watches:
        if not w.enabled:
            continue
        n = 0
        for item in _search(ctx, w, settings):
            if n >= w.want_max_per_run:
                break
            if not matches(item, w):
                continue
            if repo.is_favorited(session, item.item_id):
                continue
            repo.upsert_item_with_price(session, item, source="search", watch_name=w.name)
            if _add_favorite(ctx, item, settings):
                repo.mark_favorited(session, item.item_id)
                repo.add_event(session, item.item_id, "favorited",
                               {"title": item.title, "url": item.url, "pic": item.pic_url})
                added += 1
                n += 1
    return added


def run_monitor(ctx, session: Session, settings: Settings) -> int:
    """R2: 读收藏 → 抓价 → 降价事件。返回降价数。

    两路信号(优先用闲鱼原生, 避免重复):
    1) 闲鱼原生"收藏后降价"(reducePrice): 权威, 能抓到首次观测前就发生的降价;
       仅在比上次记录有"新降"且累计降幅达 min_drop_abs 时触发。
    2) 跨次比价(兜底): 闲鱼未给 reducePrice 时, 比上次观测价。
    """
    drops = 0
    for item in _read_favorites(ctx, settings):
        was_dead = repo.is_dead(session, item.item_id)
        prev_price = repo.get_latest_price(session, item.item_id)
        prev_reduce = repo.get_reduce_price(session, item.item_id) or 0.0
        repo.upsert_item_with_price(session, item, source="favorite")
        repo.mark_collected(session, item.item_id)   # 收藏夹里=已收藏, 退出待审
        if item.dead and not was_dead:               # 收藏的商品刚被卖出/下架 → 通知
            repo.add_event(session, item.item_id, "sold",
                           {"title": item.title, "url": item.url, "pic": item.pic_url,
                            "reason": item.dead_reason or "已下架"})
            continue
        cur_reduce = item.reduce_price or 0.0

        payload: dict | None = None
        if cur_reduce > prev_reduce and cur_reduce >= settings.min_drop_abs:
            payload = {"reason": "收藏后累计降价", "drop_abs": cur_reduce,
                       "curr_price": item.price}
        elif prev_price is not None:
            d = detect_drop(item.item_id, prev=prev_price, curr=item.price,
                            min_pct=settings.min_drop_pct, min_abs=settings.min_drop_abs)
            if d:
                payload = {"reason": "比上次降价", "prev_price": d.prev_price,
                           "curr_price": d.curr_price, "drop_abs": d.drop_abs,
                           "drop_pct": d.drop_pct}
        if payload:
            repo.add_event(session, item.item_id, "price_drop",
                           {"title": item.title, "url": item.url, "pic": item.pic_url, **payload})
            drops += 1
    return drops
