# AGENTS.md — 给 AI 协作者的工程指南

闲鱼控制台：本地运行的闲鱼选品(R1) + 降价监控(R2) Web 控制台。Python 3.12+ / Playwright(sync) / SQLAlchemy 2 / FastAPI + APScheduler / React + Vite。面向人类的说明见 [`README.md`](README.md)。

## 黄金规则(先读这条)

1. **内置(inline)Pyright 在本仓库是坏的**，会报不可能的错(`import time` 无法解析、`X | None` 操作符不支持、`Mapped[...]` 参数错误等)。**不要信任内置诊断**。权威检查只用：
   ```bash
   npx --yes pyright@latest --pythonpath /opt/miniconda3/bin/python src tests scripts
   /opt/miniconda3/bin/python -m pytest -q
   ```
2. **绝不把隐私/密钥写进仓库**：邮箱、SMTP 密码、LLM Token、内网接口地址、登录态——全部只能来自系统环境变量或 gitignored 的 `data/secret.env`。内网/私有模型代理等地址**只配在 `data/secret.env`**，代码里默认值必须是通用占位(`https://api.openai.com/v1`)。
3. **没有任何写死的业务配置**：可调项走 `config.py` 默认 ← `AppConfig`(DB) ← 设置页 三层。新增配置项要三层都过。
4. **不要主动 `git commit`**，除非用户明确要求。
5. **默认中文回答**；代码标识符/库名/报错保留英文。

## 验证命令(完成前必跑)

```bash
/opt/miniconda3/bin/python -m pytest -q
npx --yes pyright@latest --pythonpath /opt/miniconda3/bin/python src tests scripts
cd frontend && npm run build          # 产物 → ../src/xianyu_crawler/web/static
```

## 代码地图

```
src/xianyu_crawler/
  config.py        Settings(BaseSettings, env_prefix=XIANYU_, 读 .env + data/secret.env) + Watch + 默认提示词
  models.py        Item 等领域值对象
  search.py        搜索(关键词空格合并成一条 query, 单次 goto)
  filter.py        matches(): 价格/城市/成色/包邮 规则过滤
  favorite.py      点"收藏"(get_by_text("收藏", exact=True)) — 不是"想要"
  favorites_list.py 读收藏夹(含 reducePrice、死链信号)
  price_monitor.py / pipeline.py  降价检测 + 事件
  review.py        LLM 二次审核(OpenAI 兼容)
  liveness.py      详情页核活(死链判定)
  parsing.py       mtop JSON 字段解析(随版本变, 有 *.sample.json 回归)
  service.py       用例层: 桥接 DB ↔ 引擎; effective_settings() 做配置合并
  storage/
    orm.py         ItemRow / PriceHistory / Event / WatchRow / AppConfig
    repo.py        纯 DB 操作(可独立测试); _now() = naive UTC
    migrate.py     幂等 ALTER 列迁移(加字段必改这里)
    db.py          make_session(create=True 时自动跑迁移)
  web/
    app.py         FastAPI 路由(/api/*) + SPA 静态托管
    runner.py      浏览器 worker(全局 _LOCK 串行) + _notify(按事件类型过滤邮件)
    scheduler.py   APScheduler 两个周期: crawl + favorites
    login_runner.py 扫码登录状态机 + logout() + _account()(取 tracknick 昵称)
    dto.py         Pydantic DTO + row↔DTO 映射; _iso() 把 naive UTC 标成 +00:00
    runtime.py     进程内单例 session
frontend/src/
  App.jsx          全屏 grid 外壳(顶栏/侧栏/主区/右栏) + 5 皮肤 + 收起 + 轮询
  sections/        Recommendations / Drops(收藏) / Watches / Settings
  components/ui.jsx, api.js, util.js, styles.css(设计系统 + 5 皮肤令牌)
```

## 数据模型要点

- **`ItemRow`** 一行即一个商品：`rec_status`(new/approved/rejected)、`rec_ok`(LLM 裁决 True/False/None)、`rec_reason`、`favorited`/`favorited_at`、`dead`/`dead_reason`(粘性)、`muted_until`、`publish_time`、`price_changed_at`、`reduce_price`。
- **`Event.type`** 目前只有 `price_drop` 和 `favorited`(右栏事件流/邮件据此)。
- **`AppConfig`** 单行(id=1)：定时/阈值/SMTP/LLM/高级/`notify_on_{drop,favorite,login}` 邮件开关。
- 列表查询语义在 `repo.py`：`list_recommendations` 排除已收藏/静音、死链排末尾；`list_favorites` = favorited ∪ source==favorite。

## 时间处理(易错)

SQLite 读回的 datetime 一律 **naive**。统一约定：库里存 **naive UTC**(`repo._now()`)；出 API 时 `dto._iso()` 标成 `+00:00`，前端再转本地时区。**新加的时间字段出参一律走 `_iso()`**（`/api/events` 曾漏标导致差 8 小时）。

## 数据库迁移

改 `orm.py` 加列 → **必须**同步在 `migrate.py` 的 `COLUMNS` 追加 `(表, 列, "DDL")`。`make_session(create=True)` 启动即幂等执行，保住用户真实数据。

## 配置分层 / 密钥

`service.effective_settings(cfg)`：`Settings()` 基线被 `AppConfig` 覆盖；SMTP/LLM 接口地址/Token 用 `pick(db_val, env_val)`——控制台填了用控制台的，留空回退 `data/secret.env`/环境变量。DTO 里密码与 Token **只接收不回传**(只给 `*_set` 布尔)。

## 前端约定

- 5 皮肤靠 `#app[data-s=...]` 切 CSS 变量，收起靠 `#app[data-collapsed]`；皮肤/收起记忆在 `localStorage`。
- Vite 构建 **压缩 CSS**(去引号/空格)——grep 验证产物时用 `data-s=linear` 而非 `data-s='linear'`。
- 字体：Geist(拉丁/数字) + Geist Mono(数据) + Noto Sans SC(中文)，CDN 引入(`index.html`)。

## 部署

```bash
docker build -t xianyu-console:latest \
  --build-arg PYTHON_IMAGE=<your-mirror>/python:3.12-slim \
  --build-arg NODE_IMAGE=node:22-alpine .
docker compose up -d --no-build --force-recreate
```
前端在镜像 `fe` 阶段构建并 COPY 进 `web/static`；只挂载 `./data`，**改 `src`/前端必须重建镜像**(不是 restart)。

## 坑 / 禁忌

- **Playwright headless 必须用真实 Chrome UA**(`anti_detect.pick_profile()`)，否则闲鱼报「非法访问」。
- 截图读取有累计上限：验证视觉用「computed-style 断言 + SendUserFile(让用户看)」，不要狂读大图。
- 浏览器作业一律经 `runner._LOCK` 串行(Playwright sync 一次只能跑一个)。
- 不要用 `as any` / `@ts-ignore` / `# type: ignore` 掩盖类型错误；按权威 pyright 修根因。
