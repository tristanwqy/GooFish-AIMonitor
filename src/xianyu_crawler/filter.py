"""规则过滤: 判断商品是否满足某个 Watch 条件 (高置信匹配)。"""
from __future__ import annotations

from .models import Item
from .config import Watch


def matches(item: Item, watch: Watch) -> bool:
    if watch.price_min is not None and item.price < watch.price_min:
        return False
    if watch.price_max is not None and item.price > watch.price_max:
        return False
    if watch.city and (not item.location or watch.city not in item.location):
        return False
    # 成色为 best-effort 提取(可能 None); 未知不过滤, 只在"已知且不符"时排除
    if watch.condition and item.condition is not None and item.condition not in watch.condition:
        return False
    if watch.free_shipping is not None and item.free_shipping != watch.free_shipping:
        return False
    # seller_min_credit: 信用分需在 Item.raw 中, v1 暂以存在即通过; 留待解析补字段
    return True
