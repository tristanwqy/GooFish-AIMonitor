#!/bin/zsh
# launchd 包装脚本: 加载私有密钥(不入库) → 跑一次 crawler。
# 按需改下面两行的 PROJECT_DIR / PYTHON。
set -e
PROJECT_DIR="${XIANYU_PROJECT_DIR:-$HOME/PycharmProjects/xianyu-crawler}"
PYTHON="${XIANYU_PYTHON:-/opt/miniconda3/bin/python}"

# 私有密钥文件(不在仓库, 建议 chmod 600): 内含
#   export XIANYU_SMTP_HOST=... XIANYU_SMTP_USER=... XIANYU_SMTP_PASS=... XIANYU_NOTIFY_TO=...
[ -f "$HOME/.xianyu.env" ] && source "$HOME/.xianyu.env"

cd "$PROJECT_DIR"
exec "$PYTHON" -m xianyu_crawler.cli run
