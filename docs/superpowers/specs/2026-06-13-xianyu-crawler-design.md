# 闲鱼自动化 Crawler — 设计文档 (Design Spec)

- **日期**: 2026-06-13
- **状态**: Approved（已与用户确认设计方向，待转 implementation plan）
- **作者**: wqy + Claude
- **仓库**: `github.com/tristanwqy/GooFish-AIMonitor`

---

## 1. 背景与目标

定时登录闲鱼（Goofish，阿里二手平台）个人账号，自动完成两件事：

- **R1 — 选品收藏**：按预设条件查找符合的商品，加入闲鱼"想要/收藏"。
- **R2 — 降价监控**：检查"我想要的/收藏"列表中商品是否降价，发现降价时通知。

收藏列表是连接两个需求的枢纽：R1 的产物（收藏）即 R2 的数据源（被监控集合）。

### 成功标准

1. 一条命令完成首次扫码登录并持久化登录态；后续运行无需人工，除非登录态失效。
2. 定时运行：按 watchlist 条件搜索、过滤、对高置信匹配点"想要"（带数量上限与随机延时）。
3. 每次运行抓取收藏列表当前价，与历史价比对，按阈值判定降价。
4. 降价/新收藏通过邮件 + 本地 CSV/日志通知。
5. 触发验证码/风控时安全中止、保存现场、邮件告警，不蛮干。

## 2. 范围

### In scope (v1)

- 本地 macOS 运行；Python + Playwright（有头/可切无头）。
- 登录态持久化（`storage_state.json`），失效邮件提醒补扫码。
- 规则式（rule-based）搜索过滤：关键词、价格区间、地区、成色、包邮、卖家信用。
- 自动"想要"（收藏），带平衡节奏限速。
- SQLite 存商品与价格历史，降价检测。
- 邮件（SMTP）+ 本地 CSV/日志通知。
- launchd 定时调度。

### Out of scope (YAGNI, v1 不做)

- Web 管理 UI（参考项目有，但当前需求不需要）。
- AI/LLM 智能过滤（过滤用规则即可；预留接口，后续可加）。
- 多账号、服务器/Docker 部署、代理池、短信登录自动化。

## 3. 需求明细

### R1 选品收藏

- 输入：`watchlist.yaml` 中一组 watch，每个含关键词、价格区间、可选地区/成色/包邮/卖家信用、单次收藏上限 `want_max_per_run`。
- 流程：搜索 → 解析 → 规则过滤 → 去重（已收藏/已见过的跳过）→ 对通过项点"想要"。
- 约束：仅对高置信匹配收藏；单次运行收藏数有上限；动作间随机延时。

### R2 降价监控

- 输入：闲鱼"我想要的/收藏"列表（线上为准）。
- 流程：遍历收藏 → 抓当前价 → 入库 `price_history` → 与该商品历史最低/上次价比对 → 命中阈值即生成 `price_drop` 事件。
- 阈值：`drop_pct >= min_drop_pct`(默认 5%) **或** `drop_abs >= min_drop_abs`(默认 ¥50)，两者均可配。

## 4. 技术选型与依据

| 维度 | 选择 | 依据 |
|---|---|---|
| 浏览器自动化 | **Playwright (sync API)** | 社区最成熟的闲鱼方案（`ai-goofish-monitor`、`xianyu-monitor-skill`）均用 Playwright；与用户已有 `browser-use`/`webapp-testing` 一致。sync API 对顺序批处理足够且更简单。 |
| 登录态 | **`storage_state.json`** | 手动扫码一次后保存 cookie+localStorage 复用，规避扫码自动化。开源验证范式。 |
| 运行环境 | **本地 macOS** | 贴合账号常用设备指纹，风控暴露面最低。 |
| 调度 | **launchd（一次性 CLI 入口）** | 平衡节奏每天数次，无需常驻进程；比 APScheduler daemon 简单。 |
| 存储 | **SQLite + SQLAlchemy 2.x** | 单机、零运维、足够。 |
| 配置 | **Pydantic Settings + YAML watchlist** | 遵循用户 python-backend 规范；密钥走系统环境变量。 |
| 通知 | **SMTP 邮件 + CSV/日志** | 用户选定。 |
| 节奏 | **平衡（balanced）** | 每天 3–4 次抖动调度；动作间 3–8s 随机延时；单次收藏上限。 |

> 解析策略：优先**拦截 mtop 搜索/详情的 JSON 响应**（`page.on("response")`），DOM 解析做兜底——比纯抠 DOM 抗改版。录制 JSON 作回归 fixture。

## 5. 架构与模块

```
launchd ──> cli.run
              │
              ▼
        ┌── session(load storage_state, 校验登录) ──┐
        │                                            │
   [R1] search ─> filter ─> favorite(点"想要")        │  写库/事件
        │            ▲                                ▼
        │       anti_detect                      notifier(邮件+CSV/日志)
        │                                            ▲
   [R2] favorites_list ─> price_monitor(抓价/比对)────┘
                                │
                              storage(SQLite)
```

### 模块职责（每个单一职责、可独立测试）

- **`config`** — 加载 Pydantic Settings（SMTP、阈值、节奏）+ 解析 `watchlist.yaml`；密钥仅来自系统环境变量。
- **`session`** — 创建/复用 Playwright context，load/save `storage_state.json`，校验登录有效性（失败→标记需补扫码）。
- **`anti_detect`** — UA/viewport 随机池、随机延时、拟人滚动、退避重试、风控页识别。
- **`search`** — 按 watch 跑搜索，拦截 JSON 解析为 `Item`，DOM 兜底；输出原始结果。
- **`filter`** — 规则过滤（价格/地区/成色/包邮/信用）+ 去重，判定"高置信匹配"。
- **`favorite`** — 对通过项点"想要"，限速 + 上限 + 记录 `want_added`。
- **`favorites_list`** — 读取线上收藏列表为 `Item` 集合（含当前价）。
- **`price_monitor`** — 入库价格观测，按阈值算降价，产出 `price_drop` 事件。
- **`storage`** — SQLAlchemy models + repository（`items`/`price_history`/`events`）。
- **`notifier`** — 汇总未通知事件 → SMTP 邮件 + 写 CSV/日志 → 标记已通知。
- **`pipeline`** — 编排一次完整运行（R1 + R2），统一异常/降级处理。
- **`cli`** — 入口：`login` / `run` / `search`(仅选品) / `monitor`(仅降价) / `--dry-run`。

### 建议项目结构

```
xianyu-crawler/
  pyproject.toml
  .env.example
  config/watchlist.yaml
  src/xianyu_crawler/
    config.py  session.py  anti_detect.py
    search.py  filter.py   favorite.py  favorites_list.py
    price_monitor.py  notifier.py  pipeline.py  cli.py
    storage/{db.py, models.py, repo.py}
  scripts/login.py                      # 首次扫码登录
  deploy/com.xianyu.crawler.plist       # launchd 模板
  tests/
  data/                                 # gitignore: storage_state.json, db, csv, logs
```

## 6. 数据模型 (SQLite)

- **`items`**: `item_id` (PK, 闲鱼商品 id), `title`, `url`, `seller_id`, `seller_nick`,
  `first_price`, `latest_price`, `first_seen_at`, `last_seen_at`,
  `source` (`search`|`favorite`), `want_added` (bool), `want_added_at`, `watch_name` (nullable)。
- **`price_history`**: `id` (PK), `item_id` (FK), `price`, `observed_at`。
- **`events`**: `id` (PK), `item_id` (FK), `type` (`price_drop`|`favorited`|`new_match`),
  `payload` (JSON), `created_at`, `notified` (bool)。

## 7. 数据流（一次 run）

1. `session` 载入 `storage_state.json` → 校验登录。无效 → 发"补扫码"邮件 → 进入只读降级（仅 R2 抓价，跳过 R1 点想要）。
2. **R1**：遍历启用的 watch → `search`（拦截 JSON）→ `filter`（规则+去重）→ 对高置信项 `favorite` 点想要（限速/上限）→ 写 `items`、`events(favorited)`。
3. **R2**：`favorites_list` 读线上收藏 → 每项写 `price_history`、更新 `items.latest_price` → `price_monitor` 比对 → 命中写 `events(price_drop)`。
4. `notifier` 取未通知事件 → 邮件 + CSV/日志 → 标记 `notified`。
5. 全程 `anti_detect` 注入延时/拟人化；任意阶段识别到验证码/风控 → 截图存档 + 告警邮件 + 安全退出。

## 8. 配置与密钥

- **系统环境变量（密钥，遵守 CLAUDE.md Rule 02，绝不写文件）**：`XIANYU_SMTP_HOST/PORT/USER/PASS`、`XIANYU_NOTIFY_TO`。
- **`.env`（非密钥默认值）**：阈值、节奏、数据目录路径。
- **`config/watchlist.yaml`**：搜索条件列表（见 R1）。
- **`data/`**：`storage_state.json`、`xianyu.db`、`events.csv`、`*.log` —— 全部 gitignore。

## 9. 反爬与风控策略（平衡节奏）

- 调度：launchd 每天 3–4 次，触发时刻加随机抖动。
- 动作：操作间 3–8s 随机延时；列表页拟人滚动加载。
- UA/viewport：小型设备画像池随机。
- 收藏限速：`want_max_per_run`（默认 5）；仅高置信匹配。
- 退避：网络/超时 3 次指数退避。
- 风控识别：检测到滑块/验证码/风控页 → 立即停止写操作、截图、告警邮件、退出。
- 合规：闲鱼 ToS 通常禁止自动化；本项目个人自用、低频、单账号，由用户承担风险；提供 `--dry-run`（不点想要）用于安全演练。

## 10. 登录与登录态

- `scripts/login.py`：有头启动 Playwright → 打开闲鱼登录 → 用户手动扫码 → 轮询直到登录成功 → `context.storage_state(path="data/storage_state.json")`。
- 运行期：以 `storage_state` 创建 context；校验登录（检查头像/访问需登录接口）。失效 → 邮件提醒补扫码 + 只读降级。

## 11. 错误处理与降级

- **登录失效**：能抓价就只跑 R2（只读），R1 跳过；邮件提醒补扫码。
- **风控/验证码**：停写、截图、告警、退出（绝不自动过验证码）。
- **网络/超时**：指数退避重试，仍失败则跳过该项并记录。
- **解析失败**：JSON 拦截失败回退 DOM；再失败记录样本供修复。

## 12. 调度

- `deploy/com.xianyu.crawler.plist`：调用 `python -m xianyu_crawler.cli run`，`StartCalendarInterval` 配多个抖动时刻；日志重定向到 `data/`。
- 用户用 `launchctl load` 启用；文档给出步骤。

## 13. 测试策略

- **纯逻辑 TDD（先写测试）**：`price_monitor` 降价判定、`filter` 规则、`notifier` 邮件/CSV 格式化。
- **解析回归**：用录制的 mtop JSON fixture 测 `search`/`favorites_list` 解析。
- **集成（opt-in，手动）**：真实登录 + `--dry-run` 搜索（不点想要）冒烟。
- 遵守用户规则：变更文件跑 diagnostics；纯逻辑模块覆盖到位。

## 14. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 自动"想要"是强 bot 信号，封号风险 | 限量 + 随机延时 + 仅高置信 + 提供 `--dry-run` |
| 闲鱼 DOM/API 改版导致解析失效 | JSON 拦截优先 + DOM 兜底 + fixture 回归；预期需维护 |
| 登录态过期需人工补扫 | 邮件告警；无法完全避免（设计已接受） |
| ToS / 合规 | 个人自用、低频、单账号；用户知情承担 |

## 15. 参考

- `dingyufei615/ai-goofish-monitor` — Playwright 闲鱼监控（反爬/登录态范式来源，仅读代码参考，不直接运行）。
- `lenkin233/xianyu-monitor-skill` — 同源 skill（Snyk 审计 fail，**不直接安装运行**，仅参考）。
- 选型结论：二者均证明 Playwright + `storage_state` + 反爬手法在闲鱼可行；但都不做"收藏 + 监控自有收藏降价"，故本项目自建。
