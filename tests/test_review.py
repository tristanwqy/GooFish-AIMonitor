import httpx

from xianyu_crawler import review
from xianyu_crawler.review import ReviewVerdict, _parse_verdicts, _extract_json_array, _build_messages
from xianyu_crawler.models import Item
from xianyu_crawler.config import Settings


def test_extract_json_array_with_fence():
    txt = '好的:\n```json\n[{"i":0,"ok":true,"reason":"符合"}]\n```'
    arr = _extract_json_array(txt)
    assert arr[0]["ok"] is True


def test_parse_verdicts_aligns_and_fills_missing():
    content = '[{"i":0,"ok":true,"reason":"M5符合"},{"i":2,"ok":false,"reason":"M4不符"}]'
    vs = _parse_verdicts(content, 3)
    assert len(vs) == 3
    assert vs[0].ok is True and "M5" in vs[0].reason
    assert vs[1].ok is True            # i=1 缺失 → 放行
    assert vs[2].ok is False


def test_review_items_no_requirement_passes_all():
    items = [Item(item_id="a", title="x", url="u", price=1)]
    assert review.review_items(items, None, Settings()) == [ReviewVerdict(ok=True)]


def test_review_items_failopen_on_error(monkeypatch):
    items = [Item(item_id="a", title="x", url="u", price=1)]

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(review, "_call_llm", boom)
    vs = review.review_items(items, "必须M5", Settings())
    assert vs[0].ok is True and "未运行" in vs[0].reason


def test_review_items_uses_llm_verdict(monkeypatch):
    items = [Item(item_id="a", title="M5", url="u", price=1),
             Item(item_id="b", title="M4", url="u", price=1)]
    monkeypatch.setattr(
        review, "_call_llm",
        lambda msgs, st: '[{"i":0,"ok":true,"reason":"M5符合"},{"i":1,"ok":false,"reason":"M4不符"}]')
    vs = review.review_items(items, "必须M5", Settings())
    assert vs[0].ok is True and vs[1].ok is False and "不符" in vs[1].reason


def _chunk_size(msgs):
    import re as _re
    return len(_re.findall(r"^\d+\. ", msgs[1]["content"], _re.M))


def test_review_items_chunks_large_batches(monkeypatch):
    # 大批量按 REVIEW_BATCH(=5) 分批调用, 而不是一次塞给模型(避免推理模型 content 为空)
    items = [Item(item_id=str(i), title="M5", url="u", price=1) for i in range(12)]
    sizes = []

    def fake(msgs, st):
        n = _chunk_size(msgs)
        sizes.append(n)
        return "[" + ",".join(f'{{"i":{k},"ok":true}}' for k in range(n)) + "]"

    monkeypatch.setattr(review, "_call_llm", fake)
    vs = review.review_items(items, "必须M5", Settings())
    assert len(vs) == 12 and all(v.ok for v in vs)
    assert sizes == [5, 5, 2]                               # REVIEW_BATCH=5


def test_review_items_one_chunk_failure_isolated(monkeypatch):
    # 某一批失败只放行那一批, 其余批次正常裁决
    items = [Item(item_id=str(i), title="x", url="u", price=1) for i in range(7)]

    def fake(msgs, st):
        n = _chunk_size(msgs)
        if n <= 2:                                          # 第二批(2 条)炸
            raise RuntimeError("boom")
        return "[" + ",".join(f'{{"i":{k},"ok":false}}' for k in range(n)) + "]"

    monkeypatch.setattr(review, "_call_llm", fake)
    vs = review.review_items(items, "req", Settings())
    assert len(vs) == 7
    assert all(v.ok is False for v in vs[:5])               # 第一批正常裁决
    assert all(v.reason == review.REVIEW_NOT_RUN for v in vs[5:])  # 第二批放行 + 标记


def test_build_messages_shape():
    items = [Item(item_id="a", title="标题X", url="u", price=1, condition="99新", location="上海")]
    msgs = _build_messages(items, "要 M5", Settings())
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert "要 M5" in msgs[1]["content"] and "标题X" in msgs[1]["content"]
    assert msgs[0]["content"] == Settings().review_system_prompt   # 系统提示词来自配置


def test_review_items_disabled_passes_all():
    items = [Item(item_id="a", title="x", url="u", price=1)]
    st = Settings(review_enabled=False)
    assert review.review_items(items, "必须M5", st) == [ReviewVerdict(ok=True)]


def test_review_uses_configured_params(monkeypatch):
    captured = {}
    items = [Item(item_id="a", title="M5", url="u", price=1)]
    st = Settings(review_temperature=0.7, review_max_tokens=512,
                  review_system_prompt="自定义提示词")

    def fake_post(url, json, headers, timeout):
        captured.update(json)

        class R:
            status_code = 200
            def raise_for_status(self): ...
            def json(self): return {"choices": [{"message": {"content": '{"verdicts":[{"i":0,"ok":true}]}'}}]}
        return R()

    monkeypatch.setattr(review.httpx, "post", fake_post)
    review.review_items(items, "必须M5", st)
    assert captured["temperature"] == 0.7 and captured["max_tokens"] == 512
    assert captured["messages"][0]["content"] == "自定义提示词"
    assert captured["response_format"]["type"] == "json_schema"   # 默认带结构化输出


def test_coerce_array_handles_shapes():
    assert review._coerce_array('{"verdicts":[{"i":0,"ok":true}]}')[0]["ok"] is True  # 结构化
    assert review._coerce_array('[{"i":0,"ok":false}]')[0]["ok"] is False             # 裸数组
    assert review._coerce_array('好的:\n```json\n[{"i":0,"ok":true}]\n```')[0]["i"] == 0  # 夹文本


def test_call_llm_falls_back_when_response_format_unsupported(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)

        class R:
            def raise_for_status(self):
                if self.status_code >= 400:
                    raise AssertionError("不该对 400 抛, 应已退回普通模式")
            def json(self): return {"choices": [{"message": {"content": '[{"i":0,"ok":true}]'}}]}
        r = R()
        # 第一次(带 response_format)→ 400; 第二次(普通)→ 200
        r.status_code = 400 if "response_format" in json else 200
        return r

    monkeypatch.setattr(review.httpx, "post", fake_post)
    vs = review.review_items([Item(item_id="a", title="x", url="u", price=1)], "req", Settings())
    assert vs[0].ok is True
    assert len(calls) == 2                       # 先结构化(400) → 退回普通
    assert "response_format" in calls[0] and "response_format" not in calls[1]


# --- test_review(控制台「测试 LLM」按钮) ---
def test_test_review_ok(monkeypatch):
    monkeypatch.setattr(review, "_call_llm", lambda msgs, st: '[{"i":0,"ok":true,"reason":"符合"}]')
    r = review.test_review(Settings(review_model="m-x"))
    assert r["ok"] is True and r["model"] == "m-x"


def test_test_review_unparsable_reply_is_not_ok(monkeypatch):
    # 连上了但返回不是 JSON 数组 → 诚实判 ok=False(否则会「测试通过但实际全跳过」)
    monkeypatch.setattr(review, "_call_llm", lambda msgs, st: "我觉得这个还行")
    r = review.test_review(Settings())
    assert r["ok"] is False and "JSON" in r["error"]


def test_test_review_empty_content_hints_reasoning_model(monkeypatch):
    # 推理模型典型症状: content 为空 → 给出可操作提示
    monkeypatch.setattr(review, "_call_llm", lambda msgs, st: "   ")
    r = review.test_review(Settings())
    assert r["ok"] is False and "content 为空" in r["error"]


def test_test_review_uses_passed_requirement(monkeypatch):
    seen = {}
    def cap(msgs, st):
        seen["user"] = msgs[1]["content"]
        return '[{"i":0,"ok":true}]'
    monkeypatch.setattr(review, "_call_llm", cap)
    review.test_review(Settings(), requirement="必须_独特要求_XYZ")
    assert "必须_独特要求_XYZ" in seen["user"]


def test_test_review_http_401_friendly(monkeypatch):
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(401, request=req)

    def boom(msgs, st):
        raise httpx.HTTPStatusError("Unauthorized", request=req, response=resp)

    monkeypatch.setattr(review, "_call_llm", boom)
    r = review.test_review(Settings())
    assert r["ok"] is False and "401" in r["error"]


def test_test_review_connect_error_friendly(monkeypatch):
    def boom(msgs, st):
        raise httpx.ConnectError("name resolution failed")

    monkeypatch.setattr(review, "_call_llm", boom)
    r = review.test_review(Settings())
    assert r["ok"] is False and "连不上" in r["error"]
