import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from xianyu_crawler.web import runtime, app as app_mod
    runtime.set_db_url(f"sqlite:///{tmp_path}/t.db")
    return TestClient(app_mod.app)


def test_watch_crud_api(client):
    r = client.post("/api/watches", json={"name": "w1", "keywords": ["iPhone"], "price_max": 5000})
    assert r.status_code == 200
    wid = r.json()["id"]
    assert client.get("/api/watches").json()[0]["name"] == "w1"
    r2 = client.put(f"/api/watches/{wid}",
                    json={"name": "w1", "keywords": ["iPhone", "苹果"], "price_max": 4000, "enabled": False})
    assert r2.json()["price_max"] == 4000 and r2.json()["enabled"] is False
    assert client.delete(f"/api/watches/{wid}").json()["ok"] is True
    assert client.get("/api/watches").json() == []


def test_config_api(client):
    assert "notify_to" in client.get("/api/config").json()   # 默认空, 走本地配置
    r = client.put("/api/config", json={"schedule_minutes": 60, "paused": True})
    assert r.json()["schedule_minutes"] == 60 and r.json()["paused"] is True


def test_recommendations_api(client):
    from xianyu_crawler.web import runtime
    from xianyu_crawler.storage import repo
    from xianyu_crawler.models import Item
    s = runtime.session()
    repo.create_recommendation(
        s, Item(item_id="x1", title="t", url="u", price=1000, location="上海", free_shipping=True), "w1")
    recs = client.get("/api/recommendations").json()
    assert len(recs) == 1 and recs[0]["item_id"] == "x1"
    assert recs[0]["location"] == "上海" and recs[0]["free_shipping"] is True
    assert client.post("/api/recommendations/x1/reject").json()["ok"] is True
    assert client.get("/api/recommendations").json() == []


def test_status_and_favorites_empty(client):
    assert client.get("/api/status").json()["running"] is False
    assert client.get("/api/favorites").json() == []
    assert client.get("/api/events").json() == []


def test_test_review_endpoint_ok(client, monkeypatch):
    from xianyu_crawler import review
    monkeypatch.setattr(review, "_call_llm", lambda msgs, st: '[{"i":0,"ok":true,"reason":"符合"}]')
    body = client.post("/api/test-review").json()
    assert body["ok"] is True and body["parsed"] is True


def test_test_review_endpoint_reports_error(client, monkeypatch):
    import httpx
    from xianyu_crawler import review
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(401, request=req)

    def boom(msgs, st):
        raise httpx.HTTPStatusError("Unauthorized", request=req, response=resp)

    monkeypatch.setattr(review, "_call_llm", boom)
    body = client.post("/api/test-review").json()
    assert body["ok"] is False and "401" in body["error"]
