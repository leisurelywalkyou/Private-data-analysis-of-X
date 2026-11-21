"""小红书网页适配器：优先用浏览器渲染通道，HTTP 直连作为兜底。

小红书已对未登录请求强制跳登录，主页数据也改为前端异步加载，
因此默认经真实浏览器读取页面状态并拦截笔记接口；仅当浏览器不可用时退回 HTTP 解析。
"""

from __future__ import annotations

import json
import re

from ..core.http import LoginRequired, ParseError
from . import xhs_browser
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

    def __init__(self, cfg: dict, http, log=print):
        super().__init__(cfg, http, log=log)
        self._rendered: dict | None = None
        self._render_tried = False
        try:
            self.detail_limit = max(0, int(cfg.get("note_detail_limit", 10)))
        except (TypeError, ValueError):
            self.detail_limit = 10

    # ---------- 浏览器渲染通道 ----------
    def _render(self) -> dict:
        """一轮采集只打开一次浏览器，账号与笔记共用结果。

        只读取主页「笔记」tab（user.notes）里本人发布的作品，
        不采集收藏、点赞过的他人笔记。
        """
        if self._render_tried:
            return self._rendered or {}
        self._render_tried = True
        if str(self.cfg.get("render") or "auto").lower() == "http":
            return {}
        self.require_account()
        if not self.user_id:
            raise PlatformError("小红书需要填写 platform_user_id（主页链接中的用户 ID）")
        try:
            self._rendered = xhs_browser.fetch_page(
                self.cfg, self.user_id, max_posts=self.max_posts,
                detail_limit=self.detail_limit, log=self.log)
        except xhs_browser.BrowserUnavailable as e:
            self.log(f"小红书浏览器通道不可用（{e}），回退 HTTP 解析")
            self._rendered = {}
        return self._rendered

    # ---------- HTTP 兜底通道 ----------
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

    # ---------- 统一取数 ----------
    def fetch_account(self) -> dict:
        rendered = self._render()
        account = rendered.get("account") if rendered else None
        if account:
            return make_account(
                self.platform, account.get("nickname") or self.account_name,
                self.user_id,
                {key: account.get(key) for key in self.account_metrics},
                extra={"red_id": account.get("red_id") or "",
                       "desc": account.get("desc") or ""},
            )
        page = self._page()
        basic = page.get("basicInfo") or page.get("basic_info") or {}
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
                "posts_count": parse_count(page.get("notesCount")
                                           or page.get("notes_count")),
                "likes_total": counts.get("获赞与收藏"),
            },
            extra={"red_id": basic.get("redId") or basic.get("red_id"),
                   "desc": basic.get("desc", "")},
        )

    def fetch_posts(self) -> list[dict]:
        rendered = self._render()
        notes = (rendered.get("notes") or []) if rendered else []
        if notes:
            posts = []
            for note in notes[: self.max_posts]:
                note_id = str(note.get("id") or "")
                if not note_id:
                    continue
                token = note.get("token") or ""
                url = f"https://www.xiaohongshu.com/explore/{note_id}"
                if token:
                    url += f"?xsec_token={token}&xsec_source=pc_user"
                posts.append(make_post(
                    self.platform, self.account_name, self.user_id, note_id,
                    created_at=note.get("time"),
                    title=note.get("title"),
                    text=note.get("desc") or note.get("title"),
                    url=url,
                    media_type="video" if note.get("type") == "video" else "image",
                    metrics={key: note.get(key)
                             for key in ("likes", "comments", "shares", "saves")},
                    extra={"type": note.get("type")},
                ))
            return posts

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
