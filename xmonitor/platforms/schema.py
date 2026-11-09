"""多平台统一字段定义与归一化工具。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

ACCOUNT_BASE = ("platform", "account_name", "platform_user_id", "captured_at")
ACCOUNT_METRICS = ("followers", "following", "posts_count", "likes_total")
ACCOUNT_TAIL = ("extra_json",)

POST_BASE = ("platform", "account_name", "platform_user_id", "post_id",
             "created_at", "title", "text", "url", "media_type")
POST_METRICS = ("likes", "comments", "shares", "saves", "views")
POST_TAIL = ("extra_json", "first_seen_at", "updated_at")

SNAP_BASE = ("platform", "post_id", "slot")


def account_columns(metrics: tuple[str, ...]) -> list[str]:
    return [*ACCOUNT_BASE, *metrics, *ACCOUNT_TAIL]


def post_columns(metrics: tuple[str, ...]) -> list[str]:
    return [*POST_BASE, *metrics, *POST_TAIL]


def snapshot_columns(metrics: tuple[str, ...]) -> list[str]:
    return [*SNAP_BASE, *metrics]


def parse_count(value: Any) -> int | None:
    """把 1234 / "1,234" / "1.2万" / "3.4亿" 归一为整数，空值返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "").replace("+", "")
    scale = 1
    for suffix, factor in (("万", 10_000), ("億", 100_000_000), ("亿", 100_000_000),
                           ("w", 10_000), ("k", 1_000), ("K", 1_000), ("M", 1_000_000)):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            scale = factor
            break
    try:
        return int(float(text) * scale)
    except ValueError:
        return None


def parse_time(value: Any) -> str | None:
    """支持 Unix 秒/毫秒、ISO、RFC 822 与常见微博相对时间，统一为 UTC ISO。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e12:
            seconds /= 1000
        return datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=0).isoformat()
    text = str(value).strip()
    if text.isdigit():
        return parse_time(int(text))
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        return None


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def extra_json(extra: dict | None) -> str:
    if not extra:
        return ""
    return json.dumps(extra, ensure_ascii=False, separators=(",", ":"))


def make_account(platform: str, name: str, user_id: str, metrics: dict,
                 extra: dict | None = None) -> dict:
    row = {
        "platform": platform,
        "account_name": name,
        "platform_user_id": str(user_id or ""),
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "extra_json": extra_json(extra),
    }
    for key in ACCOUNT_METRICS:
        row[key] = metrics.get(key)
    return row


def make_post(platform: str, name: str, user_id: str, post_id: Any, *,
              created_at: Any, text: Any = "", title: Any = "", url: str = "",
              media_type: str = "", metrics: dict | None = None,
              extra: dict | None = None) -> dict:
    row = {
        "platform": platform,
        "account_name": name,
        "platform_user_id": str(user_id or ""),
        "post_id": str(post_id or ""),
        "created_at": parse_time(created_at) or "",
        "title": clean_text(title),
        "text": clean_text(text),
        "url": url,
        "media_type": media_type,
        "extra_json": extra_json(extra),
    }
    for key in POST_METRICS:
        row[key] = parse_count((metrics or {}).get(key))
    return row
