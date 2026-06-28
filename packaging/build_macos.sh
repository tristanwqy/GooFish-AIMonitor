#!/usr/bin/env bash
# 构建 macOS 桌面应用(.app + 拖拽安装的 .dmg, 含打进包的 Chromium)。
# 依赖: pip install -e . pyinstaller ; cd frontend && npm ci && npm run build
# 用法: bash packaging/build_macos.sh [版本号]   # 版本号缺省 0.0.0-dev
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-0.0.0-dev}"

echo ">> 确保 Playwright 浏览器在缓存里"
python -m playwright install chromium

echo ">> PyInstaller 打包"
rm -rf dist build
python -m PyInstaller packaging/goofish.spec --noconfirm --distpath dist --workpath build

echo ">> 把 Chromium 拷进 .app"
python packaging/copy_browsers.py "dist/GooFish-AIMonitor.app/Contents/Resources/ms-playwright"

# 改动过 bundle 内容后必须重签, 否则下载到别的 Mac 会「已损坏, 无法打开」。
echo ">> ad-hoc 重新签名"
bash packaging/sign_macos.sh "dist/GooFish-AIMonitor.app"

echo ">> 冒烟: 拉起包内 Chromium"
"dist/GooFish-AIMonitor.app/Contents/MacOS/GooFish-AIMonitor" --selfcheck

echo ">> 打 DMG(带「拖到 Applications」入口)"
bash packaging/make_dmg.sh "dist/GooFish-AIMonitor.app" "GooFish-AIMonitor" \
  "GooFish-AIMonitor-macos-arm64-${VERSION}.dmg"

echo "✓ 完成: dist/GooFish-AIMonitor.app + GooFish-AIMonitor-macos-arm64-${VERSION}.dmg"
