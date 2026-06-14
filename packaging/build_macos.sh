#!/usr/bin/env bash
# 构建 macOS 桌面应用(.app, 含打进包的 Chromium)。
# 依赖: pip install -e . pyinstaller ; cd frontend && npm ci && npm run build
set -euo pipefail
cd "$(dirname "$0")/.."

echo ">> 确保 Playwright 浏览器在缓存里"
python -m playwright install chromium

echo ">> PyInstaller 打包"
rm -rf dist build
python -m PyInstaller packaging/goofish.spec --noconfirm --distpath dist --workpath build

echo ">> 把 Chromium 拷进 .app"
python packaging/copy_browsers.py "dist/GooFish-AIMonitor.app/Contents/Resources/ms-playwright"

echo ">> 冒烟: 拉起包内 Chromium"
"dist/GooFish-AIMonitor.app/Contents/MacOS/GooFish-AIMonitor" --selfcheck

echo "✓ 完成: dist/GooFish-AIMonitor.app"
