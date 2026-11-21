"""离线测试：字段归一化、存储裁剪、适配器解析、HTTP 重试、调度与路由。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from xmonitor.core import collector, report
from xmonitor.core.config import load_config
from xmonitor.core.http import HttpClient, LoginRequired, RateLimited
from xmonitor.core.scheduler import MultiCollectScheduler
from xmonitor.core.store import PlatformStore
from xmonitor.platforms.base import PlatformAdapter, PlatformError
from xmonitor.platforms import (available, clean_session_value, extra_cookie_names,
                                has_session, load, session_cookie_name,
                                session_header, unload, user_id_required)
from xmonitor.platforms.browser_session import (DOMAINS, LOGIN_URLS, session_value,
                                                session_values)
from xmonitor.platforms.schema import make_account, make_post, parse_count, parse_time


class FakeResponse:
    def __init__(self, status=200, payload=None, text="", headers=None, url="https://example.com"):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.headers = headers or {}
        self.url = url

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def headers(self):
        return {}

    def close(self):
        pass


class FakeHttp:
    def __init__(self, json_map=None, text_map=None):
        self.json_map = json_map or {}
        self.text_map = text_map or {}

    def get_json(self, url, **kwargs):
        for key, value in self.json_map.items():
            if key in url:
                return value
        raise AssertionError(f"unexpected json url: {url}")

    def get_text(self, url, **kwargs):
        for key, value in self.text_map.items():
            if key in url:
                return value
        raise AssertionError(f"unexpected text url: {url}")


class SchemaTest(unittest.TestCase):
    def test_parse_count(self):
        self.assertEqual(parse_count("1,234"), 1234)
        self.assertEqual(parse_count("1.2万"), 12000)
        self.assertEqual(parse_count("3.4亿"), 340000000)
        self.assertEqual(parse_count("12K"), 12000)
        self.assertIsNone(parse_count(None))

    def test_parse_time(self):
        self.assertTrue(parse_time(1790000000000).startswith("2026-"))
        self.assertTrue(parse_time("Sat Oct 31 10:00:00 +0000 2026").startswith("2026-10-31"))
        self.assertIsNone(parse_time(""))

    def test_make_post(self):
        row = make_post("x", "demo", "1", "p1", created_at=1790000000,
                        text="hi", metrics={"likes": 5, "comments": None})
        self.assertEqual(row["post_id"], "p1")
        self.assertEqual(row["likes"], 5)
        self.assertIsNone(row["comments"])


class StoreTest(unittest.TestCase):
    def test_columns_and_idempotent_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PlatformStore(tmp, "x", account_metrics=("followers",),
                                  post_metrics=("likes", "comments", "shares"))
            self.assertNotIn("saves", store.post_fields)
            self.assertNotIn("views", store.post_fields)
            now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
            rows = [{"platform": "x", "account_name": "a", "platform_user_id": "1",
                     "post_id": "p1", "created_at": "2026-10-31T11:00:00+00:00",
                     "title": "", "text": "hello", "url": "u", "media_type": "text",
                     "likes": 5, "comments": 2, "shares": 1}]
            store.upsert_posts(rows, now)
            store.add_snapshots(rows, now)
            store.add_snapshots(rows, now)
            self.assertEqual(store.stats()["snapshots"], 1)
            self.assertEqual(store.posts_recent(1)[0]["likes"], 5)
            self.assertEqual(store.upsert_posts(rows, now), 0)
            self.assertEqual(store.upsert_posts([{**rows[0], "post_id": "p2"}], now), 1)

    def test_clear_removes_all_platform_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PlatformStore(tmp, "x", account_metrics=("followers",),
                                  post_metrics=("likes", "comments", "shares"))
            now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
            rows = [{"platform": "x", "account_name": "a", "platform_user_id": "1",
                     "post_id": "p1", "created_at": "2026-10-31T11:00:00+00:00",
                     "title": "", "text": "hello", "url": "u", "media_type": "text",
                     "likes": 5, "comments": 2, "shares": 1}]
            store.upsert_posts(rows, now)
            store.add_snapshots(rows, now)
            store.set_account({"platform": "x", "account_name": "a",
                               "platform_user_id": "1", "followers": 10})
            store.record_run(status="ok")
            cleared = store.clear()
            self.assertEqual((cleared["posts"], cleared["snapshots"],
                              cleared["runs"]), (1, 1, 1))
            stats = store.stats()
            self.assertEqual((stats["posts"], stats["snapshots"], stats["runs"]),
                             (0, 0, 0))
            self.assertFalse(store.account_path.exists())
            self.assertFalse(store.posts_path.exists())
            self.assertFalse(store.runs_path.exists())


class ReportWriteTest(unittest.TestCase):
    def test_same_second_reports_do_not_collide(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"generated_at": datetime(2026, 10, 31, 12, 0,
                                            tzinfo=timezone.utc)}
            with mock.patch.object(report, "build_html", return_value="<html></html>"):
                first = report.write_report(data, "x @a", tmp)
                second = report.write_report(data, "x @a", tmp)
            self.assertTrue(first["html"].exists())
            self.assertTrue(second["html"].exists())
            self.assertNotEqual(first["html"], second["html"])


class HttpTest(unittest.TestCase):
    def test_retry_then_success(self):
        client = HttpClient(retries=3, backoff=0.01, min_interval=0, max_rpm=1000)
        client.session = FakeSession([FakeResponse(500), FakeResponse(200, {"ok": 1})])
        self.assertEqual(client.get_json("https://example.com"), {"ok": 1})
        self.assertEqual(client.session.calls, 2)

    def test_login_required(self):
        client = HttpClient(retries=2, backoff=0.01, min_interval=0, max_rpm=1000)
        client.session = FakeSession([FakeResponse(401, url="https://example.com/login")])
        with self.assertRaises(LoginRequired):
            client.get_text("https://example.com")

    def test_rate_limited(self):
        client = HttpClient(retries=2, backoff=0.01, min_interval=0, max_rpm=1000)
        client.session = FakeSession([FakeResponse(429, headers={"Retry-After": "200"}),
                                      FakeResponse(429, headers={"Retry-After": "200"})])
        with self.assertRaises(RateLimited):
            client.get_text("https://example.com")


class AdapterParseTest(unittest.TestCase):
    def test_x(self):
        profile = ('<meta property="profile:username" content="demo">'
                   '\\"relationship_counts\\":{\\"followers\\":1200,\\"following\\":88},'
                   '\\"tweet_counts\\":{\\"tweets\\":340},restId:"42"')
        adapter = load("x")({"account_name": "demo", "max_posts": 5}, FakeHttp(
            text_map={"x.com/demo": profile,
                      "timeline-profile": '<script id="__NEXT_DATA__" type="application/json">'
                     + json.dumps({"props": {"pageProps": {"timeline": {"entries": [
                         {"content": {"tweet": {"id_str": "1", "full_text": "hello",
                                                "created_at": "Sat Oct 31 10:00:00 +0000 2026",
                                                "favorite_count": 3, "reply_count": 1,
                                                "retweet_count": 2,
                                                "views": {"count": "99"}}}}]}}}})
                     + "</script>"},
        ))
        account = adapter.fetch_account()
        posts = adapter.fetch_posts()
        self.assertEqual(account["followers"], 1200)
        self.assertEqual(account["platform_user_id"], "42")
        self.assertEqual(posts[0]["likes"], 3)
        self.assertEqual(posts[0]["comments"], 1)
        self.assertEqual(posts[0]["views"], 99)

    def test_x_resolves_handle_from_login_session(self):
        profile = ('<meta property="profile:username" content="demo">'
                   '\\"relationship_counts\\":{\\"followers\\":1200,\\"following\\":88},'
                   '\\"tweet_counts\\":{\\"tweets\\":340},restId:"42"')

        class SessionHttp:
            def get_text(self, url, **kwargs):
                if "x.com/home" in url:
                    return '<script>{"screen_name":"demo"}</script>'
                return profile

        adapter = load("x")({"account_name": "昵称", "session_id": "token",
                             "max_posts": 5}, SessionHttp())
        account = adapter.fetch_account()
        self.assertEqual(account["account_name"], "demo")

    def test_x_rejects_invalid_handle_without_session(self):
        adapter = load("x")({"account_name": "invalid handle"}, FakeHttp())
        with self.assertRaises(PlatformError):
            adapter.fetch_account()

    def test_x_falls_back_to_profile_html(self):
        profile = ('<meta property="profile:username" content="demo">'
                   '\\"relationship_counts\\":{\\"followers\\":1200,\\"following\\":88},'
                   '\\"tweet_counts\\":{\\"tweets\\":340},restId:"42",'
                   '\\"tweet_results\\":{\\"rest_id\\":\\"101\\",'
                   '\\"counts\\":{\\"bookmark_count\\":0,\\"favorite_count\\":7,'
                   '\\"quote_count\\":1,\\"reply_count\\":2,\\"retweet_count\\":3},'
                   '\\"details\\":{\\"created_at_ms\\":1790000000000,\\"full_text\\":\\"hi\\"},'
                   '\\"views\\":{\\"count\\":\\"321\\"}}')

        class TimelineBlocked:
            def get_text(self, url, **kwargs):
                if "timeline-profile" in url:
                    raise RateLimited("Rate limit exceeded")
                return profile

        adapter = load("x")({"account_name": "demo", "max_posts": 5}, TimelineBlocked())
        posts = adapter.fetch_posts()
        self.assertEqual(posts[0]["post_id"], "101")
        self.assertEqual(posts[0]["likes"], 7)
        self.assertEqual(posts[0]["shares"], 3)
        self.assertEqual(posts[0]["views"], 321)

    def test_x_fills_views_from_status_page(self):
        profile = ('<meta property="profile:username" content="demo">'
                   '\\"relationship_counts\\":{\\"followers\\":1200,\\"following\\":88},'
                   '\\"tweet_counts\\":{\\"tweets\\":340},restId:"42"')
        timeline = ('<script id="__NEXT_DATA__" type="application/json">'
                    + json.dumps({"props": {"pageProps": {"timeline": {"entries": [
                        {"content": {"tweet": {"id_str": "1", "full_text": "hello",
                                               "created_at": "Sat Oct 31 10:00:00 +0000 2026",
                                               "favorite_count": 3, "reply_count": 1,
                                               "retweet_count": 2}}}]}}}})
                    + "</script>")

        class StatusHttp:
            def get_text(self, url, **kwargs):
                if "timeline-profile" in url:
                    return timeline
                if "/status/" in url:
                    return '\\"views\\":{\\"count\\":\\"456\\"}'
                return profile

        adapter = load("x")({"account_name": "demo", "max_posts": 5}, StatusHttp())
        adapter.fetch_account()
        posts = adapter.fetch_posts()
        self.assertEqual(posts[0]["views"], 456)

    def test_x_reply_and_repost_flags(self):
        def entry(tid, text, **extra):
            tweet = {"id_str": tid, "full_text": text,
                     "created_at": "Sat Oct 31 10:00:00 +0000 2026",
                     "favorite_count": 1, "reply_count": 0, "retweet_count": 0,
                     "views": {"count": "10"}}
            tweet.update(extra)
            return {"content": {"tweet": tweet}}

        timeline = ('<script id="__NEXT_DATA__" type="application/json">'
                    + json.dumps({"props": {"pageProps": {"timeline": {"entries": [
                        entry("1", "original"),
                        entry("2", "RT @other: hi", retweeted_status={"id_str": "9"}),
                        entry("3", "reply other", in_reply_to_status_id_str="8",
                              in_reply_to_screen_name="other"),
                        entry("4", "self thread", in_reply_to_status_id_str="1",
                              in_reply_to_screen_name="demo"),
                    ]}}}}) + "</script>")
        adapter = load("x")({"account_name": "demo", "max_posts": 10},
                            FakeHttp(text_map={"timeline-profile": timeline}))
        posts = adapter.fetch_posts()
        flags = [(p["post_id"], adapter.is_repost(p), adapter.is_reply(p)) for p in posts]
        self.assertEqual(flags, [("1", False, False), ("2", True, False),
                                 ("3", False, True), ("4", False, False)])
        kept = collector.apply_filters(
            adapter, posts, {"exclude_reposts": True, "exclude_replies": True})
        self.assertEqual([p["post_id"] for p in kept], ["1", "4"])

    def test_xiaohongshu(self):
        state = {"user": {"userPageData": {
            "basicInfo": {"nickname": "红"},
            "interactions": [{"name": "粉丝", "count": "1.2万"},
                             {"name": "关注", "count": "30"},
                             {"name": "获赞与收藏", "count": "8.8万"}],
            "notes": [{"noteId": "n1", "displayTitle": "标题",
                       "interactInfo": {"likedCount": "100", "commentCount": "5",
                                        "shareCount": "2", "collectedCount": "20"},
                       "time": 1790000000000, "type": "normal"}],
        }}}
        html = ("<script>window.__INITIAL_STATE__="
                + json.dumps(state) + "</script>")
        adapter = load("xiaohongshu")({"account_name": "红", "platform_user_id": "u1",
                                       "max_posts": 5, "render": "http"},
                                      FakeHttp(text_map={"user/profile": html}))
        account = adapter.fetch_account()
        posts = adapter.fetch_posts()
        self.assertEqual(account["followers"], 12000)
        self.assertEqual(posts[0]["saves"], 20)

    def test_xhs_note_normalize(self):
        """新版页面 noteCard 与接口 snake_case 两种结构都要能归一。"""
        from xmonitor.platforms.xhs_browser import normalize_note

        camel = normalize_note({
            "id": "n1", "xsecToken": "tok",
            "noteCard": {"displayTitle": "标题", "type": "video", "time": 1790000000000,
                         "interactInfo": {"likedCount": "1.2万", "commentCount": "5",
                                          "shareCount": "2", "collectedCount": "20"}},
        })
        self.assertEqual(camel["note_id"], "n1")
        self.assertEqual(camel["likes"], "1.2万")
        self.assertEqual(camel["xsec_token"], "tok")

        snake = normalize_note({
            "id": "n2", "xsec_token": "t2",
            "note_card": {"display_title": "标题2", "type": "normal", "time": 1790000000000,
                          "interact_info": {"liked_count": "9", "collected_count": "3"}},
        })
        self.assertEqual(snake["title"], "标题2")
        self.assertEqual(snake["saves"], "3")
        self.assertIsNone(normalize_note({}))

    def test_weibo(self):
        adapter = load("weibo")({"account_name": "博主", "platform_user_id": "100",
                                 "max_posts": 5}, FakeHttp(
            json_map={
                "profile/info": {"data": {"user": {"idstr": "100", "screen_name": "博主",
                                                   "followers_count": 500,
                                                   "friends_count": 20,
                                                   "statuses_count": 90}}},
                "statuses/mymblog": {"data": {"list": [
                    {"mid": "m1", "created_at": "1小时前", "text_raw": "<b>hi</b>",
                     "attitudes_count": 8, "comments_count": 2, "reposts_count": 1}]}},
            },
        ))
        account = adapter.fetch_account()
        posts = adapter.fetch_posts()
        self.assertEqual(account["followers"], 500)
        self.assertEqual(posts[0]["likes"], 8)

    def test_tiktok(self):
        state = {"__DEFAULT_SCOPE__": {"webapp.user-detail": {
            "userInfo": {"user": {"id": "1", "uniqueId": "demo", "secUid": "s1",
                                  "stats": {"followerCount": 1000, "followingCount": 10,
                                            "videoCount": 20, "heartCount": 5000}},
                         "itemList": [{"id": "v1", "desc": "hi", "createTime": 1790000000,
                                       "stats": {"diggCount": 30, "commentCount": 4,
                                                 "shareCount": 2, "collectCount": 5,
                                                 "playCount": 1000}}]},
        }}}
        html = ('<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
                + json.dumps(state) + "</script>")
        adapter = load("tiktok")({"account_name": "demo", "max_posts": 5},
                                 FakeHttp(text_map={"tiktok.com/@demo": html}))
        account = adapter.fetch_account()
        posts = adapter.fetch_posts()
        self.assertEqual(account["followers"], 1000)
        self.assertEqual(posts[0]["views"], 1000)

    def test_instagram(self):
        payload = {"data": {"user": {
            "id": "1", "username": "demo",
            "edge_followed_by": {"count": 100}, "edge_follow": {"count": 10},
            "edge_owner_to_timeline_media": {"count": 5, "edges": [{"node": {
                "id": "m1", "shortcode": "abc", "taken_at_timestamp": 1790000000,
                "edge_liked_by": {"count": 20}, "edge_media_to_comment": {"count": 3},
                "is_video": True, "video_view_count": 500,
                "edge_media_to_caption": {"edges": [{"node": {"text": "hi"}}]}}}]},
        }}}
        adapter = load("instagram")({"account_name": "demo", "max_posts": 5},
                                    FakeHttp(json_map={"web_profile_info": payload}))
        account = adapter.fetch_account()
        posts = adapter.fetch_posts()
        self.assertEqual(account["posts_count"], 5)
        self.assertEqual(posts[0]["likes"], 20)
        self.assertEqual(posts[0]["views"], 500)

    def test_pixiv(self):
        adapter = load("pixiv")({"account_name": "画师", "platform_user_id": "9",
                                 "max_posts": 5}, FakeHttp(json_map={
            "profile/all": {"error": False,
                            "body": {"illusts": {"2": None, "1": None}, "manga": {},
                                     "novels": {}}},
            "illust/2": {"body": {"title": "t2", "description": "d2",
                                  "createDate": "2026-10-31T10:00:00+09:00",
                                  "viewCount": 200, "likeCount": 20,
                                  "bookmarkCount": 10, "commentCount": 2}},
            "illust/1": {"body": {"title": "t1", "description": "d1",
                                  "createDate": "2026-10-30T10:00:00+09:00",
                                  "viewCount": 100, "likeCount": 10,
                                  "bookmarkCount": 5, "commentCount": 1}},
        }))
        account = adapter.fetch_account()
        posts = adapter.fetch_posts()
        self.assertEqual(account["posts_count"], 2)
        self.assertEqual(posts[0]["post_id"], "2")
        self.assertEqual(posts[0]["saves"], 10)

    def test_pixiv_resolves_uid_from_login_session(self):
        adapter = load("pixiv")({"account_name": "画师", "platform_user_id": "user_demo",
                                 "max_posts": 5}, FakeHttp(json_map={
            "user/self": {"userData": {"id": "123456", "name": "画师"}},
            "profile/all": {"error": False,
                            "body": {"illusts": {}, "manga": {}, "novels": {}}},
        }))
        account = adapter.fetch_account()
        self.assertEqual(account["platform_user_id"], "123456")
        self.assertEqual(account["posts_count"], 0)

    def test_pixiv_accepts_profile_url(self):
        adapter = load("pixiv")({"account_name": "画师",
                                 "platform_user_id": "https://www.pixiv.net/users/123456",
                                 "max_posts": 5}, FakeHttp(json_map={
            "profile/all": {"error": False,
                            "body": {"illusts": {}, "manga": {}, "novels": {}}},
        }))
        account = adapter.fetch_account()
        self.assertEqual(account["platform_user_id"], "123456")


class FakeAdapter(PlatformAdapter):
    platform = "x"
    label = "Fake"
    account_metrics = ("followers",)
    post_metrics = ("likes", "comments", "shares")

    def fetch_account(self):
        return make_account("x", "demo", "1", {"followers": 100})

    def fetch_posts(self):
        return [make_post("x", "demo", "1", "p1", created_at=1790000000,
                          text="hello", url="u", media_type="text",
                          metrics={"likes": 5, "comments": 2, "shares": 1})]

    def verify(self, account):
        return {"checked": True, "matches": True}


class CollectorTest(unittest.TestCase):
    def test_collect_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"data_dir": tmp, "platforms": {"x": {
                "enabled": True, "account_name": "demo", "max_posts": 5,
                "filters": {}, "retry": {}, "rate_limit": {}, "timeout": 5}}}
            with mock.patch.object(collector, "load", return_value=FakeAdapter):
                result = collector.collect_platform(cfg, "x", log=lambda _m: None)
            self.assertEqual(result["new"], 1)
            self.assertEqual(result["coverage"], 100.0)
            store = PlatformStore(tmp, "x", account_metrics=FakeAdapter.account_metrics,
                                  post_metrics=FakeAdapter.post_metrics)
            self.assertEqual(store.stats()["posts"], 1)
            self.assertEqual(len(store.load_posts()), 1)


class SchedulerTest(unittest.TestCase):
    def test_events_and_stop(self):
        cfg = {"collect_interval_minutes": 30, "platforms": {
            "x": {"enabled": False, "account_name": ""}}}
        scheduler = MultiCollectScheduler(cfg)
        scheduler.start()
        time.sleep(1.2)
        events = scheduler.poll()
        kinds = [kind for kind, _ in events]
        self.assertIn("need_config", kinds)
        scheduler.stop()
        time.sleep(0.6)
        self.assertFalse(scheduler._thread.is_alive())

    def test_error_event_and_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"collect_interval_minutes": 30, "data_dir": tmp, "platforms": {
                "x": {"enabled": True, "account_name": "demo", "cookies": ""}}}
            scheduler = MultiCollectScheduler(cfg)
            with mock.patch("xmonitor.core.scheduler.collect_platform",
                            side_effect=LoginRequired("login wall")):
                scheduler._collect_round(set())
            events = scheduler.poll()
            kinds = [kind for kind, _ in events]
            self.assertIn("platform_error", kinds)
            state = scheduler.platform_state("x")
            self.assertIsNotNone(state["cooldown_until"])


class BrowserSessionTest(unittest.TestCase):
    def test_domains_and_urls_cover_platforms(self):
        self.assertEqual(set(DOMAINS), set(available()))
        self.assertEqual(set(LOGIN_URLS), set(available()))

    def test_session_value_only_takes_anchor(self):
        value = session_value([
            {"name": "PHPSESSID", "value": "abc", "domain": ".pixiv.net"},
            {"name": "other", "value": "1", "domain": ".pixiv.net"},
        ], DOMAINS["pixiv"], "PHPSESSID")
        self.assertEqual(value, "abc")
        self.assertEqual(session_value([
            {"name": "PHPSESSID", "value": "abc", "domain": ".evil.com"},
        ], DOMAINS["pixiv"], "PHPSESSID"), "")
        self.assertEqual(session_value([
            {"name": "PHPSESSID", "value": "", "domain": ".pixiv.net"},
        ], DOMAINS["pixiv"], "PHPSESSID"), "")


class SessionAnchorTest(unittest.TestCase):
    def test_anchor_names(self):
        self.assertEqual(
            {p: session_cookie_name(p) for p in available()},
            {"x": "auth_token", "instagram": "sessionid", "xiaohongshu": "web_session",
             "weibo": "SUB", "pixiv": "PHPSESSID", "tiktok": "sessionid"})

    def test_clean_pasted_value(self):
        self.assertEqual(clean_session_value("pixiv", "PHPSESSID=abc"), "abc")
        self.assertEqual(clean_session_value("pixiv", "abc; other=1"), "abc")
        self.assertEqual(clean_session_value("pixiv", "  abc  "), "abc")

    def test_header_anchor_plus_extra(self):
        self.assertEqual(session_header({"session_id": "abc", "cookies": "ct0=xyz"},
                                        "pixiv"), "ct0=xyz; PHPSESSID=abc")
        self.assertEqual(session_header({"session_id": "PHPSESSID=abc"}, "pixiv"),
                         "PHPSESSID=abc")
        self.assertEqual(session_header({}, "pixiv"), "")

    def test_has_session(self):
        self.assertTrue(has_session({"session_id": "abc"}, "pixiv"))
        self.assertFalse(has_session({"session_id": "  "}, "pixiv"))
        self.assertTrue(has_session({"cookies": "PHPSESSID=abc; other=1"}, "pixiv"))
        self.assertFalse(has_session({"cookies": "ct0=1"}, "pixiv"))
        self.assertFalse(has_session({"cookies": "tt_chain_token=1"}, "tiktok"))
        self.assertTrue(has_session({"cookies": "sessionid=abc; tt_chain_token=1"},
                                    "tiktok"))
        self.assertTrue(has_session({}, "x"))

    def test_user_id_required_only_three_platforms(self):
        required = {p for p in available() if user_id_required(p)}
        self.assertEqual(required, {"xiaohongshu", "weibo", "pixiv"})

    def test_extra_cookie_names(self):
        self.assertEqual(
            {p: extra_cookie_names(p) for p in available()},
            {"x": ("ct0",), "tiktok": ("tt_chain_token",), "instagram": (),
             "xiaohongshu": (), "weibo": (), "pixiv": ()})

    def test_session_values_reads_anchor_and_extras(self):
        values = session_values([
            {"name": "auth_token", "value": "a", "domain": ".x.com"},
            {"name": "ct0", "value": "c", "domain": ".x.com"},
            {"name": "bad", "value": "b", "domain": ".evil.com"},
        ], DOMAINS["x"], ("auth_token", "ct0"))
        self.assertEqual(values, {"auth_token": "a", "ct0": "c"})


class ExtraCookieTest(unittest.TestCase):
    def setUp(self):
        collector._EXTRA_CACHE.clear()

    def test_fetch_from_home(self):
        class FakeHttp:
            def __init__(self):
                self.jar = {}
                self.session = mock.Mock()
                self.session.cookies = mock.Mock()
                self.session.cookies.get.side_effect = lambda n: self.jar.get(n)
                self.session.cookies.set.side_effect = lambda n, v: self.jar.__setitem__(n, v)

            def get_text(self, url):
                self.jar["ct0"] = "token-1"
                return ""

        pcfg = {"session_id": "auth-1", "cookies": ""}
        got = collector.ensure_extra_cookies(FakeHttp(), pcfg, "x", log=lambda _m: None)
        self.assertEqual(got, {"ct0": "token-1"})
        self.assertEqual(pcfg["cookies"], "ct0=token-1")
        # 第二轮应命中缓存，不再请求首页
        got_again = collector.ensure_extra_cookies(FakeHttp(), pcfg, "x",
                                                   log=lambda _m: None)
        self.assertEqual(got_again, {"ct0": "token-1"})


class ConfigTest(unittest.TestCase):
    def test_deep_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"platforms": {"x": {"account_name": "demo"}}}),
                            encoding="utf-8")
            cfg = load_config(str(path))
            self.assertEqual(cfg["platforms"]["x"]["account_name"], "demo")
            self.assertIn("min_interval_seconds", cfg["platforms"]["x"]["rate_limit"])
            self.assertEqual(cfg["platforms"]["x"]["session_id"], "")
            self.assertNotIn("llm", cfg)


class RegistryTest(unittest.TestCase):
    def test_load_unload(self):
        self.assertEqual(len(available()), 6)
        cls = load("pixiv")
        self.assertEqual(cls.label, "pixiv")
        unload("pixiv")
        self.assertEqual(load("pixiv").label, "pixiv")


if __name__ == "__main__":
    unittest.main()
