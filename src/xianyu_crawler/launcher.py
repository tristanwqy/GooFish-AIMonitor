"""桌面启动器: 起控制台服务 + 用系统原生 WebView 开「应用窗口」。

用于 PyInstaller 打成 Mac/Windows 桌面应用(双击即用):
- 数据写到用户目录(不是程序目录, 卸载/升级不丢);
- UI 用 pywebview(macOS 走系统 WKWebView)在**本进程**里开一个原生窗口,
  所以 Dock 图标 / 菜单栏应用名都来自我们自己的 .app, 不是浏览器外壳;
- 打进包里的 Chromium 只供 Playwright 后台抓闲鱼 / 扫码登录用(PLAYWRIGHT_BROWSERS_PATH);
- 服务在后台线程跑, 关掉窗口即退出整个应用;
- 万一没有 pywebview, 退回系统默认浏览器;
- `--selfcheck` 只做"能不能拉起 Chromium"的冒烟测试(CI / 本地验证打包是否成功)。
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

HOST, PORT = "127.0.0.1", 8000
WINDOW_TITLE = "闲鱼控制台"


def _user_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "GooFish-AIMonitor"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "GooFish-AIMonitor"
    return Path.home() / ".goofish-aimonitor"


def _bundled_browsers_dir() -> Path | None:
    """打包后 Chromium 被放进 bundle 的 ms-playwright 目录(构建脚本 post-build 拷入)。"""
    if not getattr(sys, "frozen", False):
        return None
    cands = []
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        cands.append(Path(mei) / "ms-playwright")
    exe_dir = Path(sys.executable).resolve().parent
    cands += [exe_dir / "ms-playwright",
              exe_dir.parent / "Resources" / "ms-playwright"]   # macOS .app: Contents/Resources
    for c in cands:
        if c.exists():
            return c
    return None


def _use_bundled_chromium() -> None:
    """打包运行时, 让 Playwright 用打进包里的 Chromium。"""
    d = _bundled_browsers_dir()
    if d is not None:
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(d))


def _selfcheck() -> int:
    """冒烟测试: 能否拉起(打包内的)Chromium。打包验证 / CI 用。"""
    _use_bundled_chromium()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("SELFCHECK_OK")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"SELFCHECK_FAIL: {type(e).__name__}: {e}")
        return 1


def _pick_port(preferred: int) -> int:
    """优先用 preferred(8000); 被占(例如 Docker 版也在跑)就让系统挑个空闲端口。"""
    for cand in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, cand))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferred


def _wait_ready(port: int, timeout_s: float = 60.0) -> bool:
    """轮询本地端口, 等服务起来。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _open_app_window(url: str) -> bool:
    """用系统原生 WebView 开应用窗口。必须在主线程, 阻塞到窗口关闭。

    成功(开过窗口)返回 True; 没装 pywebview 返回 False(交给调用方退回默认浏览器)。
    """
    try:
        import webview
    except Exception:  # noqa: BLE001 — 没有就退回默认浏览器, 不让启动失败
        return False
    webview.create_window(WINDOW_TITLE, url, width=1320, height=860, min_size=(980, 640))
    webview.start()
    return True


def main() -> None:
    if "--selfcheck" in sys.argv:
        sys.exit(_selfcheck())

    os.environ.setdefault("XIANYU_DATA_DIR", str(_user_data_dir()))
    _use_bundled_chromium()
    Path(os.environ["XIANYU_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

    import uvicorn
    # 绝对导入: 打包后 launcher 作为 __main__ 运行, 相对导入会失败
    from xianyu_crawler.web import scheduler, runtime
    from xianyu_crawler.web.app import app
    from xianyu_crawler.storage import repo
    from xianyu_crawler.config import Settings

    Settings().data_dir.mkdir(parents=True, exist_ok=True)
    s = runtime.session()
    try:
        cfg = repo.get_config(s)
        scheduler.start(cfg.schedule_minutes, cfg.favorites_minutes)
    finally:
        s.close()

    port = _pick_port(PORT)   # 8000 被占(如 Docker 版在跑)就自动换空闲端口
    url = f"http://{HOST}:{port}"
    print(f">> 闲鱼控制台: {url} (数据目录: {os.environ['XIANYU_DATA_DIR']})")

    # 服务跑后台线程, 主线程留给原生窗口(WKWebView 必须在主线程)
    config = uvicorn.Config(app, host=HOST, port=port, log_level="warning")
    server = uvicorn.Server(config)
    srv_thread = threading.Thread(target=server.run, daemon=True)
    srv_thread.start()
    if not _wait_ready(port):
        print("服务启动超时, 退出。")
        sys.exit(1)

    if _open_app_window(url):       # 原生窗口, 阻塞到关闭 → 退出应用
        server.should_exit = True
        return

    # 没有 pywebview: 退回系统默认浏览器, 保持服务存活到进程被杀
    webbrowser.open(url)
    srv_thread.join()


if __name__ == "__main__":
    main()
