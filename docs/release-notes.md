GooFish-AIMonitor 桌面版 —— 双击安装,打开就是一个**独立的应用窗口**(自带图标和应用名,不是浏览器标签页)。Chromium 已打进包里,装完离线即用;数据存在你自己的用户目录,不外传。

## 下载

- **macOS · Apple 芯片(M1/M2/M3/M4)**:下 `*-macos-arm64-*.dmg`(暂不支持 Intel 芯片 Mac)
- **Windows 10 / 11(64 位)**:下 `*-Setup-*.exe`

## 第一次打开(重要)

这是未签名的个人自用包,首次打开系统会拦一下,放行即可:

- **macOS**:打开 `.dmg` 后把图标**拖进「应用程序」**;再到「应用程序」里 **右键图标 →「打开」**,在弹窗里点「打开」(只需第一次)。或到「系统设置 → 隐私与安全性」点「仍要打开」。
  - 万一仍提示「已损坏」,在「终端」跑一行解掉隔离标记即可:
    `xattr -dr com.apple.quarantine "/Applications/GooFish-AIMonitor.app"`
- **Windows**:出现「Windows 已保护你的电脑」时,点「更多信息 → 仍要运行」。

打开后扫码登录即可使用。

## 它能干嘛

按你的要求自动搜闲鱼、请大模型逐个把关只挑对版的,收藏的东西一降价就邮件提醒;卖掉/下架的链接自动变灰。详见 [README](https://github.com/tristanwqy/GooFish-AIMonitor#readme)。
