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
            def raise_for_status(self): ...
            def json(self): return {"choices": [{"message": {"content": '[{"i":0,"ok":true}]'}}]}
        return R()

    monkeypatch.setattr(review.httpx, "post", fake_post)
    review.review_items(items, "必须M5", st)
    assert captured["temperature"] == 0.7 and captured["max_tokens"] == 512
    assert captured["messages"][0]["content"] == "自定义提示词"
