"""领域类型: 无 IO, 纯数据。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Item(BaseModel):
    item_id: str
    title: str
    url: str
    price: float
    seller_id: str | None = None
    seller_nick: str | None = None
    location: str | None = None
    condition: str | None = None        # 成色文本, 如 "99新"
    free_shipping: bool | None = None
    reduce_price: float | None = None   # 闲鱼原生"收藏后降价"金额(¥); 仅收藏数据有
    pic_url: str | None = None          # 商品主图
    publish_time: datetime | None = None  # 闲鱼发布时间(search 的 args.publishTime)
    dead: bool = False                  # 已售出/已删除/已下架(死链, 别再打开)
    dead_reason: str | None = None      # "已售出" / "已删除" / "已下架"
    raw: dict | None = None             # 原始 JSON, 调试用


class DropResult(BaseModel):
    item_id: str
    prev_price: float
    curr_price: float
    drop_abs: float
    drop_pct: float
