"""服务层: 桥接 DB(watches/config) ↔ 引擎(search/filter/favorite/monitor)。

控制台与调度都调这里。审核制: 搜索命中 → 写"推荐"(不自动收藏);
用户在控制台批准 → 点"收藏" → 进闲鱼收藏列表 → 自动进降价监控。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .config import Settings, Watch
from .models import Item
from .filter import matches
from .storage import repo
from .storage.orm import WatchRow, AppConfig, ItemRow
from . import search as _search_mod
from . import favorite as _favorite_mod
from . import pipeline
from . import review
from . import liveness as _liveness_mod


# --- 测试可 monkeypatch 的间接层(隔离真实浏览器) ---
def _search(ctx, watch: Watch, settings: Settings):
    return _search_mod.search(ctx, watch, settings.search_max_pages, settings.search_url)


def _check_liveness(ctx, item_id: str) -> tuple[bool, str | None, dict | None]:
    return _liveness_mod.check_liveness(ctx, item_id)


def _add_favorite(ctx, item: Item, settings: Settings) -> bool:
    return _favorite_mod.add_favorite(ctx, item, settings)


# --- row ↔ domain 映射 ---
def watchrow_to_watch(w: WatchRow) -> Watch:
    return Watch(
        name=w.name,
        keywords=json.loads(w.keywords or "[]"),
        price_min=w.price_min,
        price_max=w.price_max,
        city=w.city,
        condition=json.loads(w.condition) if w.condition else None,
        free_shipping=w.free_shipping,
        seller_min_credit=w.seller_min_credit,
        requirement=w.requirement,
        enabled=w.enabled,
    )


def effective_settings(cfg: AppConfig) -> Settings:
    """DB 配置覆盖到 Settings; SMTP 控制台填了用控制台的, 没填回退系统环境变量。"""
    base = Settings()

    def pick(db_val, env_val):
        return db_val if db_val not in (None, "") else env_val

    return base.model_copy(update={
        "min_drop_pct": cfg.min_drop_pct,
        "min_drop_abs": cfg.min_drop_abs,
        "notify_to": cfg.notify_to or base.notify_to,
        "headless": cfg.headless,
        "search_max_pages": cfg.search_max_pages,
        "favorites_max_pages": cfg.favorites_max_pages,
        # LLM 二次审核(接口地址/token 控制台没填则回退本地 secret.env)
        "review_enabled": cfg.review_enabled,
        "review_base_url": pick(cfg.review_base_url, base.review_base_url),
        "review_model": cfg.review_model,
        "review_api_token": pick(cfg.review_api_token, base.review_api_token),
        "review_timeout": cfg.review_timeout,
        "review_temperature": cfg.review_temperature,
        "review_max_tokens": cfg.review_max_tokens,
        "review_system_prompt": cfg.review_system_prompt or base.review_system_prompt,
        # 高级(抓取/反爬)
        "action_delay_min": cfg.action_delay_min,
        "action_delay_max": cfg.action_delay_max,
        "liveness_max_checks": cfg.liveness_max_checks,
        "search_url": cfg.search_url,
        "favorites_url": cfg.favorites_url,
        # SMTP
        "smtp_host": pick(cfg.smtp_host, base.smtp_host),
        "smtp_port": cfg.smtp_port or base.smtp_port,
        "smtp_user": pick(cfg.smtp_user, base.smtp_user),
        "smtp_pass": pick(cfg.smtp_pass, base.smtp_pass),
        # 邮件提醒事件开关
        "notify_on_new": cfg.notify_on_new,
        "notify_on_drop": cfg.notify_on_drop,
        "notify_on_sold": cfg.notify_on_sold,
        "notify_on_favorite": cfg.notify_on_favorite,
        "notify_on_login": cfg.notify_on_login,
    })


# --- 用例 ---
def scan_recommendations(ctx, session: Session, settings: Settings,
                         watches: list[Watch]) -> int:
    """搜索 → 规则过滤 → 去重 → LLM 二次审核 → 写"我没见过的"推荐。返回新增数。"""
    created = 0
    for w in watches:
        if not w.enabled:
            continue
        # 规则过滤 + 去重(本轮内 & 已推荐过的)
        fresh: list[Item] = []
        seen: set[str] = set()
        for item in _search(ctx, w, settings):
            if item.item_id in seen or not matches(item, w):
                continue
            # 跳过已推荐过的、已在闲鱼收藏的、已知死链的、近期不看的
            if (repo.has_been_recommended(session, item.item_id)
                    or repo.is_collected(session, item.item_id)
                    or repo.is_dead(session, item.item_id)
                    or repo.is_muted(session, item.item_id)):
                continue
            seen.add(item.item_id)
            fresh.append(item)
        # LLM 二次审核(有 requirement 才审; 无要求/失败放行)。
        # 未通过的也入库(带 rec_ok=False + 理由), 由前端筛选展示; 返回值只数"通过"的(头条数字)。
        verdicts = review.review_items(fresh, w.requirement, settings)
        for item, verdict in zip(fresh, verdicts):
            new = repo.create_recommendation(
                session, item, w.name, verdict.reason or None, ok=verdict.ok)
            if not new:
                continue
            if verdict.ok:
                created += 1
            if verdict.ok is not False:        # 通过或未审(无要求)→ 算"新发现", 可推送
                repo.add_event(session, item.item_id, "new_recommendation",
                               {"title": item.title, "url": item.url, "price": item.price,
                                "pic": item.pic_url, "watch": w.name})
    return created


def rereview_pending(session: Session, settings: Settings) -> dict:
    """对已入库的「待审」推荐, 用当前 LLM 配置重新跑一次 AI 审核并更新裁决(不重新抓闲鱼)。

    用途: 之前接口没配好时 review fail-open 攒下的「未审核」推荐(rec_reason=(审核未运行)),
    把接口配好(可用「测试 LLM」验证)后一键补审。没跑通的保留原样并计数提示。
    """
    if not settings.review_enabled:
        return {"ok": False, "error": "AI 审核未启用, 请先在设置里打开「启用 AI 审核」"}
    rows = [r for r in repo.list_recommendations(session, "new") if not r.dead]
    requirements = {w.name: w.requirement for w in repo.list_watches(session)}
    by_watch: dict[str | None, list] = {}
    for r in rows:
        by_watch.setdefault(r.watch_name, []).append(r)

    reviewed = passed = rejected = not_run = skipped = 0
    for wname, recs in by_watch.items():
        requirement = requirements.get(wname)
        if not requirement:                  # 该监控条件没写「AI 审核要求」→ 无从审核
            skipped += len(recs)
            continue
        items = [Item(item_id=r.item_id, title=r.title, url=r.url, price=r.latest_price,
                      condition=r.condition, location=r.location) for r in recs]
        verdicts = review.review_items(items, requirement, settings)
        for r, v in zip(recs, verdicts):
            if v.reason == review.REVIEW_NOT_RUN:   # 接口没跑通 → 保留原裁决, 只计数
                not_run += 1
                continue
            repo.update_rec_verdict(session, r.item_id, v.ok, v.reason or None)
            reviewed += 1
            passed += int(bool(v.ok))
            rejected += int(not v.ok)
    return {"ok": True, "reviewed": reviewed, "passed": passed, "rejected": rejected,
            "not_run": not_run, "skipped_no_requirement": skipped}


def sweep_liveness(ctx, session: Session, settings: Settings) -> int:
    """对待审推荐逐条打开详情页核活, 已删除/下架的标死链(置灰, 不再误开)。

    收藏夹的死链由收藏 API 直接给出(run_monitor 入库); 这里专补"纯搜索来源、
    卖出后从搜索消失"的推荐。每轮限量 settings.liveness_max_checks。返回新判死数。
    """
    rows = repo.list_recommendations(session, "new")
    pending = [r for r in rows if not r.dead][: settings.liveness_max_checks]
    newly_dead = 0
    for r in pending:
        dead, reason, stats = _check_liveness(ctx, r.item_id)
        if stats:                          # 顺带回写浏览/收藏/想要次数
            repo.update_item_stats(session, r.item_id, **stats)
        if dead:
            repo.mark_dead(session, r.item_id, reason or "已删除")
            repo.add_event(session, r.item_id, "sold",
                           {"title": r.title, "url": r.url, "pic": r.pic_url,
                            "reason": reason or "已删除"})
            newly_dead += 1
    return newly_dead


def approve_recommendation(ctx, session: Session, settings: Settings, item_id: str) -> bool:
    """批准推荐 → 在闲鱼点"收藏" → 标记 favorited/approved。"""
    row = session.get(ItemRow, item_id)
    if row is None:
        return False
    item = Item(item_id=row.item_id, title=row.title, url=row.url, price=row.latest_price)
    if _add_favorite(ctx, item, settings):
        repo.mark_favorited(session, item_id)
        repo.set_rec_status(session, item_id, "approved")
        return True
    return False


def reject_recommendation(session: Session, item_id: str) -> None:
    repo.set_rec_status(session, item_id, "rejected")


_MUTE_FOREVER = datetime(9999, 12, 31)


def mute_recommendation(session: Session, item_id: str, days: int) -> None:
    """近期不看: days>0 → 隐藏到 N 天后(到期自动重现); days<=0 → 永久不看。"""
    if days <= 0:
        until = _MUTE_FOREVER
    else:
        until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days)
    repo.mute_item(session, item_id, until)


def run_price_monitor(ctx, session: Session, settings: Settings) -> int:
    return pipeline.run_monitor(ctx, session, settings)
