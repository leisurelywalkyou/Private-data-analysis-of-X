"""浏览器登录对话框：由用户手动完成登录，只读取本人会话锚点 Cookie。"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox

from ..platforms import load
from ..platforms.browser_session import BrowserSessionBridge
from .theme import (FONT_SMALL, FONT_TITLE, HAIRLINE, INK, MUTED, PAPER, PAPER_2,
                    TEAL, VERMILION, action_button, apply_style, eyebrow, rule)


class BrowserLoginDialog(tk.Toplevel):
    def __init__(self, master, platform: str, profile_dir: str, on_session,
                 channel: str = "auto"):
        super().__init__(master)
        self.platform = platform
        self.on_session = on_session
        self.anchor = load(platform).session_cookie
        self.extras = tuple(getattr(load(platform), "extra_cookies", ()) or ())
        self.events: queue.Queue = queue.Queue()
        self.closed = False
        self.ready = False

        self.title("浏览器登录 · x 观测台")
        self.configure(bg=PAPER)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        apply_style(self)

        tk.Frame(self, bg=INK, height=4).pack(fill="x")
        body = tk.Frame(self, bg=PAPER, padx=26, pady=20)
        body.pack(fill="both", expand=True)

        eyebrow(body, "Browser Session · 手动登录").pack(anchor="w")
        tk.Label(body, text=f"登录 {load(platform).label}", bg=PAPER, fg=INK,
                 font=FONT_TITLE, anchor="w").pack(anchor="w", pady=(4, 6))
        credentials = self.anchor + ("、" + "、".join(self.extras) if self.extras else "")
        tk.Label(body, text="将打开独立浏览器窗口，请手动完成登录（含验证码）。"
                            f"程序只读取会话凭据 {credentials}，不注入脚本、不换代理。",
                 bg=PAPER, fg=MUTED, font=FONT_SMALL, wraplength=430,
                 justify="left", anchor="w").pack(anchor="w")

        rule(body).pack(fill="x", pady=(14, 12))

        status_row = tk.Frame(body, bg=PAPER)
        status_row.pack(fill="x")
        self.dot = tk.Canvas(status_row, width=8, height=8, bg=PAPER, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.status_lbl = tk.Label(status_row, text="正在启动浏览器…", bg=PAPER,
                                   fg=MUTED, font=FONT_SMALL, wraplength=420,
                                   justify="left", anchor="w")
        self.status_lbl.pack(side="left", fill="x", expand=True)
        self.set_status("正在启动浏览器…", "busy")

        btns = tk.Frame(body, bg=PAPER)
        btns.pack(fill="x", pady=(18, 0))
        self.read_btn = action_button(btns, "读取会话", self.read_session, "primary")
        self.read_btn.configure(state="disabled")
        self.set_read_enabled(False)
        self.read_btn.pack(side="right")
        action_button(btns, "关闭浏览器", self.cancel, "secondary").pack(
            side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bridge = BrowserSessionBridge(platform, profile_dir, self._on_event,
                                           channel=channel)
        self.bridge.start()
        self.after(300, self.poll)

    def set_status(self, text: str, tone: str = "muted"):
        color = {"muted": MUTED, "busy": VERMILION, "ok": TEAL}.get(tone, MUTED)
        self.dot.delete("all")
        self.dot.create_oval(0, 0, 7, 7, fill=color, outline="")
        self.status_lbl.configure(text=text)

    def set_read_enabled(self, enabled: bool):
        self.read_btn.configure(
            state="normal" if enabled else "disabled",
            bg=INK if enabled else HAIRLINE,
            fg=PAPER_2 if enabled else MUTED,
            activebackground=VERMILION,
            disabledforeground=MUTED)

    def _on_event(self, kind: str, payload):
        self.events.put((kind, payload))

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "ready":
                    self.ready = True
                    self.set_status("浏览器已打开。请完成登录，然后点击「读取会话」。", "ok")
                    self.set_read_enabled(True)
                elif kind == "session":
                    name = payload.get("name") or self.anchor
                    extras = payload.get("extras") or {}
                    read = name + ("、" + "、".join(extras) if extras else "")
                    self.set_status(f"已读取 {read}", "ok")
                    if self.on_session:
                        self.on_session(payload)
                    messagebox.showinfo("完成", f"已读取 {read}，请返回设置后点击保存。",
                                        parent=self)
                    self._close_browser()
                    self.destroy()
                    return
                elif kind == "error":
                    self.set_status(str(payload), "busy")
                    messagebox.showwarning("浏览器会话", str(payload), parent=self)
                    self.set_read_enabled(self.ready)
                elif kind == "closed":
                    self.destroy()
                    return
        except queue.Empty:
            pass
        self.after(300, self.poll)

    def read_session(self):
        self.set_read_enabled(False)
        self.set_status("正在读取会话…", "busy")
        self.bridge.read()

    def _close_browser(self):
        self.bridge.close()

    def cancel(self):
        self._close_browser()
        self.closed = True
        self.destroy()
