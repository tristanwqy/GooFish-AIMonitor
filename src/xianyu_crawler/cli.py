"""CLI 入口: run(选品+监控) / --monitor-only / --dry-run。"""
from __future__ import annotations

import argparse
import json

from .config import Settings, load_watchlist
from .storage.db import make_session
from .storage import repo
from . import pipeline, notifier
from .session import browser_session


def _notify(session, settings: Settings) -> None:
    evs = repo.unnotified_events(session)
    if not evs:
        return
    views = [{"type": e.type, **json.loads(e.payload)} for e in evs]
    subject, body = notifier.format_email(views)
    notifier.append_csv(settings.data_dir / "events.csv", views)
    notifier.send_email(settings, subject, body)
    repo.mark_notified(session, [e.id for e in evs])


def cmd_run(settings: Settings, args: argparse.Namespace) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    session = make_session(f"sqlite:///{settings.data_dir / 'xianyu.db'}", create=True)
    watches = load_watchlist(args.watchlist)
    with browser_session(settings) as ctx:
        if not args.monitor_only:
            pipeline.run_search(ctx, session, settings, watches)
        pipeline.run_monitor(ctx, session, settings)
    _notify(session, settings)


def cmd_serve(args: argparse.Namespace) -> None:
    """启动控制台: FastAPI + 进程内 APScheduler + 静态前端。"""
    import uvicorn
    from .web import scheduler, runtime
    from .web.app import app
    from .storage import repo

    Settings().data_dir.mkdir(parents=True, exist_ok=True)
    s = runtime.session()
    try:
        cfg = repo.get_config(s)
        crawl_minutes, fav_minutes = cfg.schedule_minutes, cfg.favorites_minutes
    finally:
        s.close()
    scheduler.start(crawl_minutes, fav_minutes)
    print(f">> 闲鱼控制台: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def cmd_test_email(args: argparse.Namespace) -> None:
    """发一封测试邮件验证 SMTP; 未配置时明确报错而非假成功。"""
    from .web import runtime
    from .storage import repo
    from . import service, notifier

    s = runtime.session()
    settings = service.effective_settings(repo.get_config(s))
    print(f"SMTP host={settings.smtp_host} port={settings.smtp_port} "
          f"user={settings.smtp_user} → 收件人 {settings.notify_to}")
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_pass and settings.notify_to):
        print("!! SMTP 未配置完整。请确认已 `source ~/.xianyu.env`"
              "(XIANYU_SMTP_HOST/USER/PASS, 收件人默认从控制台配置取)。")
        return
    try:
        notifier.send_email(settings, "闲鱼控制台 SMTP 测试", "配置成功 ✅ 这是一封测试邮件。")
        print(f">> 已发送到 {settings.notify_to}，去收件箱确认。")
    except Exception as e:  # noqa: BLE001
        print(f"!! 发送失败 {type(e).__name__}: {e}")
        print("   腾讯企业邮多半要用「客户端专用密码」而非登录密码。")


def main() -> None:
    ap = argparse.ArgumentParser(prog="xianyu")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="跑一次: 选品收藏 + 降价监控(CLI 无人值守模式)")
    r.add_argument("--watchlist", default="config/watchlist.yaml")
    r.add_argument("--monitor-only", action="store_true", help="只跑降价监控(R2)")
    r.add_argument("--dry-run", action="store_true", help="不真实收藏")
    sv = sub.add_parser("serve", help="启动控制台(FastAPI + 定时)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sub.add_parser("test-email", help="发一封测试邮件验证 SMTP")
    args = ap.parse_args()
    if args.cmd == "run":
        settings = Settings()
        if args.dry_run:
            pipeline._add_favorite = lambda ctx, it, st: False  # 演练: 不收藏
        cmd_run(settings, args)
    elif args.cmd == "serve":
        cmd_serve(args)
    elif args.cmd == "test-email":
        cmd_test_email(args)


if __name__ == "__main__":
    main()
