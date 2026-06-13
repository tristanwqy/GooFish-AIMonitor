from xianyu_crawler.price_monitor import detect_drop


def test_no_drop_when_price_up():
    assert detect_drop("1", prev=100, curr=120, min_pct=5, min_abs=50) is None


def test_no_drop_when_equal():
    assert detect_drop("1", prev=100, curr=100, min_pct=5, min_abs=50) is None


def test_drop_by_pct_only():
    d = detect_drop("1", prev=100, curr=94, min_pct=5, min_abs=50)  # 6% / ¥6
    assert d is not None and round(d.drop_pct, 1) == 6.0 and d.drop_abs == 6


def test_drop_by_abs_only():
    d = detect_drop("1", prev=1000, curr=940, min_pct=10, min_abs=50)  # 6% / ¥60
    assert d is not None and d.drop_abs == 60


def test_below_both_thresholds_is_none():
    assert detect_drop("1", prev=1000, curr=970, min_pct=5, min_abs=50) is None  # 3% / ¥30


def test_prev_zero_guard():
    assert detect_drop("1", prev=0, curr=0, min_pct=5, min_abs=50) is None
