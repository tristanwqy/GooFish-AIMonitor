from xianyu_crawler.models import Item
from xianyu_crawler import pipeline
from xianyu_crawler.storage.db import make_session
from xianyu_crawler.storage import repo
from xianyu_crawler.config import Settings, Watch


def test_run_monitor_detects_drop(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    # 预置: 收藏商品上次价 100
    repo.upsert_item_with_price(s, Item(item_id="1", title="t", url="u", price=100), source="favorite")
    # 本次抓到 80 → 应产生 price_drop 事件
    monkeypatch.setattr(pipeline, "_read_favorites",
                        lambda ctx, settings: [Item(item_id="1", title="t", url="u", price=80)])
    settings = Settings(min_drop_pct=5, min_drop_abs=50)
    n = pipeline.run_monitor(ctx=None, session=s, settings=settings)
    assert n == 1
    assert repo.unnotified_events(s)[0].type == "price_drop"


def test_run_monitor_fav_reduce_signal(monkeypatch):
    # 闲鱼原生"收藏后降价"信号: 首次见到即通知, 同值不重复, 进一步降再通知
    s = make_session("sqlite:///:memory:", create=True)
    settings = Settings(min_drop_abs=50, min_drop_pct=99)
    it1 = Item(item_id="7", title="t", url="u", price=20000, reduce_price=500)
    monkeypatch.setattr(pipeline, "_read_favorites", lambda ctx, settings: [it1])
    assert pipeline.run_monitor(ctx=None, session=s, settings=settings) == 1   # 首次降价500
    assert pipeline.run_monitor(ctx=None, session=s, settings=settings) == 0   # 同样500不重复
    it2 = Item(item_id="7", title="t", url="u", price=19000, reduce_price=1500)
    monkeypatch.setattr(pipeline, "_read_favorites", lambda ctx, settings: [it2])
    assert pipeline.run_monitor(ctx=None, session=s, settings=settings) == 1   # 进一步降到1500


def test_run_monitor_reduce_below_threshold_skipped(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    it = Item(item_id="8", title="t", url="u", price=100, reduce_price=10)  # 仅降10 < 50
    monkeypatch.setattr(pipeline, "_read_favorites", lambda ctx, settings: [it])
    assert pipeline.run_monitor(ctx=None, session=s, settings=Settings(min_drop_abs=50)) == 0


def test_run_monitor_no_drop_for_new_item(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    # 首次见到的收藏(无历史) 不应判降价
    monkeypatch.setattr(pipeline, "_read_favorites",
                        lambda ctx, settings: [Item(item_id="9", title="t", url="u", price=50)])
    n = pipeline.run_monitor(ctx=None, session=s, settings=Settings())
    assert n == 0 and repo.unnotified_events(s) == []


def test_run_search_respects_want_cap(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    items = [Item(item_id=str(i), title="t", url="u", price=1000) for i in range(10)]
    monkeypatch.setattr(pipeline, "_search", lambda ctx, w, settings: items)
    monkeypatch.setattr(pipeline, "_add_favorite", lambda ctx, it, st: True)
    w = Watch(name="w", keywords=["x"], price_min=500, price_max=2000, want_max_per_run=3)
    added = pipeline.run_search(ctx=None, session=s, settings=Settings(), watches=[w])
    assert added == 3  # 上限生效


def test_run_search_filters_out_of_range(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    items = [Item(item_id="hi", title="t", url="u", price=9999),   # 超价, 过滤掉
             Item(item_id="ok", title="t", url="u", price=1000)]
    monkeypatch.setattr(pipeline, "_search", lambda ctx, w, settings: items)
    monkeypatch.setattr(pipeline, "_add_favorite", lambda ctx, it, st: True)
    w = Watch(name="w", keywords=["x"], price_max=2000)
    added = pipeline.run_search(ctx=None, session=s, settings=Settings(), watches=[w])
    assert added == 1 and repo.is_favorited(s, "ok") and not repo.is_favorited(s, "hi")
