"""DB session 工厂。"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .orm import Base
from .migrate import ensure_columns

_MIGRATED: set[str] = set()      # 每个 DB 文件每进程只补一次列


def make_session(url: str, create: bool = False) -> Session:
    engine = create_engine(url, future=True)
    if create:
        Base.metadata.create_all(engine)        # 建缺失的表
        if url not in _MIGRATED and url.startswith("sqlite:///") and ":memory:" not in url:
            ensure_columns(url[len("sqlite:///"):])   # 给旧表补缺失列
            _MIGRATED.add(url)
    return Session(engine, future=True)
