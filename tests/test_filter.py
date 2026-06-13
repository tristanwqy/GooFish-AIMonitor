from xianyu_crawler.models import Item
from xianyu_crawler.config import Watch
from xianyu_crawler.filter import matches


def W(**kw):
    return Watch(name="w", keywords=["x"]).model_copy(update=kw)


def I(**kw):
    return Item(item_id="1", title="t", url="u", price=1000.0,
                location="上海市", condition="99新", free_shipping=True).model_copy(update=kw)


def test_price_within_range():
    assert matches(I(price=1000), W(price_min=500, price_max=2000)) is True


def test_price_below_min():
    assert matches(I(price=400), W(price_min=500)) is False


def test_price_above_max():
    assert matches(I(price=3000), W(price_max=2000)) is False


def test_city_substring():
    assert matches(I(location="上海市浦东"), W(city="上海")) is True
    assert matches(I(location="北京市"), W(city="上海")) is False


def test_condition_in_list():
    assert matches(I(condition="95新"), W(condition=["99新", "95新"])) is True
    assert matches(I(condition="8成新"), W(condition=["99新"])) is False


def test_unknown_condition_passes():
    # 成色未知(None)时不应被成色过滤排除
    assert matches(I(condition=None), W(condition=["99新"])) is True


def test_free_shipping_required():
    assert matches(I(free_shipping=False), W(free_shipping=True)) is False


def test_none_criteria_ignored():
    assert matches(I(location=None, condition=None), W()) is True
