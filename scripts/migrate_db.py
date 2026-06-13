"""手动跑列迁移(serve 启动也会自动跑, 见 storage/db.make_session)。

用法: python scripts/migrate_db.py [db_path]
"""
from __future__ import annotations

import sys
from pathlib import Path

from xianyu_crawler.storage.migrate import ensure_columns


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/xianyu.db")
    if not path.exists():
        print(f"DB 不存在, 跳过(首次 serve 时会建全): {path}")
        return
    n = ensure_columns(path)
    print(f"完成: 新增 {n} 列 → {path}")


if __name__ == "__main__":
    main()
