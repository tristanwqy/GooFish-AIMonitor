"""把 Playwright 需要的浏览器(Chromium 等)从默认缓存拷进打包目录。

PyInstaller 不能直接打 Chromium(.app 嵌套 / 权限), 所以构建后用这个脚本把浏览器
原样拷进 bundle 的 ms-playwright 目录, 运行时 launcher 把 PLAYWRIGHT_BROWSERS_PATH
指过去。Mac/Windows 通用。

用法: python packaging/copy_browsers.py <目标 ms-playwright 目录>
拷前确保缓存里有: python -m playwright install chromium
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _cache_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _needed_dirs() -> list[str]:
    import playwright
    bj = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
    data = json.loads(bj.read_text(encoding="utf-8"))
    wanted = {"chromium", "chromium-headless-shell", "ffmpeg"}
    return [f"{b['name'].replace('-', '_')}-{b['revision']}"
            for b in data["browsers"] if b["name"] in wanted]


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python packaging/copy_browsers.py <目标目录>")
        return 2
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)
    src = _cache_dir()
    copied = 0
    for d in _needed_dirs():
        s = src / d
        if s.exists():
            shutil.copytree(s, target / d, dirs_exist_ok=True, symlinks=True)
            print("  copied", d)
            copied += 1
        else:
            print("  !! 缓存缺失(先 playwright install chromium):", s)
    print(f"完成, 拷入 {copied} 个浏览器目录 → {target}")
    return 0 if copied else 1


if __name__ == "__main__":
    sys.exit(main())
