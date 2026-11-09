"""Instagram 网页适配器：读取本人主页公开数据与最近媒体。"""

from __future__ import annotations

import re

from ..core.http import LoginRequired, ParseError
from .base import PlatformAdapter, PlatformError
from .schema import make_account, make_post, parse_count

PROFILE_API = "https://www.instagram.com/api/v1/users/web_profile_info/"


class InstagramAdapter(PlatformAdapter):
    platform = "instagram"
    label = "Instagram"
    account_metrics = ("followers", "following", "posts_count")
    post_metrics = ("likes", "comments", "views")
    requires_cookie = True
    session_cookie = "sessionid"
    domains = (".instagram.com",)
    default_headers = {
        "x-ig-app-id": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
    }
    profile_url = "https://www.instagram.com/{account}/"

    def _fetch_user(self) -> dict:
        # 同一轮采集内 fetch_account / fetch_posts 共用一份主页数据
        if getattr(self, "_user_cache", None) is not None:
            return self._user_cache
        self.require_account()
        name = self.account_name or self.user_id
        data = self.http.get_json(PROFILE_API, params={"username": name},
                                  headers={**self.default_headers,
                                           "Referer": f"https://www.instagram.com/{name}/"})
        user = (data.get("data") or {}).get("user")
        if not user:
            raise LoginRequired("Instagram 未返回用户数据，请在设置中填写会话锚点 sessionid")
        self._user_cache = user
        return user

    def fetch_account(self) -> dict:
        user = self._fetch_user()
        self.user_id = str(user.get("id") or self.user_id)
        media = user.get("edge_owner_to_timeline_media") or {}
        return make_account(
            self.platform, user.get("username") or self.account_name, self.user_id,
            {
                "followers": parse_count((user.get("edge_followed_by") or {}).get("count")),
                "following": parse_count((user.get("edge_follow") or {}).get("count")),
                "posts_count": parse_count(media.get("count")),
            },
            extra={"full_name": user.get("full_name", ""), "is_private": user.get("is_private")},
        )

    def fetch_posts(self) -> list[dict]:
        user = self._fetch_user()
        edges = ((user.get("edge_owner_to_timeline_media") or {}).get("edges") or [])
        posts = []
        for edge in edges:
            node = edge.get("node") or {}
            post_id = node.get("id") or node.get("shortcode")
            if not post_id:
                continue
            caption = ""
            caption_edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
            if caption_edges:
                caption = ((caption_edges[0] or {}).get("node") or {}).get("text", "")
            likes = (node.get("edge_liked_by") or node.get("edge_media_preview_like") or {}).get("count")
            posts.append(make_post(
                self.platform, self.account_name, self.user_id, post_id,
                created_at=node.get("taken_at_timestamp"),
                text=caption,
                url=f"https://www.instagram.com/p/{node.get('shortcode', '')}/",
                media_type="video" if node.get("is_video") else "image",
                metrics={
                    "likes": likes,
                    "comments": (node.get("edge_media_to_comment") or {}).get("count"),
                    "views": node.get("video_view_count") if node.get("is_video") else None,
                },
                extra={"shortcode": node.get("shortcode"), "is_video": node.get("is_video")},
            ))
            if len(posts) >= self.max_posts:
                break
        return posts

    def verify(self, account: dict) -> dict:
        try:
            html = self.http.get_text(f"https://www.instagram.com/{self.account_name}/",
                                      headers={"Referer": "https://www.instagram.com/"})
        except Exception as e:
            return {"checked": False, "reason": f"{type(e).__name__}: {e}"}
        match = re.search(
            r"([\d.,]+[KMB]?)\s*Followers,\s*([\d.,]+[KMB]?)\s*Following,\s*([\d.,]+[KMB]?)\s*Posts",
            html, re.I)
        if not match:
            return {"checked": False, "reason": "public_page_no_counts"}
        public = {key: parse_count(value) for key, value in
                  zip(("followers", "following", "posts_count"), match.groups())}
        mismatches = [key for key, value in public.items()
                      if value is not None and account.get(key) is not None
                      and value != account.get(key)]
        return {"checked": True, "matches": not mismatches, "public": public,
                "mismatches": mismatches}


ADAPTER = InstagramAdapter
