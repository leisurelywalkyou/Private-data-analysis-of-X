"""小红书网页适配器：解析本人主页的 __INITIAL_STATE__ 数据。"""

from __future__ import annotations

import json
import re

from ..core.http import LoginRequired, ParseError
from .base import PlatformAdapter, PlatformError
from .schema import make_account, make_post, parse_count

STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", re.S)


def _iter_notes(obj):
    if isinstance(obj, dict):
        if "noteId" in obj and "interactInfo" in obj:
            yield obj
            return
        for value in obj.values():
            yield from _iter_notes(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_notes(value)


class XiaohongshuAdapter(PlatformAdapter):
    platform = "xiaohongshu"
    label = "小红书"
    account_metrics = ("followers", "following", "posts_count", "likes_total")
    post_metrics = ("likes", "comments", "shares", "saves")
    requires_cookie = True
    session_cookie = "web_session"
    user_id_required = True
    domains = (".xiaohongshu.com",)
    default_headers = {"Referer": "https://www.xiaohongshu.com/"}
    profile_url = "https://www.xiaohongshu.com/user/profile/{id}"

    def _state(self) -> dict:
        self.require_account()
        uid = self.user_id
        if not uid:
            raise PlatformError("小红书需要填写 platform_user_id（主页链接中的用户 ID）")
        html = self.http.get_text(f"https://www.xiaohongshu.com/user/profile/{uid}")
        match = STATE_RE.search(html)
        if not match:
            raise LoginRequired("小红书页面未返回数据，请先登录并填写会话锚点 web_session")
        raw = match.group(1).replace("undefined", "null")
        try:
            return json.loads(raw)
        except ValueError as e:
            raise ParseError("小红书 __INITIAL_STATE__ 解析失败") from e

    def _page(self) -> dict:
        state = self._state()
        user = state.get("user") or {}
        page = user.get("userPageData") or {}
        if not page:
            raise ParseError("小红书页面结构缺少 userPageData")
        return page

    def fetch_account(self) -> dict:
        page = self._page()
        basic = page.get("basicInfo") or {}
        counts = {}
        for item in page.get("interactions") or []:
            name = item.get("name") or ""
            if name:
                counts[name] = parse_count(item.get("count"))
        name = basic.get("nickname") or self.account_name
        return make_account(
            self.platform, name, self.user_id,
            {
                "followers": counts.get("粉丝"),
                "following": counts.get("关注"),
                "posts_count": parse_count(page.get("notesCount")),
                "likes_total": counts.get("获赞与收藏"),
            },
            extra={"red_id": basic.get("redId") or basic.get("red_id"),
                   "desc": basic.get("desc", "")},
        )

    def fetch_posts(self) -> list[dict]:
        page = self._page()
        cards = []
        seen = set()
        for item in _iter_notes(page.get("notes") or []):
            note_id = str(item.get("noteId") or "")
            if note_id and note_id not in seen:
                seen.add(note_id)
                cards.append(item)
        posts = []
        for card in cards:
            inter = card.get("interactInfo") or {}
            posts.append(make_post(
                self.platform, self.account_name, self.user_id, card.get("noteId"),
                created_at=card.get("time"),
                title=card.get("displayTitle"),
                text=card.get("desc") or card.get("displayTitle"),
                url=f"https://www.xiaohongshu.com/explore/{card.get('noteId')}",
                media_type="video" if card.get("type") == "video" else "image",
                metrics={
                    "likes": inter.get("likedCount"),
                    "comments": inter.get("commentCount"),
                    "shares": inter.get("shareCount"),
                    "saves": inter.get("collectedCount"),
                },
                extra={"type": card.get("type")},
            ))
            if len(posts) >= self.max_posts:
                break
        return posts


ADAPTER = XiaohongshuAdapter
