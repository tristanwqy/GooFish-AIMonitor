"""二次审核: 调任意 OpenAI 兼容接口, 判定候选是否符合 watch.requirement。

端点: POST {review_base_url}/chat/completions (OpenAI Chat Completions 格式)。
具体接口地址/密钥由本地配置(data/secret.env 的 XIANYU_REVIEW_BASE_URL /
XIANYU_REVIEW_API_TOKEN)或控制台设置提供, 不写进仓库。不强制 response_format,
故让模型输出 JSON 数组再自行解析。无要求/未启用/调用失败时**放行全部**(fail-open),
避免把推荐误黑洞掉(用户仍能看到候选, 只是这轮没审)。
"""
from __future__ import annotations

import json
import logging

import httpx
from pydantic import BaseModel

from .config import Settings
from .models import Item

logger = logging.getLogger(__name__)

# 审核没跑通(接口报错/未配置)时的占位理由; 一键补审据此识别"还没真正审过"的条目。
REVIEW_NOT_RUN = "(审核未运行)"


class ReviewVerdict(BaseModel):
    ok: bool
    reason: str = ""


def review_items(items: list[Item], requirement: str | None,
                 settings: Settings) -> list[ReviewVerdict]:
    """逐条判定候选是否符合 requirement; 未启用/无要求/失败则全部放行。"""
    if not settings.review_enabled or not requirement or not items:
        return [ReviewVerdict(ok=True) for _ in items]
    try:
        content = _call_llm(_build_messages(items, requirement, settings), settings)
        return _parse_verdicts(content, len(items))
    except Exception as e:  # noqa: BLE001 - 审核失败不应黑洞推荐
        logger.warning("二次审核调用失败, 放行全部: %s", e)
        return [ReviewVerdict(ok=True, reason=REVIEW_NOT_RUN) for _ in items]


def _build_messages(items: list[Item], requirement: str, settings: Settings) -> list[dict]:
    lines = []
    for i, it in enumerate(items):
        meta = " | ".join(p for p in [
            f"¥{it.price:.0f}",
            f"成色:{it.condition}" if it.condition else "",
            f"地区:{it.location}" if it.location else "",
        ] if p)
        lines.append(f"{i}. {it.title}  [{meta}]")
    user = (
        f"要求: {requirement}\n\n"
        "逐个判断下面的商品是否符合上面的要求:\n" + "\n".join(lines) +
        '\n\n只输出 JSON 数组, 每项 {"i":序号,"ok":true/false,"reason":"一句话中文理由"}。不要输出别的。'
    )
    return [{"role": "system", "content": settings.review_system_prompt},
            {"role": "user", "content": user}]


def _call_llm(messages: list[dict], settings: Settings) -> str:
    url = settings.review_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.review_api_token:
        headers["Authorization"] = f"Bearer {settings.review_api_token}"
    body = {
        "model": settings.review_model,
        "messages": messages,
        "stream": False,
        "max_tokens": settings.review_max_tokens,
        "temperature": settings.review_temperature,
    }
    resp = httpx.post(url, json=body, headers=headers, timeout=settings.review_timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _parse_verdicts(content: str, n: int) -> list[ReviewVerdict]:
    arr = _extract_json_array(content)
    by_i: dict[int, dict] = {}
    for v in arr:
        if isinstance(v, dict) and "i" in v:
            try:
                by_i[int(v["i"])] = v
            except (ValueError, TypeError):
                continue
    out: list[ReviewVerdict] = []
    for idx in range(n):
        v = by_i.get(idx)
        if v is None:
            out.append(ReviewVerdict(ok=True))          # 缺失 → 放行
        else:
            out.append(ReviewVerdict(ok=bool(v.get("ok")), reason=str(v.get("reason") or "")))
    return out


def _extract_json_array(text: str) -> list:
    s = text.strip()
    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("响应里没有 JSON 数组")
    return json.loads(s[start:end + 1])


def _friendly_error(e: Exception) -> str:
    """把底层异常翻成控制台能看懂的一句话(尤其区分 401/404, 帮用户判断是 key 还是地址/模型)。"""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        hint = {
            400: "请求被拒(模型名或参数可能不对)",
            401: "Key 无效或无权限(鉴权失败)",
            403: "无权限 / 被拒绝",
            404: "接口地址或模型名不对",
            429: "调用频率 / 额度超限",
            500: "服务端错误", 502: "网关错误", 503: "服务暂不可用",
        }.get(code, "")
        return f"HTTP {code} {hint}".strip()
    if isinstance(e, httpx.ConnectError):
        return f"连不上接口地址(base url 可能写错): {e}"
    if isinstance(e, httpx.TimeoutException):
        return "请求超时(可调大超时或检查网络)"
    return f"{type(e).__name__}: {e}"


def test_review(settings: Settings) -> dict:
    """用当前配置对一条样例做一次真实 LLM 调用, 回显成功或失败原因(控制台「测试」按钮用)。

    只验证「接口地址 + 模型 + 鉴权」是否打通。返回内容能否解析成规整 JSON 只作附加提示:
    解析失败时审核本就 fail-open 放行, 不影响"能不能调用"这件事。
    """
    sample = [Item(item_id="0", title="MacBook Pro 16寸 M1 Pro 32G 1T 国行 95新",
                   url="", price=7000.0, condition="95新", location="北京")]
    messages = _build_messages(sample, "只要国行 16寸 M1 Pro 32G 1T", settings)
    try:
        content = _call_llm(messages, settings)
    except Exception as e:  # noqa: BLE001 - 失败原因回显给控制台, 不抛
        return {"ok": False, "error": _friendly_error(e)}
    try:
        _parse_verdicts(content, 1)
        parsed = True
    except Exception:  # noqa: BLE001
        parsed = False
    return {"ok": True, "model": settings.review_model,
            "parsed": parsed, "reply": content.strip()[:300]}
