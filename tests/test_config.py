from xianyu_crawler.config import Watch, load_watchlist, Settings


def test_watch_defaults():
    w = Watch(name="w", keywords=["a"])
    assert w.want_max_per_run == 5 and w.enabled is True and w.price_min is None


def test_load_watchlist(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text(
        "watches:\n"
        "  - name: t\n"
        "    keywords: ['iPhone']\n"
        "    price_max: 5000\n",
        encoding="utf-8",
    )
    ws = load_watchlist(p)
    assert len(ws) == 1 and ws[0].name == "t" and ws[0].price_max == 5000


def test_settings_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("XIANYU_MIN_DROP_PCT", "8")
    s = Settings()
    assert s.min_drop_pct == 8.0
