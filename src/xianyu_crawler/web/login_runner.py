"""控制台图形化扫码登录: 后台 headless 浏览器开闲鱼登录页, 截二维码给前端扫,
扫码确认成功后存 storage_state.json。复用 runner 全局浏览器锁(与抓取串行)。
"""
from __future__ import annotations

import base64
import json
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from ..anti_detect import pick_profile
from ..config import Settings
from . import account, runner          # account: 头像缓存; runner: 复用全局浏览器锁 + STATE

LOGIN_URL = "https://www.goofish.com/login"
_TIMEOUT_S = 180               # 二维码等待上限

# 前端轮询读这里: status=idle|starting|waiting|success|expired|failed|busy
STATE: dict = {"status": "idle", "qr": None, "message": "", "at": None}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _account() -> str | None:
    """从登录态 cookie 取闲鱼昵称(tracknick)显示在"已登录"处。只取昵称, 不含邮箱等隐私。"""
    f = Settings().data_dir / "storage_state.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    cks = {c.get("name"): c.get("value", "") for c in data.get("cookies", [])}
    raw = cks.get("tracknick") or cks.get("lgc") or cks.get("dnk") or cks.get("nick")
    if not raw:
        return None
    try:
        v = urllib.parse.unquote(urllib.parse.unquote(raw))
        if "\\u" in v:                          # 中文昵称为 \uXXXX 转义
            v = v.encode("latin-1", "ignore").decode("unicode_escape")
        return v or None
    except Exception:
        return raw or None


def status() -> dict:
    """给前端: 登录流程状态 + 是否已有登录态 + 闲鱼昵称。"""
    state_file = Settings().data_dir / "storage_state.json"
    return {
        "status": STATE["status"],
        "qr": STATE["qr"],
        "message": STATE["message"],
        "has_state": state_file.exists(),
        "account": _account(),
        "avatar": account.avatar(),
    }


def start() -> dict:
    """启动扫码登录流程(后台线程)。已在进行中/抓取占用则不重入。"""
    if STATE["status"] in ("starting", "waiting"):
        return {"status": STATE["status"]}
    if not runner._LOCK.acquire(blocking=False):
        return {"status": "busy", "message": "正在抓取，请稍后再试"}
    STATE.update(status="starting", qr=None, message="正在打开登录页…", at=_now())
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "starting"}


def _logged_in(url: str) -> bool:
    u = url.lower()
    return "login" not in u and "passport" not in u and "sign" not in u


# 二维码被手机扫过、等待手机端点「确认」时, passport iframe 里会出现这些字样
_SCAN_HINTS = ("扫描成功", "扫码成功", "请在手机", "确认登录", "登录确认", "已扫描", "请确认")


def _is_scanned(frame) -> bool:
    """iframe 文案出现"扫码成功/请在手机确认"→ 判定已扫码(给前端"登录中"反馈)。"""
    try:
        txt = frame.inner_text("body", timeout=800)
    except Exception:
        return False
    return any(h in txt for h in _SCAN_HINTS)


def logout() -> dict:
    """退出登录 / 换号: 删除 storage_state.json 并重置流程状态。"""
    f = Settings().data_dir / "storage_state.json"
    try:
        f.unlink()
    except FileNotFoundError:
        pass
    STATE.update(status="idle", qr=None, message="已退出登录", at=_now())
    return status()


def _run() -> None:
    runner.STATE["running"] = True
    state_path = str(Settings().data_dir / "storage_state.json")
    prof = pick_profile()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                locale="zh-CN", user_agent=prof["user_agent"], viewport=prof["viewport"])
            page = ctx.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            STATE.update(status="waiting", message="用「闲鱼」App 扫一扫登录")
            deadline = time.time() + _TIMEOUT_S
            ok = False
            scanned = False
            while time.time() < deadline:
                if _logged_in(page.url):
                    ok = True
                    break
                frame = next((f for f in page.frames
                              if "mini_login" in f.url or "passport" in f.url), None)
                if not scanned and frame is not None and _is_scanned(frame):
                    scanned = True                     # 已扫码, 等手机端确认 → 给前端"登录中"
                    STATE.update(status="scanned", qr=None,
                                 message="扫码成功，请在手机点「确认登录」…")
                if not scanned and frame is not None:
                    try:                               # 截二维码(passport iframe 里的 canvas)
                        png = frame.locator("canvas").first.screenshot(timeout=3000)
                        STATE["qr"] = "data:image/png;base64," + base64.b64encode(png).decode()
                    except Exception:
                        pass                           # 二维码暂不可用/刷新中, 下轮再试
                page.wait_for_timeout(1200)            # 提速: 扫码后更快翻到 success
            if ok:
                Path(state_path).parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=state_path)
                STATE.update(status="success", qr=None, message="登录成功，已保存登录态", at=_now())
            else:
                STATE.update(status="expired", qr=None, message="二维码超时，请重试", at=_now())
            browser.close()
    except Exception as e:  # noqa: BLE001 - 后台作业, 记录不抛
        STATE.update(status="failed", qr=None, message=f"登录出错: {e}", at=_now())
    finally:
        runner.STATE["running"] = False
        runner._LOCK.release()
