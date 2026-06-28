"""browser_session 的登录态文件必须锚定到 data_dir, 不能用相对 CWD 的路径。

回归: 打包成桌面应用后进程 CWD 不是数据目录, 旧默认 "data/storage_state.json"
(相对 CWD)读不到扫码登录存的 data_dir/storage_state.json, 导致每轮抓取都被判
未登录 → 收藏夹空、零推荐。这里钉死「不传 state_path 时锚定到 data_dir」。
"""
from unittest.mock import MagicMock

from xianyu_crawler import session as sess
from xianyu_crawler.config import Settings


def _mock_playwright(monkeypatch, captured: dict):
    ctx = MagicMock(name="ctx")
    browser = MagicMock(name="browser")
    browser.new_context.side_effect = lambda **kw: (captured.update(kw), ctx)[1]
    p = MagicMock(name="p")
    p.chromium.launch.return_value = browser
    pw_cm = MagicMock(name="playwright_cm")
    pw_cm.__enter__.return_value = p
    monkeypatch.setattr(sess, "sync_playwright", lambda: pw_cm)
    return ctx


def test_browser_session_anchors_state_to_data_dir(tmp_path, monkeypatch):
    (tmp_path / "storage_state.json").write_text("{}")
    settings = Settings(data_dir=tmp_path)
    captured: dict = {}
    ctx = _mock_playwright(monkeypatch, captured)

    # 不传 state_path —— 与 runner.crawl / cli 的调用方式一致
    with sess.browser_session(settings) as got:
        assert got is ctx

    want = str(tmp_path / "storage_state.json")
    # 载入登录态: 锚定到 data_dir(绝对路径), 不是相对 CWD 的 "data/storage_state.json"
    assert captured["storage_state"] == want
    assert captured["storage_state"] != "data/storage_state.json"
    # 退出保存: 写回同一个 data_dir 路径
    assert ctx.storage_state.call_args.kwargs["path"] == want


def test_browser_session_missing_state_passes_none(tmp_path, monkeypatch):
    # data_dir 里还没有登录态文件 → 以无登录态启动(storage_state=None), 不报错
    settings = Settings(data_dir=tmp_path)
    captured: dict = {}
    _mock_playwright(monkeypatch, captured)
    with sess.browser_session(settings):
        pass
    assert captured["storage_state"] is None


def test_browser_session_explicit_state_path_wins(tmp_path, monkeypatch):
    explicit = tmp_path / "custom.json"
    explicit.write_text("{}")
    settings = Settings(data_dir=tmp_path)
    captured: dict = {}
    _mock_playwright(monkeypatch, captured)
    with sess.browser_session(settings, state_path=str(explicit)):
        pass
    assert captured["storage_state"] == str(explicit)
