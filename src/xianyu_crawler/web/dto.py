"""API DTO + row↔DTO 映射。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel

from ..config import DEFAULT_REVIEW_SYSTEM_PROMPT, Settings
from ..storage.orm import WatchRow, AppConfig, ItemRow


def _iso(dt: datetime | None) -> str | None:
    """库里存的是 naive UTC, 序列化时标成 UTC(带 +00:00), 前端才能转本地时区。"""
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


class WatchIn(BaseModel):
    name: str
    keywords: list[str] = []
    price_min: float | None = None
    price_max: float | None = None
    city: str | None = None
    condition: list[str] | None = None
    free_shipping: bool | None = None
    seller_min_credit: int | None = None
    requirement: str | None = None
    enabled: bool = True


class WatchOut(WatchIn):
    id: int


class ConfigIn(BaseModel):
    schedule_minutes: int | None = None
    favorites_minutes: int | None = None
    paused: bool | None = None
    min_drop_pct: float | None = None
    min_drop_abs: float | None = None
    notify_to: str | None = None
    headless: bool | None = None
    search_max_pages: int | None = None
    favorites_max_pages: int | None = None
    # LLM 二次审核
    review_enabled: bool | None = None
    review_base_url: str | None = None
    review_model: str | None = None
    review_api_token: str | None = None     # 只接收, 不回传
    review_timeout: float | None = None
    review_temperature: float | None = None
    review_max_tokens: int | None = None
    review_system_prompt: str | None = None
    # 高级(抓取/反爬)
    action_delay_min: float | None = None
    action_delay_max: float | None = None
    liveness_max_checks: int | None = None
    search_url: str | None = None
    favorites_url: str | None = None
    # SMTP
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None        # 只接收, 不回传
    # 邮件提醒事件开关
    notify_on_new: bool | None = None
    notify_on_drop: bool | None = None
    notify_on_sold: bool | None = None
    notify_on_favorite: bool | None = None
    notify_on_login: bool | None = None


class ConfigOut(BaseModel):
    schedule_minutes: int
    favorites_minutes: int
    paused: bool
    min_drop_pct: float
    min_drop_abs: float
    notify_to: str
    headless: bool
    search_max_pages: int
    favorites_max_pages: int
    # LLM 二次审核(token 不回传明文, 只给 set 标记)
    review_enabled: bool
    review_base_url: str
    review_model: str
    review_token_set: bool = False
    review_timeout: float
    review_temperature: float
    review_max_tokens: int
    review_system_prompt: str
    # 高级(抓取/反爬)
    action_delay_min: float
    action_delay_max: float
    liveness_max_checks: int
    search_url: str
    favorites_url: str
    # SMTP
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass_set: bool = False         # 是否已设置密码(不回传明文)
    # 邮件提醒事件开关
    notify_on_new: bool = True
    notify_on_drop: bool = True
    notify_on_sold: bool = True
    notify_on_favorite: bool = True
    notify_on_login: bool = True


class RecommendationOut(BaseModel):
    item_id: str
    title: str
    url: str
    price: float
    location: str | None = None
    condition: str | None = None
    free_shipping: bool | None = None
    seller_nick: str | None = None
    watch_name: str | None = None
    pic_url: str | None = None
    reason: str | None = None
    rec_ok: bool | None = None            # LLM 裁决: True 通过 / False 未过 / None 未审
    dead: bool = False
    dead_reason: str | None = None
    publish_time: str | None = None       # 闲鱼发布时间
    first_seen_at: str | None = None      # 入库时间
    rec_created_at: str | None = None     # 推荐时间
    price_changed_at: str | None = None   # 最近调价时间


class FavoriteOut(BaseModel):
    item_id: str
    title: str
    url: str
    price: float
    reduce_price: float
    location: str | None = None
    condition: str | None = None
    free_shipping: bool | None = None
    seller_nick: str | None = None
    favorited_at: str | None = None
    pic_url: str | None = None
    dead: bool = False
    dead_reason: str | None = None
    publish_time: str | None = None
    first_seen_at: str | None = None
    price_changed_at: str | None = None


# --- mappers ---
def watchin_to_fields(b: WatchIn) -> dict:
    return {
        "name": b.name,
        "keywords": json.dumps(b.keywords, ensure_ascii=False),
        "price_min": b.price_min,
        "price_max": b.price_max,
        "city": b.city,
        "condition": json.dumps(b.condition, ensure_ascii=False) if b.condition is not None else None,
        "free_shipping": b.free_shipping,
        "seller_min_credit": b.seller_min_credit,
        "requirement": b.requirement,
        "enabled": b.enabled,
    }


def watchrow_to_out(w: WatchRow) -> WatchOut:
    return WatchOut(
        id=w.id,
        name=w.name,
        keywords=json.loads(w.keywords or "[]"),
        price_min=w.price_min,
        price_max=w.price_max,
        city=w.city,
        condition=json.loads(w.condition) if w.condition else None,
        free_shipping=w.free_shipping,
        seller_min_credit=w.seller_min_credit,
        requirement=w.requirement,
        enabled=w.enabled,
    )


def config_to_out(c: AppConfig) -> ConfigOut:
    return ConfigOut(
        schedule_minutes=c.schedule_minutes,
        favorites_minutes=c.favorites_minutes,
        paused=c.paused,
        min_drop_pct=c.min_drop_pct,
        min_drop_abs=c.min_drop_abs,
        notify_to=c.notify_to,
        headless=c.headless,
        search_max_pages=c.search_max_pages,
        favorites_max_pages=c.favorites_max_pages,
        review_enabled=c.review_enabled,
        review_base_url=c.review_base_url or Settings().review_base_url,  # 显示生效值(可能来自本地 secret.env)
        review_model=c.review_model,
        review_token_set=bool(c.review_api_token),
        review_timeout=c.review_timeout,
        review_temperature=c.review_temperature,
        review_max_tokens=c.review_max_tokens,
        review_system_prompt=c.review_system_prompt or DEFAULT_REVIEW_SYSTEM_PROMPT,
        action_delay_min=c.action_delay_min,
        action_delay_max=c.action_delay_max,
        liveness_max_checks=c.liveness_max_checks,
        search_url=c.search_url,
        favorites_url=c.favorites_url,
        smtp_host=c.smtp_host,
        smtp_port=c.smtp_port,
        smtp_user=c.smtp_user,
        smtp_pass_set=bool(c.smtp_pass),
        notify_on_new=c.notify_on_new,
        notify_on_drop=c.notify_on_drop,
        notify_on_sold=c.notify_on_sold,
        notify_on_favorite=c.notify_on_favorite,
        notify_on_login=c.notify_on_login,
    )


def itemrow_to_rec(r: ItemRow) -> RecommendationOut:
    return RecommendationOut(
        item_id=r.item_id, title=r.title, url=r.url, price=r.latest_price,
        location=r.location, condition=r.condition, free_shipping=r.free_shipping,
        seller_nick=r.seller_nick, watch_name=r.watch_name, pic_url=r.pic_url,
        reason=r.rec_reason, rec_ok=r.rec_ok, dead=r.dead, dead_reason=r.dead_reason,
        publish_time=_iso(r.publish_time), first_seen_at=_iso(r.first_seen_at),
        rec_created_at=_iso(r.rec_created_at), price_changed_at=_iso(r.price_changed_at),
    )


def itemrow_to_fav(r: ItemRow) -> FavoriteOut:
    return FavoriteOut(
        item_id=r.item_id, title=r.title, url=r.url, price=r.latest_price,
        reduce_price=r.reduce_price or 0.0, location=r.location,
        condition=r.condition, free_shipping=r.free_shipping, seller_nick=r.seller_nick,
        favorited_at=_iso(r.favorited_at),
        pic_url=r.pic_url, dead=r.dead, dead_reason=r.dead_reason,
        publish_time=_iso(r.publish_time), first_seen_at=_iso(r.first_seen_at),
        price_changed_at=_iso(r.price_changed_at),
    )
