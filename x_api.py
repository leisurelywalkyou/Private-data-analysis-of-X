"""极简 X (Twitter) API v2 客户端：只依赖 requests，带限流/重试处理。"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import requests

from config import METRICS

API_BASE = os.environ.get("X_API_BASE", "https://api.x.com/2")
TWEET_FIELDS = "created_at,public_metrics"
USER_FIELDS = "public_metrics,created_at"


class XApiError(RuntimeError):
    pass


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_tweet(obj: dict) -> dict:
    m = obj.get("public_metrics") or {}
    row = {
        "tweet_id": obj["id"],
        "created_at": parse_time(obj.get("created_at")),
        "text": obj.get("text", ""),
    }
    for col, api_field in METRICS.items():
        row[col] = int(m.get(api_field) or 0)
    return row


class XClient:
    def __init__(self, bearer_token: str = "", user_token: str = "", timeout: int = 20, log=print):
        self.bearer = (bearer_token or "").strip()
        self.user_token = (user_token or "").strip()
        if not (self.bearer or self.user_token):
            raise XApiError(
                "缺少凭据：请在 config.json 填写 bearer_token，或设置环境变量 X_BEARER_TOKEN。"
            )
        self.timeout = timeout
        self.log = log
        self.session = requests.Session()

    def _headers(self, user_context: bool) -> dict:
        token = self.user_token if (user_context and self.user_token) else (self.bearer or self.user_token)
        return {"Authorization": f"Bearer {token}", "User-Agent": "x-stats-tracker/1.0"}

    def _get(self, path: str, params: dict, user_context: bool = False) -> dict:
        url = API_BASE + path
        for attempt in range(4):
            resp = self.session.get(url, params=params, headers=self._headers(user_context), timeout=self.timeout)
            if resp.status_code == 200:
                body = resp.json()
                if "errors" in body and not body.get("data"):
                    raise XApiError(f"API 返回错误：{body['errors']}")
                return body

            if resp.status_code == 429:
                reset = int(resp.headers.get("x-rate-limit-reset", "0") or 0)
                wait = max(reset - int(time.time()), 5) if reset else 60
                if wait > 300:
                    raise XApiError(f"触发限流，需等待 {wait}s（{path}），请稍后重试。")
                self.log(f"限流，等待 {wait}s 后重试 ...")
                time.sleep(wait + 2)
                continue
            if resp.status_code in (500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue

            hint = ""
            if resp.status_code == 401:
                hint = "（Bearer Token 无效或已失效）"
            elif resp.status_code == 403:
                hint = "（权限不足：确认 App 属于该账号/有读取权限；必要时用 user_access_token 走用户上下文）"
            raise XApiError(f"HTTP {resp.status_code}{hint} {path} -> {resp.text[:300]}")

        raise XApiError(f"重试多次仍失败：{path}")

    def get_user(self, username: str) -> dict:
        body = self._get(
            "/users/by/username/" + username.lstrip("@"),
            {"user.fields": USER_FIELDS},
            user_context=True,
        )
        data = body.get("data")
        if not data:
            raise XApiError(f"找不到用户 @{username}")
        return {
            "id": data["id"],
            "username": data.get("username", username),
            "name": data.get("name", ""),
            "followers": int((data.get("public_metrics") or {}).get("followers_count") or 0),
        }

    def get_user_tweets(self, user_id: str, since_id: str | None = None,
                        exclude_retweets: bool = True, exclude_replies: bool = False,
                        max_pages: int = 5) -> list[dict]:
        params = {
            "max_results": 100,
            "tweet.fields": TWEET_FIELDS,
        }
        exclude = []
        if exclude_retweets:
            exclude.append("retweets")
        if exclude_replies:
            exclude.append("replies")
        if exclude:
            params["exclude"] = ",".join(exclude)
        if since_id:
            params["since_id"] = since_id

        tweets: list[dict] = []
        token = None
        for _ in range(max_pages):
            if token:
                params["pagination_token"] = token
            body = self._get(f"/users/{user_id}/tweets", params)
            tweets.extend(parse_tweet(t) for t in body.get("data", []))
            token = (body.get("meta") or {}).get("next_token")
            if not token:
                break
        return tweets

    def get_tweets_metrics(self, ids: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            body = self._get(
                "/tweets",
                {"ids": ",".join(chunk), "tweet.fields": TWEET_FIELDS},
                user_context=True,
            )
            out.extend(parse_tweet(t) for t in body.get("data", []))
        return out
