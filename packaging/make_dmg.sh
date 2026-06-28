#!/usr/bin/env bash
# 把 .app 打成带「拖到 Applications 安装」入口的 DMG。
#
# 旧做法 `hdiutil create -srcfolder dist/xxx.app` 直接把单个 .app 塞进 DMG, 用户打开后
# 只看到一个图标, 没有「移动到 Applications」的提示, 多半就直接在只读 DMG 里双击运行 ——
# 既没装到本机, 还会触发 App Translocation(随机只读路径运行), 更容易打不开。
#
# 这里在 staging 目录里放上 .app + 一个指向 /Applications 的符号链接, 打开 DMG 后里面
# 同时有「App 图标」和「应用程序」快捷方式, 用户把 App 拖到「应用程序」即完成安装
# (标准 macOS 安装姿势)。
#
# 注: 没有刻意排版窗口/背景图箭头(那要 osascript 驱动 Finder, 在 headless CI runner 上
# 不稳、易卡构建)。这里给的是「能装」的可靠版: 两个图标都在, 拖一下即可。
#
# 用法: bash packaging/make_dmg.sh <App路径> <卷名> <输出.dmg>
# 例:   bash packaging/make_dmg.sh dist/GooFish-AIMonitor.app GooFish-AIMonitor GooFish-AIMonitor.dmg
set -euo pipefail

APP="${1:?用法: make_dmg.sh <App路径> <卷名> <输出.dmg>}"
VOLNAME="${2:?缺少卷名}"
OUT="${3:?缺少输出 dmg 路径}"

[ -d "$APP" ] || { echo "找不到 .app: $APP" >&2; exit 1; }

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

# ditto 保留签名 / 扩展属性 / 符号链接, 比 cp -R 更安全(不会破坏 codesign 封印)
ditto "$APP" "$STAGING/$(basename "$APP")"

# 「应用程序」快捷方式: 用户把左边的 App 拖到这里即完成安装
ln -s /Applications "$STAGING/Applications"

rm -f "$OUT"
hdiutil create -volname "$VOLNAME" -srcfolder "$STAGING" \
  -fs HFS+ -ov -format UDZO "$OUT"

echo "✓ DMG: $OUT"
