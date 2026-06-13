"""对单个商品点"收藏"(加入收藏列表)。

注意: 闲鱼"想要"(data-spm=want)是联系卖家/聊天, **不是收藏**, 不要点。
真实页面确认: "收藏"按钮 = 商品详情页操作行右侧 div(图标 + 文字"收藏"),
get_by_text("收藏", exact=True) 唯一且可点。
"""
from __future__ import annotations

import random

from .models import Item
from .anti_detect import human_delay, human_scroll, is_risk_control

_FAVORITE_TEXT = "收藏"


def _try_favorite(page) -> bool:
    """单次尝试: 等"收藏"按钮渲染 → 点 → 确认变"已收藏"。已收藏返回 True。"""
    done = page.get_by_text("已收藏", exact=True)
    fav = page.get_by_text(_FAVORITE_TEXT, exact=True).first
    try:
        fav.wait_for(state="visible", timeout=12000)    # 详情页重 SPA, 收藏按钮 ~4-5s 才出
    except Exception:
        return done.count() > 0                         # 没"收藏"按钮: 多半本就已收藏
    try:                                                 # 像真人: 滚到按钮 → 悬停 → 停顿再点
        fav.scroll_into_view_if_needed(timeout=3000)
        fav.hover(timeout=3000)
        page.wait_for_timeout(random.randint(300, 900))
    except Exception:
        pass
    fav.click(timeout=5000)
    try:
        done.first.wait_for(state="visible", timeout=6000)   # 必须变"已收藏"才算真成功
        return True
    except Exception:
        return False


def add_favorite(ctx, item: Item, settings) -> bool:
    """在商品详情页点"收藏"并**确认生效**; 已收藏视为成功; 风控/未生效返回 False。

    点完必须看到"已收藏"才返回成功, 杜绝"卡片移走了、闲鱼里却没收藏"的假象。
    闲鱼对详情页有概率弹滑块验证(headless 更易触发): 命中验证直接放弃, 其它失败重载再试一次。
    """
    page = ctx.new_page()
    try:
        page.goto(item.url, wait_until="domcontentloaded")
        try:
            human_scroll(page, steps=2)                  # 模拟阅读, 降低反爬触发
        except Exception:
            pass
        for _ in range(2):
            try:
                if _try_favorite(page):
                    human_delay(settings.action_delay_min, settings.action_delay_max)
                    return True
            except Exception:
                pass
            if is_risk_control(page):                   # 真滑块验证 → 重试也没用
                return False
            page.wait_for_timeout(1500)
            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                break
        return False
    except Exception:
        return False
    finally:
        page.close()
