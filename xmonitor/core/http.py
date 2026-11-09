"""共享 HTTP 客户端：超时、重试、退避、限频与错误分类。

只做正常请求与低频访问，不提供代理轮换、指纹伪造或验证码绕过。
"""

from __future__ import annotations

import random
import time
from http.cookies import SimpleCookie

import requests

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


class HttpError(RuntimeError):
    kind = "error"


class NetworkError(HttpError):
    kind = "network"


class LoginRequired(HttpError):
    kind = "login"


class ChallengeRequired(HttpError):
    kind = "challenge"


class RateLimited(HttpError):
    kind = "rate_limit"


class NotFoundError(HttpError):
    kind = "not_found"


class ParseError(HttpError):
    kind = "parse"


def parse_cookies(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    jar = SimpleCookie()
    try:
        jar.load(raw)
        return {k: morsel.value for k, morsel in jar.items()}
    except Exception:
        out = {}
        for part in raw.split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                out[key.strip()] = value.strip()
        return out


class HttpClient:
    def __init__(self, *, timeout: float = 20, retries: int = 4,
                 backoff: float = 2.0, backoff_max: float = 60,
                 min_interval: float = 1.0, max_rpm: int = 30,
                 headers: dict | None = None, cookies: str = "", log=print):
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.backoff = backoff
        self.backoff_max = backoff_max
        self.min_interval = max(0.0, min_interval)
        self.max_rpm = max(1, int(max_rpm))
        self.log = log
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT,
                                     "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
        if headers:
            self.session.headers.update(headers)
        cookie_dict = parse_cookies(cookies)
        if cookie_dict:
            self.session.cookies.update(cookie_dict)
        self._last_request = 0.0
        self._recent: list[float] = []

    # ---------- 限频 ----------
    def _throttle(self):
        now = time.monotonic()
        wait = self.min_interval - (now - self._last_request)
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        while len(self._recent) >= self.max_rpm and now - self._recent[0] < 60:
            sleep_s = 60 - (now - self._recent[0]) + 0.5
            time.sleep(min(sleep_s, 30))
            now = time.monotonic()
        self._recent = [t for t in self._recent if now - t < 60]
        self._recent.append(now)
        self._last_request = now

    @staticmethod
    def _retry_after(resp: requests.Response) -> float:
        value = resp.headers.get("Retry-After")
        if value:
            try:
                return max(float(value), 1.0)
            except ValueError:
                pass
        reset = resp.headers.get("x-rate-limit-reset")
        if reset:
            try:
                return max(float(reset) - time.time(), 1.0)
            except ValueError:
                pass
        return 30.0

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("allow_redirects", True)
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                resp = self.session.request(method, url, **kwargs)
            except requests.RequestException as e:
                last_error = e
                if attempt >= self.retries:
                    raise NetworkError(f"网络请求失败：{e}") from e
                self._sleep(attempt)
                continue

            final_url = (resp.url or "").lower()
            if resp.status_code == 200:
                if "/login" in final_url or "/passport" in final_url:
                    raise LoginRequired(f"被重定向到登录页：{url}")
                return resp
            if resp.status_code in (301, 302, 303, 307, 308):
                raise LoginRequired(f"请求被重定向，可能需要登录：{url}")
            if resp.status_code == 429:
                wait = self._retry_after(resp)
                if wait > 180 or attempt >= self.retries:
                    raise RateLimited(f"触发限流，建议等待 {int(wait)} 秒：{url}")
                self.log(f"限流，等待 {int(wait)}s 后重试（{url}）")
                time.sleep(wait)
                continue
            if resp.status_code in (500, 502, 503, 504):
                last_error = HttpError(f"服务端错误 {resp.status_code}")
                if attempt >= self.retries:
                    raise HttpError(f"服务端连续错误：{url}")
                self._sleep(attempt)
                continue
            if resp.status_code == 401:
                raise LoginRequired(f"登录态失效（401）：{url}")
            if resp.status_code == 403:
                raise ChallengeRequired(f"访问被拒绝（403），可能触发风控或权限不足：{url}")
            if resp.status_code == 404:
                raise NotFoundError(f"资源不存在（404）：{url}")
            raise HttpError(f"HTTP {resp.status_code}：{url}")

        raise NetworkError(f"重试耗尽：{url}（{last_error}）")

    def _sleep(self, attempt: int):
        delay = min(self.backoff_max, self.backoff ** (attempt - 1))
        delay += random.uniform(0, 1)
        time.sleep(delay)

    # ---------- 便捷方法 ----------
    def get_json(self, url: str, **kwargs):
        resp = self.request("GET", url, **kwargs)
        try:
            return resp.json()
        except ValueError as e:
            raise ParseError(f"响应不是合法 JSON：{url}") from e

    def get_text(self, url: str, **kwargs) -> str:
        resp = self.request("GET", url, **kwargs)
        return resp.text

    # ---------- 资源释放 ----------
    def close(self):
        self.session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc_info):
        self.close()
