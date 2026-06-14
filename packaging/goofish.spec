# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包: GooFish-AIMonitor 桌面应用。

构建前需先把 Chromium 装进 playwright 包里(随包一起打):
    PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium
构建:
    pyinstaller packaging/goofish.spec --noconfirm
产物: dist/GooFish-AIMonitor.app (macOS) 或 dist/GooFish-AIMonitor/ (Windows onedir)
"""
import os
import sys

import xianyu_crawler
from PyInstaller.utils.hooks import collect_all

PKG_DIR = os.path.dirname(xianyu_crawler.__file__)

datas, binaries, hiddenimports = [], [], []
# 这些包有数据文件/动态导入/原生驱动
for pkg in ("playwright", "uvicorn", "fastapi", "starlette", "apscheduler",
            "sqlalchemy", "pydantic", "pydantic_settings", "anyio"):
    d, b, h = collect_all(pkg)
    # Chromium(.local-browsers)不让 PyInstaller "处理"(会因 .app 嵌套而失败);
    # 它由构建脚本 post-build 用 ditto/robocopy 原样拷进 bundle 的 ms-playwright。
    d = [(s, dst) for (s, dst) in d if ".local-browsers" not in s]
    b = [(s, dst) for (s, dst) in b if ".local-browsers" not in s]
    datas += d
    binaries += b
    hiddenimports += h

# 前端构建产物(放到与包结构一致的相对路径, app.py 据 _MEIPASS 解析)
datas += [(os.path.join(PKG_DIR, "web", "static"), "xianyu_crawler/web/static")]
hiddenimports += ["xianyu_crawler", "xianyu_crawler.web.app"]

a = Analysis(
    [os.path.join(PKG_DIR, "launcher.py")],
    pathex=[os.path.dirname(PKG_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GooFish-AIMonitor",
    console=True,            # 保留控制台便于看服务日志(后续可改 windowed)
)
coll = COLLECT(exe, a.binaries, a.datas, name="GooFish-AIMonitor")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="GooFish-AIMonitor.app",
        bundle_identifier="org.tristanwqy.goofish-aimonitor",
    )
