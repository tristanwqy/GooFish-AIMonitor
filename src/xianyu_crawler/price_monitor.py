"""降价检测: 纯逻辑, 无 IO。"""
from __future__ import annotations

from .models import DropResult


def detect_drop(item_id: str, prev: float, curr: float,
                min_pct: float, min_abs: float) -> DropResult | None:
    """与上次价 prev 比较: 降幅达 min_pct(%) 或 min_abs(¥) 任一即判降价。"""
    if prev <= 0:
        return None
    drop_abs = prev - curr
    if drop_abs <= 0:
        return None
    drop_pct = drop_abs / prev * 100
    if drop_pct >= min_pct or drop_abs >= min_abs:
        return DropResult(item_id=item_id, prev_price=prev, curr_price=curr,
                          drop_abs=drop_abs, drop_pct=drop_pct)
    return None
