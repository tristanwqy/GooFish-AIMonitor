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
import re

import httpx
from pydantic import BaseModel

from .config import Settings
from .models import Item

logger = logging.getLogger(__name__)

# 审核没跑通(接口报错/未配置)时的占位理由; 一键补审据此识别"还没真正审过"的条目。
REVIEW_NOT_RUN = "(审核未运行)"

# 一次最多送几条给模型审。分批是为了「推理模型」: 它们会把大量 token 花在思考
# (reasoning_content)上, 一次塞太多条会把 max_tokens 用光、正文(content)为空 → 解析失败
# → 整批被 fail-open 放行(显示「审核未运行」)。分小批让每次调用的思考量可控。
REVIEW_BATCH = 5

# 有些推理模型把思考内联在 content 里(<think>...</think>), 解析前先剥掉。
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str | None) -> str:
    return _THINK_RE.sub("", text or "").strip()


class ReviewVerdict(BaseModel):
    ok: bool
    reason: str = ""


def review_items(items: list[Item], requirement: str | None,
                 settings: Settings) -> list[ReviewVerdict]:
    """逐条判定候选是否符合 requirement; 未启用/无要求/失败则全部放行。

    分小批(REVIEW_BATCH)调用: 某一批失败只放行那一批, 不会一条坏掉拖垮整轮。
    """
    if not settings.review_enabled or not requirement or not items:
        return [ReviewVerdict(ok=True) for _ in items]
    out: list[ReviewVerdict] = []
    for i in range(0, len(items), REVIEW_BATCH):
        chunk = items[i:i + REVIEW_BATCH]
        try:
            content = _call_llm(_build_messages(chunk, requirement, settings), settings)
            out.extend(_parse_verdicts(content, len(chunk)))
        except Exception as e:  # noqa: BLE001 - 审核失败不应黑洞推荐, 本批放行
            logger.warning("二次审核失败(本批 %d 条放行): %s", len(chunk), _friendly_error(e))
            out.extend(ReviewVerdict(ok=True, reason=REVIEW_NOT_RUN) for _ in chunk)
    return out


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
    msg = (resp.json().get("choices") or [{}])[0].get("message") or {}
    content = _strip_think(msg.get("content"))
    if not content:
        # 推理模型常把正文留在 reasoning_content; content 为空时兜底取它(也剥思考标签)
        content = _strip_think(msg.get("reasoning_content"))
    return content


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
    s = (text or "").strip()
    if not s:
        raise ValueError("模型没有返回正文(content 为空) — 多半是推理模型把 token 用在思考上, 或 max_tokens 太小")
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


def test_review(settings: Settings, requirement: str | None = None) -> dict:
    """用当前配置做一次真实审核, 回显成功或失败原因(控制台「测试 LLM」按钮用)。

    诚实判定: 只有「真的拿到可解析的裁决」才算 ok。连上了但正文为空 / 不是 JSON 都算失败
    并给出可操作的原因——否则会出现「测试通过但实际审核全跳过」的假阳性(正是推理模型的坑)。
    用一整批(REVIEW_BATCH 条)+ 真实「AI 审核要求」来测, 尽量贴近真实一轮, 能提前暴露
    「推理模型把 token 用在思考、content 为空」的问题。
    """
    sample = [
        Item(item_id="0", title="MacBook Pro 16寸 M1 Pro 32G 1T 国行 95新", url="", price=7000, condition="95新", location="北京"),
        Item(item_id="1", title="MacBook Pro 14寸 M1 Pro 16G 512G", url="", price=5000, condition="9成新", location="上海"),
        Item(item_id="2", title="MacBook Air M1 8G 256G", url="", price=3000, condition="95新", location="广州"),
        Item(item_id="3", title="MacBook Pro 16寸 M1 Max 32G 1T 国行", url="", price=8000, condition="99新", location="深圳"),
        Item(item_id="4", title="MacBook Pro 16寸 M1 Pro 32G 512G", url="", price=6000, condition="9成新", location="杭州"),
    ][:REVIEW_BATCH]
    req = requirement or "只要 16 寸、M1 Pro、32G 内存、1T 硬盘、国行; 不要阉割版 / 16G / 512G"
    try:
        content = _call_llm(_build_messages(sample, req, settings), settings)
    except Exception as e:  # noqa: BLE001 - 失败原因回显给控制台, 不抛
        return {"ok": False, "error": _friendly_error(e)}
    if not content.strip():
        return {"ok": False, "model": settings.review_model,
                "error": "连上了, 但模型没返回正文(content 为空)。多半是推理模型把 token 额度用在思考上 —"
                         "调大「最大 tokens」(如 8000)、缩短「AI 审核要求」, 或换非推理模型。"}
    try:
        _parse_verdicts(content, len(sample))
    except Exception:  # noqa: BLE001
        return {"ok": False, "model": settings.review_model, "reply": content.strip()[:200],
                "error": "连上了, 但返回的不是可解析的 JSON 数组(见下方片段)。调大 max_tokens 或换模型。"}
    return {"ok": True, "model": settings.review_model, "reply": content.strip()[:200]}
