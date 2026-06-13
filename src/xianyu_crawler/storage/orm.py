"""SQLAlchemy ORM: items / price_history / events。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)   # naive UTC(见 repo._now 说明)


class Base(DeclarativeBase):
    pass


class ItemRow(Base):
    __tablename__ = "items"
    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    seller_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    seller_nick: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    free_shipping: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    pic_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_price: Mapped[float] = mapped_column(Float)
    latest_price: Mapped[float] = mapped_column(Float)
    reduce_price: Mapped[float] = mapped_column(Float, default=0.0)  # 闲鱼"收藏后降价"金额
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)   # 入库时间
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)    # 最近抓取
    price_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 最近调价
    publish_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)      # 闲鱼发布时间
    muted_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)       # 近期不看截止
    source: Mapped[str] = mapped_column(String)            # search|favorite
    favorited: Mapped[bool] = mapped_column(Boolean, default=False)
    favorited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    watch_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rec_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # new|approved|rejected
    rec_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rec_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # LLM 二次审核理由
    rec_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)     # LLM 裁决: True过/False未过/None未审
    dead: Mapped[bool] = mapped_column(Boolean, default=False)                 # 已售/已删除/已下架
    dead_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 已售出|已删除|已下架
    dead_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.item_id"))
    price: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.item_id"))
    type: Mapped[str] = mapped_column(String)              # price_drop|favorited|new_match
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)


class WatchRow(Base):
    """控制台管理的监控条件(持久化, 取代 watchlist.yaml)。"""
    __tablename__ = "watches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    keywords: Mapped[str] = mapped_column(Text, default="[]")              # JSON list
    price_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    free_shipping: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    seller_min_credit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requirement: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 自然语言要求(LLM审核)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AppConfig(Base):
    """单行(id=1)应用配置, 控制台可改。"""
    __tablename__ = "app_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    schedule_minutes: Mapped[int] = mapped_column(Integer, default=120)       # 推荐抓取间隔
    favorites_minutes: Mapped[int] = mapped_column(Integer, default=30)        # 收藏刷新间隔(独立定时)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    min_drop_pct: Mapped[float] = mapped_column(Float, default=5.0)
    min_drop_abs: Mapped[float] = mapped_column(Float, default=50.0)
    notify_to: Mapped[str] = mapped_column(String, default="")  # 空=回退本地 XIANYU_NOTIFY_TO
    headless: Mapped[bool] = mapped_column(Boolean, default=True)
    search_max_pages: Mapped[int] = mapped_column(Integer, default=3)
    favorites_max_pages: Mapped[int] = mapped_column(Integer, default=5)
    # LLM 二次审核(控制台可改; token 只写不回传, 留空回退环境变量)
    review_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 空 → 回退本地 data/secret.env 的 XIANYU_REVIEW_BASE_URL(接口地址不入仓库)
    review_base_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    review_model: Mapped[str] = mapped_column(String, default="doubao-seed-2.0-pro")
    review_api_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    review_timeout: Mapped[float] = mapped_column(Float, default=30.0)
    review_temperature: Mapped[float] = mapped_column(Float, default=0.0)
    review_max_tokens: Mapped[int] = mapped_column(Integer, default=2000)
    review_system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 空=用默认
    # 高级(抓取/反爬); 留空/默认即可
    action_delay_min: Mapped[float] = mapped_column(Float, default=3.0)
    action_delay_max: Mapped[float] = mapped_column(Float, default=8.0)
    liveness_max_checks: Mapped[int] = mapped_column(Integer, default=30)
    search_url: Mapped[str] = mapped_column(String, default="https://www.goofish.com/search")
    favorites_url: Mapped[str] = mapped_column(String, default="https://www.goofish.com/collection")
    # SMTP(控制台可填; 留空则回退系统环境变量)。密码只写不回传。
    smtp_host: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    smtp_user: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_pass: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 邮件提醒事件开关: 每类事件单独控制是否发通知
    notify_on_new: Mapped[bool] = mapped_column(Boolean, default=True)        # 发现新推荐
    notify_on_drop: Mapped[bool] = mapped_column(Boolean, default=True)       # 收藏降价
    notify_on_sold: Mapped[bool] = mapped_column(Boolean, default=True)       # 已售出·下架
    notify_on_favorite: Mapped[bool] = mapped_column(Boolean, default=True)   # 自动收藏成功
    notify_on_login: Mapped[bool] = mapped_column(Boolean, default=True)      # 登录失效
