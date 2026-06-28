"""配置: Watch(搜索条件) + Settings(运行参数, 密钥走系统环境变量)。"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根 / 数据目录锚定到这里, 与启动 CWD 无关
# (否则从别的目录 `xianyu serve` 会读到另一个空 ./data/xianyu.db)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
# 本地(不入库)配置/密钥文件: 内网接口地址、token、SMTP 等放这里, 不写进仓库
_LOCAL_ENV_FILES = (str(_REPO_ROOT / ".env"), str(_DEFAULT_DATA_DIR / "secret.env"))

# LLM 二次审核的默认系统提示词(唯一权威默认值; 控制台可覆盖)
DEFAULT_REVIEW_SYSTEM_PROMPT = (
    "你是二手商品相关性筛选助手。判断每个商品是否符合用户的「要求」"
    "(型号/规格/成色/价格/正品等综合判断)。"
    "严格判断: 不确定或明显不符、或疑似钓鱼/配件 就 ok=false。"
)


class Watch(BaseModel):
    name: str
    keywords: list[str]
    price_min: float | None = None
    price_max: float | None = None
    city: str | None = None
    condition: list[str] | None = None
    free_shipping: bool | None = None
    seller_min_credit: int | None = None
    want_max_per_run: int = 5
    requirement: str | None = None      # 自然语言要求, 供 LLM 二次审核
    enabled: bool = True


def load_watchlist(path: str | Path) -> list[Watch]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    data: dict = raw if isinstance(raw, dict) else {}
    return [Watch(**w) for w in data.get("watches", [])]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="XIANYU_", env_file=_LOCAL_ENV_FILES, extra="ignore"
    )
    data_dir: Path = _DEFAULT_DATA_DIR
    min_drop_pct: float = 5.0
    min_drop_abs: float = 50.0
    headless: bool = False
    action_delay_min: float = 3.0
    action_delay_max: float = 8.0
    search_url: str = "https://www.goofish.com/search"
    favorites_url: str = "https://www.goofish.com/collection"
    search_max_pages: int = 3
    favorites_max_pages: int = 5
    # 二次审核(LLM 相关性过滤) — 任意 OpenAI 兼容接口。
    # 具体接口地址/密钥放本地 data/secret.env(XIANYU_REVIEW_BASE_URL / XIANYU_REVIEW_API_TOKEN),
    # 不写进仓库; 这里只给通用占位默认。
    review_enabled: bool = True
    review_base_url: str = "https://api.openai.com/v1"
    review_model: str = "doubao-seed-2.0-pro"
    review_api_token: str | None = None
    review_timeout: float = 60.0          # 本地/推理模型偏慢, 给足时间(否则易 ReadTimeout 整批放行)
    review_temperature: float = 0.0
    review_max_tokens: int = 4000         # 推理模型要先思考再出 JSON, 额度太小会导致正文(content)为空
    review_system_prompt: str = DEFAULT_REVIEW_SYSTEM_PROMPT
    # 死链探测: 每轮最多对多少条待审推荐打开详情页核活(防止单轮太久)
    liveness_max_checks: int = 30
    # 密钥(系统环境变量): XIANYU_SMTP_HOST/PORT/USER/PASS, XIANYU_NOTIFY_TO
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_pass: str | None = None
    notify_to: str | None = None
    # 邮件提醒事件开关(控制台可改): 哪些事件触发邮件
    notify_on_new: bool = True         # 发现新推荐
    notify_on_drop: bool = True        # 收藏降价
    notify_on_sold: bool = True        # 收藏/推荐 已售出·下架
    notify_on_favorite: bool = True    # 自动收藏成功(自动收藏流程才会触发)
    notify_on_login: bool = True       # 登录失效
