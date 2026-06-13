"""通知: 邮件(SMTP) + 本地 CSV。"""
from __future__ import annotations

import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from pathlib import Path

CSV_FIELDS = ["type", "title", "url", "reason", "prev_price", "curr_price", "drop_abs", "drop_pct"]


def format_email(events: list[dict]) -> tuple[str, str]:
    news = [e for e in events if e["type"] == "new_recommendation"]
    drops = [e for e in events if e["type"] == "price_drop"]
    solds = [e for e in events if e["type"] == "sold"]
    favs = [e for e in events if e["type"] == "favorited"]

    bits = []
    if news:
        bits.append(f"{len(news)} 新发现")
    if drops:
        bits.append(f"{len(drops)} 降价")
    if solds:
        bits.append(f"{len(solds)} 售出")
    if favs:
        bits.append(f"{len(favs)} 收藏")
    subject = "闲鱼: " + (" / ".join(bits) if bits else "有新动静")

    lines: list[str] = []
    if news:
        lines.append("== 新发现 ==")
        for e in news:
            tail = f"  ({e['watch']})" if e.get("watch") else ""
            lines.append(f"- {e['title']}: ¥{e.get('price')}{tail}  {e['url']}")
    if drops:
        lines.append("== 降价 ==")
        for e in drops:
            reason = e.get("reason", "降价")
            cur = e.get("curr_price")
            drop = e.get("drop_abs")
            pct = e.get("drop_pct")
            seg = f"- {e['title']}: 现价¥{cur}"
            if drop is not None:
                seg += f" ({reason} ¥{drop:.0f}"
                seg += f", {pct:.1f}%)" if pct is not None else ")"
            seg += f"  {e['url']}"
            lines.append(seg)
    if solds:
        lines.append("== 已售出 / 下架 ==")
        for e in solds:
            lines.append(f"- {e['title']}（{e.get('reason', '已下架')}）  {e['url']}")
    if favs:
        lines.append("== 新收藏 ==")
        for e in favs:
            lines.append(f"- {e['title']}  {e['url']}")
    return subject, "\n".join(lines)


# ---------- HTML 邮件(仿网页卡片样式) ----------

def _esc(s) -> str:
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _yuan(v) -> str:
    try:
        return "¥" + format(round(float(v)), ",")
    except Exception:
        return ""


def _thumb(pic) -> str:
    if not pic:
        return ""
    u = pic + "_200x200q90.jpg" if "alicdn.com" in pic else pic
    return (f'<td width="80" style="width:80px;padding:0;">'
            f'<img src="{_esc(u)}" width="80" height="80" alt="" '
            f'style="display:block;width:80px;height:80px;object-fit:cover;'
            f'border-radius:8px;background:#eef1f5;"></td>')


def _badge(text: str, color: str, bg: str) -> str:
    return (f'<span style="display:inline-block;font-size:12px;font-weight:600;color:{color};'
            f'background:{bg};border-radius:6px;padding:2px 8px;">{_esc(text)}</span>')


def _card(e: dict, badge: str = "") -> str:
    price = e.get("price")
    price = e.get("curr_price") if price is None else price
    price_html = (f'<div style="font-size:17px;font-weight:700;color:#0a2540;margin:5px 0 4px;">{_yuan(price)}</div>'
                  if price is not None else "")
    return (
        f'<a href="{_esc(e.get("url"))}" style="text-decoration:none;color:#1d1d1f;display:block;">'
        f'<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:separate;'
        f'border:1px solid #e3e8ee;border-radius:12px;overflow:hidden;background:#fff;margin:0 0 10px;">'
        f'<tr>{_thumb(e.get("pic"))}'
        f'<td style="padding:11px 14px;vertical-align:top;">'
        f'<div style="font-size:13.5px;line-height:1.45;color:#1d1d1f;">{_esc(e.get("title"))}</div>'
        f'{price_html}{badge}</td></tr></table></a>'
    )


def format_email_html(events: list[dict]) -> str:
    news = [e for e in events if e["type"] == "new_recommendation"]
    drops = [e for e in events if e["type"] == "price_drop"]
    solds = [e for e in events if e["type"] == "sold"]
    favs = [e for e in events if e["type"] == "favorited"]

    bits = []
    for n, lab in ((len(news), "新发现"), (len(drops), "降价"), (len(solds), "售出"), (len(favs), "收藏")):
        if n:
            bits.append(f"{n} {lab}")
    summary = " · ".join(bits) if bits else "有新动静"

    def section(title: str, items: list[dict], badge_fn) -> str:
        if not items:
            return ""
        head = (f'<div style="font-size:13px;font-weight:700;color:#697386;'
                f'margin:18px 2px 9px;">{title}（{len(items)}）</div>')
        return head + "".join(_card(e, badge_fn(e)) for e in items)

    def b_new(e):
        w = (f'<span style="font-size:12px;color:#697386;">　条件 {_esc(e.get("watch"))}</span>'
             if e.get("watch") else "")
        return _badge("新发现", "#0a7", "#e6f7f0") + w

    def b_drop(e):
        drop = e.get("drop_abs")
        txt = f"收藏后降 {_yuan(drop)}" if drop is not None else "降价"
        tail = (f'<span style="font-size:12px;color:#697386;">　{_yuan(e.get("prev_price"))} → {_yuan(e.get("curr_price"))}</span>'
                if e.get("prev_price") is not None else "")
        return _badge(txt, "#d4380d", "#fff1ec") + tail

    body = (section("🆕 新发现", news, b_new)
            + section("📉 降价", drops, b_drop)
            + section("⚠️ 已售出 / 下架", solds, lambda e: _badge(e.get("reason") or "已下架", "#697386", "#eef1f5"))
            + section("⭐ 新收藏", favs, lambda e: ""))

    return (
        '<div style="background:#f6f9fc;padding:20px 0;margin:0;'
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;\">"
        '<div style="max-width:640px;margin:0 auto;padding:0 16px;">'
        '<div style="font-size:19px;font-weight:700;color:#0a2540;">🐟 闲鱼控制台</div>'
        f'<div style="font-size:13px;color:#697386;margin:3px 0 6px;">{_esc(summary)}</div>'
        f'{body}'
        '<div style="font-size:11px;color:#9aa5b1;text-align:center;margin-top:20px;">'
        '由「闲鱼控制台」自动发送 · 点卡片直达商品</div></div></div>'
    )


def append_csv(path: str | Path, events: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for e in events:
            w.writerow(e)


def send_test(settings) -> None:
    """发送一封测试邮件; 配置不全或发送失败都抛异常(供控制台「测试」报错)。"""
    missing = [k for k in ("smtp_host", "smtp_user", "smtp_pass", "notify_to")
               if not getattr(settings, k, None)]
    if missing:
        raise ValueError("SMTP 配置不完整, 缺: " + ", ".join(missing))
    msg = MIMEText("这是一封来自闲鱼控制台的测试邮件，收到说明 SMTP 配置成功。", "plain", "utf-8")
    msg["Subject"] = Header("闲鱼控制台 · 测试邮件", "utf-8").encode()
    msg["From"] = settings.smtp_user
    msg["To"] = settings.notify_to
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as srv:
        srv.login(settings.smtp_user, settings.smtp_pass)
        srv.sendmail(settings.smtp_user, [settings.notify_to], msg.as_string())


def send_email(settings, subject: str, body: str, html: str | None = None) -> None:
    """未配置 SMTP 则跳过(降级为仅 CSV/日志)。有 html 则发 multipart(纯文本兜底 + HTML)。"""
    if not (settings.smtp_host and settings.smtp_user and settings.notify_to):
        return
    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))      # 不支持 HTML 的客户端看纯文本
        msg.attach(MIMEText(html, "html", "utf-8"))       # 现代客户端看卡片样式
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8").encode()
    msg["From"] = settings.smtp_user
    msg["To"] = settings.notify_to
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as srv:
        srv.login(settings.smtp_user, settings.smtp_pass)
        srv.sendmail(settings.smtp_user, [settings.notify_to], msg.as_string())
