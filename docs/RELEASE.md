# 发布桌面安装包

GooFish-AIMonitor 除了 Docker, 还能打成 **Mac/Windows 桌面应用**(双击启动 → 弹出独立应用窗口)。Chromium 直接打进包里, 既当后台抓取引擎, 也用 `--app` 模式渲染控制台窗口; 安装后离线即用。

## 自动发布(推荐)

推一个 `v` 开头的 tag, GitHub Actions 会在 macOS + Windows runner 上各自构建并发到 Release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

[`.github/workflows/release.yml`](../.github/workflows/release.yml) 会产出并上传:

| 平台 | 产物 |
|---|---|
| macOS Apple Silicon | `GooFish-AIMonitor-macos-arm64-<版本>.dmg` |
| Windows x64 | `GooFish-AIMonitor-Setup-<版本>.exe`(Inno Setup 安装程序) |

> 只出 Apple 芯片版 Mac;Intel Mac 用 Docker / 源码方式跑(GitHub Intel runner 排队太久, 且新 Mac 已全面转 Apple 芯片)。

每个平台构建时都会跑一次 `--selfcheck`(拉起包内 Chromium), 失败就让该平台构建红, 避免发出坏包。也可在 Actions 页面用 **workflow_dispatch** 手动触发(不发 Release, 只产 artifact, 用于试构建)。

> **Windows 包只能在 Windows 上构建**(PyInstaller 不跨平台编译), 所以走 CI。

## 本地构建

### macOS

```bash
pip install -e . pyinstaller
(cd frontend && npm ci && npm run build)
bash packaging/build_macos.sh 0.1.0     # → dist/GooFish-AIMonitor.app + GooFish-AIMonitor-macos-arm64-0.1.0.dmg
```

`build_macos.sh` 内部已经做了 **ad-hoc 重签名**(拷完 Chromium 后)和**带「拖到 Applications」入口的 DMG**, 不用再手动 `hdiutil`。

### Windows(需装 Inno Setup 6)

```powershell
pip install -e . pyinstaller
cd frontend; npm ci; npm run build; cd ..
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 0.1.0
# → packaging\Output\GooFish-AIMonitor-Setup-0.1.0.exe
```

## 怎么测

- **冒烟(自动)**:`<可执行文件> --selfcheck` 只验证「能不能拉起打包内的 Chromium」, 打印 `SELFCHECK_OK`。CI 每次构建都跑。
- **手动**:双击安装/运行 → 自动弹出应用窗口(控制台)→ 扫码登录 → 跑一轮看推荐/收藏。关掉窗口即退出应用。
- 数据存用户目录(macOS `~/Library/Application Support/GooFish-AIMonitor`、Windows `%APPDATA%\GooFish-AIMonitor`), 升级/卸载不丢, 与 Docker 版互不干扰。

## 打包是怎么搭的

- [`src/xianyu_crawler/launcher.py`](../src/xianyu_crawler/launcher.py) — 桌面入口:起服务(后台线程)+ 用包内 Chromium 以 `--app` 开应用窗口(关窗即退);打包时把 `PLAYWRIGHT_BROWSERS_PATH` 指向包内 Chromium;`--selfcheck` 冒烟。
- [`packaging/goofish.spec`](../packaging/goofish.spec) — PyInstaller 配置。**故意不让它打 Chromium**(嵌套 .app/权限会让 PyInstaller 报错), 只打 Python + 前端。
- [`packaging/copy_browsers.py`](../packaging/copy_browsers.py) — 构建后把 Chromium 从 Playwright 缓存原样拷进包(保留可执行权限), 运行时由 launcher 指过去。
- [`packaging/sign_macos.sh`](../packaging/sign_macos.sh) — **拷完 Chromium 后给「外层 bundle」重新 ad-hoc 签名**。PyInstaller 出包时已 ad-hoc 签过, 但 `copy_browsers.py` 又往 `Contents/Resources` 塞了 Chromium, 让外层那张资源清单封印失效;不重签的话, 包下载到别的 Mac(带 `com.apple.quarantine`)会被判「已损坏, 无法打开」, 连右键「打开」都救不回。重签外层后退化成普通的「未验证开发者」拦截, 右键「打开」即可放行。**故意不 `--deep`、不动包内 Chromium**:它自带 Playwright/Google 的有效签名(还有 headed 渲染要的 entitlements), 重签反而会抹掉、且对 Chromium 嵌套结构容易签挂搞红构建。
- [`packaging/make_dmg.sh`](../packaging/make_dmg.sh) — 出 DMG 时放上 `.app` + 指向 `/Applications` 的符号链接, 打开 DMG 就能把 App 拖进「应用程序」安装(而不是在只读 DMG 里直接跑, 那样易触发 App Translocation / 打不开)。

> **为什么之前 mac 包打不开?** 不是签名「没签」, 而是签名被 `copy_browsers.py` 后续改动「弄坏」了 → Gatekeeper 报「已损坏」。根因是「先签名、后改 bundle」的顺序, 补一步「改完再重签」即解。若仍想完全免拦截(双击即开), 需自备 Apple 开发者账号做 Developer ID 签名 + 公证(notarize), 本仓库默认不做。
