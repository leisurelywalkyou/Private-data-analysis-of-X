"""平台适配器统一接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.http import HttpClient


class PlatformError(RuntimeError):
    """采集失败：请求、解析或配置错误。"""


class PlatformAdapter(ABC):
    """各平台只实现请求与解析，调度、清洗、存储由核心复用。"""

    platform = ""
    label = ""
    account_metrics: tuple[str, ...] = ()
    post_metrics: tuple[str, ...] = ()
    requires_cookie = False
    session_cookie = ""
    user_id_required = False
    extra_cookies: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    default_headers: dict[str, str] = {}
    profile_url = ""

    def __init__(self, cfg: dict, http: HttpClient, log=print):
        self.cfg = cfg or {}
        self.log = log
        self.http = http
        self.account_name = str(self.cfg.get("account_name") or "").strip().lstrip("@")
        self.user_id = str(self.cfg.get("platform_user_id") or "").strip()
        try:
            self.max_posts = max(1, min(200, int(self.cfg.get("max_posts") or 50)))
        except (TypeError, ValueError):
            self.max_posts = 50

    def require_account(self) -> None:
        if not (self.account_name or self.user_id):
            raise PlatformError("请在设置中填写账号名称与 platform_user_id")

    @abstractmethod
    def fetch_account(self) -> dict:
        """返回统一账号字段：followers / following / posts_count / likes_total。"""

    @abstractmethod
    def fetch_posts(self) -> list[dict]:
        """返回统一帖子字段，按时间倒序，数量由 max_posts 限制。"""

    def is_repost(self, post: dict) -> bool:
        return bool(post.get("is_repost"))

    def verify(self, account: dict) -> dict:
        """用第二个来源交叉校验账号数据；无第二来源时明确标记。"""
        return {"checked": False, "reason": "single_source"}
