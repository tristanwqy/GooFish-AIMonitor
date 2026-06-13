import pytest

from xianyu_crawler.config import Settings
from xianyu_crawler.notifier import format_email, append_csv, send_test


def test_send_test_raises_when_unconfigured():
    # 未配 SMTP → 抛错并指出缺哪些(供控制台「测试」回显)
    with pytest.raises(ValueError, match="SMTP 配置不完整"):
        send_test(Settings(smtp_host=None, smtp_user=None, smtp_pass=None, notify_to=None))


def test_format_email_groups_by_type():
    events = [
        {"type": "price_drop", "title": "iPhone", "url": "u1",
         "prev_price": 100, "curr_price": 80, "drop_abs": 20, "drop_pct": 20.0},
        {"type": "favorited", "title": "iPad", "url": "u2"},
    ]
    subject, body = format_email(events)
    assert "降价" in subject
    assert "iPhone" in body and "80" in body and "iPad" in body


def test_format_email_new_and_sold():
    # 新增事件类型: 发现新推荐 + 已售出/下架, 各自成段且进标题
    events = [
        {"type": "new_recommendation", "title": "M4 Pro", "url": "u1", "price": 18000, "watch": "MBP"},
        {"type": "sold", "title": "M1 Pro", "url": "u2", "reason": "已售出"},
    ]
    subject, body = format_email(events)
    assert "新发现" in subject and "售出" in subject
    assert "M4 Pro" in body and "18000" in body
    assert "M1 Pro" in body and "已售出" in body


def test_append_csv(tmp_path):
    p = tmp_path / "events.csv"
    append_csv(p, [{"type": "price_drop", "title": "x", "url": "u", "curr_price": 1}])
    text = p.read_text(encoding="utf-8")
    assert "price_drop" in text and "x" in text
    append_csv(p, [{"type": "favorited", "title": "y", "url": "u2"}])
    assert p.read_text(encoding="utf-8").count("\n") >= 3  # header + 2 rows
