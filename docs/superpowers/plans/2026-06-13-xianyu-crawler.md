# 闲鱼自动化 Crawler 实现计划 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended for this project, because browser tasks need live iteration against a logged-in session) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 定时登录闲鱼，按条件搜索→自动"想要"收藏，并监控收藏列表降价，邮件/CSV 通知。

**Architecture:** 本地 macOS，Python + Playwright(sync)，登录态存 `storage_state.json`，SQLite 存价格历史。一次 run 串起 R1(选品收藏) + R2(降价监控)。纯逻辑模块 TDD；浏览器模块用"抓真实响应→存 fixture→对 fixture 测解析"的发现式流程。

**Tech Stack:** Python 3.12, Playwright, SQLAlchemy 2.x, Pydantic v2 / pydantic-settings, PyYAML, pytest, smtplib(stdlib), launchd。

参考 spec：`docs/superpowers/specs/2026-06-13-xianyu-crawler-design.md`

---

## 文件结构 (File Structure)

```
xianyu-crawler/
  pyproject.toml                        # 依赖与打包
  .gitignore                            # 忽略 data/ 与 fixtures 的敏感样本
  .env.example                          # 非密钥默认值样例
  config/watchlist.yaml                 # 搜索条件
  src/xianyu_crawler/
    __init__.py
    models.py            # 领域类型: Item, DropResult (Pydantic, 无 IO)
    config.py            # Settings(pydantic-settings) + load_watchlist()
    storage/
      __init__.py
      db.py              # engine/session 工厂
      orm.py             # SQLAlchemy ORM: ItemRow, PriceHistory, Event
      repo.py            # 仓储函数 (纯 DB, 可测)
    price_monitor.py     # detect_drop() 纯逻辑
    filter.py            # matches() 纯逻辑
    notifier.py          # format_email/append_csv/send_email
    anti_detect.py       # 延时/UA 池/拟人滚动/风控识别
    session.py           # Playwright context + storage_state + 登录校验
    search.py            # 搜索 + 拦截 JSON 解析为 Item
    favorite.py          # 点"想要"
    favorites_list.py    # 读"我想要的"列表为 Item
    pipeline.py          # 编排一次 run (R1+R2)
    cli.py               # login/run/search/monitor 入口
  scripts/
    discover_search.py   # 一次性: 抓搜索 mtop JSON 存 fixture
    discover_favorites.py# 一次性: 抓收藏列表 JSON 存 fixture
  deploy/com.xianyu.crawler.plist
  tests/
    fixtures/            # 录制的 JSON 样本 (脱敏)
    test_*.py
  data/                  # gitignore: storage_state.json, xianyu.db, events.csv, *.log, screenshots/
```

**类型契约（跨任务保持一致）**

```python
# models.py
class Item(BaseModel):
    item_id: str
    title: str
    url: str
    price: float
    seller_id: str | None = None
    seller_nick: str | None = None
    location: str | None = None
    condition: str | None = None        # 成色文本, 如 "99新"
    free_shipping: bool | None = None
    raw: dict | None = None             # 原始 JSON, 调试用

class DropResult(BaseModel):
    item_id: str
    prev_price: float
    curr_price: float
    drop_abs: float
    drop_pct: float
```

---

## Task 0: 项目脚手架

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/xianyu_crawler/__init__.py`, `config/watchlist.yaml`, `tests/__init__.py`

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[project]
name = "xianyu-crawler"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.45",
    "sqlalchemy>=2.0",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-mock>=3"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[project.scripts]
xianyu = "xianyu_crawler.cli:main"
```

- [ ] **Step 2: 写 `.gitignore`**

```gitignore
data/
*.pyc
__pycache__/
.env
.venv/
tests/fixtures/*.real.json
```

- [ ] **Step 3: 写 `.env.example`**

```dotenv
# 非密钥默认值; 密钥(SMTP/收件人)走系统环境变量, 见 README
XIANYU_DATA_DIR=./data
XIANYU_MIN_DROP_PCT=5.0
XIANYU_MIN_DROP_ABS=50.0
XIANYU_HEADLESS=false
XIANYU_ACTION_DELAY_MIN=3.0
XIANYU_ACTION_DELAY_MAX=8.0
```

- [ ] **Step 4: 写 `config/watchlist.yaml` 样例**

```yaml
watches:
  - name: "iPhone15Pro"
    keywords: ["iPhone 15 Pro", "苹果15Pro"]
    price_min: 3000
    price_max: 5000
    city: "上海"
    condition: ["99新", "几乎全新", "全新"]
    free_shipping: true
    seller_min_credit: null
    want_max_per_run: 5
    enabled: true
```

- [ ] **Step 5: 建空包文件**

`src/xianyu_crawler/__init__.py`、`src/xianyu_crawler/storage/__init__.py`、`tests/__init__.py` 写空文件。

- [ ] **Step 6: 安装并冒烟**

Run: `pip install -e ".[dev]" && python -c "import xianyu_crawler; print('ok')"`
Expected: 打印 `ok`

- [ ] **Step 7: Commit** — `git add -A && git commit -m "chore: scaffold xianyu-crawler project"`

---

## Task 1: 领域类型 models.py

**Files:** Create `src/xianyu_crawler/models.py`; Test `tests/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_models.py
from xianyu_crawler.models import Item, DropResult

def test_item_minimal():
    it = Item(item_id="1", title="t", url="u", price=100.0)
    assert it.price == 100.0 and it.seller_id is None

def test_drop_result_fields():
    d = DropResult(item_id="1", prev_price=100, curr_price=80, drop_abs=20, drop_pct=20.0)
    assert d.drop_abs == 20 and d.drop_pct == 20.0
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_models.py -v` → FAIL (ImportError)
- [ ] **Step 3: 实现 `models.py`**（用上文「类型契约」中的 `Item`/`DropResult` 完整定义，文件头 `from pydantic import BaseModel`）
- [ ] **Step 4: 跑测试确认通过** — `pytest tests/test_models.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat: domain models Item/DropResult"`

---

## Task 2: 降价逻辑 price_monitor.py (核心纯逻辑, TDD)

**Files:** Create `src/xianyu_crawler/price_monitor.py`; Test `tests/test_price_monitor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_price_monitor.py
from xianyu_crawler.price_monitor import detect_drop

def test_no_drop_when_price_up():
    assert detect_drop("1", prev=100, curr=120, min_pct=5, min_abs=50) is None

def test_no_drop_when_equal():
    assert detect_drop("1", prev=100, curr=100, min_pct=5, min_abs=50) is None

def test_drop_by_pct_only():
    d = detect_drop("1", prev=100, curr=94, min_pct=5, min_abs=50)  # 6% / ¥6
    assert d is not None and round(d.drop_pct, 1) == 6.0 and d.drop_abs == 6

def test_drop_by_abs_only():
    d = detect_drop("1", prev=1000, curr=940, min_pct=10, min_abs=50)  # 6% / ¥60
    assert d is not None and d.drop_abs == 60

def test_below_both_thresholds_is_none():
    assert detect_drop("1", prev=1000, curr=970, min_pct=5, min_abs=50) is None  # 3% / ¥30

def test_prev_zero_guard():
    assert detect_drop("1", prev=0, curr=0, min_pct=5, min_abs=50) is None
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_price_monitor.py -v` → FAIL
- [ ] **Step 3: 实现**

```python
# src/xianyu_crawler/price_monitor.py
from .models import DropResult

def detect_drop(item_id: str, prev: float, curr: float,
                min_pct: float, min_abs: float) -> DropResult | None:
    if prev <= 0:
        return None
    drop_abs = prev - curr
    if drop_abs <= 0:
        return None
    drop_pct = drop_abs / prev * 100
    if drop_pct >= min_pct or drop_abs >= min_abs:
        return DropResult(item_id=item_id, prev_price=prev, curr_price=curr,
                          drop_abs=drop_abs, drop_pct=drop_pct)
    return None
```

- [ ] **Step 4: 跑测试确认通过** — `pytest tests/test_price_monitor.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat: price drop detection logic"`

---

## Task 3: 过滤逻辑 filter.py (纯逻辑, TDD)

**Files:** Create `src/xianyu_crawler/filter.py`; Test `tests/test_filter.py`
依赖 Task 4 的 `Watch` 类型 → **先做 Task 4 的 `Watch` 定义再回来**，或在本任务内用最小 `Watch`。为避免循环，`Watch` 定义放 `config.py`（Task 4），此任务 import 它。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_filter.py
from xianyu_crawler.models import Item
from xianyu_crawler.config import Watch
from xianyu_crawler.filter import matches

def W(**kw):
    base = dict(name="w", keywords=["x"], price_min=None, price_max=None,
                city=None, condition=None, free_shipping=None,
                seller_min_credit=None, want_max_per_run=5, enabled=True)
    base.update(kw); return Watch(**base)

def I(**kw):
    base = dict(item_id="1", title="t", url="u", price=1000.0,
                location="上海市", condition="99新", free_shipping=True)
    base.update(kw); return Item(**base)

def test_price_within_range():
    assert matches(I(price=1000), W(price_min=500, price_max=2000)) is True
def test_price_below_min():
    assert matches(I(price=400), W(price_min=500)) is False
def test_price_above_max():
    assert matches(I(price=3000), W(price_max=2000)) is False
def test_city_substring():
    assert matches(I(location="上海市浦东"), W(city="上海")) is True
    assert matches(I(location="北京市"), W(city="上海")) is False
def test_condition_in_list():
    assert matches(I(condition="95新"), W(condition=["99新","95新"])) is True
    assert matches(I(condition="8成新"), W(condition=["99新"])) is False
def test_free_shipping_required():
    assert matches(I(free_shipping=False), W(free_shipping=True)) is False
def test_none_criteria_ignored():
    assert matches(I(location=None, condition=None), W()) is True
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_filter.py -v` → FAIL
- [ ] **Step 3: 实现**

```python
# src/xianyu_crawler/filter.py
from .models import Item
from .config import Watch

def matches(item: Item, watch: Watch) -> bool:
    if watch.price_min is not None and item.price < watch.price_min:
        return False
    if watch.price_max is not None and item.price > watch.price_max:
        return False
    if watch.city and (not item.location or watch.city not in item.location):
        return False
    if watch.condition and (item.condition not in watch.condition):
        return False
    if watch.free_shipping is not None and item.free_shipping != watch.free_shipping:
        return False
    # seller_min_credit: 信用分需在 Item.raw 中, v1 暂以存在即通过; 留待解析补字段
    return True
```

- [ ] **Step 4: 跑测试确认通过**（需 Task 4 的 `Watch` 已存在）— `pytest tests/test_filter.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat: rule-based item filter"`

---

## Task 4: 配置 config.py (Watch + Settings, TDD)

**Files:** Create `src/xianyu_crawler/config.py`; Test `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
from xianyu_crawler.config import Watch, load_watchlist, Settings

def test_watch_defaults():
    w = Watch(name="w", keywords=["a"])
    assert w.want_max_per_run == 5 and w.enabled is True and w.price_min is None

def test_load_watchlist(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text(
        "watches:\n"
        "  - name: t\n"
        "    keywords: ['iPhone']\n"
        "    price_max: 5000\n", encoding="utf-8")
    ws = load_watchlist(p)
    assert len(ws) == 1 and ws[0].name == "t" and ws[0].price_max == 5000

def test_settings_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("XIANYU_MIN_DROP_PCT", "8")
    s = Settings()
    assert s.min_drop_pct == 8.0
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_config.py -v` → FAIL
- [ ] **Step 3: 实现**

```python
# src/xianyu_crawler/config.py
from pathlib import Path
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class Watch(BaseModel):
    name: str
    keywords: list[str]
    price_min: float | None = None
    price_max: float | None = None
    city: str | None = None
    condition: list[str] | None = None
    free_shipping: bool | None = None
    seller_min_credit: int | None = None
    want_max_per_run: int = 5
    enabled: bool = True

def load_watchlist(path: str | Path) -> list[Watch]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [Watch(**w) for w in (data or {}).get("watches", [])]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XIANYU_", env_file=".env", extra="ignore")
    data_dir: Path = Path("./data")
    min_drop_pct: float = 5.0
    min_drop_abs: float = 50.0
    headless: bool = False
    action_delay_min: float = 3.0
    action_delay_max: float = 8.0
    # 密钥(系统环境变量): XIANYU_SMTP_HOST/PORT/USER/PASS, XIANYU_NOTIFY_TO
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_pass: str | None = None
    notify_to: str | None = None
```

- [ ] **Step 4: 跑测试确认通过** — `pytest tests/test_config.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat: config Watch + Settings"`

---

## Task 5: 存储层 storage/ (ORM + repo, TDD with in-memory SQLite)

**Files:** Create `storage/db.py`, `storage/orm.py`, `storage/repo.py`; Test `tests/test_repo.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_repo.py
from xianyu_crawler.storage.db import make_session
from xianyu_crawler.storage import repo
from xianyu_crawler.models import Item

def session():
    return make_session("sqlite:///:memory:", create=True)

def test_upsert_and_get_prev_price():
    s = session()
    it = Item(item_id="1", title="t", url="u", price=100.0)
    assert repo.get_latest_price(s, "1") is None
    repo.upsert_item_with_price(s, it, source="favorite")
    assert repo.get_latest_price(s, "1") == 100.0
    it2 = it.model_copy(update={"price": 80.0})
    prev = repo.upsert_item_with_price(s, it2, source="favorite")
    assert prev == 100.0 and repo.get_latest_price(s, "1") == 80.0

def test_mark_want_added():
    s = session()
    repo.upsert_item_with_price(s, Item(item_id="2", title="t", url="u", price=5), source="search")
    repo.mark_want_added(s, "2")
    assert repo.is_want_added(s, "2") is True

def test_record_and_fetch_unnotified_events():
    s = session()
    repo.upsert_item_with_price(s, Item(item_id="3", title="t", url="u", price=5), source="favorite")
    repo.add_event(s, "3", "price_drop", {"drop_abs": 20})
    evs = repo.unnotified_events(s)
    assert len(evs) == 1 and evs[0].type == "price_drop"
    repo.mark_notified(s, [evs[0].id])
    assert repo.unnotified_events(s) == []
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_repo.py -v` → FAIL
- [ ] **Step 3: 实现 `storage/db.py`**

```python
# src/xianyu_crawler/storage/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .orm import Base

def make_session(url: str, create: bool = False) -> Session:
    engine = create_engine(url, future=True)
    if create:
        Base.metadata.create_all(engine)
    return Session(engine, future=True)
```

- [ ] **Step 4: 实现 `storage/orm.py`**

```python
# src/xianyu_crawler/storage/orm.py
from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class ItemRow(Base):
    __tablename__ = "items"
    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    seller_id: Mapped[str | None] = mapped_column(String, nullable=True)
    seller_nick: Mapped[str | None] = mapped_column(String, nullable=True)
    first_price: Mapped[float] = mapped_column(Float)
    latest_price: Mapped[float] = mapped_column(Float)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    source: Mapped[str] = mapped_column(String)            # search|favorite
    want_added: Mapped[bool] = mapped_column(Boolean, default=False)
    want_added_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    watch_name: Mapped[str | None] = mapped_column(String, nullable=True)

class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.item_id"))
    price: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.item_id"))
    type: Mapped[str] = mapped_column(String)              # price_drop|favorited|new_match
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 5: 实现 `storage/repo.py`**

```python
# src/xianyu_crawler/storage/repo.py
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Item
from .orm import ItemRow, PriceHistory, Event

def _now():
    return datetime.now(timezone.utc)

def get_latest_price(s: Session, item_id: str) -> float | None:
    row = s.get(ItemRow, item_id)
    return row.latest_price if row else None

def upsert_item_with_price(s: Session, item: Item, source: str,
                           watch_name: str | None = None) -> float | None:
    """写入/更新商品并追加一条价格观测; 返回更新前的 latest_price(无则 None)。"""
    row = s.get(ItemRow, item.item_id)
    prev = row.latest_price if row else None
    if row is None:
        row = ItemRow(item_id=item.item_id, title=item.title, url=item.url,
                      seller_id=item.seller_id, seller_nick=item.seller_nick,
                      first_price=item.price, latest_price=item.price,
                      source=source, watch_name=watch_name)
        s.add(row)
    else:
        row.latest_price = item.price
        row.last_seen_at = _now()
    s.add(PriceHistory(item_id=item.item_id, price=item.price))
    s.commit()
    return prev

def mark_want_added(s: Session, item_id: str) -> None:
    row = s.get(ItemRow, item_id)
    row.want_added = True
    row.want_added_at = _now()
    s.commit()

def is_want_added(s: Session, item_id: str) -> bool:
    row = s.get(ItemRow, item_id)
    return bool(row and row.want_added)

def add_event(s: Session, item_id: str, type_: str, payload: dict) -> None:
    s.add(Event(item_id=item_id, type=type_, payload=json.dumps(payload, ensure_ascii=False)))
    s.commit()

def unnotified_events(s: Session) -> list[Event]:
    return list(s.scalars(select(Event).where(Event.notified == False)))  # noqa: E712

def mark_notified(s: Session, ids: list[int]) -> None:
    for e in s.scalars(select(Event).where(Event.id.in_(ids))):
        e.notified = True
    s.commit()
```

- [ ] **Step 6: 跑测试确认通过** — `pytest tests/test_repo.py -v` → PASS
- [ ] **Step 7: Commit** — `git commit -am "feat: storage ORM + repository"`

---

## Task 6: 通知 notifier.py (email + csv, TDD with mock)

**Files:** Create `src/xianyu_crawler/notifier.py`; Test `tests/test_notifier.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_notifier.py
from xianyu_crawler.notifier import format_email, append_csv

def test_format_email_groups_by_type():
    events = [
        {"type": "price_drop", "title": "iPhone", "url": "u1",
         "prev_price": 100, "curr_price": 80, "drop_abs": 20, "drop_pct": 20.0},
        {"type": "favorited", "title": "iPad", "url": "u2"},
    ]
    subject, body = format_email(events)
    assert "降价" in subject
    assert "iPhone" in body and "80" in body and "iPad" in body

def test_append_csv(tmp_path):
    p = tmp_path / "events.csv"
    append_csv(p, [{"type": "price_drop", "title": "x", "url": "u", "curr_price": 1}])
    text = p.read_text(encoding="utf-8")
    assert "price_drop" in text and "x" in text
    append_csv(p, [{"type": "favorited", "title": "y", "url": "u2"}])
    assert p.read_text(encoding="utf-8").count("\n") >= 3  # header + 2 rows
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_notifier.py -v` → FAIL
- [ ] **Step 3: 实现**

```python
# src/xianyu_crawler/notifier.py
import csv, smtplib
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path

CSV_FIELDS = ["type", "title", "url", "prev_price", "curr_price", "drop_abs", "drop_pct"]

def format_email(events: list[dict]) -> tuple[str, str]:
    drops = [e for e in events if e["type"] == "price_drop"]
    favs = [e for e in events if e["type"] == "favorited"]
    subject = f"闲鱼: {len(drops)} 降价 / {len(favs)} 新收藏"
    lines = []
    if drops:
        lines.append("== 降价 ==")
        for e in drops:
            lines.append(f"- {e['title']}: ¥{e['prev_price']} → ¥{e['curr_price']} "
                         f"(降 ¥{e['drop_abs']:.0f}, {e['drop_pct']:.1f}%)  {e['url']}")
    if favs:
        lines.append("== 新收藏 ==")
        for e in favs:
            lines.append(f"- {e['title']}  {e['url']}")
    return subject, "\n".join(lines)

def append_csv(path: str | Path, events: list[dict]) -> None:
    path = Path(path)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for e in events:
            w.writerow(e)

def send_email(settings, subject: str, body: str) -> None:
    if not (settings.smtp_host and settings.smtp_user and settings.notify_to):
        return  # 未配置则跳过(降级为仅 CSV/日志)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = settings.smtp_user
    msg["To"] = settings.notify_to
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as srv:
        srv.login(settings.smtp_user, settings.smtp_pass)
        srv.sendmail(settings.smtp_user, [settings.notify_to], msg.as_string())
```

- [ ] **Step 4: 跑测试确认通过** — `pytest tests/test_notifier.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat: email + csv notifier"`

---

## Task 7: 反爬助手 anti_detect.py (可测部分 TDD)

**Files:** Create `src/xianyu_crawler/anti_detect.py`; Test `tests/test_anti_detect.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_anti_detect.py
from xianyu_crawler.anti_detect import pick_profile, is_risk_control, PROFILES

def test_pick_profile_returns_member():
    p = pick_profile(seed=3)
    assert p in PROFILES and "user_agent" in p and "viewport" in p

def test_risk_control_detection():
    assert is_risk_control("<html>滑块验证 请拖动</html>") is True
    assert is_risk_control("<html>baxia-dialog punish</html>") is True
    assert is_risk_control("<html>正常商品列表</html>") is False
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_anti_detect.py -v` → FAIL
- [ ] **Step 3: 实现**

```python
# src/xianyu_crawler/anti_detect.py
import random, time

PROFILES = [
    {"user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36", "viewport": {"width": 1440, "height": 900}},
    {"user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.4 Safari/605.1.15", "viewport": {"width": 1280, "height": 800}},
    {"user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36", "viewport": {"width": 1536, "height": 864}},
]
_RISK_MARKERS = ["滑块", "拖动", "baxia", "punish", "验证码", "_____tmd_____", "captcha"]

def pick_profile(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    return rng.choice(PROFILES)

def human_delay(lo: float = 3.0, hi: float = 8.0) -> None:
    time.sleep(random.uniform(lo, hi))

def is_risk_control(html: str) -> bool:
    low = html.lower()
    return any(m.lower() in low for m in _RISK_MARKERS)

def human_scroll(page, steps: int = 4) -> None:
    for _ in range(steps):
        page.mouse.wheel(0, random.randint(400, 900))
        time.sleep(random.uniform(0.6, 1.6))
```

- [ ] **Step 4: 跑测试确认通过** — `pytest tests/test_anti_detect.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat: anti-detect helpers"`

---

## Task 8: 登录脚本 + session.py（**发现式/live，需真实账号**）

**Files:** Create `scripts/login.py`, `src/xianyu_crawler/session.py`

> 浏览器模块无法盲写精确选择器；本任务产出可运行脚手架 + 验收标准，细节对着真实页面收敛。

- [ ] **Step 1: 写 `scripts/login.py`（首次扫码登录）**

```python
# scripts/login.py  —— 有头启动, 手动扫码, 保存 storage_state
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE = Path("data/storage_state.json")
LOGIN_URL = "https://www.goofish.com/"   # 闲鱼网页版

def main():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(LOGIN_URL)
        print(">> 请在浏览器中完成扫码登录, 登录成功后回到终端按回车...")
        input()
        ctx.storage_state(path=str(STATE))
        print(f">> 已保存登录态到 {STATE}")
        browser.close()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑登录脚本（人工）** — `python scripts/login.py` → 扫码 → 确认 `data/storage_state.json` 生成
- [ ] **Step 3: 实现 `session.py`（载入 + 登录校验）**

```python
# src/xianyu_crawler/session.py
from pathlib import Path
from contextlib import contextmanager
from playwright.sync_api import sync_playwright
from .anti_detect import pick_profile

HOME = "https://www.goofish.com/"

@contextmanager
def browser_session(settings, state_path: str = "data/storage_state.json"):
    profile = pick_profile()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        ctx = browser.new_context(
            storage_state=state_path if Path(state_path).exists() else None,
            user_agent=profile["user_agent"], viewport=profile["viewport"],
            locale="zh-CN",
        )
        try:
            yield ctx
        finally:
            ctx.storage_state(path=state_path)  # 刷新登录态
            browser.close()

def is_logged_in(page) -> bool:
    """校验登录: 访问首页, 检查是否存在「我的」入口/未跳登录。
    实现细节对着真实 DOM 收敛 —— 验收: 登录态有效返回 True, 删除 state 后返回 False。"""
    page.goto(HOME)
    page.wait_for_timeout(2000)
    # TODO(live): 用真实选择器, 如 page.get_by_text("我的") 是否可见; 或检查未重定向到登录页
    return "login" not in page.url.lower()
```

- [ ] **Step 4: 验收**：写 `scripts/check_login.py` 临时跑：有 `storage_state.json` 时 `is_logged_in` 为 True；改名后为 False。
- [ ] **Step 5: Commit** — `git add scripts/login.py src/xianyu_crawler/session.py && git commit -m "feat: login script + session loader"`

---

## Task 9: 搜索解析 search.py（**发现式: 先抓 JSON → fixture → TDD 解析**）

**Files:** Create `scripts/discover_search.py`, `src/xianyu_crawler/search.py`; Test `tests/test_search_parse.py`

- [ ] **Step 1: 写 `scripts/discover_search.py`（抓真实搜索响应）**

```python
# scripts/discover_search.py —— 登录态下搜索一个关键词, dump 命中的 mtop JSON
import json, sys
from pathlib import Path
from xianyu_crawler.config import Settings
from xianyu_crawler.session import browser_session

OUT = Path("tests/fixtures/search.real.json")  # gitignore; 脱敏后另存 search.sample.json

def main(keyword: str):
    captured = []
    with browser_session(Settings()) as ctx:
        page = ctx.new_page()
        page.on("response", lambda r: captured.append(r) if "mtop" in r.url and "search" in r.url.lower() else None)
        page.goto(f"https://www.goofish.com/search?q={keyword}")
        page.wait_for_timeout(6000)
        for r in captured:
            try:
                body = r.json()
                OUT.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
                print("saved", r.url)
                break
            except Exception:
                continue

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "iPhone")
```

- [ ] **Step 2: 跑 discover（人工）** — `python scripts/discover_search.py "iPhone 15"` → 得到 `search.real.json`
- [ ] **Step 3: 脱敏存样本** — 手动裁剪为 1-2 条商品，存 `tests/fixtures/search.sample.json`，确认含字段：商品 id、标题、价格、地区、卖家。**记录真实字段路径**（如 `data.resultList[].data.item.main.exContent.title`），据此写解析。
- [ ] **Step 4: 写失败测试（对样本 fixture）**

```python
# tests/test_search_parse.py
import json
from pathlib import Path
from xianyu_crawler.search import parse_search_json

def test_parse_sample():
    raw = json.loads(Path("tests/fixtures/search.sample.json").read_text(encoding="utf-8"))
    items = parse_search_json(raw)
    assert len(items) >= 1
    it = items[0]
    assert it.item_id and it.title and it.price > 0
```

- [ ] **Step 5: 跑测试确认失败** — `pytest tests/test_search_parse.py -v` → FAIL
- [ ] **Step 6: 实现 `search.py`**（`parse_search_json(raw) -> list[Item]`：按 Step 3 记录的真实字段路径取值，做健壮的 `.get` 链与价格转 float；并实现 `search(ctx, watch) -> list[Item]`：goto 搜索页 + `page.on("response")` 收集 + `human_scroll` + 调 `parse_search_json`）。**字段路径以 fixture 实测为准**。
- [ ] **Step 7: 跑测试确认通过** — `pytest tests/test_search_parse.py -v` → PASS
- [ ] **Step 8: Commit** — `git commit -am "feat: search + JSON parse (fixture-tested)"`

---

## Task 10: 收藏列表 favorites_list.py（**发现式, 同 Task 9 套路**）

**Files:** Create `scripts/discover_favorites.py`, `src/xianyu_crawler/favorites_list.py`; Test `tests/test_favorites_parse.py`

- [ ] **Step 1: 写 `scripts/discover_favorites.py`** — 打开"我想要的/我的收藏"页，拦截其 mtop 列表响应，dump 到 `tests/fixtures/favorites.real.json`。（页面 URL 与接口名 live 确认；收藏页通常在「我的」→「我想要的」。）
- [ ] **Step 2: 跑 discover（人工）** → 得到 `favorites.real.json`
- [ ] **Step 3: 脱敏存 `tests/fixtures/favorites.sample.json`，记录字段路径（商品 id / 当前价 / 标题 / 链接）**
- [ ] **Step 4: 写失败测试**

```python
# tests/test_favorites_parse.py
import json
from pathlib import Path
from xianyu_crawler.favorites_list import parse_favorites_json

def test_parse_favorites_sample():
    raw = json.loads(Path("tests/fixtures/favorites.sample.json").read_text(encoding="utf-8"))
    items = parse_favorites_json(raw)
    assert len(items) >= 1 and items[0].price > 0 and items[0].item_id
```

- [ ] **Step 5: 跑测试确认失败** → FAIL
- [ ] **Step 6: 实现 `favorites_list.py`**（`parse_favorites_json(raw) -> list[Item]` 按实测字段；`read_favorites(ctx) -> list[Item]`：goto 收藏页 + 拦截响应 + 翻页/滚动 + 解析）
- [ ] **Step 7: 跑测试确认通过** → PASS
- [ ] **Step 8: Commit** — `git commit -am "feat: favorites list reader (fixture-tested)"`

---

## Task 11: 点"想要" favorite.py（**发现式, UI 动作**）

**Files:** Create `src/xianyu_crawler/favorite.py`

- [ ] **Step 1: 实现 `add_want(ctx, item, settings) -> bool`**

```python
# src/xianyu_crawler/favorite.py  —— 打开商品详情, 点"想要", 人类延时
from .anti_detect import human_delay, is_risk_control

def add_want(ctx, item, settings) -> bool:
    """对单个商品点"想要"; 命中风控返回 False 并由上层中止。"""
    page = ctx.new_page()
    try:
        page.goto(item.url)
        page.wait_for_timeout(1500)
        if is_risk_control(page.content()):
            return False
        # TODO(live): 用真实选择器定位"想要"按钮, 如 page.get_by_role("button", name="想要")
        btn = page.get_by_text("想要", exact=False).first
        btn.click(timeout=5000)
        human_delay(settings.action_delay_min, settings.action_delay_max)
        return True
    except Exception:
        return False
    finally:
        page.close()
```

- [ ] **Step 2: 验收（人工 dry-run 对照）** — 选 1 个商品手动跑，确认其出现在"我想要的"列表（**注意：这会真实收藏，确认用测试商品**）。
- [ ] **Step 3: Commit** — `git commit -am "feat: add-to-want action"`

---

## Task 12: 编排 pipeline.py (TDD with mocks)

**Files:** Create `src/xianyu_crawler/pipeline.py`; Test `tests/test_pipeline.py`

- [ ] **Step 1: 写失败测试（mock 掉浏览器与解析，只测编排与降级逻辑）**

```python
# tests/test_pipeline.py
from xianyu_crawler.models import Item
from xianyu_crawler import pipeline
from xianyu_crawler.storage.db import make_session
from xianyu_crawler.config import Settings, Watch

def test_run_monitor_detects_drop(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    # 预置: 收藏商品上次价 100
    from xianyu_crawler.storage import repo
    repo.upsert_item_with_price(s, Item(item_id="1", title="t", url="u", price=100), source="favorite")
    # 本次抓到 80 → 应产生 price_drop 事件
    monkeypatch.setattr(pipeline, "_read_favorites", lambda ctx: [Item(item_id="1", title="t", url="u", price=80)])
    settings = Settings(min_drop_pct=5, min_drop_abs=50)
    n = pipeline.run_monitor(ctx=None, session=s, settings=settings)
    assert n == 1
    assert repo.unnotified_events(s)[0].type == "price_drop"

def test_run_search_respects_want_cap(monkeypatch):
    s = make_session("sqlite:///:memory:", create=True)
    items = [Item(item_id=str(i), title="t", url="u", price=1000) for i in range(10)]
    monkeypatch.setattr(pipeline, "_search", lambda ctx, w: items)
    monkeypatch.setattr(pipeline, "_add_want", lambda ctx, it, st: True)
    w = Watch(name="w", keywords=["x"], price_min=500, price_max=2000, want_max_per_run=3)
    added = pipeline.run_search(ctx=None, session=s, settings=Settings(), watches=[w])
    assert added == 3  # 上限生效
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_pipeline.py -v` → FAIL
- [ ] **Step 3: 实现 `pipeline.py`**

```python
# src/xianyu_crawler/pipeline.py
from .price_monitor import detect_drop
from .filter import matches
from .storage import repo
from . import search as _search_mod
from . import favorites_list as _fav_mod
from . import favorite as _favorite_mod

# 间接层便于测试 mock
def _search(ctx, watch): return _search_mod.search(ctx, watch)
def _read_favorites(ctx): return _fav_mod.read_favorites(ctx)
def _add_want(ctx, item, settings): return _favorite_mod.add_want(ctx, item, settings)

def run_search(ctx, session, settings, watches) -> int:
    added = 0
    for w in watches:
        if not w.enabled:
            continue
        cap = w.want_max_per_run
        n = 0
        for item in _search(ctx, w):
            if n >= cap:
                break
            if not matches(item, w):
                continue
            if repo.is_want_added(session, item.item_id):
                continue
            repo.upsert_item_with_price(session, item, source="search", watch_name=w.name)
            if _add_want(ctx, item, settings):
                repo.mark_want_added(session, item.item_id)
                repo.add_event(session, item.item_id, "favorited", {"title": item.title, "url": item.url})
                added += 1; n += 1
    return added

def run_monitor(ctx, session, settings) -> int:
    drops = 0
    for item in _read_favorites(ctx):
        prev = repo.upsert_item_with_price(session, item, source="favorite")
        if prev is None:
            continue
        d = detect_drop(item.item_id, prev=prev, curr=item.price,
                        min_pct=settings.min_drop_pct, min_abs=settings.min_drop_abs)
        if d:
            repo.add_event(session, item.item_id, "price_drop",
                           {"title": item.title, "url": item.url,
                            "prev_price": d.prev_price, "curr_price": d.curr_price,
                            "drop_abs": d.drop_abs, "drop_pct": d.drop_pct})
            drops += 1
    return drops
```

- [ ] **Step 4: 跑测试确认通过** — `pytest tests/test_pipeline.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat: run_search + run_monitor orchestration"`

---

## Task 13: CLI cli.py + 通知串联

**Files:** Create `src/xianyu_crawler/cli.py`; Test `tests/test_cli_smoke.py`

- [ ] **Step 1: 实现 `cli.py`**

```python
# src/xianyu_crawler/cli.py
import argparse, json
from pathlib import Path
from .config import Settings, load_watchlist
from .storage.db import make_session
from .storage import repo
from . import pipeline, notifier
from .session import browser_session

def _notify(session, settings):
    evs = repo.unnotified_events(session)
    if not evs:
        return
    views = [{"type": e.type, **json.loads(e.payload)} for e in evs]
    subject, body = notifier.format_email(views)
    notifier.append_csv(settings.data_dir / "events.csv", views)
    notifier.send_email(settings, subject, body)
    repo.mark_notified(session, [e.id for e in evs])

def cmd_run(settings, args):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    session = make_session(f"sqlite:///{settings.data_dir/'xianyu.db'}", create=True)
    watches = load_watchlist(args.watchlist)
    with browser_session(settings) as ctx:
        if not args.monitor_only:
            pipeline.run_search(ctx, session, settings, watches)
        pipeline.run_monitor(ctx, session, settings)
    _notify(session, settings)

def main():
    ap = argparse.ArgumentParser(prog="xianyu")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--watchlist", default="config/watchlist.yaml")
    r.add_argument("--monitor-only", action="store_true")
    r.add_argument("--dry-run", action="store_true", help="不点想要")
    args = ap.parse_args()
    settings = Settings()
    if args.cmd == "run":
        if args.dry_run:
            pipeline._add_want = lambda ctx, it, st: False  # 不真实收藏
        cmd_run(settings, args)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 冒烟测试** — `tests/test_cli_smoke.py`：`from xianyu_crawler import cli; assert callable(cli.main)`；`python -m xianyu_crawler.cli run --help` 返回 0。
- [ ] **Step 3: Commit** — `git commit -am "feat: CLI run + notify wiring"`

---

## Task 14: launchd 调度 + README

**Files:** Create `deploy/com.xianyu.crawler.plist`, 更新 `README.md`

- [ ] **Step 1: 写 launchd 模板**（多个抖动时刻；`<PYTHON>`/`<PROJECT>` 由用户替换）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.xianyu.crawler</string>
  <key>ProgramArguments</key>
  <array><string><PYTHON></string><string>-m</string><string>xianyu_crawler.cli</string><string>run</string></array>
  <key>WorkingDirectory</key><string><PROJECT></string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>17</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>41</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>5</integer></dict>
  </array>
  <key>StandardOutPath</key><string><PROJECT>/data/launchd.out.log</string>
  <key>StandardErrorPath</key><string><PROJECT>/data/launchd.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>XIANYU_SMTP_HOST</key><string></string>
    <key>XIANYU_SMTP_USER</key><string></string>
    <key>XIANYU_SMTP_PASS</key><string></string>
    <key>XIANYU_NOTIFY_TO</key><string></string>
  </dict>
</dict></plist>
```

- [ ] **Step 2: 写 README**：安装、`python scripts/login.py` 扫码、配置 `watchlist.yaml`、设置 SMTP 环境变量、`launchctl load deploy/com.xianyu.crawler.plist` 启用、`xianyu run --dry-run` 演练。
- [ ] **Step 3: 全量测试** — `pytest -v` → 全绿（live 解析任务依赖 fixture 存在）
- [ ] **Step 4: Commit** — `git commit -am "feat: launchd schedule + README"`

---

## Self-Review（spec 覆盖核对）

- R1 选品收藏 → Task 9(search) + 3(filter) + 11(favorite) + 12(run_search, 含 want 上限) ✓
- R2 降价监控 → Task 10(favorites_list) + 2(detect_drop) + 12(run_monitor) ✓
- 登录态持久化/校验 → Task 8 ✓
- 通知(邮件+CSV) → Task 6 + 13 ✓
- 存储/价格历史 → Task 5 ✓
- 反爬/风控/限速 → Task 7 + 11/8 中的 is_risk_control / human_delay ✓
- 降级(登录失效只读) → 在 Task 8 `is_logged_in` + Task 13 可加 monitor-only 分支（cli 已支持 `--monitor-only`）✓
- 调度 → Task 14 ✓
- 测试策略 → 纯逻辑全 TDD；解析用 fixture；live 部分有 discover 脚本 ✓

**已知诚实缺口**：Task 8/9/10/11 的精确选择器与 JSON 字段路径需对真实登录页收敛——计划已用 discover→fixture→TDD 流程把"盲区"转成可验证步骤，而非假装有精确代码。`seller_min_credit` 过滤在 v1 留作 Item.raw 补字段后启用（filter.py 已注明）。
