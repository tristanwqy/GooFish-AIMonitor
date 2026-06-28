#!/usr/bin/env bash
# 给 .app 打 ad-hoc 签名并校验。
#
# 为什么必须有这一步(否则别的 Mac 上「已损坏, 无法打开」):
#   PyInstaller 产出的 .app 自带 ad-hoc 签名, 但构建后 copy_browsers.py 又把 Chromium
#   拷进 Contents/Resources/ms-playwright —— 这改动了 bundle 内容, 让原签名里对 Resources
#   的封印(CodeResources)对不上了。这个包在本机(无 quarantine)还能跑, 但一旦经浏览器
#   下载到别人 Mac(带 com.apple.quarantine), Gatekeeper 校验封印失败 →
#   「"GooFish-AIMonitor" 已损坏, 你应该把它移到废纸篓」。这种「已损坏」连右键「打开」
#   都救不回来(损坏弹窗没有「打开」按钮)。
#   改完内容后对「外层 bundle」重新 ad-hoc 签一次, 让这张资源清单封印重新对上;
#   之后下载只会是普通的「未验证的开发者」拦截(右键 →「打开」即可放行), 不再是「已损坏」。
#
# 用法: bash packaging/sign_macos.sh <App路径>
set -euo pipefail

APP="${1:?用法: sign_macos.sh <App路径>}"
[ -d "$APP" ] || { echo "找不到 .app: $APP" >&2; exit 1; }

# 只重签「外层 bundle」, 故意不 --deep、不碰打进包的 Chromium:
#   坏掉的只是外层那张「资源清单封印」(copy_browsers 往 Resources 里塞了 Chromium,
#   清单和实际内容对不上了)。重签外层会按当前内容重算这张清单 → 封印重新有效, 「已损坏」即解。
#   打进包的 Chromium 自带 Playwright/Google 的有效签名(还带 headed 渲染要用的 allow-jit
#   等 entitlements), 用 --deep 重签反而会把这些 entitlements 抹掉, 且对 Chromium 那种带
#   符号链接 framework + 多层 helper 的嵌套结构容易签挂、把整条构建搞红。它本就有效, 不用动。
# --sign -          : ad-hoc 签名(无需 Apple 开发者账号)
# --force           : 覆盖外层既有签名
# --timestamp=none  : ad-hoc 不需要(也拿不到)安全时间戳, 关掉省一次联网
echo ">> ad-hoc 重签外层 bundle(不动包内 Chromium 的既有签名)"
codesign --force --sign - --timestamp=none "$APP"

# 关键校验(硬卡): 外层封印必须有效 —— 这正是之前「已损坏」的根因, 失败即让构建红, 绝不发坏包。
echo ">> 校验外层签名封印"
codesign --verify --verbose=2 "$APP"

# 附加(仅告警): 深度校验整棵树的嵌套签名(主要是我们没改过的 Playwright Chromium)。
# 第三方嵌套包对 --strict 偶有无害告警, 故不挡构建; 真·回归由上面的硬卡 + --selfcheck 兜底。
echo ">> 深度校验(仅告警)"
codesign --verify --deep --strict --verbose=2 "$APP" \
  || echo "⚠️ 深度校验有告警(通常不影响打开), 见上。"

echo "✓ 签名有效: $APP"
