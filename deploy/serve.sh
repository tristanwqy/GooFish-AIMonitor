#!/bin/zsh
# launchd 包装: 加载私有密钥(不入库) → 常驻启动控制台。
set -e
PROJECT_DIR="${XIANYU_PROJECT_DIR:-$HOME/PycharmProjects/xianyu-crawler}"
PYTHON="${XIANYU_PYTHON:-/opt/miniconda3/bin/python}"

# 私有密钥(chmod 600): export XIANYU_SMTP_HOST/USER/PASS 等
[ -f "$HOME/.xianyu.env" ] && source "$HOME/.xianyu.env"

cd "$PROJECT_DIR"
exec "$PYTHON" -m xianyu_crawler.cli serve --host 127.0.0.1 --port 8000
