"""pixiv 网页适配器：读取本人作品列表并逐条取详情。"""

from __future__ import annotations

import re

from ..core.http import HttpError
from .base import PlatformAdapter, PlatformError
from .schema import make_account, make_post

TAG_RE = re.compile(r"<[^>]+>")
BASE = "https://www.pixiv.net/ajax"


class PixivAdapter(PlatformAdapter):
    platform = "pixiv"
    label = "pixiv"
    account_metrics = ("posts_count",)
    post_metrics = ("likes", "comments", "saves", "views")
    requires_cookie = True
    session_cookie = "PHPSESSID"
    user_id_required = True
    domains = (".pixiv.net",)
    default_headers = {"Referer": "https://www.pixiv.net/"}
    profile_url = "https://www.pixiv.net/users/{id}"

    def _uid(self) -> str:
        if self.user_id:
            return self.user_id
        if self.account_name.isdigit():
            return self.account_name
        raise PlatformError("pixiv 需要填写 platform_user_id（数字用户 ID）")

    def _all_works(self) -> dict:
        # 同一轮采集内 fetch_account / fetch_posts 共用一份作品索引
        if getattr(self, "_works_cache", None) is not None:
            return self._works_cache
        data = self.http.get_json(f"{BASE}/user/{self._uid()}/profile/all",
                                  params={"lang": "zh"})
        if data.get("error"):
            raise PlatformError(f"pixiv 返回错误：{data.get('message')}")
        self._works_cache = data.get("body") or {}
        return self._works_cache

    def fetch_account(self) -> dict:
        body = self._all_works()
        illusts = body.get("illusts") or {}
        manga = body.get("manga") or {}
        novels = body.get("novels") or {}
        return make_account(
            self.platform, self.account_name, self.user_id,
            {"posts_count": len(illusts) + len(manga) + len(novels)},
            extra={"illusts": len(illusts), "manga": len(manga), "novels": len(novels),
                   "followers_available": False},
        )

    def fetch_posts(self) -> list[dict]:
        body = self._all_works()
        ids = []
        for bucket in ("illusts", "manga"):
            ids.extend((body.get(bucket) or {}).keys())
        ids = [i for i in ids if str(i).isdigit()]
        ids.sort(key=int, reverse=True)
        posts = []
        for work_id in ids[: self.max_posts]:
            try:
                detail = self.http.get_json(f"{BASE}/illust/{work_id}", params={"lang": "zh"})
            except HttpError as e:
                self.log(f"pixiv 作品 {work_id} 详情失败：{e}")
                continue
            item = detail.get("body") or {}
            if not item:
                continue
            posts.append(make_post(
                self.platform, self.account_name, self.user_id, work_id,
                created_at=item.get("createDate") or item.get("uploadDate"),
                title=item.get("title"),
                text=TAG_RE.sub("", item.get("description") or ""),
                url=f"https://www.pixiv.net/artworks/{work_id}",
                media_type="illust",
                metrics={
                    "likes": item.get("likeCount"),
                    "comments": item.get("commentCount"),
                    "saves": item.get("bookmarkCount"),
                    "views": item.get("viewCount"),
                },
                extra={"illust_type": item.get("illustType")},
            ))
        return posts


ADAPTER = PixivAdapter
