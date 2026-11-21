"""X 网页适配器：主页 HTML 取账号指标，syndication 时间线取帖子（失败时回退主页内嵌推文）。"""

from __future__ import annotations

import json
import re
from urllib.parse import quote

from ..core.http import HttpError, LoginRequired, NotFoundError, ParseError
from .base import PlatformAdapter, PlatformError
from .schema import make_account, make_post

NEXT_DATA = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
FOLLOWERS = re.compile(r'relationship_counts\\":\{\\"followers\\":(\d+),\\"following\\":(\d+)\}')
TWEETS = re.compile(r'tweet_counts\\":\{\\"(?:media_tweets\\":\d+,\\")?tweets\\":(\d+)\}')
REST_ID = re.compile(r'restId:"(\d+)"')
SCREEN_NAME = re.compile(r'property="profile:username" content="([^"]+)"')
HANDLE_IN_URL = re.compile(r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})")
HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}")
SESSION_HANDLE = re.compile(r'screen_name":"([A-Za-z0-9_]{1,15})"')

TWEET_SPLIT = '\\"tweet_results\\":{'
TWEET_ID = re.compile(r'\\"rest_id\\":\\"(\d+)\\"')
TWEET_COUNTS = re.compile(r'\\"counts\\":\{\\"bookmark_count\\":(\d+),\\"favorite_count\\":(\d+),'
                          r'\\"quote_count\\":(\d+),\\"reply_count\\":(\d+),\\"retweet_count\\":(\d+)\}')
TWEET_VIEWS = re.compile(r'\\"views\\":\{\\"count\\":\\"(\d+)\\"\}')
TWEET_CREATED = re.compile(r'\\"created_at_ms\\":(\d+)')
TWEET_TEXT = re.compile(r'\\"full_text\\":\\"(.*?)\\"', re.S)
TWEET_AUTHOR = re.compile(r'\\"screen_name\\":\\"([^"\\]+)\\"')
TWEET_REPLY = re.compile(r'\\"in_reply_to_status_id')


class XAdapter(PlatformAdapter):
    platform = "x"
    label = "X"
    account_metrics = ("followers", "following", "posts_count")
    post_metrics = ("likes", "comments", "shares", "views")
    session_cookie = "auth_token"
    extra_cookies = ("ct0",)
    default_headers = {"Referer": "https://x.com/"}
    profile_url = "https://x.com/{account}"

    def _session_handle(self) -> str:
        """填的是昵称等非 handle 时，用登录会话识别本人 handle。"""
        if not str(self.cfg.get("session_id") or "").strip():
            return ""
        try:
            html = self.http.get_text("https://x.com/home")
        except HttpError:
            return ""
        match = SESSION_HANDLE.search(html)
        if match:
            self.log(f"X 已按登录会话解析账号 handle：{match.group(1)}")
            return match.group(1)
        return ""

    def _handle(self) -> str:
        """规范化账号名：支持 @handle 与主页链接；昵称等非 handle 输入按登录会话识别。"""
        raw = self.account_name.strip()
        match = HANDLE_IN_URL.search(raw)
        handle = match.group(1) if match else (raw if HANDLE.fullmatch(raw) else "")
        if not handle:
            handle = self._session_handle()
        if not handle:
            raise PlatformError(
                f"X 账号名称 “{raw}” 不是有效 handle：请填个人主页 x.com/<handle> 中 @ 后面的"
                "英文、数字或下划线，不是昵称。")
        self.account_name = handle
        return handle

    def _profile_html(self) -> str:
        # 同一次采集里账号与帖子回退共用一份主页 HTML，避免重复请求
        # 公开主页不携带登录态：带 auth_token 时 x.com 会返回登录后的应用外壳，拿不到账号指标
        if getattr(self, "_html", None) is None:
            self._html = self.http.get_text(
                f"https://x.com/{quote(self.account_name, safe='')}", drop_cookies=True)
        return self._html

    def fetch_account(self) -> dict:
        self.require_account()
        self._handle()
        try:
            html = self._profile_html()
        except NotFoundError as e:
            raise PlatformError(
                f"X 账号 @{self.account_name} 不存在（404），请确认 handle 是否正确") from e
        except HttpError as e:
            raise PlatformError(f"打不开 X 主页 @{self.account_name}：{e}") from e

        counts = FOLLOWERS.search(html)
        if not counts:
            raise PlatformError(
                f"未解析到 X 账号 @{self.account_name} 的数据：账号可能不存在、受限，或页面结构已变化")
        tweets = TWEETS.search(html)
        rest = REST_ID.search(html)
        screen = SCREEN_NAME.search(html)
        if rest:
            self.user_id = rest.group(1)
        if screen:
            self.account_name = screen.group(1)
        return make_account(
            self.platform, self.account_name, self.user_id,
            {
                "followers": int(counts.group(1)),
                "following": int(counts.group(2)),
                "posts_count": int(tweets.group(1)) if tweets else None,
            },
            extra={"source": "profile_html"},
        )

    def fetch_posts(self) -> list[dict]:
        self.require_account()
        self._handle()
        try:
            posts = self._posts_from_timeline()
        except HttpError as e:
            self.log(f"X 时间线接口不可用（{e}），改用主页内嵌推文")
            posts = self._posts_from_html()
        return self._fill_views(posts)

    def _fill_views(self, posts: list[dict]) -> list[dict]:
        """时间线接口不返回浏览量，逐条从公开状态页补齐（缺失时才请求）。"""
        missing = [post for post in posts if post.get("views") is None]
        if not missing:
            return posts
        filled = 0
        for post in missing:
            url = post.get("url") or ""
            if not url:
                continue
            try:
                html = self.http.get_text(url, drop_cookies=True)
            except HttpError as e:
                self.log(f"X 浏览量获取失败（{post.get('post_id')}）：{e}")
                continue
            match = TWEET_VIEWS.search(html)
            if match:
                post["views"] = int(match.group(1))
                filled += 1
        if filled:
            self.log(f"X 已补充 {filled}/{len(missing)} 条浏览量")
        return posts

    def _posts_from_timeline(self) -> list[dict]:
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
                    "views": self._views(tweet),
                },
                extra={"quotes": tweet.get("quote_count"),
                       "is_repost": (tweet.get("retweeted_status") is not None)
                       or str(tweet.get("full_text") or "").startswith("RT @"),
                       "is_reply": self._is_reply(tweet)},
            ))
            if len(posts) >= self.max_posts:
                break
        return posts

    def _posts_from_html(self) -> list[dict]:
        """从主页 HTML 内嵌的 tweet_results 解析本人推文（时间线接口限流时的兜底）。"""
        segments = self._profile_html().split(TWEET_SPLIT)[1:]
        if not segments:
            # 主页可正常解析账号指标但未内嵌推文：按本轮 0 条记录，不当作错误
            self.log("X 主页未内嵌推文，本轮按 0 条记录")
            return []
        posts = []
        for segment in segments:
            segment = segment[:8000]
            author = TWEET_AUTHOR.search(segment)
            if author and author.group(1).lower() != self.account_name.lower():
                continue
            post_id = TWEET_ID.search(segment)
            if not post_id:
                continue
            counts = TWEET_COUNTS.search(segment)
            created = TWEET_CREATED.search(segment)
            text = TWEET_TEXT.search(segment)
            raw = text.group(1) if text else ""
            try:
                raw = json.loads('"' + raw + '"')
            except ValueError:
                pass
            metrics = counts.groups() if counts else (None,) * 5
            views = TWEET_VIEWS.search(segment)
            posts.append(make_post(
                self.platform, self.account_name, self.user_id, post_id.group(1),
                created_at=int(created.group(1)) if created else None,
                text=raw,
                url=f"https://x.com/{self.account_name}/status/{post_id.group(1)}",
                media_type="text",
                metrics={"likes": metrics[1], "comments": metrics[3], "shares": metrics[4],
                         "views": views.group(1) if views else None},
                extra={"quotes": metrics[2],
                       "is_repost": "retweeted_status_results" in segment,
                       "is_reply": bool(TWEET_REPLY.search(segment))},
            ))
            if len(posts) >= self.max_posts:
                break
        posts.sort(key=lambda p: p.get("created_at") or "", reverse=True)
        return posts

    @staticmethod
    def _views(tweet: dict):
        """浏览量：时间线接口多为 views.count，部分版本直接给数字。"""
        views = tweet.get("views")
        if isinstance(views, dict):
            return views.get("count")
        return views if views is not None else tweet.get("view_count")

    def _is_reply(self, tweet: dict) -> bool:
        """是否回复他人：有目标账号时比对自身，否则按存在回复目标 ID 判断。"""
        target = tweet.get("in_reply_to_screen_name")
        if isinstance(target, str) and target:
            return target.lower() != (self.account_name or "").lower()
        return bool(tweet.get("in_reply_to_status_id_str")
                    or tweet.get("in_reply_to_user_id_str"))

    def is_repost(self, post: dict) -> bool:
        try:
            return bool(json.loads(post.get("extra_json") or "{}").get("is_repost"))
        except ValueError:
            return False

    def is_reply(self, post: dict) -> bool:
        try:
            return bool(json.loads(post.get("extra_json") or "{}").get("is_reply"))
        except ValueError:
            return False


ADAPTER = XAdapter
