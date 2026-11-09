"""真实浏览器会话桥接：手动登录后读取本人会话锚点 Cookie。

只读取平台声明的锚点 Cookie（如 pixiv 的 PHPSESSID），不做反检测、代理或验证码处理。
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
from pathlib import Path

from . import load

DOMAINS = {
    "x": (".x.com", ".twitter.com"),
    "instagram": (".instagram.com",),
    "xiaohongshu": (".xiaohongshu.com",),
    "weibo": (".weibo.com", ".weibo.cn"),
    "pixiv": (".pixiv.net",),
    "tiktok": (".tiktok.com",),
}

LOGIN_URLS = {
    "x": "https://x.com/login",
    "instagram": "https://www.instagram.com/accounts/login/",
    "xiaohongshu": "https://www.xiaohongshu.com/login",
    "weibo": "https://weibo.com/login.php",
    "pixiv": "https://accounts.pixiv.net/login.php?lang=zh",
    "tiktok": "https://www.tiktok.com/login",
}


class BrowserSessionError(RuntimeError):
    pass


def session_value(cookies: list[dict], domains: tuple[str, ...], name: str) -> str:
    """只取目标域名下的锚点 Cookie 值。"""
    if not name:
        return ""
    for cookie in cookies:
        if cookie.get("name") != name:
            continue
        value = cookie.get("value")
        if not value:
            continue
        raw_domain = (cookie.get("domain") or "").lstrip(".").lower()
        for allowed in domains:
            host = allowed.lstrip(".").lower()
            if raw_domain == host or raw_domain.endswith("." + host):
                return value
    return ""


def session_values(cookies: list[dict], domains: tuple[str, ...],
                   names: tuple[str, ...]) -> dict[str, str]:
    """批量提取锚点与必需附加 Cookie（ct0 / tt_chain_token 等）。"""
    out = {}
    for name in names:
        if not name:
            continue
        value = session_value(cookies, domains, name)
        if value:
            out[name] = value
    return out


def find_browser_executable() -> str | None:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Microsoft/Edge/Application/msedge.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return shutil.which("chrome") or shutil.which("msedge")


class BrowserSessionBridge:
    """在后台线程运行 Playwright，保持浏览器窗口供手动登录。

    事件：
      ready   浏览器已打开，可以登录
      session 读取成功，payload 为
              {"name": 锚点名, "value": 锚点值, "extras": {附加 Cookie}} 
      error   启动或读取失败
      closed  浏览器已关闭
    """

    def __init__(self, platform: str, profile_dir: str, on_event,
                 channel: str = "auto"):
        self.platform = platform
        self.profile_dir = profile_dir
        self.on_event = on_event
        self.channel = channel or "auto"
        self.commands: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def read(self):
        self.commands.put("read")

    def close(self):
        self.commands.put("close")

    def _emit(self, kind: str, payload=None):
        self.on_event(kind, payload)

    def _launch(self, playwright):
        profile = Path(self.profile_dir)
        profile.mkdir(parents=True, exist_ok=True)
        kwargs = {"user_data_dir": str(profile), "headless": False}
        if self.channel != "auto":
            kwargs["channel"] = self.channel
        else:
            exe = find_browser_executable()
            if exe:
                kwargs["executable_path"] = exe
            else:
                kwargs["channel"] = "chrome"
        return playwright.chromium.launch_persistent_context(**kwargs)

    def _run(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._emit("error", "未安装 playwright：pip install playwright")
            return

        context = None
        try:
            with sync_playwright() as playwright:
                context = self._launch(playwright)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(LOGIN_URLS[self.platform], wait_until="domcontentloaded")
                self._emit("ready")
                while True:
                    try:
                        command = self.commands.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if command == "close":
                        break
                    if command == "read":
                        cls = load(self.platform)
                        anchor = cls.session_cookie
                        names = (anchor, *tuple(getattr(cls, "extra_cookies", ()) or ()))
                        values = session_values(context.cookies(),
                                                DOMAINS[self.platform], names)
                        if not values.get(anchor):
                            self._emit("error",
                                       f"未读取到 {anchor}，请确认已完成登录")
                        else:
                            extras = {k: v for k, v in values.items()
                                      if k != anchor}
                            self._emit("session", {"name": anchor,
                                                   "value": values[anchor],
                                                   "extras": extras})
        except Exception as e:
            self._emit("error", f"{type(e).__name__}: {e}")
        finally:
            # 正常关闭或启动失败都要释放持久化上下文，避免浏览器进程残留
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
                self._emit("closed")
