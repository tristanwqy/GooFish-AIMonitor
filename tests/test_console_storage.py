from xianyu_crawler.storage.db import make_session
from xianyu_crawler.storage import repo
from xianyu_crawler.models import Item


def session():
    return make_session("sqlite:///:memory:", create=True)


def test_watch_crud():
    s = session()
    w = repo.add_watch(s, name="w1", keywords='["iPhone"]', price_max=5000, enabled=True)
    assert w.id is not None
    assert len(repo.list_watches(s)) == 1
    repo.update_watch(s, w.id, price_max=4000, enabled=False)
    got = repo.get_watch(s, w.id)
    assert got is not None and got.price_max == 4000 and got.enabled is False
    repo.delete_watch(s, w.id)
    assert repo.list_watches(s) == []


def test_config_defaults_and_update():
    s = session()
    cfg = repo.get_config(s)
    assert cfg.notify_to == "" and cfg.schedule_minutes == 120   # 默认空, 走本地配置/UI
    repo.update_config(s, schedule_minutes=60, paused=True)
    cfg2 = repo.get_config(s)
    assert cfg2.schedule_minutes == 60 and cfg2.paused is True


def test_recommendation_lifecycle():
    s = session()
    it = Item(item_id="r1", title="t", url="u", price=1000)
    assert repo.create_recommendation(s, it, "w1") is True
    assert repo.create_recommendation(s, it, "w1") is False     # 已见过 → 不重复
    recs = repo.list_recommendations(s, "new")
    assert len(recs) == 1 and recs[0].item_id == "r1"
    repo.set_rec_status(s, "r1", "rejected")
    assert repo.list_recommendations(s, "new") == []
    assert len(repo.list_recommendations(s, "rejected")) == 1
