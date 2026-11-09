"""X 网页适配器：使用公开 syndication 接口，不调用官方 API。"""

from __future__ import annotations

import json
import re

from ..core.http import LoginRequired, ParseError
from .base import PlatformAdapter, PlatformError
from .schema import make_account, make_post, parse_count

NEXT_DATA = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class XAdapter(PlatformAdapter):
    platform = "x"
    label = "X"
    account_metrics = ("followers", "following", "posts_count")
    post_metrics = ("likes", "comments", "shares")
    session_cookie = "auth_token"
    extra_cookies = ("ct0",)
    default_headers = {"Referer": "https://x.com/"}
    profile_url = "https://x.com/{account}"

    def fetch_account(self) -> dict:
        self.require_account()
        info = self.http.get_json(
            "https://cdn.syndication.twimg.com/widgets/followbutton/info.json",
            params={"screen_names": self.account_name},
        )
        rows = info if isinstance(info, list) else []
        if not rows:
            raise PlatformError(f"未找到 X 账号 @{self.account_name}，请确认账号名与会话锚点")
        row = rows[0]
        self.user_id = str(row.get("id_str") or row.get("id") or self.user_id)
        return make_account(
            self.platform, row.get("screen_name") or self.account_name, self.user_id,
            {
                "followers": parse_count(row.get("followers_count")),
                "following": parse_count(row.get("following_count")),
                "posts_count": parse_count(row.get("tweet_count") or row.get("statuses_count")),
            },
            extra={"verified": bool(row.get("verified"))},
        )

    def fetch_posts(self) -> list[dict]:
        self.require_account()
        html = self.http.get_text(
            f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{self.account_name}"
        )
        if "Log in" in html and "timeline" not in html:
            raise LoginRequired("X 时间线要求登录，请在设置中填写会话锚点 auth_token")
        match = NEXT_DATA.search(html)
        if not match:
            raise ParseError("未能解析 X 时间线数据，页面结构可能已变化")
        try:
            data = json.loads(match.group(1))
        except ValueError as e:
            raise ParseError("X 时间线 JSON 解析失败") from e

        entries = (((data.get("props") or {}).get("pageProps") or {})
                   .get("timeline") or {}).get("entries") or []
        posts = []
        for entry in entries:
            tweet = (entry.get("content") or {}).get("tweet")
            if not isinstance(tweet, dict):
                continue
            post_id = tweet.get("id_str") or tweet.get("id")
            if not post_id:
                continue
            media = tweet.get("extended_entities") or tweet.get("entities") or {}
            media_items = (media.get("media") or []) if isinstance(media, dict) else []
            media_type = media_items[0].get("type", "photo") if media_items else "text"
            posts.append(make_post(
                self.platform, self.account_name, self.user_id, post_id,
                created_at=tweet.get("created_at"),
                text=tweet.get("full_text") or tweet.get("text") or "",
                url=f"https://x.com/{self.account_name}/status/{post_id}",
                media_type=media_type,
                metrics={
                    "likes": tweet.get("favorite_count"),
                    "comments": tweet.get("reply_count"),
                    "shares": tweet.get("retweet_count"),
                },
                extra={"quotes": tweet.get("quote_count"),
                       "is_repost": (tweet.get("retweeted_status") is not None)
                       or str(tweet.get("full_text") or "").startswith("RT @")},
            ))
            if len(posts) >= self.max_posts:
                break
        return posts

    def is_repost(self, post: dict) -> bool:
        try:
            return bool(json.loads(post.get("extra_json") or "{}").get("is_repost"))
        except ValueError:
            return False


ADAPTER = XAdapter
