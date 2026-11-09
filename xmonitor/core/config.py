"""配置加载、路径解析与全局常量。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

# 项目根目录：所有相对路径（配置、数据、报告）都以它为基准，避免依赖启动目录
# 打包为绿色版后，根目录取可执行文件所在目录（data/、reports/ 与 exe 同级，便于整包移动）
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_NAME = "config.json"

COMMON_PLATFORM = {
    "enabled": False,
    "account_name": "",
    "platform_user_id": "",
    "session_id": "",
    "cookies": "",
    "use_browser_cookies": False,
    "max_posts": 50,
    "timeout": 20,
    "filters": {
        "include_keywords": [],
        "exclude_keywords": [],
        "exclude_reposts": False,
        "only_changed": False,
    },
    "retry": {
        "max_attempts": 4,
        "backoff_seconds": 2,
        "backoff_max_seconds": 60,
    },
    "rate_limit": {
        "min_interval_seconds": 3,
        "max_requests_per_minute": 20,
    },
}


def _platform(enabled: bool, min_interval: float) -> dict:
    block = json.loads(json.dumps(COMMON_PLATFORM))
    block["enabled"] = enabled
    block["rate_limit"]["min_interval_seconds"] = min_interval
    return block


DEFAULTS = {
    "timezone": "Asia/Shanghai",
    "data_dir": "data",
    "report_days": 30,
    "report_dir": "reports",
    "collect_interval_minutes": 30,
    "max_consecutive_failures": 3,
    "cooldown_minutes": 60,
    "browser": {
        "channel": "auto",
    },
    "platforms": {
        "x": _platform(True, 3),
        "instagram": _platform(False, 5),
        "xiaohongshu": _platform(False, 6),
        "weibo": _platform(False, 3),
        "pixiv": _platform(False, 2),
        "tiktok": _platform(False, 5),
    },
    "pet": {
        "x": None,
        "y": None,
    },
}


def _deep_merge(base: dict, extra: dict) -> dict:
    """嵌套字典逐层合并，避免配置文件里的局部字段覆盖整块默认值。"""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def resolve_path(path: str | Path) -> Path:
    """相对路径按项目根解析；绝对路径原样返回。"""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def data_dir(cfg: dict) -> Path:
    return resolve_path(cfg.get("data_dir") or "data")


def report_dir(cfg: dict) -> Path:
    return resolve_path(cfg.get("report_dir") or "reports")


def load_config(path: str | None = None) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    p = resolve_path(path or DEFAULT_CONFIG_NAME)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            _deep_merge(cfg, json.load(f))

    cfg["timezone"] = os.environ.get("X_TIMEZONE") or cfg.get("timezone", "Asia/Shanghai")
    for platform, block in (cfg.get("platforms") or {}).items():
        env = os.environ.get(f"X_SESSION_{platform.upper()}")
        if env:
            block["session_id"] = env
        legacy = os.environ.get(f"X_COOKIE_{platform.upper()}")
        if legacy:
            block["cookies"] = legacy
    return cfg


def save_config(cfg: dict, updates: dict, path: str | None = None) -> dict:
    """把界面改动写回配置文件：只合并本次改动的字段，保留其余手工配置。"""
    p = resolve_path(path or DEFAULT_CONFIG_NAME)
    raw = {}
    if p.exists():
        raw = json.loads(p.read_text(encoding="utf-8"))
    _deep_merge(raw, updates)
    _deep_merge(cfg, updates)
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cfg


def get_tz(cfg: dict) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.get("timezone") or "Asia/Shanghai")
    except Exception:
        return ZoneInfo("Asia/Shanghai")
