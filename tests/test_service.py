from xianyu_crawler import service
from xianyu_crawler.storage.db import make_session
from xianyu_crawler.storage import repo
from xianyu_crawler.storage.orm import ItemRow
from xianyu_crawler.models import Item
from xianyu_crawler.config import Settings, Watch


def test_scan_recommendations_filters_and_dedups(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    items = [Item(item_id="a", title="t", url="u", price=1000),
             Item(item_id="b", title="t", url="u", price=9999)]   # 超价, 过滤掉
    monkeypatch.setattr(service, "_search", lambda ctx, w, st: items)
    w = Watch(name="w", keywords=["x"], price_max=2000)
    n = service.scan_recommendations(None, s, Settings(), [w])
    assert n == 1 and repo.list_recommendations(s)[0].item_id == "a"
    # 再扫不重复
    assert service.scan_recommendations(None, s, Settings(), [w]) == 0


def test_scan_recommendations_llm_review(monkeypatch):
    from xianyu_crawler import review
    s = make_session("sqlite:///:memory:", create=True)
    items = [Item(item_id="a", title="M5", url="u", price=1000),
             Item(item_id="b", title="M4", url="u", price=1000)]
    monkeypatch.setattr(service, "_search", lambda ctx, w, st: items)
    monkeypatch.setattr(
        review, "review_items",
        lambda its, req, st: [review.ReviewVerdict(ok=(it.item_id == "a"), reason="r") for it in its])
    w = Watch(name="w", keywords=["x"], requirement="必须 M5")
    n = service.scan_recommendations(None, s, Settings(), [w])
    assert n == 1                                   # 头条数字只数"通过"的
    recs = {r.item_id: r for r in repo.list_recommendations(s)}
    assert set(recs) == {"a", "b"}                  # 通过+未通过 都入库, 由前端筛选
    assert recs["a"].rec_ok is True and recs["b"].rec_ok is False
    assert recs["a"].rec_reason == "r" and recs["b"].rec_reason == "r"


def test_scan_skips_dead_items(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    # b 已知死链(收藏夹观测到已售) → 不应再进推荐
    repo.upsert_item_with_price(
        s, Item(item_id="b", title="t", url="u", price=1000, dead=True, dead_reason="已售出"),
        source="favorite")
    items = [Item(item_id="a", title="t", url="u", price=1000),
             Item(item_id="b", title="t", url="u", price=1000)]
    monkeypatch.setattr(service, "_search", lambda ctx, w, st: items)
    w = Watch(name="w", keywords=["x"])
    n = service.scan_recommendations(None, s, Settings(), [w])
    ids = [r.item_id for r in repo.list_recommendations(s)]
    assert n == 1 and ids == ["a"]      # 死链 b 被跳过


def test_sweep_liveness_marks_dead(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    repo.create_recommendation(s, Item(item_id="alive", title="t", url="u", price=500), "w")
    repo.create_recommendation(s, Item(item_id="gone", title="t", url="u", price=500), "w")
    # 模拟详情核活: gone 已删除, alive 在售; 两者都顺带返回浏览/收藏/想要次数
    monkeypatch.setattr(
        service, "_check_liveness",
        lambda ctx, iid: (True, "已删除", {"browse_count": 9, "collect_count": 2, "want_count": 5})
        if iid == "gone"
        else (False, None, {"browse_count": 134, "collect_count": 3, "want_count": 7}))
    n = service.sweep_liveness(None, s, Settings())
    assert n == 1
    assert repo.is_dead(s, "gone") is True
    assert repo.is_dead(s, "alive") is False
    # 核活顺带把浏览/收藏/想要次数回写到 alive
    row = s.get(ItemRow, "alive")
    assert (row.browse_count, row.collect_count, row.want_count) == (134, 3, 7)
    # 死链仍在待审列表(置灰展示, 不删除), 但不会被重复判死
    assert {r.item_id for r in repo.list_recommendations(s, "new")} == {"alive", "gone"}
    assert service.sweep_liveness(None, s, Settings()) == 0   # gone 已死, 跳过


def test_approve_recommendation(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    repo.create_recommendation(s, Item(item_id="c", title="t", url="u", price=500), "w")
    monkeypatch.setattr(service, "_add_favorite", lambda ctx, it, st: True)
    assert service.approve_recommendation(None, s, Settings(), "c") is True
    assert repo.is_favorited(s, "c") is True
    assert repo.list_recommendations(s, "approved")[0].item_id == "c"


def test_approve_recommendation_fails_gracefully(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    repo.create_recommendation(s, Item(item_id="e", title="t", url="u", price=500), "w")
    monkeypatch.setattr(service, "_add_favorite", lambda ctx, it, st: False)  # 收藏失败
    assert service.approve_recommendation(None, s, Settings(), "e") is False
    assert repo.is_favorited(s, "e") is False
    assert repo.list_recommendations(s, "new")[0].item_id == "e"   # 仍在待审


def test_reject_recommendation():
    s = make_session("sqlite:///:memory:", create=True)
    repo.create_recommendation(s, Item(item_id="d", title="t", url="u", price=500), "w")
    service.reject_recommendation(s, "d")
    assert repo.list_recommendations(s, "new") == []


def test_mute_recommendation_hides_and_blocks_rescan(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    repo.create_recommendation(s, Item(item_id="z", title="t", url="u", price=500), "w")
    service.mute_recommendation(s, "z", 7)
    assert repo.list_recommendations(s, "new") == []          # 7 天内不看 → 隐藏
    assert repo.is_muted(s, "z") is True
    # 再扫到同一商品也不会重新推荐
    monkeypatch.setattr(service, "_search",
                        lambda ctx, w, st: [Item(item_id="z", title="t", url="u", price=500)])
    w = Watch(name="w", keywords=["x"])
    assert service.scan_recommendations(None, s, Settings(), [w]) == 0


def test_mute_forever():
    s = make_session("sqlite:///:memory:", create=True)
    repo.create_recommendation(s, Item(item_id="f", title="t", url="u", price=1), "w")
    service.mute_recommendation(s, "f", 0)                     # 永远不看
    assert repo.is_muted(s, "f") is True
    assert repo.list_recommendations(s, "new") == []


def test_effective_settings_overrides():
    s = make_session("sqlite:///:memory:", create=True)
    repo.update_config(s, min_drop_pct=8, headless=True, notify_to="me@test.com")
    cfg = repo.get_config(s)
    st = service.effective_settings(cfg)
    assert st.min_drop_pct == 8 and st.notify_to == "me@test.com" and st.headless is True


def test_effective_settings_smtp_from_db():
    s = make_session("sqlite:///:memory:", create=True)
    repo.update_config(s, smtp_host="smtp.test.com", smtp_port=465,
                       smtp_user="me@test.com", smtp_pass="secret")
    st = service.effective_settings(repo.get_config(s))
    assert st.smtp_host == "smtp.test.com" and st.smtp_user == "me@test.com"
    assert st.smtp_pass == "secret" and st.smtp_port == 465


def test_effective_settings_smtp_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("XIANYU_SMTP_HOST", "env.smtp.com")
    s = make_session("sqlite:///:memory:", create=True)
    st = service.effective_settings(repo.get_config(s))   # DB 未填 → 用环境变量
    assert st.smtp_host == "env.smtp.com"


def test_watchrow_to_watch_roundtrip():
    s = make_session("sqlite:///:memory:", create=True)
    row = repo.add_watch(s, name="w", keywords='["iPhone","苹果"]',
                         price_max=5000, condition='["99新"]', free_shipping=True)
    w = service.watchrow_to_watch(row)
    assert w.keywords == ["iPhone", "苹果"] and w.condition == ["99新"]
    assert w.price_max == 5000 and w.free_shipping is True


# --- 一键 AI 审核(补审已入库推荐) ---
def _seed_pending(s, review):
    repo.add_watch(s, name="w", keywords='["x"]', requirement="必须 M1 Pro")
    repo.create_recommendation(s, Item(item_id="a", title="M1 Pro 机", url="u", price=7000),
                               "w", reason=review.REVIEW_NOT_RUN, ok=True)
    repo.create_recommendation(s, Item(item_id="b", title="别的机", url="u", price=7000),
                               "w", reason=review.REVIEW_NOT_RUN, ok=True)


def test_rereview_pending_updates_verdicts(monkeypatch):
    from xianyu_crawler import review
    s = make_session("sqlite:///:memory:", create=True)
    _seed_pending(s, review)
    monkeypatch.setattr(review, "review_items", lambda items, req, st: [
        review.ReviewVerdict(ok=(it.item_id == "a"), reason="符合" if it.item_id == "a" else "不符")
        for it in items])
    out = service.rereview_pending(s, Settings())
    assert out["ok"] and out["reviewed"] == 2 and out["passed"] == 1 and out["rejected"] == 1
    recs = {r.item_id: r for r in repo.list_recommendations(s)}
    assert recs["a"].rec_ok is True and recs["b"].rec_ok is False
    assert recs["b"].rec_reason == "不符"


def test_rereview_keeps_unrun_when_llm_still_fails(monkeypatch):
    from xianyu_crawler import review
    s = make_session("sqlite:///:memory:", create=True)
    _seed_pending(s, review)
    # LLM 仍没跑通 → 占位裁决, 不改写原裁决, 只计数
    monkeypatch.setattr(review, "review_items", lambda items, req, st: [
        review.ReviewVerdict(ok=True, reason=review.REVIEW_NOT_RUN) for _ in items])
    out = service.rereview_pending(s, Settings())
    assert out["reviewed"] == 0 and out["not_run"] == 2


def test_rereview_disabled_returns_error():
    s = make_session("sqlite:///:memory:", create=True)
    out = service.rereview_pending(s, Settings(review_enabled=False))
    assert out["ok"] is False and "启用" in out["error"]


def test_rereview_skips_watch_without_requirement(monkeypatch):
    from xianyu_crawler import review
    s = make_session("sqlite:///:memory:", create=True)
    repo.add_watch(s, name="w", keywords='["x"]')   # 无 requirement
    repo.create_recommendation(s, Item(item_id="a", title="t", url="u", price=1000), "w")
    called = {"n": 0}
    monkeypatch.setattr(review, "review_items",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or [])
    out = service.rereview_pending(s, Settings())
    assert out["skipped_no_requirement"] == 1 and out["reviewed"] == 0 and called["n"] == 0
