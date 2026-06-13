"""反爬助手: 设备画像/随机延时/拟人滚动/风控识别。"""
from __future__ import annotations

import random
import time

PROFILES = [
    {"user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
     "viewport": {"width": 1440, "height": 900}},
    {"user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
     "viewport": {"width": 1280, "height": 800}},
    {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "viewport": {"width": 1536, "height": 864}},
]
# URL 跳到这些 = 真验证/punish 页; 可见文案出现这些 = 真 challenge。
# 注意: 不能扫整页 HTML —— 闲鱼每页都预加载 baxia/captcha 风控 SDK 脚本,
# 全量匹配会把每个**正常**页都误判成风控(收藏永远点不成, 表现为"假收藏")。
_RISK_URL_MARKERS = ("punish", "_____tmd_____", "captcha", "nocaptcha")
_RISK_TEXT_MARKERS = ("滑块", "向右滑动", "安全验证", "拖动下方滑块", "完成验证",
                      "确保正常访问", "网络不见了")


def pick_profile(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    return rng.choice(PROFILES)


def human_delay(lo: float = 3.0, hi: float = 8.0) -> None:
    time.sleep(random.uniform(lo, hi))


def _looks_risky(url: str, visible_text: str) -> bool:
    """纯函数(可单测): 据 URL + 可见文案判断是否真风控。"""
    if any(m in (url or "").lower() for m in _RISK_URL_MARKERS):
        return True
    return any(m in (visible_text or "") for m in _RISK_TEXT_MARKERS)


def is_risk_control(page) -> bool:
    """真风控判定: URL 跳到验证/punish 页, 或页面**可见文案**出现验证提示。
    扫 page.url + 主体可见文本 + 各 iframe 可见文本(滑块验证常在 iframe 里);
    不扫 page.content()(整页 HTML 含预载 baxia/captcha SDK 会把正常页误判)。"""
    try:
        url = page.url
    except Exception:
        url = ""
    parts: list[str] = []
    try:
        parts.append(page.inner_text("body", timeout=2000))
    except Exception:
        pass
    for fr in page.frames:                      # 滑块/验证码经常嵌在 iframe
        try:
            parts.append(fr.inner_text("body", timeout=400))
        except Exception:
            pass
    return _looks_risky(url, " ".join(parts))


def human_scroll(page, steps: int = 4) -> None:
    for _ in range(steps):
        page.mouse.wheel(0, random.randint(400, 900))
        time.sleep(random.uniform(0.6, 1.6))
