"""配置加载与全局常量。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

# 统一指标字段：数据库列名 -> X API public_metrics 字段名
METRICS = {
    "likes": "like_count",
    "retweets": "retweet_count",
    "replies": "reply_count",
    "quotes": "quote_count",
    "impressions": "impression_count",
    "bookmarks": "bookmark_count",
}

DEFAULTS = {
    "username": "",
    "bearer_token": "",
    "user_access_token": "",
    "timezone": "Asia/Shanghai",
    "track_recent_days": 7,
    "max_snapshot_tweets": 200,
    "exclude_retweets": True,
    "exclude_replies": False,
    "include_impressions": True,
    "data_dir": "data",
    "report_days": 30,
    "report_dir": "reports",
}


def load_config(path: str = "config.json") -> dict:
    cfg = dict(DEFAULTS)
    p = Path(path)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            cfg.update(json.load(f))

    # 环境变量优先，方便不把密钥写进文件
    cfg["bearer_token"] = os.environ.get("X_BEARER_TOKEN") or cfg.get("bearer_token", "")
    cfg["user_access_token"] = os.environ.get("X_USER_TOKEN") or cfg.get("user_access_token", "")
    cfg["username"] = os.environ.get("X_USERNAME") or cfg.get("username", "")

    cfg["timezone"] = os.environ.get("X_TIMEZONE") or cfg.get("timezone", "Asia/Shanghai")
    return cfg


def get_tz(cfg: dict) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.get("timezone") or "Asia/Shanghai")
    except Exception:
        return ZoneInfo("Asia/Shanghai")
