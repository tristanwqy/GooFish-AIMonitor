"""仓储: 纯 DB 操作, 可独立测试。"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from ..models import Item
from .orm import ItemRow, PriceHistory, Event, WatchRow, AppConfig


def _now() -> datetime:
    # naive UTC: SQLite 读回的 datetime 一律无 tzinfo, 统一成 naive 才能安全比较/排序
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_latest_price(s: Session, item_id: str) -> float | None:
    row = s.get(ItemRow, item_id)
    return row.latest_price if row else None


def get_reduce_price(s: Session, item_id: str) -> float | None:
    row = s.get(ItemRow, item_id)
    return row.reduce_price if row else None


def upsert_item_with_price(s: Session, item: Item, source: str,
                           watch_name: str | None = None) -> float | None:
    """写入/更新商品并追加一条价格观测; 返回更新前的 latest_price(无则 None)。"""
    reduce = item.reduce_price or 0.0
    row = s.get(ItemRow, item.item_id)
    prev = row.latest_price if row else None
    if row is None:
        row = ItemRow(item_id=item.item_id, title=item.title, url=item.url,
                      seller_id=item.seller_id, seller_nick=item.seller_nick,
                      location=item.location, condition=item.condition,
                      free_shipping=item.free_shipping, pic_url=item.pic_url,
                      first_price=item.price, latest_price=item.price,
                      reduce_price=reduce, source=source, watch_name=watch_name,
                      publish_time=item.publish_time,
                      dead=item.dead, dead_reason=item.dead_reason,
                      dead_at=_now() if item.dead else None)
        s.add(row)
    else:
        if prev is not None and item.price != prev:   # 价格变了 → 记调价时间
            row.price_changed_at = _now()
        row.latest_price = item.price
        row.reduce_price = reduce
        row.location = item.location
        row.condition = item.condition
        row.free_shipping = item.free_shipping
        row.pic_url = item.pic_url
        if item.publish_time and not row.publish_time:   # 补发布时间(收藏源没有)
            row.publish_time = item.publish_time
        row.last_seen_at = _now()
        if item.dead and not row.dead:        # 死链信号是"粘性"的: 一旦死掉就不复活
            row.dead = True
            row.dead_reason = item.dead_reason
            row.dead_at = _now()
    s.add(PriceHistory(item_id=item.item_id, price=item.price))
    s.commit()
    return prev


def mark_favorited(s: Session, item_id: str) -> None:
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    row.favorited = True
    row.favorited_at = _now()
    s.commit()


def is_favorited(s: Session, item_id: str) -> bool:
    row = s.get(ItemRow, item_id)
    return bool(row and row.favorited)


def is_collected(s: Session, item_id: str) -> bool:
    """已在闲鱼收藏(我们点过收藏, 或出现在收藏列表)→ 不再作为推荐。"""
    row = s.get(ItemRow, item_id)
    return bool(row and (row.favorited or row.source == "favorite"))


def is_dead(s: Session, item_id: str) -> bool:
    """已售出/已删除/已下架 → 不再作为推荐。"""
    row = s.get(ItemRow, item_id)
    return bool(row and row.dead)


def mark_dead(s: Session, item_id: str, reason: str) -> None:
    row = s.get(ItemRow, item_id)
    if row is None or row.dead:
        return
    row.dead = True
    row.dead_reason = reason
    row.dead_at = _now()
    s.commit()


def mark_collected(s: Session, item_id: str) -> None:
    """收藏夹里观测到该商品 → 标 favorited(幂等), 并把仍在待审的退出(approved)。

    修复: 用户直接在闲鱼收藏(非控制台批准)的商品, 之前不会被标 favorited,
    导致反复进推荐、且不出现在收藏视图。
    """
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    if not row.favorited:
        row.favorited = True
        row.favorited_at = _now()
    if row.rec_status == "new":          # 已收藏的不该再在待审队列里
        row.rec_status = "approved"
    s.commit()


def mute_item(s: Session, item_id: str, until: datetime) -> None:
    """近期不看: muted_until 之前从待审隐藏 + 不再推荐; 到期后(1天/7天)自动重现,
    永久=远未来(9999)。保留 rec_status=new, 仅靠 muted_until 过滤, 到期即回归。"""
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    row.muted_until = until
    s.commit()


def is_muted(s: Session, item_id: str) -> bool:
    row = s.get(ItemRow, item_id)
    return bool(row and row.muted_until and row.muted_until > _now())


def add_event(s: Session, item_id: str, type_: str, payload: dict) -> None:
    s.add(Event(item_id=item_id, type=type_,
                payload=json.dumps(payload, ensure_ascii=False)))
    s.commit()


def unnotified_events(s: Session) -> list[Event]:
    return list(s.scalars(select(Event).where(Event.notified.is_(False))))


def mark_notified(s: Session, ids: list[int]) -> None:
    for e in s.scalars(select(Event).where(Event.id.in_(ids))):
        e.notified = True
    s.commit()


# ---------- Watches (控制台管理) ----------

def list_watches(s: Session) -> list[WatchRow]:
    return list(s.scalars(select(WatchRow).order_by(WatchRow.id)))


def get_watch(s: Session, watch_id: int) -> WatchRow | None:
    return s.get(WatchRow, watch_id)


def add_watch(s: Session, **fields) -> WatchRow:
    row = WatchRow(**fields)
    s.add(row)
    s.commit()
    return row


def update_watch(s: Session, watch_id: int, **fields) -> WatchRow | None:
    row = s.get(WatchRow, watch_id)
    if row is None:
        return None
    for k, v in fields.items():
        setattr(row, k, v)
    s.commit()
    return row


def delete_watch(s: Session, watch_id: int) -> None:
    row = s.get(WatchRow, watch_id)
    if row is not None:
        s.delete(row)
        s.commit()


# ---------- App config (单行) ----------

def get_config(s: Session) -> AppConfig:
    cfg = s.get(AppConfig, 1)
    if cfg is None:
        cfg = AppConfig(id=1)
        s.add(cfg)
        s.commit()
    return cfg


def update_config(s: Session, **fields) -> AppConfig:
    cfg = get_config(s)
    for k, v in fields.items():
        setattr(cfg, k, v)
    s.commit()
    return cfg


# ---------- Recommendations (审核队列) ----------

def has_been_recommended(s: Session, item_id: str) -> bool:
    row = s.get(ItemRow, item_id)
    return bool(row and row.rec_status)


def create_recommendation(s: Session, item: Item, watch_name: str | None,
                          reason: str | None = None, ok: bool | None = None) -> bool:
    """新推荐(未见过)→ 写入并标 rec_status=new; 已见过返回 False。
    ok = LLM 裁决(True 通过 / False 未过 / None 未审); 未过的也入库, 由前端筛选。"""
    if has_been_recommended(s, item.item_id):
        return False
    upsert_item_with_price(s, item, source="search", watch_name=watch_name)
    row = s.get(ItemRow, item.item_id)
    if row is None:
        return False
    row.rec_status = "new"
    row.rec_created_at = _now()
    row.rec_reason = reason
    row.rec_ok = ok
    s.commit()
    return True


def list_recommendations(s: Session, status: str = "new") -> list[ItemRow]:
    q = select(ItemRow).where(ItemRow.rec_status == status)
    if status == "new":
        # 待审里排除已收藏、当前静音中的; 死链保留(置灰提示别再开)
        q = q.where(ItemRow.favorited.is_(False)).where(
            or_(ItemRow.muted_until.is_(None), ItemRow.muted_until <= _now()))
    return list(s.scalars(
        q.order_by(ItemRow.dead.asc(), ItemRow.rec_created_at.desc())))


def set_rec_status(s: Session, item_id: str, status: str) -> None:
    row = s.get(ItemRow, item_id)
    if row is not None:
        row.rec_status = status
        s.commit()


def update_rec_verdict(s: Session, item_id: str, ok: bool | None, reason: str | None) -> None:
    """一键补审: 只更新 LLM 裁决(rec_ok/rec_reason), 不动 rec_status。"""
    row = s.get(ItemRow, item_id)
    if row is not None:
        row.rec_ok = ok
        row.rec_reason = reason
        s.commit()


def list_favorites(s: Session) -> list[ItemRow]:
    """收藏视图 = 闲鱼收藏夹(source=favorite) ∪ 我们批准收藏过的。死链排末尾。"""
    return list(s.scalars(
        select(ItemRow)
        .where(or_(ItemRow.favorited.is_(True), ItemRow.source == "favorite"))
        .order_by(ItemRow.dead.asc(), ItemRow.reduce_price.desc(),
                  ItemRow.last_seen_at.desc())))


def recent_events(s: Session, limit: int = 100) -> list[Event]:
    return list(s.scalars(select(Event).order_by(Event.created_at.desc()).limit(limit)))


def stats(s: Session) -> dict:
    """仪表盘指标。"""
    def cnt(q) -> int:
        return int(s.scalar(select(func.count()).select_from(ItemRow).where(q)) or 0)

    new = list_recommendations(s, "new")          # 已排除已收藏/静音
    return {
        "pending": len(new),
        "passed": sum(1 for r in new if r.rec_ok is not False),
        "watches": int(s.scalar(select(func.count()).select_from(WatchRow)) or 0),
        "favorites": cnt(or_(ItemRow.favorited.is_(True), ItemRow.source == "favorite")),
        "dead": cnt(ItemRow.dead.is_(True)),
        "drops_today": int(s.scalar(
            select(func.count()).select_from(Event)
            .where(Event.type == "price_drop", Event.created_at >= _now() - timedelta(days=1))) or 0),
    }
