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
        return [ReviewVerdict(ok=True, reason="(审核未运行)") for _ in items]


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
