"""闲鱼账号头像缓存。

从登录态页面抓到的头像 URL 落地到 data/account.json, 给控制台「已登录」处展示。
默认灰头像(没设过自定义头像)视为无头像 → 不展示, 前端回退昵称首字母。
"""
from __future__ import annotations

import json

from ..config import Settings

# 淘宝/闲鱼默认灰头像标记: 命中即视为"未设头像", 不展示
_DEFAULT_MARKERS = ("TB1LFGeKVXXXXbCaXXX07tlTXXX",)


def _path():
    return Settings().data_dir / "account.json"


def save(avatar_url: str | None) -> None:
    """落地头像 URL; 默认灰头像或空 → 存 null(前端回退字母)。"""
    url = (avatar_url or "").replace("\\/", "/").strip()
    if not url or any(m in url for m in _DEFAULT_MARKERS):
        url = None
    elif url.startswith("http://"):          # 统一 https, 防控制台升级 https 后混合内容被拦
        url = "https://" + url[len("http://"):]
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"avatar": url}, ensure_ascii=False), encoding="utf-8")


def avatar() -> str | None:
    """读缓存头像; 无则 None。"""
    p = _path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("avatar")
    except Exception:
        return None
