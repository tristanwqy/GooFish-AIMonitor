"""通用解析助手单测 (供 discover 用); search/favorites 显式解析见各自测试。"""
from xianyu_crawler.parsing import to_price, node_to_item, items_from_json, guess_condition, to_dt_ms


def test_to_dt_ms():
    dt = to_dt_ms("1781241796000")          # 毫秒时间戳
    assert dt is not None and dt.year == 2026 and dt.tzinfo is None
    assert to_dt_ms(0) is None
    assert to_dt_ms("abc") is None
    assert to_dt_ms(None) is None


def test_to_price_variants():
    assert to_price("¥1,299") == 1299.0
    assert to_price(99) == 99.0
    assert to_price("abc") is None
    assert to_price(None) is None
    assert to_price(True) is None


def test_guess_condition():
    assert guess_condition("MacBook 99新 国行") == "99新"
    assert guess_condition("全新未拆封 iPad") == "全新"
    assert guess_condition("九成新相机") == "九成新"
    assert guess_condition("iPhone 13 描述里没成色") is None
    assert guess_condition(None) is None


def test_node_to_item_minimal():
    it = node_to_item({"itemId": "123", "title": "iPhone", "price": "¥3999", "area": "上海"})
    assert it is not None
    assert it.item_id == "123" and it.price == 3999.0 and it.location == "上海"


def test_items_from_json_walk_and_dedup():
    raw = {"data": {"list": [
        {"itemId": "1", "title": "A", "price": "100"},
        {"itemId": "2", "title": "B", "price": "200"},
        {"itemId": "1", "title": "A", "price": "100"},
    ]}}
    items = items_from_json(raw)
    assert sorted(i.item_id for i in items) == ["1", "2"]
