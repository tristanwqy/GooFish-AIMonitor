from datetime import datetime, timedelta

from xianyu_crawler.storage.db import make_session
from xianyu_crawler.storage import repo
from xianyu_crawler.storage.orm import ItemRow
from xianyu_crawler.models import Item


def session():
    return make_session("sqlite:///:memory:", create=True)


def _row(s, item_id: str) -> ItemRow:
    row = s.get(ItemRow, item_id)
    assert row is not None
    return row


def test_upsert_and_get_prev_price():
    s = session()
    it = Item(item_id="1", title="t", url="u", price=100.0)
    assert repo.get_latest_price(s, "1") is None
    repo.upsert_item_with_price(s, it, source="favorite")
    assert repo.get_latest_price(s, "1") == 100.0
    it2 = it.model_copy(update={"price": 80.0})
    prev = repo.upsert_item_with_price(s, it2, source="favorite")
    assert prev == 100.0 and repo.get_latest_price(s, "1") == 80.0


def test_reduce_price_roundtrip():
    s = session()
    repo.upsert_item_with_price(
        s, Item(item_id="5", title="t", url="u", price=100, reduce_price=80), source="favorite")
    assert repo.get_reduce_price(s, "5") == 80.0
    # 再次写入无 reduce 的同一商品 → 归 0
    repo.upsert_item_with_price(s, Item(item_id="5", title="t", url="u", price=90), source="favorite")
    assert repo.get_reduce_price(s, "5") == 0.0


def test_mark_favorited():
    s = session()
    repo.upsert_item_with_price(s, Item(item_id="2", title="t", url="u", price=5), source="search")
    repo.mark_favorited(s, "2")
    assert repo.is_favorited(s, "2") is True


def test_record_and_fetch_unnotified_events():
    s = session()
    repo.upsert_item_with_price(s, Item(item_id="3", title="t", url="u", price=5), source="favorite")
    repo.add_event(s, "3", "price_drop", {"drop_abs": 20})
    evs = repo.unnotified_events(s)
    assert len(evs) == 1 and evs[0].type == "price_drop"
    repo.mark_notified(s, [evs[0].id])
    assert repo.unnotified_events(s) == []


def test_dead_from_upsert_and_sticky():
    s = session()
    # 首见即死链 → 入库带 dead
    repo.upsert_item_with_price(
        s, Item(item_id="d1", title="t", url="u", price=10, dead=True, dead_reason="已售出"),
        source="favorite")
    assert repo.is_dead(s, "d1") is True
    # 活观测不复活死链(粘性)
    repo.upsert_item_with_price(s, Item(item_id="d1", title="t", url="u", price=10), source="favorite")
    assert repo.is_dead(s, "d1") is True
    # 活→死转换
    repo.upsert_item_with_price(s, Item(item_id="d2", title="t", url="u", price=10), source="favorite")
    assert repo.is_dead(s, "d2") is False
    repo.upsert_item_with_price(
        s, Item(item_id="d2", title="t", url="u", price=10, dead=True, dead_reason="已删除"),
        source="favorite")
    assert repo.is_dead(s, "d2") is True


def test_mark_dead():
    s = session()
    repo.upsert_item_with_price(s, Item(item_id="m1", title="t", url="u", price=10), source="search")
    repo.mark_dead(s, "m1", "已下架")
    assert repo.is_dead(s, "m1") is True


def test_mark_collected_demotes_pending_rec():
    s = session()
    # 一个还在待审、但用户已在闲鱼收藏的商品
    repo.create_recommendation(s, Item(item_id="g", title="t", url="u", price=500), "w")
    assert repo.list_recommendations(s, "new")[0].item_id == "g"
    repo.mark_collected(s, "g")
    assert repo.is_favorited(s, "g") is True
    assert repo.list_recommendations(s, "new") == []      # 退出待审
    assert _row(s, "g").rec_status == "approved"


def test_list_recommendations_excludes_favorited_and_muted():
    s = session()
    for iid in ("a", "b", "c"):
        repo.create_recommendation(s, Item(item_id=iid, title="t", url="u", price=1), "w")
    repo.mark_collected(s, "a")                           # 已收藏 → 隐藏
    repo.mute_item(s, "b", repo._now() + timedelta(days=7))  # 静音中 → 隐藏
    ids = {r.item_id for r in repo.list_recommendations(s, "new")}
    assert ids == {"c"}


def test_mute_expiry_resurfaces():
    s = session()
    repo.create_recommendation(s, Item(item_id="m", title="t", url="u", price=1), "w")
    repo.mute_item(s, "m", repo._now() - timedelta(minutes=1))   # 已过期
    assert repo.is_muted(s, "m") is False
    assert {r.item_id for r in repo.list_recommendations(s, "new")} == {"m"}  # 到期重现


def test_price_changed_at_set_on_change():
    s = session()
    repo.upsert_item_with_price(s, Item(item_id="p", title="t", url="u", price=100), source="favorite")
    assert _row(s, "p").price_changed_at is None       # 首见无调价
    repo.upsert_item_with_price(s, Item(item_id="p", title="t", url="u", price=100), source="favorite")
    assert _row(s, "p").price_changed_at is None       # 价没变
    repo.upsert_item_with_price(s, Item(item_id="p", title="t", url="u", price=80), source="favorite")
    assert _row(s, "p").price_changed_at is not None   # 降价 → 记时间


def test_publish_time_persisted():
    s = session()
    pt = datetime(2026, 6, 10, 3, 0, 0)
    repo.upsert_item_with_price(
        s, Item(item_id="pt", title="t", url="u", price=1, publish_time=pt), source="search")
    assert _row(s, "pt").publish_time == pt


def test_list_favorites_includes_collection_and_sorts_dead_last():
    s = session()
    # 收藏夹来源(未经我们 approve)也应出现在收藏视图
    repo.upsert_item_with_price(s, Item(item_id="f1", title="活", url="u", price=10), source="favorite")
    repo.upsert_item_with_price(
        s, Item(item_id="f2", title="死", url="u", price=10, dead=True, dead_reason="已售出"),
        source="favorite")
    favs = repo.list_favorites(s)
    ids = [r.item_id for r in favs]
    assert set(ids) == {"f1", "f2"}     # source=favorite 即纳入(无需 favorited=True)
    assert ids[-1] == "f2"              # 死链排末尾
