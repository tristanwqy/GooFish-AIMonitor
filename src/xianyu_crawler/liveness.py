"""商品存活性探测: 打开详情页, 拦截 mtop 详情接口的 ret 码判定死链。

权威信号(真实验证):
- 活: mtop.taobao.idle.pc.detail → ret ["SUCCESS::调用成功"]
- 死: ret ["FAIL_BIZ_ITEM_DEL_NOT_FOUND::您要看的宝贝不存在或已被删除啦!"]

保守原则: 只在拿到明确"不存在/已删除/已下架"信号时判死; 其它(含拿不到 ret、
风控、超时)一律视为"活", 绝不误杀在售商品(误杀 = 用户错过好货, 代价更高)。
"""
from __future__ import annotations

DETAIL_API = "mtop.taobao.idle.pc.detail"
_DEAD_MARKERS = ("ITEM_DEL", "不存在", "已被删除", "已删除", "已下架", "下架", "ITEM_NOT_FOUND")
_ITEM_URL = "https://www.goofish.com/item?id={}"


def _ret_blob(ret: object) -> str:
    if isinstance(ret, list):
        return " ".join(str(x) for x in ret)
    return str(ret or "")


def check_liveness(ctx, item_id: str, wait_ms: int = 2500) -> tuple[bool, str | None]:
    """返回 (dead, reason)。拿不到明确死亡信号即判活。"""
    page = ctx.new_page()
    captured: dict = {"ret": None}

    def _on_response(resp) -> None:
        if f"{DETAIL_API}/" in resp.url and captured["ret"] is None:
            try:
                captured["ret"] = resp.json().get("ret")
            except Exception:
                pass

    page.on("response", _on_response)
    try:
        page.goto(_ITEM_URL.format(item_id), wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)
    except Exception:
        return False, None          # 打开失败 → 不判死
    finally:
        page.close()

    blob = _ret_blob(captured["ret"])
    if "SUCCESS" in blob:
        return False, None
    if any(m in blob for m in _DEAD_MARKERS):
        return True, "已删除"
    return False, None              # 不确定 → 保守判活
