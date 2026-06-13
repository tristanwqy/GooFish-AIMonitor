"""favorites 显式解析回归 (合成 sample, 结构同真实 mtop 响应)。"""
import json
from pathlib import Path

import pytest

from xianyu_crawler.favorites_list import parse_favorites_json

FIXTURE = Path(__file__).parent / "fixtures" / "favorites.sample.json"


@pytest.mark.skipif(not FIXTURE.exists(), reason="缺 favorites.sample.json")
def test_parse_favorites_sample():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = parse_favorites_json(raw)
    assert len(items) == 1
    it = items[0]
    assert it.item_id == "222"
    assert it.price == 5000.0
    assert it.location == "北京"
    assert it.free_shipping is True
    assert it.condition == "95新"
    assert it.reduce_price == 500.0      # 收藏后降价 ¥500
    assert it.dead is False              # 正常在售
    assert it.dead_reason is None


def _fav_raw(extra: dict) -> dict:
    base = {"id": "x", "title": "测试 MacBook 99新", "price": "100"}
    return {"data": {"items": [{**base, **extra}]}}


def test_parse_favorites_dead_states():
    # itemStatus == -1 → 已售出
    sold = parse_favorites_json(_fav_raw({"id": "sold", "itemStatus": -1}))[0]
    assert sold.dead is True and sold.dead_reason == "已售出"
    # itemDeleted == True 优先标"已删除"
    deleted = parse_favorites_json(_fav_raw({"id": "del", "itemStatus": -1, "itemDeleted": True}))[0]
    assert deleted.dead is True and deleted.dead_reason == "已删除"
    # offline 截断 → 已下架
    off = parse_favorites_json(_fav_raw({"id": "off", "offline": 1}))[0]
    assert off.dead is True and off.dead_reason == "已下架"
    # 正常 itemStatus==0 → 活
    live = parse_favorites_json(_fav_raw({"id": "live", "itemStatus": 0}))[0]
    assert live.dead is False and live.dead_reason is None
