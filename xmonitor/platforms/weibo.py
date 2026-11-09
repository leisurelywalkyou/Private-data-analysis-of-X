"""微博网页适配器：使用 weibo.com ajax 接口读取本人主页与微博列表。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..core.http import LoginRequired
from .base import PlatformAdapter, PlatformError
from .schema import make_account, make_post, parse_count

TAG_RE = re.compile(r"<[^>]+>")
PROFILE_API = "https://weibo.com/ajax/profile/info"
TIMELINE_API = "https://weibo.com/ajax/statuses/mymblog"


def _relative_time(text: str) -> str | None:
    now = datetime.now(timezone.utc)
    text = (text or "").strip()
    if not text:
        return None
    if text in ("刚刚", "现在"):
        return now.replace(microsecond=0).isoformat()
    match = re.match(r"(\d+)\s*分钟前", text)
    if match:
        return (now - timedelta(minutes=int(match.group(1)))).replace(microsecond=0).isoformat()
    match = re.match(r"(\d+)\s*小时前", text)
    if match:
        return (now - timedelta(hours=int(match.group(1)))).replace(microsecond=0).isoformat()
    match = re.match(r"今天\s*(\d{1,2}):(\d{2})", text)
    if match:
        local = now.astimezone(timezone(timedelta(hours=8)))
        dt = local.replace(hour=int(match.group(1)), minute=int(match.group(2)),
                           second=0, microsecond=0)
        return dt.astimezone(timezone.utc).isoformat()
    return text


class WeiboAdapter(PlatformAdapter):
    platform = "weibo"
    label = "微博"
    account_metrics = ("followers", "following", "posts_count")
    post_metrics = ("likes", "comments", "shares")
    requires_cookie = True
    session_cookie = "SUB"
    user_id_required = True
    domains = (".weibo.com", ".weibo.cn")
    default_headers = {"Referer": "https://weibo.com/"}
    profile_url = "https://weibo.com/u/{id}"

    def _uid(self) -> str:
        if self.user_id:
            return self.user_id
        if self.account_name.isdigit():
            return self.account_name
        raise PlatformError("微博需要填写 platform_user_id（数字 UID）")

    def fetch_account(self) -> dict:
        data = self.http.get_json(PROFILE_API, params={"uid": self._uid()})
        user = ((data.get("data") or {}).get("user")) or {}
        if not user:
            raise LoginRequired("微博未返回用户数据，请先登录并填写会话锚点 SUB")
        self.user_id = str(user.get("idstr") or self.user_id)
        return make_account(
            self.platform, user.get("screen_name") or self.account_name, self.user_id,
            {
                "followers": parse_count(user.get("followers_count")),
                "following": parse_count(user.get("friends_count")),
                "posts_count": parse_count(user.get("statuses_count")),
            },
            extra={"verified": bool(user.get("verified")), "location": user.get("location", "")},
        )

    def fetch_posts(self) -> list[dict]:
        posts = []
        seen = set()
        for page in range(1, 4):
            data = self.http.get_json(TIMELINE_API,
                                      params={"uid": self._uid(), "page": page, "feature": 0})
            items = ((data.get("data") or {}).get("list")) or []
            for item in items:
                mid = str(item.get("mid") or item.get("id") or "")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                text = TAG_RE.sub("", item.get("text_raw") or item.get("text") or "")
                posts.append(make_post(
                    self.platform, self.account_name, self.user_id, mid,
                    created_at=_relative_time(item.get("created_at")),
                    text=text,
                    url=f"https://m.weibo.cn/detail/{mid}",
                    media_type="repost" if item.get("retweeted_status") else "text",
                    metrics={
                        "likes": item.get("attitudes_count"),
                        "comments": item.get("comments_count"),
                        "shares": item.get("reposts_count"),
                    },
                    extra={"is_repost": item.get("retweeted_status") is not None,
                           "source": TAG_RE.sub("", item.get("source") or "")},
                ))
                if len(posts) >= self.max_posts:
                    return posts
            if not items:
                break
        return posts

    def is_repost(self, post: dict) -> bool:
        return post.get("media_type") == "repost"


ADAPTER = WeiboAdapter
