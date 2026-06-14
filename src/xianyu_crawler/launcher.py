"""桌面启动器: 起控制台服务 + 自动打开浏览器。

用于 PyInstaller 打成 Mac/Windows 桌面应用(双击即用):
- 数据写到用户目录(不是程序目录, 卸载/升级不丢);
- 打包运行(sys.frozen)时用**打进包里**的 Chromium(PLAYWRIGHT_BROWSERS_PATH=0);
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


def _open_when_ready() -> None:
    for _ in range(120):
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                break
        except OSError:
            time.sleep(0.5)
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

    threading.Thread(target=_open_when_ready, daemon=True).start()
    print(f">> 闲鱼控制台: http://{HOST}:{PORT} (数据目录: {os.environ['XIANYU_DATA_DIR']})")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
