from xianyu_crawler.anti_detect import pick_profile, _looks_risky, PROFILES


def test_pick_profile_returns_member():
    p = pick_profile(seed=3)
    assert p in PROFILES and "user_agent" in p and "viewport" in p


def test_risk_control_detection():
    # 真风控: 可见"滑动/验证"文案, 或 URL 跳到 punish 页
    assert _looks_risky("https://www.goofish.com/item?id=1", "请向右滑动完成验证") is True
    assert _looks_risky("https://h5.m.goofish.com/punish?f=x", "访问被拦截") is True
    # 正常详情页: 可见文案正常(整页脚本含 baxia/captcha SDK, 但我们不扫脚本)→ 不误判
    assert _looks_risky("https://www.goofish.com/item?id=1", "MacBook Pro 99新 拖动查看大图") is False
