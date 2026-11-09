"""平台适配器注册表：按平台标识动态加载、卸载与实例化。"""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

from .base import PlatformAdapter

RESERVED = {"__init__", "base", "schema", "browser_session", "__pycache__"}
ORDER = ("x", "instagram", "xiaohongshu", "weibo", "pixiv", "tiktok")
_CACHE: dict[str, type[PlatformAdapter]] = {}


def available() -> list[str]:
    root = Path(__file__).parent
    found = {p.stem for p in root.glob("*.py") if p.stem not in RESERVED}
    if getattr(sys, "frozen", False):
        found |= set(ORDER)  # 打包后模块在归档内，源码文件不可枚举，按内置清单兜底
    ordered = [name for name in ORDER if name in found]
    return ordered + sorted(found - set(ordered))


def load(platform: str) -> type[PlatformAdapter]:
    if platform not in available():
        raise KeyError(f"未找到平台适配器：{platform}")
    if platform in _CACHE:
        return _CACHE[platform]
    module = import_module(f"{__name__}.{platform}")
    cls = getattr(module, "ADAPTER", None)
    if not (isinstance(cls, type) and issubclass(cls, PlatformAdapter)):
        raise TypeError(f"{platform} 适配器缺少 ADAPTER 类或未继承 PlatformAdapter")
    _CACHE[platform] = cls
    return cls


def unload(platform: str) -> None:
    _CACHE.pop(platform, None)
    sys.modules.pop(f"{__name__}.{platform}", None)


def create(platform: str, cfg: dict, http, log=print) -> PlatformAdapter:
    return load(platform)(cfg, http, log=log)


def enabled_ids(cfg: dict) -> list[str]:
    blocks = cfg.get("platforms") or {}
    return [p for p in available()
            if isinstance(blocks.get(p), dict) and blocks[p].get("enabled")]


def session_cookie_name(platform: str) -> str:
    """该平台的会话锚点 Cookie 名（pixiv 为 PHPSESSID）。"""
    return getattr(load(platform), "session_cookie", "") or ""


def extra_cookie_names(platform: str) -> tuple[str, ...]:
    """锚点之外由程序自动获取的必需 Cookie（X 的 ct0、TikTok 的 tt_chain_token）。"""
    return tuple(getattr(load(platform), "extra_cookies", ()) or ())


def user_id_required(platform: str) -> bool:
    """只有小红书、微博、pixiv 必须在设置里填写平台用户 ID。"""
    return bool(getattr(load(platform), "user_id_required", False))


def clean_session_value(platform: str, raw: str) -> str:
    """允许粘贴 `PHPSESSID=xxx`、`xxx; 其他=...` 或纯值，只保留锚点值。"""
    name = session_cookie_name(platform)
    text = (raw or "").strip()
    if name and text.startswith(f"{name}="):
        text = text[len(name) + 1:]
    return text.split(";")[0].strip()


def has_session(block: dict, platform: str) -> bool:
    """必须存在会话锚点；仅附加 Cookie 不能算登录态完整。"""
    if not getattr(load(platform), "requires_cookie", False):
        return True
    block = block or {}
    if str(block.get("session_id") or "").strip():
        return True
    cookies = str(block.get("cookies") or "").strip()
    if not cookies:
        return False
    name = session_cookie_name(platform).strip().lower()
    if not name:
        return True
    for part in cookies.split(";"):
        key = part.split("=", 1)[0].strip().lower()
        if key == name:
            return True
    return False


def session_header(block: dict, platform: str) -> str:
    """锚点 Cookie + 可选附加 Cookie；同名时锚点优先。"""
    block = block or {}
    parts = []
    extra = str(block.get("cookies") or "").strip().rstrip(";")
    if extra:
        parts.append(extra)
    name = session_cookie_name(platform)
    value = clean_session_value(platform, str(block.get("session_id") or ""))
    if name and value:
        parts.append(f"{name}={value}")
    return "; ".join(parts)
