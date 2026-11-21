"""小红书浏览器渲染通道。

小红书对未登录请求会强制 302 到登录页，headless 浏览器还会触发风控（error_code 300012），
且主页数据被包成 Vue ref 对象、由前端异步渲染。因此用真实 Chromium（持久化 profile）
打开页面，在页面内解包 state 提取数据，并按需打开笔记详情补齐互动指标。
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from ..core.config import data_dir
from ..core.http import LoginRequired, ParseError
from .schema import parse_count

NOTE_API_HINTS = ("/api/sns/web/v1/user_posted",)
LOGIN_HINTS = ("/login", "/website-login")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    # 采集窗口放在屏幕外，避免每轮采集时打扰使用者
    "--window-position=-32000,-32000",
    "--window-size=1280,900",
    "--mute-audio",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=Translate,MediaRouter",
]

# 真人浏览节奏：所有停留都是随机区间，避免固定间隔形成脚本特征
OPEN_PAUSE = (3.0, 6.0)          # 主页打开后先"看一眼"
RELOAD_PAUSE = (2.5, 4.5)        # 首屏数据未就绪时的二次等待
SCROLL_PAUSE = (2.5, 5.5)        # 每次下滑之间的浏览停顿
DETAIL_PAUSE = (5.0, 11.0)       # 打开笔记详情前的停顿
DETAIL_READ_PAUSE = (1.2, 2.4)   # 详情页加载后的阅读停顿
DETAIL_REST_EVERY = 3            # 每连续看几篇笔记歇一次
DETAIL_REST = (12.0, 24.0)       # 长休息，模拟真人放下手机/切换注意力


def _pause(page, span: tuple[float, float]):
    page.wait_for_timeout(int(random.uniform(*span) * 1000))


def _human_scroll(page):
    """先随机移动鼠标再滚动，滚动距离也随机，接近真人翻页。"""
    page.mouse.move(random.randint(320, 1080), random.randint(220, 680),
                    steps=random.randint(6, 14))
    page.wait_for_timeout(random.randint(200, 600))
    page.mouse.wheel(0, random.randint(1600, 2800))


# 页面内提取：解包 Vue ref、扁平化笔记数组，只回传标量字段，避免循环引用
PROFILE_JS = """() => {
  const un = (v, d) => {
    d = d || 0;
    if (!v || typeof v !== 'object' || d > 8) return v;
    if (v.__v_isRef || '_rawValue' in v || '_value' in v) {
      const raw = ('_rawValue' in v && v._rawValue !== undefined) ? v._rawValue : v._value;
      return un(raw, d + 1);
    }
    return v;
  };
  const s = window.__INITIAL_STATE__;
  const u = s && s.user;
  if (!u) return '';
  const p = un(u.userPageData) || {};
  const basic = p.basicInfo || p.basic_info || {};
  const out = [];
  const walk = (v, d) => {
    d = d || 0;
    if (!v || d > 6) return;
    if (Array.isArray(v)) { for (const item of v) walk(item, d + 1); return; }
    if (typeof v === 'object') {
      const card = v.noteCard || v.note_card || v;
      const id = v.id || card.noteId || card.id || v.noteId;
      if (id) { out.push({ id: String(id), token: v.xsecToken || v.xsec_token || '', card: card }); return; }
    }
  };
  walk(un(u.notes));
  const notes = out.map(function (row) {
    const c = row.card || {};
    const inter = c.interactInfo || c.interact_info || {};
    return {
      id: row.id,
      token: row.token,
      title: c.displayTitle || c.display_title || c.title || '',
      type: c.type || '',
      time: c.time || c.create_time || 0,
      likes: inter.likedCount || inter.liked_count || null,
      comments: inter.commentCount || inter.comment_count || null,
      shares: inter.shareCount || inter.share_count || null,
      saves: inter.collectedCount || inter.collected_count || null
    };
  });
  const tab = p.tabPublic || p.tab_public || {};
  const posted = p.posted || (tab.collectionNote && tab.collectionNote.count) || null;
  return JSON.stringify({
    basic: { nickname: basic.nickname || '', redId: basic.redId || basic.red_id || '',
             desc: String(basic.desc || '').slice(0, 200) },
    interactions: (p.interactions || []).map(function (i) {
      return { name: i.name || '', type: i.type || '', count: i.count === undefined ? null : i.count };
    }),
    posted: posted,
    notes: notes
  });
}"""

DETAIL_JS = """() => {
  const s = window.__INITIAL_STATE__ || {};
  const map = (s.note && s.note.noteDetailMap) || {};
  const key = Object.keys(map).find(function (k) { return k && map[k] && map[k].note; });
  if (!key) return '';
  const n = map[key].note;
  const i = n.interactInfo || {};
  return JSON.stringify({
    id: n.noteId || key,
    likes: i.likedCount === undefined ? null : i.likedCount,
    comments: i.commentCount === undefined ? null : i.commentCount,
    shares: i.shareCount === undefined ? null : i.shareCount,
    saves: i.collectedCount === undefined ? null : i.collectedCount,
    title: n.title || '',
    desc: String(n.desc || '').slice(0, 500),
    time: n.time || 0,
    type: n.type || ''
  });
}"""


class BrowserUnavailable(RuntimeError):
    """浏览器通道不可用：未安装 playwright 或 profile 被占用。"""


def profile_dir(cfg: dict) -> Path:
    path = Path(data_dir(cfg)) / "browser" / "xiaohongshu"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pick(data, *names):
    """兼容 camelCase / snake_case 两套字段名。"""
    if not isinstance(data, dict):
        return None
    for name in names:
        if name in data:
            value = data[name]
            if value not in (None, "", [], {}):
                return value
    return None


def normalize_note(raw: dict) -> dict | None:
    """把三种来源的笔记结构归一为统一字段。"""
    if not isinstance(raw, dict):
        return None
    card = raw.get("note_card") or raw.get("noteCard") or raw
    note_id = _pick(raw, "id", "noteId", "note_id") or _pick(card, "id", "noteId", "note_id")
    if not note_id:
        return None
    inter = (_pick(card, "interact_info", "interactInfo")
             or _pick(raw, "interact_info", "interactInfo") or {})
    return {
        "note_id": str(note_id),
        "title": _pick(card, "display_title", "displayTitle", "title") or "",
        "desc": _pick(card, "desc", "description", "text") or "",
        "type": _pick(card, "type") or "",
        "created_at": (_pick(card, "time", "create_time", "createTime")
                       or _pick(raw, "time", "create_time", "createTime")),
        "likes": _pick(inter, "liked_count", "likedCount"),
        "comments": _pick(inter, "comment_count", "commentCount"),
        "shares": _pick(inter, "share_count", "shareCount"),
        "saves": _pick(inter, "collected_count", "collectedCount"),
        "xsec_token": _pick(raw, "xsec_token", "xsecToken") or "",
    }


def _launch(playwright, profile: Path, headless: bool = False,
            offscreen: bool = True):
    args = list(LAUNCH_ARGS)
    if not offscreen:
        # 手动登录窗口必须可见，去掉离屏定位
        args = [arg for arg in args if not arg.startswith("--window-position")]
    kwargs = {
        "user_data_dir": str(profile),
        "headless": headless,
        "locale": "zh-CN",
        "viewport": {"width": 1440, "height": 900},
        "user_agent": UA,
        "args": args,
    }
    return playwright.chromium.launch_persistent_context(**kwargs)


def _logged_in(page) -> bool:
    """页面内判定登录态。

    小红书登录页对游客也会返回 state.user.loggedIn = true，因此必须同时满足
    「已离开登录页」与「loggedIn 为真」才算登录成功。
    """
    try:
        if any(hint in (page.url or "") for hint in LOGIN_HINTS):
            return False
        return bool(page.evaluate(
            "() => { const s = window.__INITIAL_STATE__;"
            " return !!(s && s.user && s.user.loggedIn); }"))
    except Exception:
        return False


def _web_session(ctx) -> str:
    return next((c["value"] for c in ctx.cookies()
                 if c.get("name") == "web_session"
                 and "xiaohongshu" in (c.get("domain") or "")), "")


def _login_error() -> LoginRequired:
    return LoginRequired(
        "小红书未登录：请在观测台「设置 → 浏览器登录」完成扫码登录后再采集")


def _read_profile(page, log) -> dict:
    """读取主页：账号指标 + 笔记列表（首屏 SSR，滚动补更多）。"""
    raw = page.evaluate(PROFILE_JS)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _read_detail(page) -> dict | None:
    try:
        raw = page.evaluate(DETAIL_JS)
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if data.get("id") else None


def fetch_page(cfg: dict, user_id: str, *, max_posts: int = 50,
               detail_limit: int = 10, timeout_ms: int = 45_000, log=print) -> dict:
    """打开本人主页，返回 {"account": {...}, "notes": [...]}。

    未登录抛 LoginRequired；环境不支持抛 BrowserUnavailable。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise BrowserUnavailable("未安装 playwright") from e

    url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
    api_notes: dict[str, dict] = {}

    def on_response(resp):
        if not any(hint in resp.url for hint in NOTE_API_HINTS):
            return
        try:
            if resp.status != 200:
                return
            payload = resp.json() or {}
        except Exception:
            return
        for raw in (payload.get("data") or {}).get("notes") or []:
            note = normalize_note(raw)
            if note and note["note_id"] not in api_notes:
                api_notes[note["note_id"]] = note

    log("小红书：打开浏览器读取主页…")
    log("小红书：按真人节奏放慢浏览，单篇笔记之间会随机停顿…")
    with sync_playwright() as pw:
        try:
            ctx = _launch(pw, profile_dir(cfg))
        except Exception as e:
            raise BrowserUnavailable(
                f"浏览器启动失败（小红书登录窗口可能正占用配置）：{e}") from e
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("response", on_response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as e:
                raise BrowserUnavailable(f"页面打开超时或失败：{e}") from e
            _pause(page, OPEN_PAUSE)
            if any(hint in page.url for hint in LOGIN_HINTS):
                raise _login_error()

            data = _read_profile(page, log)
            if not data:
                _pause(page, RELOAD_PAUSE)
                data = _read_profile(page, log)
            if not data:
                raise ParseError("小红书主页未返回数据，请确认登录态有效")

            notes = data.get("notes") or []
            # 笔记多于一屏时向下滚动，触发下一页接口
            rounds = 0
            while len(notes) < max_posts and rounds < 8:
                before = len(notes)
                _human_scroll(page)
                _pause(page, SCROLL_PAUSE)
                rounds += 1
                if len(notes) == before and rounds >= 3:
                    break
                data = _read_profile(page, log) or data
                notes = data.get("notes") or notes

            for note_id, note in api_notes.items():
                notes.append(note)

            # 首屏 SSR 的 interactInfo 只有点赞数，按需打开详情页补齐
            limit = max(0, int(detail_limit))
            filled = 0
            opened = 0
            for note in notes:
                if filled >= limit:
                    break
                if note.get("comments") is not None and note.get("saves") is not None:
                    continue
                if not note.get("token"):
                    continue
                # 打开详情前停留，间隔随机；每连续看几篇再长休息一次
                if opened and opened % DETAIL_REST_EVERY == 0:
                    _pause(page, DETAIL_REST)
                else:
                    _pause(page, DETAIL_PAUSE)
                detail_url = (f"https://www.xiaohongshu.com/explore/{note['id']}"
                              f"?xsec_token={note['token']}&xsec_source=pc_user")
                try:
                    page.goto(detail_url, wait_until="domcontentloaded",
                              timeout=timeout_ms)
                except Exception:
                    break
                opened += 1
                _pause(page, DETAIL_READ_PAUSE)
                detail = None
                for _ in range(6):
                    detail = _read_detail(page)
                    if detail:
                        break
                    page.wait_for_timeout(int(random.uniform(0.7, 1.1) * 1000))
                if not detail:
                    continue
                note.update({
                    "likes": detail.get("likes") if detail.get("likes") is not None else note.get("likes"),
                    "comments": detail.get("comments"),
                    "shares": detail.get("shares"),
                    "saves": detail.get("saves"),
                    "title": note.get("title") or detail.get("title") or "",
                    "desc": note.get("desc") or detail.get("desc") or "",
                    "time": note.get("time") or detail.get("time") or 0,
                    "type": note.get("type") or detail.get("type") or "",
                })
                filled += 1
                log(f"小红书：已补全详情 {filled}/{min(limit, len(notes))}")
            if notes:
                notes = notes[:max_posts]
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    basic = data.get("basic") or {}
    counts = {}
    for item in data.get("interactions") or []:
        name = item.get("name") or ""
        kind = item.get("type") or ""
        value = parse_count(item.get("count"))
        if name:
            counts[name] = value
        if kind == "fans":
            counts.setdefault("粉丝", value)
        elif kind == "follows":
            counts.setdefault("关注", value)
        elif kind == "interaction":
            counts.setdefault("获赞与收藏", value)
    account = {
        "nickname": basic.get("nickname") or "",
        "red_id": basic.get("redId") or "",
        "desc": basic.get("desc") or "",
        "followers": counts.get("粉丝"),
        "following": counts.get("关注"),
        "posts_count": parse_count(data.get("posted")),
        "likes_total": counts.get("获赞与收藏"),
    }
    return {"account": account, "notes": notes}


def interactive_login(cfg: dict, *, timeout: float = 300, log=print) -> str:
    """打开浏览器供本人手动扫码登录，登录成功返回 web_session 值。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise BrowserUnavailable("未安装 playwright：pip install playwright") from e

    log("小红书：已打开浏览器，请用小红书 App 扫码并在手机上确认登录…")
    with sync_playwright() as pw:
        try:
            ctx = _launch(pw, profile_dir(cfg), offscreen=False)
        except Exception as e:
            raise BrowserUnavailable(f"浏览器启动失败：{e}") from e
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.xiaohongshu.com/login",
                      wait_until="domcontentloaded", timeout=60_000)
            page.bring_to_front()
            waited = 0.0
            announced = 0.0
            while waited < timeout:
                page.wait_for_timeout(1000)
                waited += 1.0
                current = ctx.pages[-1] if ctx.pages else page
                if _logged_in(current):
                    page.wait_for_timeout(1200)  # 等站点写完整登录态
                    value = _web_session(ctx)
                    if value:
                        log("小红书：检测到已登录，会话已保存")
                        return value
                if waited - announced >= 20:
                    announced = waited
                    log(f"小红书：仍在等待扫码（已等 {int(waited)} 秒）…")
            raise LoginRequired("等待登录超时，请重试")
        finally:
            try:
                ctx.close()
            except Exception:
                pass
