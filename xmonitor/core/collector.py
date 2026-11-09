"""通用采集器：适配器取数 → 校验 → 过滤 → 入库，六平台共用。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..platforms import extra_cookie_names, load, session_header
from .config import data_dir
from .http import HttpClient, HttpError, parse_cookies
from .store import PlatformStore

# 首次请求页面时会下发附加 Cookie 的站点入口
HOME_URLS = {
    "x": "https://x.com/",
    "tiktok": "https://www.tiktok.com/",
}
# 进程内缓存：按（平台, 锚点）缓存，避免旧会话的附加 Cookie 串用
_EXTRA_CACHE: dict[str, dict[str, str]] = {}


def _merge_extra_header(pcfg: dict, got: dict[str, str]) -> None:
    base = parse_cookies(str(pcfg.get("cookies") or ""))
    base.update(got)
    pcfg["cookies"] = "; ".join(f"{name}={value}" for name, value in base.items())


def ensure_extra_cookies(http: HttpClient, pcfg: dict, platform: str,
                         log=print) -> dict[str, str]:
    """补齐锚点之外的必需 Cookie：配置 → 进程缓存 → 请求站点首页。"""
    names = extra_cookie_names(platform)
    if not names:
        return {}
    if not str(pcfg.get("session_id") or "").strip():
        return {}
    cache_key = f"{platform}:{str(pcfg.get('session_id') or '')}"
    cache = _EXTRA_CACHE.setdefault(cache_key, {})
    got = {name: http.session.cookies.get(name) for name in names
           if http.session.cookies.get(name)}
    for name in names:
        if name not in got and cache.get(name):
            http.session.cookies.set(name, cache[name])
            got[name] = cache[name]
    if len(got) < len(names):
        url = HOME_URLS.get(platform)
        if url:
            try:
                http.get_text(url)
            except HttpError as e:
                log(f"{platform} 自动获取附加 Cookie 失败：{e}")
            for name in names:
                value = http.session.cookies.get(name)
                if value:
                    got[name] = value
                    cache[name] = value
            if len(got) == len(names):
                log(f"{platform} 已自动获取 {', '.join(got)}")
    missing = [name for name in names if name not in got]
    if missing:
        log(f"{platform} 缺少必需 Cookie {'、'.join(missing)}，请重新浏览器登录")
    if got:
        _merge_extra_header(pcfg, got)
    return got


def build_http(pcfg: dict, adapter_cls, log=print) -> HttpClient:
    retry = pcfg.get("retry") or {}
    rate = pcfg.get("rate_limit") or {}
    headers = dict(getattr(adapter_cls, "default_headers", {}))
    headers.update(pcfg.get("headers") or {})
    return HttpClient(
        timeout=float(pcfg.get("timeout") or 20),
        retries=int(retry.get("max_attempts") or 4),
        backoff=float(retry.get("backoff_seconds") or 2),
        backoff_max=float(retry.get("backoff_max_seconds") or 60),
        min_interval=float(rate.get("min_interval_seconds") or 1),
        max_rpm=int(rate.get("max_requests_per_minute") or 30),
        headers=headers,
        cookies=session_header(pcfg, adapter_cls.platform),
        log=log,
    )


def make_store(cfg: dict, platform: str, adapter_cls=None) -> PlatformStore:
    cls = adapter_cls or load(platform)
    return PlatformStore(
        str(data_dir(cfg)), platform,
        account_metrics=tuple(cls.account_metrics),
        post_metrics=tuple(cls.post_metrics),
    )


def validate_posts(posts: list[dict]) -> tuple[list[dict], list[str]]:
    valid, rejected, seen = [], [], set()
    for row in posts:
        post_id = str(row.get("post_id") or "").strip()
        if not post_id:
            rejected.append("缺少 post_id")
            continue
        if post_id in seen:
            continue
        if not (row.get("text") or row.get("title") or row.get("url")):
            rejected.append(f"{post_id}: 内容为空")
            continue
        created = row.get("created_at") or ""
        if created:
            try:
                datetime.fromisoformat(created)
            except ValueError:
                row["created_at"] = ""
        seen.add(post_id)
        valid.append(row)
    return valid, rejected


def apply_filters(adapter, posts: list[dict], filters: dict) -> list[dict]:
    include = [w.lower() for w in filters.get("include_keywords") or [] if str(w).strip()]
    exclude = [w.lower() for w in filters.get("exclude_keywords") or [] if str(w).strip()]
    only_changed = bool(filters.get("only_changed"))
    exclude_reposts = bool(filters.get("exclude_reposts"))
    out = []
    for post in posts:
        haystack = f"{post.get('title') or ''} {post.get('text') or ''}".lower()
        if include and not any(word in haystack for word in include):
            continue
        if exclude and any(word in haystack for word in exclude):
            continue
        if exclude_reposts and adapter.is_repost(post):
            continue
        out.append(post)
    return out


def field_coverage(posts: list[dict], metrics: tuple[str, ...]) -> float | None:
    if not posts or not metrics:
        return None
    expected = len(posts) * len(metrics)
    present = sum(1 for post in posts for key in metrics
                  if post.get(key) is not None)
    return round(present / expected * 100, 1)


def collect_platform(cfg: dict, platform: str, log=print) -> dict:
    pcfg = (cfg.get("platforms") or {}).get(platform) or {}
    if not pcfg.get("enabled"):
        raise RuntimeError(f"{platform} 未启用")

    adapter_cls = load(platform)
    store = make_store(cfg, platform, adapter_cls)
    started = datetime.now(timezone.utc)
    # HttpClient 负责整轮采集，结束后必须关闭底层 Session
    with build_http(pcfg, adapter_cls, log=log) as http:
        ensure_extra_cookies(http, pcfg, platform, log=log)
        adapter = adapter_cls(pcfg, http, log=log)

        account = adapter.fetch_account()
        raw_posts = adapter.fetch_posts()
        posts, rejected = validate_posts(raw_posts)
        posts = apply_filters(adapter, posts, pcfg.get("filters") or {})

        if pcfg.get("filters", {}).get("only_changed"):
            previous = store.load_posts()
            changed = []
            for post in posts:
                old = previous.get(str(post.get("post_id")) or "")
                if not old:
                    changed.append(post)
                    continue
                differs = any(post.get(key) is not None and post.get(key) != old.get(key)
                              for key in adapter.post_metrics)
                if differs:
                    changed.append(post)
            posts = changed

        posts = posts[: adapter.max_posts]
        new_count = store.upsert_posts(posts, started)
        snapshots = store.add_snapshots(posts, started)
        store.set_account(account)

        verification = adapter.verify(account)
        verify_json = json.dumps(verification, ensure_ascii=False, separators=(",", ":"))
        coverage = field_coverage(posts, adapter.post_metrics)
        coverage_text = "—" if coverage is None else coverage
        store.record_run(
            status="ok", new_posts=new_count, snapshots=snapshots,
            note=f"posts={len(posts)} rejected={len(rejected)} coverage={coverage_text}",
            verify=verify_json, started_at=started,
        )
        return {
            "platform": platform,
            "account": account,
            "new": new_count,
            "fetched": len(raw_posts),
            "kept": len(posts),
            "snapshots": snapshots,
            "rejected": rejected,
            "coverage": coverage,
            "verification": verification,
            "at": started,
        }


def record_error(cfg: dict, platform: str, message: str) -> None:
    try:
        store = make_store(cfg, platform)
        store.record_run(status="error", error=message[:400])
    except Exception:
        pass
