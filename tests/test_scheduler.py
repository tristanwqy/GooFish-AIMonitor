def test_scheduler_lifecycle(monkeypatch):
    from xianyu_crawler.web import scheduler, runner
    monkeypatch.setattr(runner, "crawl", lambda: {"ok": True})            # 防止真跑浏览器
    monkeypatch.setattr(runner, "refresh_favorites", lambda: {"ok": True})
    assert scheduler.is_running() is False
    scheduler.start(60, 30)        # 推荐 60 分钟 / 收藏 30 分钟, 测试窗口内不触发
    try:
        assert scheduler.is_running() is True
        scheduler.reschedule(120, 15)   # 两个间隔都改, 不应报错
    finally:
        scheduler.shutdown()
    assert scheduler.is_running() is False
