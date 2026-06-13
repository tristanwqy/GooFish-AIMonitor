"""Web 进程共享运行时: DB URL + session 工厂(app 与 runner 共用)。"""
from __future__ import annotations

from ..storage.db import make_session
from ..config import Settings

# 绝对路径, 避免 serve 与手动脚本 CWD 不同导致用错 DB
DB_URL = f"sqlite:///{(Settings().data_dir.resolve() / 'xianyu.db')}"


def set_db_url(url: str) -> None:
    global DB_URL
    DB_URL = url


def session():
    return make_session(DB_URL, create=True)
