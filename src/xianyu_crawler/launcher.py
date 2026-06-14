"""桌面启动器: 起控制台服务 + 用包内 Chromium 开「应用窗口」。

用于 PyInstaller 打成 Mac/Windows 桌面应用(双击即用):
- 数据写到用户目录(不是程序目录, 卸载/升级不丢);
- 打包运行(sys.frozen)时用**打进包里**的 Chromium(PLAYWRIGHT_BROWSERS_PATH);
- UI 用包内完整 Chromium 以 `--app` 模式开一个无地址栏的独立窗口(像原生应用),
  关掉窗口就退出整个应用; 服务在后台线程里跑。找不到包内 Chromium 时退回系统默认浏览器;
- `--selfcheck` 只做"能不能拉起 Chromium"的冒烟测试(CI / 本地验证打包是否成功)。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

HOST, PORT = "127.0.0.1", 8000


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


def _wait_ready(timeout_s: float = 60.0) -> bool:
    """轮询本地端口, 等服务起来。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _bundled_chromium_exe() -> str | None:
    """包内(或本地缓存里)完整 Chromium 的可执行文件, 用来开应用窗口。

    用 Playwright 自己给的 executable_path, 不硬编码目录结构(随版本/架构而变);
    它会跟随 PLAYWRIGHT_BROWSERS_PATH, 打包后指向包内那份。找不到则返回 None。
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        if exe and Path(exe).exists():
            return exe
    except Exception:  # noqa: BLE001 — 拿不到就退回默认浏览器, 不该让启动失败
        pass
    return None


def _launch_app_window(chrome_exe: str, url: str) -> subprocess.Popen[bytes] | None:
    """用包内 Chromium 以 --app 模式开一个独立窗口(无标签/地址栏), 返回其进程。"""
    profile = Path(os.environ["XIANYU_DATA_DIR"]) / "ui-profile"
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [
        chrome_exe,
        f"--app={url}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1320,860",
    ]
    try:
        return subprocess.Popen(cmd)
    except Exception:  # noqa: BLE001 — 起窗口失败就退回默认浏览器
        return None


def _open_default_browser() -> None:
    if _wait_ready():
        webbrowser.open(f"http://{HOST}:{PORT}")


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

    url = f"http://{HOST}:{PORT}"
    chrome = _bundled_chromium_exe()
    print(f">> 闲鱼控制台: {url} (数据目录: {os.environ['XIANYU_DATA_DIR']})")

    if chrome is None:
        # 找不到 Chromium(一般是没装浏览器的环境): 开系统默认浏览器, 前台跑服务
        threading.Thread(target=_open_default_browser, daemon=True).start()
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
        return

    # 桌面应用模式: 服务跑后台线程, 用包内 Chromium 开应用窗口, 关掉窗口即退出整个应用
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    srv_thread = threading.Thread(target=server.run, daemon=True)
    srv_thread.start()
    if not _wait_ready():
        print("服务启动超时, 退出。")
        sys.exit(1)

    proc = _launch_app_window(chrome, url)
    if proc is None:
        webbrowser.open(url)   # 起窗口失败 → 退回默认浏览器, 阻塞到服务结束
        srv_thread.join()
        return

    print(">> 已打开应用窗口, 关掉窗口即退出。")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
    server.should_exit = True


if __name__ == "__main__":
    main()
