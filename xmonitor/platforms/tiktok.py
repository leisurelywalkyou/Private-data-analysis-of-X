"""TikTok 网页适配器：解析主页 __UNIVERSAL_DATA_FOR_REHYDRATION__。"""

from __future__ import annotations

import json
import re

from ..core.http import LoginRequired, ParseError
from .base import PlatformAdapter, PlatformError
from .schema import make_account, make_post, parse_count

STATE_RE = re.compile(
    r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S)
ITEM_API = "https://www.tiktok.com/api/post/item_list/"


class TikTokAdapter(PlatformAdapter):
    platform = "tiktok"
    label = "TikTok"
    account_metrics = ("followers", "following", "posts_count", "likes_total")
    post_metrics = ("likes", "comments", "shares", "saves", "views")
    requires_cookie = True
    session_cookie = "sessionid"
    extra_cookies = ("tt_chain_token",)
    domains = (".tiktok.com",)
    default_headers = {"Referer": "https://www.tiktok.com/"}
    profile_url = "https://www.tiktok.com/@{account}"

    def _load(self) -> tuple[dict, list]:
        # 同一轮采集内 fetch_account / fetch_posts 共用一份页面数据
        cached = getattr(self, "_cache", None)
        if cached is not None:
            return cached
        self.require_account()
        handle = self.account_name or self.user_id
        html = self.http.get_text(f"https://www.tiktok.com/@{handle}")
        match = STATE_RE.search(html)
        if not match:
            raise LoginRequired("TikTok 页面未返回数据，请先登录并填写会话锚点 sessionid")
        try:
            data = json.loads(match.group(1))
        except ValueError as e:
            raise ParseError("TikTok 页面 JSON 解析失败") from e
        scope = data.get("__DEFAULT_SCOPE__") or {}
        detail = scope.get("webapp.user-detail") or {}
        user_info = detail.get("userInfo") or {}
        user = user_info.get("user") or {}
        if not user:
            raise PlatformError("TikTok 页面缺少用户信息")
        items = detail.get("itemList") or user_info.get("itemList") or []
        if not items:
            items = self._api_items(user.get("secUid"))
        self._cache = (user, items)
        return self._cache

    def _api_items(self, sec_uid: str | None) -> list:
        if not sec_uid:
            return []
        data = self.http.get_json(ITEM_API, params={
            "secUid": sec_uid,
            "count": min(self.max_posts, 35),
            "cursor": "0",
            "aid": "1988",
            "app_name": "tiktok_web",
            "device_platform": "web_pc",
        })
        return data.get("itemList") or []

    def fetch_account(self) -> dict:
        user, _items = self._load()
        stats = user.get("stats") or {}
        self.user_id = str(user.get("id") or user.get("secUid") or self.user_id)
        return make_account(
            self.platform, user.get("uniqueId") or self.account_name, self.user_id,
            {
                "followers": parse_count(stats.get("followerCount")),
                "following": parse_count(stats.get("followingCount")),
                "posts_count": parse_count(stats.get("videoCount")),
                "likes_total": parse_count(stats.get("heartCount")),
            },
            extra={"nickname": user.get("nickname", ""), "secUid": user.get("secUid")},
        )

    def fetch_posts(self) -> list[dict]:
        _user, items = self._load()
        posts = []
        for item in items:
            stats = item.get("stats") or {}
            post_id = item.get("id")
            if not post_id:
                continue
            posts.append(make_post(
                self.platform, self.account_name, self.user_id, post_id,
                created_at=item.get("createTime"),
                text=item.get("desc"),
                url=f"https://www.tiktok.com/@{self.account_name}/video/{post_id}",
                media_type="video",
                metrics={
                    "likes": stats.get("diggCount"),
                    "comments": stats.get("commentCount"),
                    "shares": stats.get("shareCount"),
                    "saves": stats.get("collectCount"),
                    "views": stats.get("playCount"),
                },
                extra={"duration": item.get("video", {}).get("duration")},
            ))
            if len(posts) >= self.max_posts:
                break
        return posts

    def verify(self, account: dict) -> dict:
        try:
            html = self.http.get_text(f"https://www.tiktok.com/@{self.account_name}")
        except Exception as e:
            return {"checked": False, "reason": f"{type(e).__name__}: {e}"}
        match = re.search(
            r"([\d.,KMB]+)\s*Followers,\s*([\d.,KMB]+)\s*Following", html, re.I)
        if not match:
            return {"checked": False, "reason": "public_page_no_counts"}
        public = {"followers": parse_count(match.group(1)),
                  "following": parse_count(match.group(2))}
        mismatches = [key for key, value in public.items()
                      if value is not None and account.get(key) is not None
                      and value != account.get(key)]
        return {"checked": True, "matches": not mismatches, "public": public,
                "mismatches": mismatches}


ADAPTER = TikTokAdapter
