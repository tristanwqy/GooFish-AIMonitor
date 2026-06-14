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

# pywebview: UI 原生窗口(含 JS 桥接资源)+ 各平台后端
d, b, h = collect_all("webview")
datas += d
binaries += b
hiddenimports += h
if sys.platform == "darwin":      # WKWebView 走 pyobjc
    hiddenimports += ["webview.platforms.cocoa", "objc", "Foundation", "AppKit", "WebKit", "Quartz"]
elif sys.platform.startswith("win"):   # WebView2 走 pythonnet
    hiddenimports += ["webview.platforms.edgechromium", "clr_loader", "pythonnet"]

a = Analysis(
    [os.path.join(PKG_DIR, "launcher.py")],
    pathex=[os.path.dirname(PKG_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
)
# 图标随仓库带(packaging/make_icon.py 生成); SPECPATH 即本 spec 所在目录
ICON_ICNS = os.path.join(SPECPATH, "appicon.icns")
ICON_ICO = os.path.join(SPECPATH, "appicon.ico")

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GooFish-AIMonitor",
    console=False,           # GUI 应用: 不带终端窗口
    icon=ICON_ICO if sys.platform.startswith("win") else ICON_ICNS,
)
coll = COLLECT(exe, a.binaries, a.datas, name="GooFish-AIMonitor")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="GooFish-AIMonitor.app",
        icon=ICON_ICNS,
        bundle_identifier="org.tristanwqy.goofish-aimonitor",
        info_plist={
            "CFBundleName": "GooFish-AIMonitor",
            "CFBundleDisplayName": "GooFish-AIMonitor",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.utilities",
        },
    )
