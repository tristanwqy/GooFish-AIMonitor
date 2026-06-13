"""进程内定时调度(APScheduler): 两个独立任务。

- crawl (schedule_minutes, 默认 120): 推荐抓取 + 死链核活 + 通知。
- favorites (favorites_minutes, 默认 30): 收藏刷新 + 降价通知。

防重入: 每个 job max_instances=1 + coalesce; runner 还有全局锁兜底(两任务共用一把锁,
不会并发开浏览器)。暂停由各 runner 函数内部检查 AppConfig.paused 实现。
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import runner

_scheduler: BackgroundScheduler | None = None
_CRAWL_JOB = "crawl"
_FAV_JOB = "favorites"


def start(crawl_minutes: int, favorites_minutes: int) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(runner.crawl, IntervalTrigger(minutes=max(1, crawl_minutes)),
                       id=_CRAWL_JOB, max_instances=1, coalesce=True)
    _scheduler.add_job(runner.refresh_favorites, IntervalTrigger(minutes=max(1, favorites_minutes)),
                       id=_FAV_JOB, max_instances=1, coalesce=True)
    _scheduler.start()


def reschedule(crawl_minutes: int, favorites_minutes: int) -> None:
    if _scheduler is None:
        return
    _scheduler.reschedule_job(_CRAWL_JOB, trigger=IntervalTrigger(minutes=max(1, crawl_minutes)))
    _scheduler.reschedule_job(_FAV_JOB, trigger=IntervalTrigger(minutes=max(1, favorites_minutes)))


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running
