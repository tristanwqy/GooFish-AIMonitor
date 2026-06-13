from xianyu_crawler.models import Item, DropResult


def test_item_minimal():
    it = Item(item_id="1", title="t", url="u", price=100.0)
    assert it.price == 100.0 and it.seller_id is None


def test_drop_result_fields():
    d = DropResult(item_id="1", prev_price=100, curr_price=80, drop_abs=20, drop_pct=20.0)
    assert d.drop_abs == 20 and d.drop_pct == 20.0
