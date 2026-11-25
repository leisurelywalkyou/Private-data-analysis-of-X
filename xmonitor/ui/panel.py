"""观测台：五页式桌面界面。

左栏固定分区与平台范围，内容区依次为观测台、运行监控、数据分析、评估报告与设置，
底部常驻状态条，右下角吐司只承担“刚发生”的反馈。

数据仍来自现有的 store / analysis / report / scheduler，不新增采集或存储逻辑。
"""

from __future__ import annotations

import html
import os
import queue
import re
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..core import analysis, filesearch, report, schedule
from ..core.collector import make_store
from ..core.config import get_tz, load_config, report_dir, save_config
from ..core.scheduler import MultiCollectScheduler
from ..platforms import available, has_session, load
from .settings import SettingsPage
from .theme import (DOWN, FONT, FONT_DISPLAY, FONT_EYEBROW, FONT_LABEL,
                    FONT_MEDIUM, FONT_MONO_SMALL, FONT_NUM_BIG, FONT_NUM_MID,
                    FONT_SMALL, FONT_TITLE, GOLD, HAIRLINE, HAIRLINE_SOFT, INK, INK_SOFT,
                    MUTED, PAPER, PAPER_2, PAPER_3, PAPER_4, TEAL, Toggle, UP,
                    VERMILION, Field, NavItem, Pill, ScopeRow, Toast, action_button,
                    apply_style, card, center_window, eyebrow, rule, vrule)

TONE = {"muted": MUTED, "busy": GOLD, "ok": TEAL, "error": VERMILION}
METRIC_LABELS = {"likes": "赞", "comments": "评论", "shares": "转发",
                 "saves": "收藏", "views": "浏览", "plays": "播放"}
METRIC_KEYS = ("likes", "comments", "shares", "saves", "views")
ACCOUNT_KEYS = (("followers", "粉丝"), ("following", "关注"),
                ("posts_count", "帖子"), ("likes_total", "获赞"))
PLATES = (("01", "星期 × 小时互动热力图"), ("02", "每日互动增益曲线"),
          ("03", "每日浏览增益曲线"), ("04", "每小时平均互动增益"),
          ("05", "Top 3 帖子累计互动曲线"))
LEVEL_TONE = {"INFO": "muted", "OK": "ok", "WARN": "busy", "ERR": "error"}


def fmt_int(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def mix(color: str, other: str, ratio: float) -> str:
    """在两个 #rrggbb 颜色之间插值，ratio 为向 other 的比例。"""
    ratio = max(0.0, min(1.0, ratio))
    a = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(other[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * ratio) for x, y in zip(a, b))


class App:
    def __init__(self, root: tk.Tk, initial_page: str = "overview"):
        self.root = root
        self.cfg = load_config()
        self.tz = get_tz(self.cfg)
        self.scheduler = MultiCollectScheduler(self.cfg)
        self.platforms = available()
        self.platform = self._initial_platform()

        self.phase = {p: {"state": "idle", "started": None} for p in self.platforms}
        self.round = {"state": "idle", "started": None, "ended": None}
        self.logs: list[dict] = []
        self.scope_cache: dict[str, tuple[float, int]] = {}
        self.run_cache: dict[str, tuple[float, dict]] = {}
        self.report_busy = False
        self.report_q: queue.Queue = queue.Queue()
        self.report_buttons: list[tuple[tk.Button, str]] = []
        self.page = "overview"
        self.status = ("启动中…", "muted")
        self.auto_var = tk.BooleanVar(value=True)
        self.toast_box = Toast(root)

        self.build_ui()
        self.refresh_all()
        self.scheduler.start()
        self.poll_job = self.root.after(200, self.poll)
        self.tick_job = self.root.after(1000, self.tick)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if initial_page and initial_page != "overview":
            self.show_page(initial_page)

    def _initial_platform(self) -> str:
        blocks = self.cfg.get("platforms") or {}
        for platform in self.platforms:
            if (blocks.get(platform) or {}).get("enabled"):
                return platform
        return self.platforms[0] if self.platforms else ""

    # ---------- 外壳 ----------
    def build_ui(self):
        self.root.title("x 观测台 · 账号数据监控")
        self.root.geometry("1280x930")
        self.root.minsize(1120, 930)
        self.root.configure(bg=PAPER)
        apply_style(self.root)

        tk.Frame(self.root, bg=INK, height=4).pack(fill="x")
        self.build_statusbar()
        tk.Frame(self.root, bg=HAIRLINE, height=1).pack(side="bottom", fill="x")

        body = tk.Frame(self.root, bg=PAPER)
        body.pack(fill="both", expand=True)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)

        self.build_rail(body)
        tk.Frame(body, bg=HAIRLINE, width=1).grid(row=0, column=1, sticky="ns")
        main = tk.Frame(body, bg=PAPER)
        main.grid(row=0, column=2, sticky="nsew")
        self.build_main(main)
        self.show_page("overview", force=True)

    def build_rail(self, body):
        rail = tk.Frame(body, bg=PAPER, width=236)
        rail.grid(row=0, column=0, sticky="ns")
        rail.grid_propagate(False)

        inner = tk.Frame(rail, bg=PAPER, padx=16, pady=14)
        inner.pack(fill="both", expand=True)

        eyebrow(inner, "Observation Ledger").pack(anchor="w")
        tk.Label(inner, text="x 观测台", bg=PAPER, fg=INK, font=FONT_DISPLAY,
                 anchor="w").pack(anchor="w", pady=(2, 0))
        rule(inner).pack(fill="x", pady=(12, 10))

        tk.Label(inner, text="视图", bg=PAPER, fg=MUTED, font=FONT_EYEBROW,
                 anchor="w").pack(anchor="w", pady=(0, 4))
        nav_items = (("overview", "01", "观测台"), ("monitor", "02", "运行监控"),
                     ("schedule", "03", "本周计划"), ("files", "04", "文件检索"),
                     ("analytics", "05", "数据分析"), ("reports", "06", "评估报告"),
                     ("settings", "07", "设置"))
        self.nav_items: dict[str, NavItem] = {}
        for key, index, title in nav_items:
            item = NavItem(inner, index, title, command=lambda k=key: self.show_page(k))
            item.pack(fill="x", pady=(0, 2))
            self.nav_items[key] = item

        rule(inner).pack(fill="x", pady=(12, 10))
        tk.Label(inner, text="平台范围", bg=PAPER, fg=MUTED, font=FONT_EYEBROW,
                 anchor="w").pack(anchor="w", pady=(0, 4))
        self.scope_rows: dict[str, ScopeRow] = {}
        for platform in self.platforms:
            row = ScopeRow(inner, load(platform).label,
                           command=lambda p=platform: self.set_platform(p))
            row.pack(fill="x")
            self.scope_rows[platform] = row

        bottom = tk.Frame(inner, bg=PAPER)
        bottom.pack(side="bottom", fill="x", pady=(10, 0))
        rule(bottom).pack(fill="x", pady=(0, 10))
        controls = tk.Frame(bottom, bg=PAPER)
        controls.pack(fill="x")
        Toggle(controls, self.auto_var, command=self.on_auto_toggle).pack(side="left")
        tk.Label(controls, text="自动采集", bg=PAPER, fg=INK_SOFT,
                 font=FONT_SMALL).pack(side="left", padx=(8, 0))
        self.auto_hint = tk.Label(bottom, text="", bg=PAPER, fg=MUTED,
                                  font=FONT_SMALL, anchor="w")
        self.auto_hint.pack(fill="x", pady=(4, 0))

        interval_row = tk.Frame(bottom, bg=PAPER)
        interval_row.pack(fill="x", pady=(6, 0))
        self.interval_var = tk.StringVar(value=str(self.scheduler.interval))
        entry = tk.Entry(interval_row, textvariable=self.interval_var, width=4, bd=0,
                         relief="flat", bg=PAPER_2, fg=INK, font=FONT_MONO_SMALL,
                         justify="center", highlightthickness=1,
                         highlightbackground=HAIRLINE, highlightcolor=VERMILION)
        entry.pack(side="left", ipady=3, ipadx=2)
        entry.bind("<FocusOut>", lambda _e: self.on_interval())
        entry.bind("<Return>", lambda _e: self.on_interval())
        tk.Label(interval_row, text="分钟 / 轮", bg=PAPER, fg=MUTED,
                 font=FONT_SMALL).pack(side="left", padx=(6, 0))

    def build_main(self, main):
        head = tk.Frame(main, bg=PAPER, padx=28, pady=12)
        head.pack(fill="x")
        self.crumb = tk.Label(head, text="", bg=PAPER, fg=MUTED, font=FONT_EYEBROW,
                              anchor="w")
        self.crumb.pack(side="left")

        right = tk.Frame(head, bg=PAPER)
        right.pack(side="right")
        self.chip = Pill(right, "IDLE", "muted", bg=PAPER)
        self.chip.pack(side="right", padx=(12, 0))
        action_button(right, "刷新", self.refresh_all).pack(side="right", padx=(8, 0))
        action_button(right, "设置", lambda: self.show_page("settings")).pack(side="right")

        rule(main, HAIRLINE, 1).pack(fill="x", padx=28)

        host = tk.Frame(main, bg=PAPER, padx=28, pady=14)
        host.pack(fill="both", expand=True)
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        self.host = host

        self.overview = OverviewPage(host, self)
        self.monitor = MonitorPage(host, self)
        self.schedule = SchedulePage(host, self)
        self.files = FileSearchPage(host, self)
        self.analytics = AnalyticsPage(host, self)
        self.reports = ReportsPage(host, self)
        self.settings_page = SettingsPage(host, self.cfg,
                                          on_saved=self.on_settings_saved,
                                          on_data_cleared=self.on_data_cleared)
        self.pages = {"overview": self.overview, "monitor": self.monitor,
                      "schedule": self.schedule, "files": self.files,
                      "analytics": self.analytics, "reports": self.reports,
                      "settings": self.settings_page}
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def build_statusbar(self):
        bar = tk.Frame(self.root, bg=PAPER_2, padx=18, pady=8)
        bar.pack(side="bottom", fill="x")
        self.dot = tk.Canvas(bar, width=9, height=9, bg=PAPER_2, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.status_lbl = tk.Label(bar, text="启动中…", bg=PAPER_2, fg=MUTED,
                                   font=FONT_SMALL, anchor="w")
        self.status_lbl.pack(side="left")
        self.meta_lbl = tk.Label(bar, text="", bg=PAPER_2, fg=MUTED,
                                 font=FONT_LABEL, anchor="w")
        self.meta_lbl.pack(side="left", padx=(14, 0))
        tk.Label(bar, text="数据目录  data/platforms/", bg=PAPER_2, fg=MUTED,
                 font=FONT_SMALL, anchor="e").pack(side="right")
        self.status_more = action_button(bar, "查看运行监控",
                                         lambda: self.show_page("monitor"))
        self.set_status("启动中…", "muted")

    # ---------- 页面切换 ----------
    def show_page(self, key: str, force: bool = False):
        if key not in self.pages:
            return
        if (not force and self.page == "settings" and key != "settings"
                and self.settings_page.is_dirty()):
            if not messagebox.askyesno("未保存的更改",
                                       "设置中有未保存的更改，离开将丢失。仍要离开？",
                                       parent=self.root):
                return
            self.settings_page.discard()
        self.page = key
        self.pages[key].tkraise()
        for name, item in self.nav_items.items():
            item.set_active(name == key)
        labels = {"overview": ("01", "观测台", "OVERVIEW"),
                  "monitor": ("02", "运行监控", "RUN LOG"),
                  "schedule": ("03", "本周计划", "WEEKLY PLAN"),
                  "files": ("04", "文件检索", "FILE FINDER"),
                  "analytics": ("05", "数据分析", "ANALYTICS"),
                  "reports": ("06", "评估报告", "REPORTS"),
                  "settings": ("07", "设置", "SETTINGS")}
        index, title, latin = labels[key]
        self.crumb.configure(text=f"{index} · {title}   /   {latin}")
        page = self.pages[key]
        if hasattr(page, "on_show"):
            page.on_show()
        self.update_chip()

    def update_chip(self):
        if not hasattr(self, "chip"):
            return
        if self.page == "settings":
            self.chip.set("SETUP", "muted")
            return
        if any(v["state"] == "busy" for v in self.phase.values()):
            self.chip.set("BUSY", "busy")
        elif self.status[1] == "error":
            self.chip.set("ERR", "error")
        else:
            enabled = [p for p in self.platforms
                       if ((self.cfg.get("platforms") or {}).get(p) or {}).get("enabled")]
            self.chip.set(f"ACTIVE {len(enabled)}", "ok" if enabled else "muted")

    def set_platform(self, key: str):
        if not key or key == self.platform:
            return
        self.platform = key
        if self.page == "settings":
            self.settings_page.focus_platform(key)
            self.refresh_scope()
            return
        self.refresh_scope()
        self.overview.refresh()
        self.monitor.refresh()
        self.analytics.invalidate()
        self.reports.load()
        if self.page == "analytics":
            self.analytics.load()

    # ---------- 数据 ----------
    def store(self, platform: str | None = None):
        return make_store(self.cfg, platform or self.platform)

    def block(self, platform: str) -> dict:
        return (self.cfg.get("platforms") or {}).get(platform) or {}

    def configured(self, platform: str) -> bool:
        block = self.block(platform)
        has_account = bool(str(block.get("account_name") or "").strip()
                           or str(block.get("platform_user_id") or "").strip())
        return has_account and has_session(block, platform)

    def scope_count(self, platform: str) -> int:
        cached = self.scope_cache.get(platform)
        if cached and time.time() - cached[0] < 10:
            return cached[1]
        try:
            count = len(self.store(platform).load_posts())
        except Exception:
            count = 0
        self.scope_cache[platform] = (time.time(), count)
        return count

    def last_run(self, platform: str) -> dict:
        cached = self.run_cache.get(platform)
        if cached and time.time() - cached[0] < 10:
            return cached[1]
        try:
            stats = self.store(platform).stats()
            last = stats.get("last_run") or {}
        except Exception:
            last = {}
        self.run_cache[platform] = (time.time(), last)
        return last

    def local_time(self, iso: str, fmt: str = "%m-%d %H:%M") -> str:
        if not iso:
            return "—"
        try:
            return datetime.fromisoformat(iso).astimezone(self.tz).strftime(fmt)
        except ValueError:
            return iso[:16]

    def invalidate(self, platform: str | None = None):
        for p in ([platform] if platform else list(self.scope_cache) + list(self.run_cache)):
            self.scope_cache.pop(p, None)
            self.run_cache.pop(p, None)

    def refresh_all(self):
        self.refresh_scope()
        self.overview.refresh()
        self.monitor.refresh()
        self.reports.load()
        self.update_meta()
        self.update_chip()

    def refresh_scope(self):
        now = datetime.now()
        for platform, row in self.scope_rows.items():
            block = self.block(platform)
            state = self.scheduler.platform_state(platform)
            phase = self.phase.get(platform, {}).get("state", "idle")
            cooldown = state.get("cooldown_until")
            if phase == "busy":
                meta, tone = "采集中", "busy"
            elif cooldown and now < cooldown:
                meta, tone = "冷却", "busy"
            elif not block.get("enabled"):
                meta, tone = "停用", "muted"
            elif not self.configured(platform):
                meta, tone = "未配置", "error"
            else:
                meta, tone = str(self.scope_count(platform)), "ok"
            row.set(meta, tone, platform == self.platform)

    def update_meta(self):
        last = self.last_run(self.platform) if self.platform else {}
        last_text = self.local_time(last.get("started_at"), "%H:%M") if last else "—"
        nxt = self.scheduler.next_run()
        next_text = nxt.strftime("%H:%M") if nxt else "—"
        self.meta_lbl.configure(text=f"上次 {last_text} · 下次 {next_text}")
        self.auto_hint.configure(
            text="运行中 · 下次采集会顺延" if not self.scheduler.auto else "")

    def set_status(self, text: str, tone: str = "muted"):
        self.status = (text, tone)
        color = TONE.get(tone, MUTED)
        self.dot.delete("all")
        self.dot.create_oval(0, 0, 8, 8, fill=color, outline="")
        self.status_lbl.configure(text=text,
                                  fg=VERMILION if tone == "error" else MUTED)
        if tone == "error":
            if not self.status_more.winfo_manager():
                self.status_more.pack(side="right", padx=(0, 12))
        elif self.status_more.winfo_manager():
            self.status_more.pack_forget()
        self.update_chip()

    def toast(self, text: str, tone: str = "muted", ms: int = 4200):
        self.toast_box.show(text, tone, ms)

    # ---------- 交互 ----------
    def on_auto_toggle(self):
        self.scheduler.set_auto(self.auto_var.get())
        self.set_status("自动采集已开启" if self.scheduler.auto else "自动采集已暂停",
                        "ok" if self.scheduler.auto else "muted")
        self.update_meta()

    def on_interval(self):
        minutes = self.scheduler.set_interval(self.interval_var.get())
        self.interval_var.set(str(minutes))
        save_config(self.cfg, {"collect_interval_minutes": minutes})
        self.update_meta()
        self.toast(f"采集间隔已设为 {minutes} 分钟", "ok")

    def run_now(self):
        if not self.platform:
            return
        self.scheduler.trigger(self.platform)
        self.set_status(f"正在采集 {load(self.platform).label}…", "busy")
        self.toast(f"{load(self.platform).label} 已加入采集队列", "busy")

    def run_all(self):
        self.scheduler.trigger()
        self.set_status("正在采集全部平台…", "busy")
        self.toast("全部平台已加入采集队列", "busy")

    def open_settings(self, platform: str | None = None):
        if platform:
            self.settings_page.focus_platform(platform)
        self.show_page("settings")

    def on_settings_saved(self, _updates: dict):
        self.tz = get_tz(self.cfg)
        self.scheduler.set_interval(self.cfg.get("collect_interval_minutes", 30))
        self.interval_var.set(str(self.scheduler.interval))
        self.invalidate()
        self.refresh_all()
        self.set_status("设置已保存", "ok")
        self.toast("设置已保存", "ok")

    def on_data_cleared(self, platform: str):
        """清理平台数据后刷新库存、流水与图表缓存。"""
        self.invalidate(platform)
        self.overview.invalidate()
        self.analytics.invalidate()
        self.refresh_scope()
        if platform == self.platform:
            self.overview.refresh()
        self.monitor.refresh()
        self.set_status(f"{load(platform).label} 采集数据已清除", "muted")
        self.toast(f"{load(platform).label} 采集数据已清除", "muted")

    # ---------- 报告 ----------
    def register_report_button(self, button: tk.Button, text: str):
        self.report_buttons.append((button, text))

    def generate_report(self, platform: str, open_browser: bool = False,
                        preview: bool = False):
        if self.report_busy:
            self.toast("报告正在生成，请稍候…", "busy")
            return
        self.report_busy = True
        for button, text in self.report_buttons:
            button.configure(text="生成中…", state="disabled")
        self.set_status(f"正在生成 {load(platform).label} 报告…", "busy")

        def worker():
            try:
                paths = report.generate(self.cfg, platform, self.tz,
                                        top_n=3)["paths"]
                self.report_q.put(("ok", platform, paths, open_browser, preview))
            except Exception as e:  # 生成失败交给界面提示
                self.report_q.put(("err", platform, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def drain_report_queue(self):
        try:
            while True:
                kind, platform, payload, *flags = self.report_q.get_nowait()
                self.report_busy = False
                for button, text in self.report_buttons:
                    button.configure(text=text, state="normal")
                if kind == "ok":
                    paths = payload
                    open_browser, preview = flags
                    self.set_status(f"报告已生成 · {paths['latest']}", "ok")
                    self.toast(f"{load(platform).label} 报告已生成", "ok")
                    self.reports.load()
                    if open_browser:
                        webbrowser.open(Path(paths["latest"]).resolve().as_uri())
                    if preview:
                        self.reports.preview(Path(paths["latest"]))
                else:
                    self.set_status(f"报告生成失败：{payload}", "error")
                    self.toast(f"报告生成失败：{payload}", "error", 6000)
        except queue.Empty:
            pass

    # ---------- 调度事件 ----------
    def poll(self):
        for kind, payload in self.scheduler.poll():
            self.handle_event(kind, payload)
        self.drain_report_queue()
        self.update_meta()
        self.poll_job = self.root.after(200, self.poll)

    def handle_event(self, kind: str, payload):
        if kind == "platform_status":
            platform = payload["platform"]
            self.phase[platform] = {"state": "busy", "started": time.time()}
            if self.round["state"] != "running":
                self.round = {"state": "running", "started": time.time(), "ended": None}
            self.add_log("INFO", platform, "采集中…")
            self.set_status(f"{load(platform).label} 采集中…", "busy")
            self.invalidate(platform)
            self.refresh_scope()
            self.monitor.refresh()
        elif kind == "platform_done":
            platform = payload["platform"]
            coverage = payload["coverage"]
            coverage_text = "—" if coverage is None else f"{coverage}%"
            self.phase[platform] = {"state": "ok", "started": None}
            self.add_log("OK", platform,
                         f"新增 {payload['new']} · 快照 {payload['snapshots']}"
                         f" · 覆盖 {coverage_text}")
            self.toast(f"{load(platform).label}：新增 {payload['new']}"
                       f" · 快照 {payload['snapshots']}", "ok")
            self.set_status(f"{load(platform).label}：新增 {payload['new']}"
                            f" · 快照 {payload['snapshots']}"
                            f" · 字段覆盖 {coverage_text}", "ok")
            self.invalidate(platform)
            self.refresh_scope()
            self.monitor.refresh()
            if platform == self.platform:
                self.overview.refresh()
        elif kind == "platform_error":
            platform = payload["platform"]
            self.phase[platform] = {"state": "error", "started": None}
            hint = {"login": "请更新会话锚点", "challenge": "可能触发风控，已冷却",
                    "rate_limit": "触发限流，已冷却"}.get(payload["kind"], "")
            self.add_log("ERR", platform,
                         f"{payload['message']} · 已冷却 {payload['cooldown_minutes']} 分钟"
                         + (f" · {hint}" if hint else ""))
            self.toast(f"{load(platform).label} 失败：{payload['message']}"
                       + (f"（{hint}）" if hint else ""), "error", 6000)
            self.set_status(f"{load(platform).label} 失败：{payload['message']}"
                            + (f"（{hint}）" if hint else ""), "error")
            self.invalidate(platform)
            self.refresh_scope()
            self.monitor.refresh()
        elif kind == "platform_skip":
            platform = payload["platform"]
            self.phase[platform] = {"state": "skip", "started": None}
            self.add_log("WARN", platform, payload["message"])
            self.set_status(f"{load(platform).label}：{payload['message']}", "busy")
            self.refresh_scope()
            self.monitor.refresh()
        elif kind == "round_done":
            self.round["state"] = "done"
            self.round["ended"] = time.time()
            for p, info in self.phase.items():
                if info["state"] == "busy":
                    self.phase[p] = {"state": "idle", "started": None}
            self.add_log("OK", "本轮",
                         f"成功 {payload['ok']} · 失败 {payload['failed']}"
                         f" · 跳过 {payload['skipped']}")
            self.set_status(f"本轮完成：成功 {payload['ok']} · 失败 {payload['failed']}"
                            f" · 跳过 {payload['skipped']}", "ok")
            self.invalidate()
            self.refresh_scope()
            self.overview.refresh()
            self.monitor.refresh()
            self.update_badge()
        elif kind == "need_config":
            self.add_log("WARN", "调度", "缺少账号或会话锚点，本轮未采集")
            self.set_status("请先完成账号与会话配置", "error")
            if self.page != "settings":
                self.toast("账号或会话缺失，点左栏「设置」补齐", "error", 6000)
            self.refresh_scope()
            self.monitor.refresh()
        elif kind == "log":
            if payload:
                self.add_log("INFO", "", str(payload))
        elif kind == "status":
            self.set_status(str(payload or ""), "muted")
        self.update_chip()

    def update_badge(self):
        problems = sum(1 for p in self.platforms
                       if self.phase[p]["state"] in ("error", "skip"))
        self.nav_items["monitor"].set_badge(str(problems) if problems else "")

    def add_log(self, level: str, platform: str, message: str):
        entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level,
                 "platform": load(platform).label if platform in self.platforms
                 else (platform or "—"), "message": message}
        self.logs.append(entry)
        if len(self.logs) > 300:
            self.logs = self.logs[-300:]
        self.monitor.add_entry(entry)

    def tick(self):
        self.monitor.tick()
        self.update_meta()
        self.tick_job = self.root.after(1000, self.tick)

    def on_close(self):
        for job in (getattr(self, "poll_job", None), getattr(self, "tick_job", None)):
            try:
                self.root.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
        self.toast_box.hide()
        self.scheduler.stop()
        self.root.destroy()


class OverviewPage(tk.Frame):
    """01 观测台：账号条、库存/时效双层指标、帖子流水。"""

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=PAPER)
        self.app = app
        self.search_var = tk.StringVar()
        self.search_job = None
        self.rows_all: list[dict] = []
        self.urls: dict[str, str] = {}
        self.sort_key = "time"
        self.sort_desc = True
        self.delta_cache: dict[str, tuple[float, object]] = {}
        self.build()

    def build(self):
        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x")
        left = tk.Frame(head, bg=PAPER)
        left.pack(side="left", anchor="n")
        eyebrow(left, "Overview · 当前平台").pack(anchor="w")
        tk.Label(left, text="账号数据观测", bg=PAPER, fg=INK,
                 font=FONT_TITLE, anchor="w").pack(anchor="w", pady=(3, 0))
        self.sub_lbl = tk.Label(left, text="", bg=PAPER, fg=MUTED, font=FONT_SMALL,
                                anchor="w")
        self.sub_lbl.pack(anchor="w", pady=(3, 0))

        actions = tk.Frame(head, bg=PAPER)
        actions.pack(side="right", anchor="n")
        self.btn_now = action_button(actions, "采集当前", self.app.run_now, "primary")
        self.btn_now.pack(side="left")
        action_button(actions, "采集全部", self.app.run_all, "secondary").pack(
            side="left", padx=(8, 0))
        self.btn_report = action_button(actions, "生成报告", self.make_report,
                                        "secondary")
        self.btn_report.pack(side="left", padx=(8, 0))
        action_button(actions, "设置", lambda: self.app.show_page("settings")).pack(
            side="left", padx=(8, 0))
        self.app.register_report_button(self.btn_report, "生成报告")

        self.banner_slot = tk.Frame(self, bg=PAPER)
        self.banner_slot.pack(fill="x")
        self.banner = tk.Frame(self.banner_slot, bg=PAPER_2, highlightthickness=1,
                               highlightbackground=HAIRLINE)
        self.banner_lbl = tk.Label(self.banner, text="", bg=PAPER_2, fg=INK_SOFT,
                                   font=FONT_SMALL, anchor="w")
        self.banner_lbl.pack(side="left", padx=(12, 0), pady=8)
        self.banner_btn = action_button(self.banner, "去设置", None)
        self.banner_btn.pack(side="right", padx=(8, 8), pady=5)

        self.build_account()
        self.build_stats()
        self.build_list()

    def build_account(self):
        strip = card(self)
        strip.pack(fill="x", pady=(12, 10))
        inner = tk.Frame(strip, bg=PAPER_2, padx=16, pady=10)
        inner.pack(fill="x")

        self.account_vars = {}
        for key, label in ACCOUNT_KEYS:
            cell = tk.Frame(inner, bg=PAPER_2)
            cell.pack(side="left", padx=(0, 26))
            var = tk.StringVar(value="—")
            tk.Label(cell, textvariable=var, bg=PAPER_2, fg=INK,
                     font=FONT_NUM_MID, anchor="w").pack(anchor="w")
            tk.Label(cell, text=label, bg=PAPER_2, fg=MUTED, font=FONT_SMALL,
                     anchor="w").pack(anchor="w")
            self.account_vars[key] = var

        self.pills = tk.Frame(inner, bg=PAPER_2)
        self.pills.pack(side="right")
        self.enabled_pill = Pill(self.pills, "未启用", "muted")
        self.enabled_pill.pack(side="left", padx=(0, 6))
        self.session_pill = Pill(self.pills, "缺少锚点", "error")
        self.session_pill.pack(side="left")

    def build_stats(self):
        strip = card(self)
        strip.pack(fill="x", pady=(0, 14))
        inner = tk.Frame(strip, bg=PAPER_2)
        inner.pack(fill="x")

        left = tk.Frame(inner, bg=PAPER_2)
        left.pack(side="left", fill="x", expand=True)
        right = tk.Frame(inner, bg=PAPER_2)
        right.pack(side="right")
        vrule(inner).pack(side="right", fill="y")

        self.stat_vars = {}
        self.stat_labels = {}
        self.stat_captions = {}
        inventory = (("posts", "帖子", "POSTS"), ("snapshots", "快照", "SNAPSHOTS"),
                     ("runs", "采集轮次", "RUNS"), ("coverage", "字段覆盖", "COVERAGE"))
        for index, (key, label, latin) in enumerate(inventory):
            cell = tk.Frame(left, bg=PAPER_2, padx=16, pady=12)
            cell.grid(row=0, column=index, sticky="nsew")
            left.columnconfigure(index, weight=1)
            var, value, caption = self._cell(cell, key, label, latin)
            self.stat_vars[key] = var
            self.stat_labels[key] = value
            self.stat_captions[key] = caption

        heartbeat = (("delta", "本轮互动", "DELTA"), ("last", "上次采集", "LAST"),
                     ("next", "下次采集", "NEXT"))
        for index, (key, label, latin) in enumerate(heartbeat):
            cell = tk.Frame(right, bg=PAPER_2, padx=16, pady=12)
            cell.grid(row=0, column=index, sticky="nsew")
            right.columnconfigure(index, weight=1)
            var, value, caption = self._cell(cell, key, label, latin)
            self.stat_vars[key] = var
            self.stat_labels[key] = value
            self.stat_captions[key] = caption

    def _cell(self, parent, key, label, latin):
        var = tk.StringVar(value="—")
        value = tk.Label(parent, textvariable=var, bg=PAPER_2, fg=INK,
                         font=FONT_NUM_BIG, anchor="w")
        value.pack(anchor="w")
        caption = tk.Label(parent, text=f"{label}  {latin}", bg=PAPER_2, fg=MUTED,
                           font=FONT_LABEL, anchor="w")
        caption.pack(anchor="w", pady=(2, 0))
        return var, value, caption

    def build_list(self):
        list_head = tk.Frame(self, bg=PAPER)
        list_head.pack(fill="x")
        tk.Label(list_head, text="帖子流水", bg=PAPER, fg=INK,
                 font=FONT_MEDIUM, anchor="w").pack(side="left")
        self.count_lbl = tk.Label(list_head, text="", bg=PAPER, fg=MUTED,
                                  font=FONT_SMALL, anchor="w")
        self.count_lbl.pack(side="left", padx=(10, 0))
        self.metric_lbl = tk.Label(list_head, text="", bg=PAPER, fg=MUTED,
                                   font=FONT_SMALL, anchor="e")
        self.metric_lbl.pack(side="right")

        toolbar = tk.Frame(self, bg=PAPER)
        toolbar.pack(fill="x", pady=(6, 8))
        tk.Label(toolbar, text="搜索内容", bg=PAPER, fg=MUTED,
                 font=FONT_SMALL).pack(side="left")
        entry = tk.Entry(toolbar, textvariable=self.search_var, width=26, bd=0,
                         relief="flat", bg=PAPER_2, fg=INK, insertbackground=INK,
                         font=FONT, highlightthickness=1,
                         highlightbackground=HAIRLINE, highlightcolor=VERMILION)
        entry.pack(side="left", padx=(8, 0), ipady=4)
        entry.bind("<KeyRelease>", self.on_search)
        action_button(toolbar, "清空", self.clear_search).pack(side="left", padx=(6, 0))
        tk.Label(toolbar, text="双击 / ↵ 打开原帖 · 点列头排序", bg=PAPER, fg=MUTED,
                 font=FONT_SMALL).pack(side="right")

        body = tk.Frame(self, bg=HAIRLINE, padx=1, pady=1)
        body.pack(fill="both", expand=True)
        inner = tk.Frame(body, bg=PAPER_2)
        inner.pack(fill="both", expand=True)
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(0, weight=1)

        cols = ("time", *METRIC_KEYS, "text")
        self.tree = ttk.Treeview(inner, columns=cols, show="headings",
                                 selectmode="browse")
        heads = (("time", "发布时间", 112, "w"), ("likes", "赞", 58, "e"),
                 ("comments", "评论", 58, "e"), ("shares", "转发", 58, "e"),
                 ("saves", "收藏", 58, "e"), ("views", "浏览", 68, "e"),
                 ("text", "内容", 380, "w"))
        for key, label, width, anchor in heads:
            self.tree.heading(key, text=label, anchor=anchor,
                              command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key == "text"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self.on_row_open)
        self.tree.bind("<Return>", self.on_row_open)
        self.tree.tag_configure("odd", background=PAPER_2)
        self.tree.tag_configure("even", background=PAPER_4)
        self.tree.tag_configure("empty", foreground=MUTED)

        self.empty = tk.Frame(inner, bg=PAPER_2)
        self.empty_title = tk.Label(self.empty, text="", bg=PAPER_2, fg=INK,
                                    font=FONT_MEDIUM)
        self.empty_title.pack(pady=(40, 0))
        self.empty_note = tk.Label(self.empty, text="", bg=PAPER_2, fg=MUTED,
                                   font=FONT_SMALL, justify="center")
        self.empty_note.pack(pady=(6, 12))
        self.empty_btn = action_button(self.empty, "采集当前", self.app.run_now,
                                       "primary")
        self.empty_btn.pack()

    # ---------- 刷新 ----------
    def on_show(self):
        self.refresh()

    def invalidate(self):
        self.delta_cache.clear()

    def refresh(self):
        platform = self.app.platform
        if not platform:
            return
        cls = load(platform)
        block = self.app.block(platform)
        account = {}
        try:
            account = self.app.store().get_account()
        except Exception:
            pass
        self.update_header(cls, block, account)
        self.update_banner(platform, block)
        self.update_account(cls, block, account)
        self.refresh_stats(cls)
        self.refresh_list(cls)

    def update_header(self, cls, block, account):
        name = account.get("account_name") or block.get("account_name") or ""
        parts = [f"{cls.label} @{name}" if name else f"{cls.label} · 未配置账号"]
        self.sub_lbl.configure(text=" · ".join(parts))

    def update_banner(self, platform: str, block: dict):
        if not block.get("enabled"):
            text, action = "未启用 · 不参与调度", "去启用"
            command = lambda: self.app.open_settings(platform)
            tone = "muted"
        elif not self.app.configured(platform):
            text, action = "账号或会话锚点缺失 · 本轮不会采集", "去设置"
            command = lambda: self.app.open_settings(platform)
            tone = "error"
        else:
            state = self.app.scheduler.platform_state(platform)
            cooldown = state.get("cooldown_until")
            if cooldown and datetime.now() < cooldown:
                text, action = f"冷却中 · {cooldown:%H:%M} 后重试", "查看运行监控"
                command = lambda: self.app.show_page("monitor")
                tone = "busy"
            else:
                self.banner.pack_forget()
                return
        color = {"error": VERMILION, "busy": GOLD}.get(tone, MUTED)
        self.banner_lbl.configure(text=text, fg=color if tone != "muted" else INK_SOFT)
        self.banner_btn.configure(text=action, command=command)
        self.banner.pack(fill="x", pady=(0, 2))

    def update_account(self, cls, block: dict, account: dict):
        for key, _label in ACCOUNT_KEYS:
            if key in getattr(cls, "account_metrics", ()):
                self.account_vars[key].set(fmt_int(account.get(key)))
            else:
                self.account_vars[key].set("—")
        self.enabled_pill.set("已启用" if block.get("enabled") else "未启用",
                              "ok" if block.get("enabled") else "muted")
        if not getattr(cls, "requires_cookie", False):
            self.session_pill.set("免会话", "ok")
        elif has_session(block, self.app.platform):
            self.session_pill.set("会话有效", "ok")
        else:
            self.session_pill.set("缺少锚点", "error")

    def refresh_stats(self, cls):
        platform = self.app.platform
        try:
            stats = self.app.store().stats()
        except Exception:
            stats = {"posts": 0, "snapshots": 0, "runs": 0, "last_run": None}
        self.stat_vars["posts"].set(fmt_int(stats["posts"]))
        self.stat_vars["snapshots"].set(fmt_int(stats["snapshots"]))
        self.stat_vars["runs"].set(fmt_int(stats["runs"]))
        last = stats.get("last_run") or {}
        match = re.search(r"coverage=([\d.]+)", last.get("note") or "")
        self.stat_vars["coverage"].set(f"{match.group(1)}%" if match else "—")
        last_text = self.app.local_time(last.get("started_at"), "%m-%d %H:%M")
        self.stat_vars["last"].set(last_text if last.get("started_at") else "—")
        nxt = self.app.scheduler.next_run()
        self.stat_vars["next"].set(nxt.strftime("%H:%M") if nxt else "—")
        self.update_delta()

    def update_delta(self):
        platform = self.app.platform
        cached = self.delta_cache.get(platform)
        if cached and time.time() - cached[0] < 30:
            value = cached[1]
        else:
            value = None
            try:
                beat = analysis.deltas(self.app.store(), self.app.tz)["beat"]
                if beat["available"]:
                    value = beat["engagement"]
            except Exception:
                value = None
            self.delta_cache[platform] = (time.time(), value)
        if value is None:
            self.stat_vars["delta"].set("—")
            self.stat_labels["delta"].configure(foreground=INK)
            self.stat_captions["delta"].configure(text="本轮互动  DELTA")
            return
        self.stat_vars["delta"].set(f"{value:+,}")
        self.stat_labels["delta"].configure(
            foreground=UP if value > 0 else DOWN if value < 0 else MUTED)
        self.stat_captions["delta"].configure(
            text="本轮互动  DELTA · 较上一快照")

    def refresh_list(self, cls=None):
        if not self.app.platform:
            return
        cls = cls or load(self.app.platform)
        try:
            rows = self.app.store().posts_recent(200)
        except Exception:
            rows = []
        self.rows_all = rows
        self.urls.clear()
        shown = ["time"] + [k for k in METRIC_KEYS if k in cls.post_metrics] + ["text"]
        self.tree.configure(displaycolumns=shown)
        self.metric_lbl.configure(
            text="平台指标：" + "、".join(METRIC_LABELS.get(k, k)
                                        for k in cls.post_metrics))
        self.rebuild_rows(cls)

    def filtered_rows(self):
        keyword = self.search_var.get().strip().lower()
        rows = self.rows_all

        def sort_value(row):
            if self.sort_key == "time":
                return row.get("created_at") or ""
            if self.sort_key == "text":
                return (row.get("title") or row.get("text") or "").lower()
            value = row.get(self.sort_key)
            return -1 if value is None else value

        rows = sorted(rows, key=sort_value, reverse=self.sort_desc)
        if keyword:
            rows = [r for r in rows if keyword in
                    (f"{r.get('title') or ''} {r.get('text') or ''}").lower()]
        return rows

    def rebuild_rows(self, cls):
        self.tree.delete(*self.tree.get_children())
        rows = self.filtered_rows()
        if rows:
            self.empty.place_forget()
        for index, row in enumerate(rows):
            when = self.app.local_time(row.get("created_at") or "")
            values = []
            for key in METRIC_KEYS:
                values.append(str(row.get(key)) if key in cls.post_metrics
                              and row.get(key) is not None else "—")
            text = (row.get("title") or row.get("text") or "").replace("\n", " ")
            iid = str(row.get("post_id") or f"row{index}")
            self.tree.insert("", "end", iid=iid, values=(when, *values, text),
                             tags=("even" if index % 2 else "odd",))
            if row.get("url"):
                self.urls[iid] = row["url"]
        shown_count = len(rows)
        if self.search_var.get().strip():
            self.count_lbl.configure(
                text=f"匹配 {shown_count} / 共 {len(self.rows_all)} 条")
        else:
            self.count_lbl.configure(text=f"最近 {len(self.rows_all)} 条")
        self.update_empty(cls, shown_count)

    def update_empty(self, cls, shown):
        platform = self.app.platform
        block = self.app.block(platform)
        if shown:
            self.empty.place_forget()
            return
        if self.rows_all and self.search_var.get().strip():
            self.empty_title.configure(text="没有匹配的帖子")
            self.empty_note.configure(text="换个关键词，或清空搜索查看全部流水。")
            self.empty_btn.configure(text="清空搜索", command=self.clear_search)
        elif not self.app.configured(platform):
            self.empty_title.configure(text="还没有配置账号")
            self.empty_note.configure(
                text="先在设置里填写账号名称与会话锚点，才能开始采集。")
            self.empty_btn.configure(
                text="去设置",
                command=lambda: self.app.open_settings(platform))
        else:
            self.empty_title.configure(text="还没有帖子数据")
            self.empty_note.configure(
                text="1 采集当前  →  2 生成报告  →  3 长期观察")
            self.empty_btn.configure(text="采集当前", command=self.app.run_now)
        self.empty.place(relx=0, rely=0, relwidth=1, relheight=1)

    def on_search(self, _event=None):
        if self.search_job:
            try:
                self.after_cancel(self.search_job)
            except ValueError:
                pass
        self.search_job = self.after(300, self.refresh_list)

    def clear_search(self):
        self.search_var.set("")
        self.refresh_list()

    def sort_by(self, key: str):
        if not self.app.platform:
            return
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = key, True
        self.rebuild_rows(load(self.app.platform))

    def on_row_open(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        url = self.urls.get(selection[0])
        if url:
            webbrowser.open(url)

    def make_report(self):
        if self.app.platform:
            self.app.generate_report(self.app.platform, open_browser=True)


class MonitorPage(tk.Frame):
    """02 运行监控：本轮进度、平台状态卡与事件日志。"""

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=PAPER)
        self.app = app
        self.cards: dict[str, dict] = {}
        self.segments: dict[str, dict] = {}
        self.filter = "all"
        self.log_rows = 0
        self.build()

    def build(self):
        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x")
        left = tk.Frame(head, bg=PAPER)
        left.pack(side="left", anchor="n")
        eyebrow(left, "Run Log · 本轮与历史").pack(anchor="w")
        tk.Label(left, text="运行监控", bg=PAPER, fg=INK, font=FONT_TITLE,
                 anchor="w").pack(anchor="w", pady=(3, 0))
        self.round_lbl = tk.Label(left, text="", bg=PAPER, fg=MUTED,
                                  font=FONT_SMALL, anchor="w")
        self.round_lbl.pack(anchor="w", pady=(3, 0))
        action_button(head, "立即采集全部", self.app.run_all, "secondary").pack(
            side="right", anchor="n")

        progress = card(self, padx=14, pady=10)
        progress.pack(fill="x", pady=(12, 12))
        self.seg_frame = tk.Frame(progress, bg=PAPER_2)
        self.seg_frame.pack(fill="x")
        for platform in self.app.platforms:
            cell = tk.Frame(self.seg_frame, bg=PAPER_2)
            cell.pack(side="left", fill="x", expand=True, padx=(0, 10))
            name = tk.Label(cell, text=load(platform).label, bg=PAPER_2, fg=INK_SOFT,
                            font=FONT_SMALL, anchor="w")
            name.pack(anchor="w")
            canvas = tk.Canvas(cell, width=20, height=5, bg=PAPER_2,
                               highlightthickness=0)
            canvas.pack(fill="x", pady=(3, 0))
            self.segments[platform] = {"canvas": canvas, "name": name}

        grid = tk.Frame(self, bg=PAPER)
        grid.pack(fill="x")
        self.card_grid = grid
        for index, platform in enumerate(self.app.platforms):
            grid.columnconfigure(index % 3, weight=1, uniform="card")
            card_frame = card(grid)
            card_frame.grid(row=index // 3, column=index % 3, sticky="nsew",
                            padx=(0 if index % 3 == 0 else 6, 0),
                            pady=(0, 8))
            inner = tk.Frame(card_frame, bg=PAPER_2, padx=13, pady=10)
            inner.pack(fill="both", expand=True)
            top = tk.Frame(inner, bg=PAPER_2)
            top.pack(fill="x")
            name = tk.Label(top, text=load(platform).label, bg=PAPER_2, fg=INK,
                            font=FONT_MEDIUM, anchor="w")
            name.pack(side="left")
            pill = Pill(top, "就绪", "muted")
            pill.pack(side="right")
            info = tk.Label(inner, text="", bg=PAPER_2, fg=INK_SOFT, font=FONT_SMALL,
                            anchor="w", justify="left", wraplength=250)
            info.pack(fill="x", pady=(4, 0))
            detail = tk.Label(inner, text="", bg=PAPER_2, fg=MUTED, font=FONT_SMALL,
                              anchor="w", justify="left", wraplength=250)
            detail.pack(fill="x", pady=(2, 4))
            button = action_button(inner, "立即采集", None)
            button.pack(anchor="w")
            self.cards[platform] = {"pill": pill, "info": info,
                                    "detail": detail, "button": button}

        log_head = tk.Frame(self, bg=PAPER)
        log_head.pack(fill="x", pady=(6, 6))
        tk.Label(log_head, text="事件日志", bg=PAPER, fg=INK,
                 font=FONT_MEDIUM).pack(side="left")
        self.log_count = tk.Label(log_head, text="", bg=PAPER, fg=MUTED,
                                  font=FONT_SMALL)
        self.log_count.pack(side="left", padx=(8, 0))
        self.filter_btns = {}
        for key, text in (("all", "全部"), ("error", "错误"), ("skip", "跳过")):
            btn = action_button(log_head, text, lambda k=key: self.set_filter(k))
            btn.pack(side="left", padx=(8, 0))
            self.filter_btns[key] = btn
        action_button(log_head, "清空", self.clear_log).pack(side="right")

        body = tk.Frame(self, bg=HAIRLINE, padx=1, pady=1)
        body.pack(fill="both", expand=True, pady=(0, 2))
        inner = tk.Frame(body, bg=PAPER_2)
        inner.pack(fill="both", expand=True)
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(0, weight=1)
        self.log_tree = ttk.Treeview(inner, columns=("time", "level", "platform",
                                                     "message"), show="headings",
                                     selectmode="browse")
        for key, label, width, anchor in (("time", "时间", 74, "w"),
                                          ("level", "级别", 54, "w"),
                                          ("platform", "平台", 96, "w"),
                                          ("message", "说明", 620, "w")):
            self.log_tree.heading(key, text=label, anchor=anchor)
            self.log_tree.column(key, width=width, anchor=anchor,
                                 stretch=(key == "message"))
        self.log_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(inner, orient="vertical", command=self.log_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_tree.configure(yscrollcommand=scroll.set)
        for level, color in (("INFO", MUTED), ("OK", TEAL),
                             ("WARN", GOLD), ("ERR", VERMILION)):
            self.log_tree.tag_configure(level, foreground=color)
        self.set_filter("all")
        for entry in self.app.logs:
            self.add_entry(entry, scroll=False)
        self.update_log_count()

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.redraw_segments()
        for platform in self.app.platforms:
            self.refresh_card(platform)
        self.update_round()

    def tick(self):
        if self.app.page != "monitor":
            return
        self.update_round()
        for platform in self.app.platforms:
            info = self.app.phase.get(platform) or {}
            if info.get("state") == "busy" and info.get("started"):
                card = self.cards.get(platform)
                if card:
                    card["detail"].configure(
                        text=f"已用时 {self.elapsed(info['started'])}")

    @staticmethod
    def elapsed(started: float) -> str:
        total = int(max(0, time.time() - started))
        return f"00:{total // 60:02d}:{total % 60:02d}"

    def update_round(self):
        busy = [p for p, v in self.app.phase.items() if v["state"] == "busy"]
        if busy:
            started = self.app.round.get("started") or time.time()
            self.round_lbl.configure(
                text=f"本轮 · 运行中 · 已用时 {self.elapsed(started)}"
                     f" · {load(busy[0]).label} 采集中")
        elif self.app.round["state"] == "done":
            self.round_lbl.configure(text="本轮 · 已完成 · 等待下一轮")
        else:
            self.round_lbl.configure(text="本轮 · 等待下一轮")
        self.redraw_segments()

    def redraw_segments(self):
        for platform, item in self.segments.items():
            canvas = item["canvas"]
            canvas.delete("all")
            width = canvas.winfo_width()
            if width <= 1:
                width = 80
            state = self.app.phase.get(platform, {}).get("state", "idle")
            cooldown = self.app.scheduler.platform_state(platform).get("cooldown_until")
            if state == "busy":
                color = GOLD
            elif cooldown and datetime.now() < cooldown:
                color = GOLD
            elif state == "ok":
                color = TEAL
            elif state in ("error", "skip"):
                color = VERMILION
            elif not self.app.block(platform).get("enabled"):
                color = HAIRLINE
            elif not self.app.configured(platform):
                color = VERMILION
            else:
                color = TEAL
            canvas.create_rectangle(0, 0, width, 5, fill=PAPER_3, outline="")
            canvas.create_rectangle(0, 0, width, 5, fill=color, outline="")

    def refresh_card(self, platform: str):
        card = self.cards.get(platform)
        if not card:
            return
        block = self.app.block(platform)
        state = self.app.phase.get(platform, {}).get("state", "idle")
        sched = self.app.scheduler.platform_state(platform)
        cooldown = sched.get("cooldown_until")
        last = self.app.last_run(platform)
        last_text = self.app.local_time(last.get("started_at"), "%H:%M")
        coverage = re.search(r"coverage=([\d.]+)", last.get("note") or "")
        config_ok = self.app.configured(platform)

        if state == "busy":
            card["pill"].set("采集中", "busy")
            card["info"].configure(text=f"上次 {last_text}")
            card["detail"].configure(
                text=f"已用时 {self.elapsed(self.app.phase[platform].get('started') or time.time())}")
            card["button"].configure(text="采集中…", state="disabled", command=None)
        elif cooldown and datetime.now() < cooldown:
            card["pill"].set("冷却中", "busy")
            card["info"].configure(text=f"冷却至 {cooldown:%H:%M} · 上次 {last_text}")
            card["detail"].configure(text=(sched.get("last_error") or "避免重复请求")[:80])
            card["button"].configure(text="立即重试", state="normal",
                                     command=lambda p=platform: self.retry(p))
        elif not block.get("enabled"):
            card["pill"].set("停用", "muted")
            card["info"].configure(text="未参与调度")
            card["detail"].configure(text="在设置里启用后会加入自动采集。")
            card["button"].configure(text="去启用", state="normal",
                                     command=lambda p=platform: self.app.open_settings(p))
        elif not config_ok:
            card["pill"].set("未配置", "error")
            card["info"].configure(text="账号或会话缺失")
            card["detail"].configure(text="补齐账号名称与会话锚点后才能采集。")
            card["button"].configure(text="去设置", state="normal",
                                     command=lambda p=platform: self.app.open_settings(p))
        else:
            card["pill"].set("就绪", "ok")
            if last.get("status") == "error":
                card["info"].configure(text=f"上次 {last_text} · 失败")
                card["detail"].configure(text=(last.get("error") or "")[:90])
            else:
                card["info"].configure(
                    text=f"上次 {last_text} · 新增 {fmt_int(last.get('new_posts'))}"
                         f" · 快照 {fmt_int(last.get('snapshots'))}"
                         f" · 覆盖 {coverage.group(1) + '%' if coverage else '—'}")
                card["detail"].configure(text="等待下一轮或立即采集。")
            card["button"].configure(text="立即采集", state="normal",
                                     command=lambda p=platform: self.retry(p))

    def retry(self, platform: str):
        self.app.scheduler.trigger(platform)
        self.app.set_status(f"{load(platform).label} 已加入采集队列", "busy")
        self.app.toast(f"{load(platform).label} 已加入采集队列", "busy")

    def set_filter(self, key: str):
        self.filter = key
        for name, btn in self.filter_btns.items():
            active = name == key
            btn.configure(bg=PAPER_2 if active else PAPER,
                          fg=INK if active else MUTED,
                          highlightbackground=VERMILION if active else PAPER)
        self.rebuild_log()

    def match_filter(self, entry: dict) -> bool:
        if self.filter == "error":
            return entry["level"] == "ERR"
        if self.filter == "skip":
            return entry["level"] == "WARN"
        return True

    def rebuild_log(self):
        self.log_tree.delete(*self.log_tree.get_children())
        self.log_rows = 0
        for entry in self.app.logs:
            if self.match_filter(entry):
                self.insert_entry(entry)
        self.update_log_count()

    def add_entry(self, entry: dict, scroll: bool = True):
        if not self.match_filter(entry):
            return
        self.insert_entry(entry)
        self.update_log_count()
        if scroll:
            self.log_tree.yview_moveto(0)

    def insert_entry(self, entry: dict):
        self.log_rows += 1
        self.log_tree.insert("", 0, iid=f"log{self.log_rows}",
                             values=(entry["time"], entry["level"],
                                     entry["platform"], entry["message"]),
                             tags=(entry["level"],))

    def update_log_count(self):
        total = len(self.app.logs)
        self.log_count.configure(text=f"{self.log_rows} / {total} 条")

    def clear_log(self):
        self.app.logs.clear()
        self.log_tree.delete(*self.log_tree.get_children())
        self.log_rows = 0
        self.update_log_count()
        self.app.toast("事件日志已清空", "muted")


class SchedulePage(tk.Frame):
    """03 本周计划：7 天 × 6 个时段，支持备注内自定义时间区间。"""

    LEFT = 96
    TOP = 50

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=PAPER)
        self.app = app
        self.tasks: dict[str, dict] = {}
        self.build()

    def build(self):
        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x")
        left = tk.Frame(head, bg=PAPER)
        left.pack(side="left", anchor="n")
        eyebrow(left, "Weekly Plan · 本周分时段任务").pack(anchor="w")
        tk.Label(left, text="本周计划", bg=PAPER, fg=INK, font=FONT_TITLE,
                 anchor="w").pack(anchor="w", pady=(3, 0))
        self.sub_lbl = tk.Label(left, text="", bg=PAPER, fg=MUTED,
                                font=FONT_SMALL, anchor="w")
        self.sub_lbl.pack(anchor="w", pady=(3, 0))
        action_button(head, "刷新", self.load).pack(side="right", anchor="n")

        tip = tk.Frame(self, bg=PAPER_2, highlightthickness=1,
                       highlightbackground=HAIRLINE)
        tip.pack(fill="x", pady=(12, 10))
        tk.Label(tip, text="点击时段格子填写任务与可选的自定义时间；桌宠会在开始前 "
                           f"{schedule.LEAD_MINUTES} 分钟提醒一次，到点时再提醒一次。",
                 bg=PAPER_2, fg=INK_SOFT, font=FONT_SMALL, anchor="w").pack(
            fill="x", padx=12, pady=8)

        body = tk.Frame(self, bg=HAIRLINE, padx=1, pady=1)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=PAPER_2, highlightthickness=0,
                                cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<Button-1>", self.on_click)
        self.font_small = tkfont.Font(font=FONT_SMALL)

        self.load()

    def on_show(self):
        self.load()

    def load(self):
        self.tasks = schedule.load(self.app.cfg)
        start, end = schedule.week_range(datetime.now())
        total = sum(len(items) for items in self.tasks.values())
        self.sub_lbl.configure(
            text=f"本周 {start:%m-%d} — {end:%m-%d} · {total} 个任务")
        self.redraw()

    def metrics(self):
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        col_w = (width - self.LEFT - 4) / 7
        row_h = (height - self.TOP - 4) / len(schedule.SLOTS)
        return width, height, col_w, row_h

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        width, height, col_w, row_h = self.metrics()
        if width < 360 or height < 260:
            return
        now = datetime.now()
        dates = schedule.week_dates(now)
        for index, day in enumerate(schedule.WEEKDAYS):
            x = self.LEFT + col_w * index
            today = dates[index].date() == now.date()
            cv.create_text(x + col_w / 2, self.TOP / 2,
                           text=f"{day}\n{dates[index]:%m-%d}",
                           fill=VERMILION if today else MUTED,
                           font=FONT_LABEL, justify="center")
        for slot, spec in enumerate(schedule.SLOTS):
            y = self.TOP + row_h * slot
            cv.create_text(
                self.LEFT - 12, y + row_h / 2,
                text=f"{spec['label']}\n"
                     f"{schedule.format_clock(spec['start'])}-"
                     f"{schedule.format_clock(spec['end'])}",
                fill=MUTED, font=FONT_LABEL, anchor="e", justify="right")
        for slot in range(len(schedule.SLOTS) + 1):
            y = self.TOP + row_h * slot
            cv.create_line(self.LEFT, y, width - 4, y, fill=HAIRLINE_SOFT)
        for index in range(8):
            x = self.LEFT + col_w * index
            cv.create_line(x, self.TOP, x, height - 4, fill=HAIRLINE_SOFT)
        for slot in range(len(schedule.SLOTS)):
            for day in range(7):
                items = self.tasks.get(f"{day}:{slot}") or []
                if not items:
                    continue
                x = self.LEFT + col_w * day
                y = self.TOP + row_h * slot
                cv.create_rectangle(x + 2, y + 2, x + col_w - 2, y + row_h - 2,
                                    fill=mix(PAPER_2, TEAL, 0.13), outline="")
                text_y = y + 7
                for task in items[:3]:
                    prefix = f"{task['start']} " if task["start"] else ""
                    text_x = x + 8
                    if prefix:
                        cv.create_text(text_x, text_y, text=prefix, fill=GOLD,
                                       font=FONT_SMALL, anchor="nw")
                        text_x += self.font_small.measure(prefix)
                    cv.create_text(
                        text_x, text_y,
                        text=self.fit_line(task["title"],
                                           x + col_w - 8 - text_x),
                        fill=TEAL, font=FONT_SMALL, anchor="nw")
                    text_y += 15
                if len(items) > 3:
                    cv.create_text(x + 8, text_y, text=f"+{len(items) - 3} 项",
                                   fill=MUTED, font=FONT_LABEL, anchor="nw")
        if 0 <= now.weekday() < 7:
            x = self.LEFT + col_w * now.weekday()
            y = self.TOP + row_h * schedule.current_slot(now)
            cv.create_rectangle(x, y, x + col_w, y + row_h,
                                outline=VERMILION, width=1)

    def fit_line(self, text: str, width: float) -> str:
        text = " ".join(str(text).split())
        width = max(20.0, width)
        if self.font_small.measure(text) <= width:
            return text
        while text and self.font_small.measure(text + "…") > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def on_click(self, event):
        _width, _height, col_w, row_h = self.metrics()
        if event.x < self.LEFT or event.y < self.TOP:
            return
        day = int((event.x - self.LEFT) // col_w)
        slot = int((event.y - self.TOP) // row_h)
        if 0 <= day <= 6 and 0 <= slot < len(schedule.SLOTS):
            ScheduleSlotDialog(self.app, day, slot, self.load)


class ScheduleSlotDialog(tk.Toplevel):
    """同一时段的多任务编辑器，窗口位于屏幕中央。"""

    WIDTH = 720
    HEIGHT = 740

    def __init__(self, app: App, day: int, slot: int, on_changed):
        super().__init__(app.root)
        self.app = app
        self.day, self.slot = day, slot
        self.on_changed = on_changed
        self.tasks: dict[str, dict] = {}
        self.editing_id: str | None = None
        self.title("编辑本周任务 · x 观测台")
        self.configure(bg=PAPER)
        self.resizable(False, False)
        self.transient(app.root)
        self.grab_set()
        apply_style(self)

        tk.Frame(self, bg=INK, height=4).pack(fill="x")
        page = tk.Frame(self, bg=PAPER, padx=22, pady=14)
        page.pack(fill="both", expand=True)
        tk.Label(page, text=f"{schedule.WEEKDAYS[day]} · {schedule.slot_summary(slot)}",
                 bg=PAPER, fg=INK, font=FONT_TITLE, anchor="w").pack(fill="x")
        tk.Label(page, text="同一时段可添加多个任务，每个任务可单独设置标题、时间与备注。",
                 bg=PAPER, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            fill="x", pady=(3, 10))

        list_card = card(page)
        list_card.pack(fill="x")
        list_inner = tk.Frame(list_card, bg=PAPER_2, padx=10, pady=8)
        list_inner.pack(fill="both", expand=True)
        tree_wrap = tk.Frame(list_inner, bg=PAPER_2)
        tree_wrap.pack(fill="both", expand=True)
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_wrap, columns=("time", "title", "note"),
                                 show="headings", selectmode="browse", height=6)
        for key, label, width, anchor in (
                ("time", "时间", 110, "w"), ("title", "标题", 150, "w"),
                ("note", "备注", 330, "w")):
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key == "note"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical",
                               command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._load_selected)
        self.tree.tag_configure("odd", background=PAPER_2)
        self.tree.tag_configure("even", background=PAPER_4)

        bar = tk.Frame(list_inner, bg=PAPER_2)
        bar.pack(fill="x", pady=(8, 0))
        action_button(bar, "新增任务", self.new_task, "secondary").pack(side="left")
        action_button(bar, "删除选中", self.delete_task, "ghost",
                      fg=VERMILION).pack(side="left", padx=(6, 0))
        self.count_lbl = tk.Label(bar, text="", bg=PAPER_2, fg=MUTED,
                                  font=FONT_SMALL)
        self.count_lbl.pack(side="right")

        rule(page).pack(fill="x", pady=(12, 10))
        self.form_title = tk.Label(page, text="新增任务", bg=PAPER, fg=INK,
                                   font=FONT_MEDIUM, anchor="w")
        self.form_title.pack(fill="x")

        form = tk.Frame(page, bg=PAPER)
        form.pack(fill="x", pady=(6, 0))
        form.columnconfigure(0, weight=2)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, weight=1)
        self.title_var = tk.StringVar()
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.title_field = Field(form, "简要标题（必填）", self.title_var, width=20)
        self.title_field.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        Field(form, "开始 HH:MM", self.start_var, width=8).grid(
            row=0, column=1, sticky="ew", padx=(0, 14))
        Field(form, "结束 HH:MM", self.end_var, width=8).grid(
            row=0, column=2, sticky="ew")
        lower, upper = schedule.slot_bounds(slot)
        tk.Label(page, text=f"自定义时间可留空，默认使用时段范围 "
                           f"{schedule.format_clock(lower)}-{schedule.format_clock(upper)}；"
                           "同一时段内可设置多个相同或不同时间的任务。",
                 bg=PAPER, fg=MUTED, font=FONT_SMALL, anchor="w",
                 justify="left").pack(fill="x", pady=(4, 0))
        tk.Label(page, text="备注", bg=PAPER, fg=MUTED, font=FONT_SMALL,
                 anchor="w").pack(fill="x", pady=(8, 2))
        self.note = tk.Text(page, height=3, bd=0, relief="flat", bg=PAPER_2,
                            fg=INK, insertbackground=INK, font=FONT,
                            highlightthickness=1, highlightbackground=HAIRLINE,
                            highlightcolor=VERMILION, wrap="word", padx=8, pady=6)
        self.note.pack(fill="both", expand=True)
        self.error_lbl = tk.Label(page, text="", bg=PAPER, fg=VERMILION,
                                  font=FONT_SMALL, anchor="w")
        self.error_lbl.pack(fill="x", pady=(2, 0))

        buttons = tk.Frame(page, bg=PAPER)
        buttons.pack(fill="x", pady=(8, 0))
        action_button(buttons, "保存任务", self.save_task, "primary").pack(
            side="right")
        action_button(buttons, "关闭", self.destroy, "secondary").pack(
            side="right", padx=(0, 8))
        action_button(buttons, "清空表单", self.new_task).pack(side="left")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-Return>", lambda _e: self.save_task())

        self.reload()
        center_window(self, self.WIDTH, self.HEIGHT)

    def reload(self, select_id: str | None = None):
        tasks = schedule.slot_tasks(self.app.cfg, self.day, self.slot)
        self.tasks = {task["id"]: task for task in tasks}
        self.tree.delete(*self.tree.get_children())
        for index, task in enumerate(tasks):
            time_text = (f"{task['start']}-{task['end']}"
                         if task["start"] else "时段内")
            note = " ".join(task["text"].split())
            self.tree.insert("", "end", iid=task["id"],
                             values=(time_text, task["title"], note),
                             tags=("even" if index % 2 else "odd",))
        self.count_lbl.configure(text=f"共 {len(tasks)} 个任务")
        if select_id and select_id in self.tasks:
            self.tree.selection_set(select_id)
            self.tree.see(select_id)
        elif tasks:
            first = tasks[0]["id"]
            self.tree.selection_set(first)
            self.tree.see(first)
        else:
            self.new_task()

    def _load_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        task = self.tasks.get(selection[0])
        if not task:
            return
        self.editing_id = task["id"]
        self.form_title.configure(text=f"编辑任务 · {task['title']}")
        self.title_var.set(task["title"])
        self.start_var.set(task["start"])
        self.end_var.set(task["end"])
        self.note.delete("1.0", "end")
        self.note.insert("1.0", task["text"])
        self.error_lbl.configure(text="")

    def new_task(self):
        self.tree.selection_remove(*self.tree.selection())
        self.editing_id = None
        self.form_title.configure(text="新增任务")
        self.title_var.set("")
        self.start_var.set("")
        self.end_var.set("")
        self.note.delete("1.0", "end")
        self.error_lbl.configure(text="")
        self.title_field.entry.focus_set()

    def save_task(self):
        title = self.title_var.get().strip()
        text = self.note.get("1.0", "end").strip()
        start = self.start_var.get().strip()
        end = self.end_var.get().strip()
        try:
            if self.editing_id:
                task = schedule.update_task(
                    self.app.cfg, self.day, self.slot, self.editing_id,
                    title, text, start, end)
            else:
                task = schedule.add_task(
                    self.app.cfg, self.day, self.slot, title, text, start, end)
        except ValueError as e:
            self.error_lbl.configure(text=str(e))
            return
        self.reload(task["id"])
        self.on_changed()
        self.error_lbl.configure(text="")

    def delete_task(self):
        selection = self.tree.selection()
        if not selection:
            self.error_lbl.configure(text="先选择要删除的任务")
            return
        task = self.tasks.get(selection[0])
        if not task:
            return
        if not messagebox.askyesno("删除任务", f"删除「{task['title']}」？",
                                   parent=self):
            return
        if schedule.delete_task(self.app.cfg, self.day, self.slot, task["id"]):
            self.reload()
            self.on_changed()


class FileSearchPage(tk.Frame):
    """04 文件检索：按多个范围顺序扫描，按名称、后缀与类型筛选。"""

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=PAPER)
        self.app = app
        self.scopes: list[dict] = []
        self.result_paths: dict[str, str] = {}
        self.result_q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.search_id = 0
        self._alive = True
        self.build()
        self.bind("<Destroy>", self._on_destroy)
        self.after(120, self._poll)
        self._load_scopes()

    def build(self):
        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x")
        left = tk.Frame(head, bg=PAPER)
        left.pack(side="left", anchor="n")
        eyebrow(left, "File Finder · 本机小范围检索").pack(anchor="w")
        tk.Label(left, text="文件检索", bg=PAPER, fg=INK, font=FONT_TITLE,
                 anchor="w").pack(anchor="w", pady=(3, 0))
        tk.Label(left, text="按顺序扫描多个范围，可按名称、后缀与文件类型筛选",
                 bg=PAPER, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            anchor="w", pady=(3, 0))

        body = tk.Frame(self, bg=PAPER)
        body.pack(fill="both", expand=True, pady=(12, 0))
        body.columnconfigure(0, minsize=320)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left_col = tk.Frame(body, bg=PAPER)
        left_col.grid(row=0, column=0, sticky="ns")
        right_col = tk.Frame(body, bg=PAPER)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(18, 0))
        self.build_scopes(left_col)
        self.build_search(right_col)

    def build_scopes(self, parent):
        box = card(parent)
        box.pack(fill="both", expand=True)
        inner = tk.Frame(box, bg=PAPER_2, padx=14, pady=12)
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text="检索范围", bg=PAPER_2, fg=INK,
                 font=FONT_MEDIUM, anchor="w").pack(anchor="w")
        tk.Label(inner, text="按列表顺序依次检索", bg=PAPER_2, fg=MUTED,
                 font=FONT_SMALL, anchor="w").pack(anchor="w", pady=(2, 8))

        list_wrap = tk.Frame(inner, bg=PAPER_2)
        list_wrap.pack(fill="both", expand=True)
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)
        self.scope_tree = ttk.Treeview(
            list_wrap, columns=("mode", "path"), show="headings",
            selectmode="browse", height=12)
        self.scope_tree.heading("mode", text="模式", anchor="w")
        self.scope_tree.heading("path", text="文件夹", anchor="w")
        self.scope_tree.column("mode", width=90, anchor="w", stretch=False)
        self.scope_tree.column("path", width=380, anchor="w", stretch=True)
        self.scope_tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(list_wrap, orient="vertical",
                                command=self.scope_tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(list_wrap, orient="horizontal",
                                command=self.scope_tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.scope_tree.configure(yscrollcommand=yscroll.set,
                                  xscrollcommand=hscroll.set)
        self.scope_tree.tag_configure("missing", foreground=VERMILION)
        self.scope_tree.tag_configure("dragging", background=PAPER_3)
        self.scope_tree.configure(cursor="hand2")
        self._drag_start = None
        self._dragging = False
        self._drag_iid = None
        self.scope_tree.bind("<ButtonPress-1>", self._scope_press)
        self.scope_tree.bind("<B1-Motion>", self._scope_drag)
        self.scope_tree.bind("<ButtonRelease-1>", self._scope_release)
        self.scope_tree.bind("<Button-3>", self._scope_menu)
        self.scope_menu = tk.Menu(
            self, tearoff=0, font=FONT, bg=PAPER_2, fg=INK,
            activebackground=INK, activeforeground=PAPER_2,
            activeborderwidth=0, bd=0, relief="flat", selectcolor=PAPER_2,
            postcommand=self._refresh_scope_menu)
        self.scope_menu.add_command(label="切换范围模式",
                                    command=self.toggle_scope_mode)
        self.scope_menu.add_separator()
        self.scope_menu.add_command(label="移除", command=self.remove_scope)

        action_button(inner, "添加文件夹", self.add_scope, "secondary").pack(
            fill="x", pady=(10, 6))
        row = tk.Frame(inner, bg=PAPER_2)
        row.pack(fill="x")
        action_button(row, "移除", self.remove_scope, "ghost",
                      fg=VERMILION).pack(side="right")
        tk.Label(inner, text="点击左侧「模式」列切换仅本级/含子文件夹；"
                            "拖拽行调整检索优先级；右键可删除。新范围默认包含子文件夹。",
                 bg=PAPER_2, fg=MUTED, font=FONT_SMALL, anchor="w",
                 justify="left", wraplength=300).pack(fill="x", pady=(8, 0))

    def build_search(self, parent):
        filters = card(parent)
        filters.pack(fill="x")
        inner = tk.Frame(filters, bg=PAPER_2, padx=14, pady=12)
        inner.pack(fill="x")
        row = tk.Frame(inner, bg=PAPER_2)
        row.pack(fill="x")
        self.name_var = tk.StringVar()
        self.ext_var = tk.StringVar()
        self.category_var = tk.StringVar(value="全部")
        Field(row, "名称包含", self.name_var, width=18).pack(
            side="left", fill="x", expand=True)
        Field(row, "后缀（逗号分隔）", self.ext_var, width=14).pack(
            side="left", padx=(14, 0))
        type_cell = tk.Frame(row, bg=PAPER_2)
        type_cell.pack(side="left", padx=(14, 0))
        tk.Label(type_cell, text="文件类型", bg=PAPER_2, fg=MUTED,
                 font=FONT_SMALL, anchor="w").pack(anchor="w")
        self.type_box = ttk.Combobox(
            type_cell, textvariable=self.category_var,
            values=filesearch.CATEGORY_NAMES, state="readonly", width=9,
            font=FONT)
        self.type_box.pack(pady=(5, 0))

        actions = tk.Frame(inner, bg=PAPER_2)
        actions.pack(fill="x", pady=(12, 0))
        self.start_btn = action_button(actions, "开始检索", self.start_search,
                                       "primary")
        self.start_btn.pack(side="left")
        self.stop_btn = action_button(actions, "停止", self.stop_search,
                                      "secondary")
        self.stop_btn.configure(state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        action_button(actions, "清空结果", self.clear_results, "ghost").pack(
            side="left", padx=(4, 0))
        self.status_lbl = tk.Label(actions, text="尚未检索", bg=PAPER_2,
                                   fg=MUTED, font=FONT_SMALL, anchor="e")
        self.status_lbl.pack(side="right")

        results = card(parent)
        results.pack(fill="both", expand=True, pady=(12, 0))
        result_inner = tk.Frame(results, bg=PAPER_2)
        result_inner.pack(fill="both", expand=True)
        toolbar = tk.Frame(result_inner, bg=PAPER_2, padx=12, pady=8)
        toolbar.pack(fill="x")
        self.count_lbl = tk.Label(toolbar, text="共 0 条", bg=PAPER_2, fg=MUTED,
                                  font=FONT_SMALL, anchor="w")
        self.count_lbl.pack(side="left")
        action_button(toolbar, "复制路径", self.copy_path).pack(side="right")
        action_button(toolbar, "打开所在文件夹", self.reveal_selected).pack(
            side="right", padx=(0, 8))
        action_button(toolbar, "打开文件", self.open_selected, "secondary").pack(
            side="right", padx=(0, 8))

        table = tk.Frame(result_inner, bg=HAIRLINE, padx=1, pady=1)
        table.pack(fill="both", expand=True)
        tree_wrap = tk.Frame(table, bg=PAPER_2)
        tree_wrap.pack(fill="both", expand=True)
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_wrap, columns=("name", "category", "ext", "size", "mtime", "path"),
            show="headings", selectmode="browse")
        for key, label, width, anchor in (
                ("name", "文件名", 180, "w"), ("category", "类型", 60, "w"),
                ("ext", "后缀", 50, "w"), ("size", "大小", 70, "e"),
                ("mtime", "修改时间", 140, "w"), ("path", "所在目录", 300, "w")):
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key == "path"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical",
                               command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(tree_wrap, orient="horizontal",
                                command=self.tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        self.tree.bind("<Double-1>", lambda _e: self.open_selected())
        self.tree.bind("<Return>", lambda _e: self.open_selected())
        self.tree.tag_configure("odd", background=PAPER_2)
        self.tree.tag_configure("even", background=PAPER_4)

    # ---------- 范围 ----------
    def _load_scopes(self):
        self.scopes = filesearch.load_scopes(self.app.cfg)
        self._render_scopes()

    def _render_scopes(self):
        self.scope_tree.delete(*self.scope_tree.get_children())
        for index, item in enumerate(self.scopes):
            path = item["path"]
            mode = "含子文件夹" if item.get("recursive", True) else "仅本级"
            tags = () if Path(path).is_dir() else ("missing",)
            self.scope_tree.insert("", "end", iid=str(index),
                                   values=(mode, path), tags=tags)

    def _save_scopes(self):
        filesearch.save_scopes(self.app.cfg, self.scopes)

    def _selected_scope(self) -> int | None:
        selection = self.scope_tree.selection()
        return int(selection[0]) if selection else None

    def _select_scope(self, index: int):
        iid = str(index)
        self.scope_tree.selection_set(iid)
        self.scope_tree.focus(iid)
        self.scope_tree.see(iid)

    def _scope_press(self, event):
        self._drag_start = None
        self._dragging = False
        self._drag_iid = None
        row = self.scope_tree.identify_row(event.y)
        if not row:
            return
        self.scope_tree.selection_set(row)
        self.scope_tree.focus(row)
        self._drag_start = (row, self.scope_tree.identify_column(event.x),
                            event.y)

    def _scope_drag(self, event):
        if not self._drag_start:
            return
        row, column, y0 = self._drag_start
        if column == "#1":
            return
        if not self._dragging:
            if abs(event.y - y0) < 8:
                return
            self._dragging = True
            self._drag_iid = row
            self.scope_tree.item(row, tags=("dragging",))
            self.scope_tree.configure(cursor="fleur")
        target = self.scope_tree.identify_row(event.y)
        if not target:
            children = self.scope_tree.get_children()
            target = children[-1] if children else ""
        if target and target != row:
            index = self.scope_tree.index(target)
            self.scope_tree.move(row, "", index)
            self.scope_tree.see(row)

    def _scope_release(self, event):
        if not self._drag_start:
            return
        row, column, y0 = self._drag_start
        dragging = self._dragging
        drag_iid = self._drag_iid
        self._drag_start = None
        self._dragging = False
        self._drag_iid = None
        self.scope_tree.configure(cursor="hand2")
        if dragging and drag_iid:
            order = [int(iid) for iid in self.scope_tree.get_children()]
            old = self.scopes
            self.scopes = [old[index] for index in order]
            self._save_scopes()
            self._render_scopes()
            self._select_scope(order.index(int(drag_iid)))
            self.app.toast("检索优先级已更新", "ok")
        elif column == "#1" and abs(event.y - y0) <= 4:
            self.toggle_scope_mode(int(row))

    def _scope_menu(self, event):
        row = self.scope_tree.identify_row(event.y)
        if row:
            self.scope_tree.selection_set(row)
        try:
            self.scope_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.scope_menu.grab_release()

    def _refresh_scope_menu(self):
        index = self._selected_scope()
        if index is None or not (0 <= index < len(self.scopes)):
            self.scope_menu.entryconfigure(0, label="切换范围模式",
                                           state="disabled")
            return
        current = self.scopes[index].get("recursive", True)
        self.scope_menu.entryconfigure(
            0, label="改为仅当前文件夹" if current else "改为包含子文件夹",
            state="normal")

    def add_scope(self):
        path = filedialog.askdirectory(parent=self.winfo_toplevel(),
                                       title="添加检索范围")
        if not path:
            return
        path = os.path.abspath(path)
        key = os.path.normcase(path)
        if any(os.path.normcase(os.path.abspath(item["path"])) == key
               for item in self.scopes):
            self.app.toast("该范围已在列表中", "busy")
            return
        self.scopes.append({"path": path, "recursive": True})
        self._save_scopes()
        self._render_scopes()
        self._select_scope(len(self.scopes) - 1)

    def toggle_scope_mode(self, index: int | None = None):
        if index is None:
            index = self._selected_scope()
        if index is None or not (0 <= index < len(self.scopes)):
            self.app.toast("先选择一个检索范围", "busy")
            return
        item = self.scopes[index]
        item["recursive"] = not item.get("recursive", True)
        self._save_scopes()
        self._render_scopes()
        self._select_scope(index)
        self.app.toast("已切换为：" + ("包含子文件夹" if item["recursive"]
                                      else "仅当前文件夹"), "ok")

    def remove_scope(self):
        index = self._selected_scope()
        if index is None:
            self.app.toast("先选择一个检索范围", "busy")
            return
        self.scopes.pop(index)
        self._save_scopes()
        self._render_scopes()
        if self.scopes:
            self._select_scope(min(index, len(self.scopes) - 1))

    # ---------- 检索 ----------
    def start_search(self):
        if self.worker and self.worker.is_alive():
            self.app.toast("正在检索，请稍候", "busy")
            return
        if not self.scopes:
            self.app.toast("请先添加检索范围", "busy")
            return
        self._clear_results()
        self.stop_event = threading.Event()
        self.search_id += 1
        search_id = self.search_id
        self.status_lbl.configure(text=f"正在检索 {len(self.scopes)} 个范围…",
                                  fg=GOLD)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.worker = threading.Thread(
            target=self._run_search,
            args=(list(self.scopes), self.name_var.get().strip(),
                  filesearch.parse_extensions(self.ext_var.get()),
                  self.category_var.get(), self.stop_event, search_id),
            daemon=True)
        self.worker.start()

    def _run_search(self, scopes, name, extensions, category, stop_event, search_id):
        try:
            results = filesearch.search(
                scopes, name=name, extensions=extensions, category=category,
                stop_event=stop_event)
            self.result_q.put(("done", results, stop_event.is_set(), search_id))
        except Exception as e:
            self.result_q.put(("error", f"{type(e).__name__}: {e}", search_id))

    def stop_search(self):
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.status_lbl.configure(text="正在停止…", fg=GOLD)

    def _poll(self):
        if not self._alive:
            return
        try:
            while True:
                event = self.result_q.get_nowait()
                if event[0] == "done":
                    if event[3] == self.search_id:
                        self._show_results(event[1], event[2])
                elif event[2] == self.search_id:
                    self._search_failed(event[1])
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _show_results(self, results: list[dict], stopped: bool):
        self._clear_results()
        for index, item in enumerate(results):
            iid = f"r{index}"
            self.tree.insert("", "end", iid=iid, values=(
                item["name"], item["category"], item["ext"] or "—",
                self.fmt_size(item["size"]),
                datetime.fromtimestamp(item["mtime"]).strftime("%Y-%m-%d %H:%M"),
                str(Path(item["path"]).parent)),
                tags=("even" if index % 2 else "odd",))
            self.result_paths[iid] = item["path"]
        self.count_lbl.configure(text=f"共 {len(results)} 条")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if stopped:
            text, tone = f"已停止：显示 {len(results)} 个文件", MUTED
        elif results:
            text, tone = f"检索完成：{len(results)} 个文件", TEAL
        else:
            text, tone = "没有匹配的文件", MUTED
        self.status_lbl.configure(text=text, fg=tone)

    def _search_failed(self, message: str):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_lbl.configure(text=f"检索失败：{message}", fg=VERMILION)
        self.app.toast(f"检索失败：{message}", "error", 6000)

    def clear_results(self):
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
        self.search_id += 1
        self._clear_results()
        self.status_lbl.configure(text="已清空", fg=MUTED)

    def _clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.result_paths.clear()
        self.count_lbl.configure(text="共 0 条")

    # ---------- 结果操作 ----------
    def _selected_path(self) -> str | None:
        selection = self.tree.selection()
        return self.result_paths.get(selection[0]) if selection else None

    def open_selected(self):
        path = self._selected_path()
        if not path:
            self.app.toast("先选择一个文件", "busy")
            return
        try:
            os.startfile(path)
        except OSError as e:
            self.app.toast(f"打开失败：{e}", "error", 6000)

    def reveal_selected(self):
        path = self._selected_path()
        if not path:
            self.app.toast("先选择一个文件", "busy")
            return
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except OSError as e:
            self.app.toast(f"打开文件夹失败：{e}", "error", 6000)

    def copy_path(self):
        path = self._selected_path()
        if not path:
            self.app.toast("先选择一个文件", "busy")
            return
        self.clipboard_clear()
        self.clipboard_append(path)
        self.app.toast("文件路径已复制", "ok")

    @staticmethod
    def fmt_size(size: float) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"

    def _on_destroy(self, _event=None):
        self._alive = False
        self.stop_event.set()


class AnalyticsPage(tk.Frame):
    """05 数据分析：区间 KPI、热力图与四张曲线图。"""

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=PAPER)
        self.app = app
        self.days = 30
        self.data = None
        self.loaded_key = None
        self.build()

    def build(self):
        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x")
        left = tk.Frame(head, bg=PAPER)
        left.pack(side="left", anchor="n")
        eyebrow(left, "Analytics · 本地快照差分").pack(anchor="w")
        tk.Label(left, text="数据分析", bg=PAPER, fg=INK, font=FONT_TITLE,
                 anchor="w").pack(anchor="w", pady=(3, 0))
        self.sub_lbl = tk.Label(left, text="", bg=PAPER, fg=MUTED, font=FONT_SMALL,
                                anchor="w")
        self.sub_lbl.pack(anchor="w", pady=(3, 0))

        right = tk.Frame(head, bg=PAPER)
        right.pack(side="right", anchor="n")
        self.range_btns = {}
        for days in (7, 30, 90):
            btn = action_button(right, f"{days} 天",
                                lambda d=days: self.set_days(d))
            btn.pack(side="left", padx=(0, 6))
            self.range_btns[days] = btn
        action_button(right, "浏览器查看完整报告", self.open_report).pack(
            side="left", padx=(6, 0))

        kpis = card(self, padx=14, pady=10)
        kpis.pack(fill="x", pady=(12, 12))
        self.kpi_vars = {}
        for index, (key, label) in enumerate((("engagement", "总互动"),
                                              ("impressions", "总浏览"),
                                              ("avg", "单条均互动"),
                                              ("days_seen", "有效采集"))):
            if index:
                vrule(kpis).pack(side="left", fill="y")
            cell = tk.Frame(kpis, bg=PAPER_2)
            cell.pack(side="left", fill="x", expand=True)
            var = tk.StringVar(value="—")
            tk.Label(cell, textvariable=var, bg=PAPER_2, fg=INK,
                     font=FONT_NUM_BIG, anchor="w").pack(anchor="w")
            tk.Label(cell, text=label, bg=PAPER_2, fg=MUTED, font=FONT_LABEL,
                     anchor="w").pack(anchor="w")
            self.kpi_vars[key] = var

        heat_card = card(self)
        heat_card.pack(fill="x")
        heat_head = tk.Frame(heat_card, bg=PAPER_2, padx=14, pady=8)
        heat_head.pack(fill="x")
        tk.Label(heat_head, text="星期 × 小时互动热力图", bg=PAPER_2, fg=INK,
                 font=FONT_MEDIUM).pack(side="left")
        self.peak_lbl = tk.Label(heat_head, text="", bg=PAPER_2, fg=MUTED,
                                 font=FONT_SMALL)
        self.peak_lbl.pack(side="right")
        self.heat_cv = tk.Canvas(heat_card, height=118, bg=PAPER_2,
                                 highlightthickness=0)
        self.heat_cv.pack(fill="x", padx=10, pady=(4, 10))
        self.heat_cv.bind("<Configure>", lambda _e: self.draw_heat())

        charts = tk.Frame(self, bg=PAPER)
        charts.pack(fill="both", expand=True, pady=(12, 0))
        for index in (0, 1):
            charts.columnconfigure(index, weight=1, uniform="chart")
        for index in (0, 1):
            charts.rowconfigure(index, weight=1)
        specs = (("daily_eng", "每日互动增益"), ("daily_imp", "每日浏览增益"),
                 ("hourly", "每小时平均互动增益"), ("growth", "Top 3 帖子累计互动"))
        self.chart_cvs = {}
        for index, (key, title) in enumerate(specs):
            box = card(charts)
            box.grid(row=index // 2, column=index % 2, sticky="nsew",
                     padx=(0 if index % 2 == 0 else 6, 0),
                     pady=(0, 6))
            tk.Label(box, text=title, bg=PAPER_2, fg=INK_SOFT,
                     font=FONT_MEDIUM).pack(anchor="w", padx=12, pady=(8, 0))
            cv = tk.Canvas(box, height=84, bg=PAPER_2, highlightthickness=0)
            cv.pack(fill="both", expand=True, padx=8, pady=(2, 8))
            cv.bind("<Configure>", lambda _e, k=key: self.draw_chart(k))
            self.chart_cvs[key] = cv

        self.set_days(30, reload=False)

    def on_show(self):
        self.load()

    def invalidate(self):
        self.loaded_key = None

    def set_days(self, days: int, reload: bool = True):
        self.days = days
        for value, btn in self.range_btns.items():
            active = value == days
            btn.configure(bg=PAPER_2 if active else PAPER,
                          fg=INK if active else MUTED,
                          highlightbackground=VERMILION if active else PAPER)
        if reload:
            self.load(force=True)

    def load(self, force: bool = False):
        if not self.app.platform:
            return
        key = (self.app.platform, self.days)
        if not force and key == self.loaded_key:
            return
        try:
            data = analysis.build(self.app.store(), self.app.tz,
                                  days=self.days, top_n=3)
        except Exception:
            data = None
        self.data = data
        self.loaded_key = key
        self.update_kpis()
        self.draw_heat()
        for name in self.chart_cvs:
            self.draw_chart(name)

    def update_kpis(self):
        if not self.data:
            for var in self.kpi_vars.values():
                var.set("—")
            self.sub_lbl.configure(text=f"{load(self.app.platform).label} · 暂无可用数据")
            self.peak_lbl.configure(text="暂无数据")
            return
        ov = self.data["overview"]
        self.kpi_vars["engagement"].set(fmt_int(ov["total_engagement"]))
        self.kpi_vars["impressions"].set(fmt_int(ov["total_impressions"]))
        self.kpi_vars["avg"].set(fmt_int(ov["avg_engagement"]))
        self.kpi_vars["days_seen"].set(
            f"{ov['days_seen']} 天 / {ov['runs']} 轮")
        peak = self.data["peak"]
        self.peak_lbl.configure(
            text=f"峰值 {peak['weekday']} {peak['hour']:02d}:00 · 约 {peak['value']} 次互动增益"
            if ov["posts"] else "暂无数据")
        self.sub_lbl.configure(
            text=f"{load(self.app.platform).label} · "
                 f"{self.data['range_start']:%Y-%m-%d} — "
                 f"{self.data['range_end']:%Y-%m-%d} · {ov['slots']} 个快照时段")

    def draw_heat(self):
        cv = self.heat_cv
        cv.delete("all")
        width, height = cv.winfo_width(), cv.winfo_height()
        if width < 200 or height < 80:
            return
        if not self.data or not self.data["overview"]["posts"]:
            cv.create_text(width / 2, height / 2, text="暂无快照数据 · 先采集几轮",
                           fill=MUTED, font=FONT_SMALL)
            return
        matrix = self.data["heatmap"]
        cov = self.data["heatmap_coverage"]
        mx = max((max(row) for row in matrix), default=0) or 1
        left, top = 40, 16
        cw = (width - left - 4) / 24
        ch = (height - top - 4) / 7
        for hour in range(0, 24, 3):
            cv.create_text(left + cw * hour + 2, 6, text=f"{hour:02d}",
                           fill=MUTED, font=FONT_LABEL, anchor="w")
        for weekday, row in enumerate(matrix):
            cv.create_text(left - 6, top + ch * weekday + ch / 2,
                           text=self.data["weekday_labels"][weekday],
                           fill=MUTED, font=FONT_LABEL, anchor="e")
            for hour, value in enumerate(row):
                x0, y0 = left + cw * hour, top + ch * weekday
                if cov[weekday][hour] == 0:
                    cv.create_rectangle(x0 + 1, y0 + 1, x0 + cw - 1, y0 + ch - 1,
                                        outline=HAIRLINE_SOFT, fill=PAPER_2)
                    continue
                ratio = value / mx
                fill = mix(PAPER_2, VERMILION, 0.1 + 0.85 * ratio)
                cv.create_rectangle(x0 + 1, y0 + 1, x0 + cw - 1, y0 + ch - 1,
                                    outline="", fill=fill)
                if cw >= 20:
                    cv.create_text(x0 + cw / 2, y0 + ch / 2, text=str(round(value)),
                                   fill=PAPER_2 if ratio > 0.55 else INK,
                                   font=FONT_LABEL)

    def draw_chart(self, key: str):
        cv = self.chart_cvs[key]
        cv.delete("all")
        width, height = cv.winfo_width(), cv.winfo_height()
        if width < 120 or height < 60:
            return
        if not self.data:
            return
        if key == "daily_eng":
            self.line(cv, self.data["daily"]["labels"],
                      self.data["daily"]["engagement"], VERMILION, width, height)
        elif key == "daily_imp":
            self.line(cv, self.data["daily"]["labels"],
                      self.data["daily"]["impressions"], TEAL, width, height)
        elif key == "hourly":
            self.line(cv, self.data["hourly"]["labels"],
                      self.data["hourly"]["avg_engagement"], GOLD, width, height)
        else:
            self.growth(cv, width, height)

    def line(self, cv, labels, values, color, width, height):
        if not values:
            cv.create_text(width / 2, height / 2, text="暂无数据", fill=MUTED,
                           font=FONT_SMALL)
            return
        pad_l, pad_r, pad_t, pad_b = 44, 10, 10, 20
        plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
        mx = max(max(values), 1)
        for step in range(4):
            value = mx * step / 3
            y = pad_t + plot_h - plot_h * (value / mx)
            cv.create_line(pad_l, y, width - pad_r, y, fill=HAIRLINE_SOFT)
            cv.create_text(pad_l - 6, y, text=f"{value:.0f}", fill=MUTED,
                           font=FONT_LABEL, anchor="e")
        points = []
        for index, value in enumerate(values):
            x = pad_l + plot_w * (index / max(len(values) - 1, 1))
            y = pad_t + plot_h - plot_h * (value / mx)
            points.append((x, y))
        if len(points) > 1:
            area = [(points[0][0], pad_t + plot_h), *points,
                    (points[-1][0], pad_t + plot_h)]
            cv.create_polygon(*[coord for point in area for coord in point],
                              fill=mix(PAPER_2, color, 0.16), outline="")
        for a, b in zip(points, points[1:]):
            cv.create_line(*a, *b, fill=color, width=2)
        tick = max(1, (len(labels) - 1) // 5)
        for index in range(0, len(labels), tick):
            x = pad_l + plot_w * (index / max(len(values) - 1, 1))
            cv.create_text(x, height - 8, text=labels[index], fill=MUTED,
                           font=FONT_LABEL, anchor="n")
        cv.create_line(pad_l, pad_t + plot_h, width - pad_r, pad_t + plot_h,
                       fill=HAIRLINE)

    def growth(self, cv, width, height):
        items = self.data["growth"] if self.data else []
        if not items:
            cv.create_text(width / 2, height / 2,
                           text="快照不足 · 继续积累后显示单帖增长曲线",
                           fill=MUTED, font=FONT_SMALL)
            return
        colors = (VERMILION, TEAL, GOLD)
        ts = [point[0] for item in items for point in item["points"]]
        t0, t1 = min(ts), max(ts)
        span = max((t1 - t0).total_seconds(), 1)
        mx = max(max(point[1] for point in item["points"]) for item in items) or 1
        pad_l, pad_r, pad_t, pad_b = 44, 10, 10, 20
        plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
        for step in range(4):
            value = mx * step / 3
            y = pad_t + plot_h - plot_h * (value / mx)
            cv.create_line(pad_l, y, width - pad_r, y, fill=HAIRLINE_SOFT)
            cv.create_text(pad_l - 6, y, text=f"{value:.0f}", fill=MUTED,
                           font=FONT_LABEL, anchor="e")
        for index, item in enumerate(items):
            color = colors[index % len(colors)]
            points = [(pad_l + plot_w * ((t - t0).total_seconds() / span),
                       pad_t + plot_h - plot_h * (value / mx))
                      for t, value in item["points"]]
            for a, b in zip(points, points[1:]):
                cv.create_line(*a, *b, fill=color, width=2)
            if points:
                cv.create_oval(points[-1][0] - 3, points[-1][1] - 3,
                               points[-1][0] + 3, points[-1][1] + 3,
                               fill=color, outline="")
            cv.create_text(8, 8 + index * 12, text=item["label"][:16], fill=color,
                           font=FONT_LABEL, anchor="nw")
        cv.create_text(width - pad_r, height - 8,
                       text=f"{t0:%m-%d} — {t1:%m-%d}", fill=MUTED,
                       font=FONT_LABEL, anchor="se")

    def open_report(self):
        if not self.app.platform:
            return
        path = report_dir(self.app.cfg) / self.app.platform / "latest.html"
        if path.exists():
            webbrowser.open(path.resolve().as_uri())
        else:
            self.app.toast("还没有报告，请先在「评估报告」生成", "busy")
            self.app.show_page("reports")


class ReportsPage(tk.Frame):
    """06 评估报告：生成、历史列表与应用内预览。"""

    def __init__(self, parent, app: App):
        super().__init__(parent, bg=PAPER)
        self.app = app
        self.paths: dict[str, Path] = {}
        self.build()

    def build(self):
        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x")
        left = tk.Frame(head, bg=PAPER)
        left.pack(side="left", anchor="n")
        eyebrow(left, "Reports · 纸本观测").pack(anchor="w")
        tk.Label(left, text="评估报告", bg=PAPER, fg=INK, font=FONT_TITLE,
                 anchor="w").pack(anchor="w", pady=(3, 0))
        self.sub_lbl = tk.Label(left, text="", bg=PAPER, fg=MUTED, font=FONT_SMALL,
                                anchor="w")
        self.sub_lbl.pack(anchor="w", pady=(3, 0))

        generate = card(self)
        generate.pack(fill="x", pady=(12, 12))
        inner = tk.Frame(generate, bg=PAPER_2, padx=16, pady=12)
        inner.pack(fill="x")
        info = tk.Frame(inner, bg=PAPER_2)
        info.pack(side="left", fill="x", expand=True)
        self.gen_title = tk.Label(info, text="", bg=PAPER_2, fg=INK,
                                  font=FONT_MEDIUM, anchor="w")
        self.gen_title.pack(anchor="w")
        self.btn_generate = action_button(inner, "生成并预览", self.generate,
                                         "primary")
        self.btn_generate.pack(side="right")
        self.app.register_report_button(self.btn_generate, "生成并预览")

        hist_head = tk.Frame(self, bg=PAPER)
        hist_head.pack(fill="x", pady=(0, 6))
        tk.Label(hist_head, text="历史报告", bg=PAPER, fg=INK,
                 font=FONT_MEDIUM).pack(side="left")
        self.count_lbl = tk.Label(hist_head, text="", bg=PAPER, fg=MUTED,
                                  font=FONT_SMALL)
        self.count_lbl.pack(side="left", padx=(8, 0))
        action_button(hist_head, "刷新", self.load).pack(side="right")
        action_button(hist_head, "复制路径", self.copy_path).pack(side="right", padx=(0, 8))
        action_button(hist_head, "浏览器打开", self.open_path).pack(
            side="right", padx=(0, 8))
        action_button(hist_head, "预览", self.preview_selected).pack(
            side="right", padx=(0, 8))
        action_button(hist_head, "删除", self.delete_selected, "ghost",
                      fg=VERMILION).pack(side="right", padx=(0, 8))

        body = tk.Frame(self, bg=HAIRLINE, padx=1, pady=1)
        body.pack(fill="both", expand=True)
        inner_list = tk.Frame(body, bg=PAPER_2)
        inner_list.pack(fill="both", expand=True)
        inner_list.columnconfigure(0, weight=1)
        inner_list.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(inner_list, columns=("time", "name", "size"),
                                 show="headings", selectmode="browse")
        for key, label, width, anchor in (("time", "生成时间", 160, "w"),
                                          ("name", "文件", 520, "w"),
                                          ("size", "大小", 90, "e")):
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key == "name"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(inner_list, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _e: self.preview_selected())
        self.tree.bind("<Return>", lambda _e: self.preview_selected())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.tree.tag_configure("odd", background=PAPER_2)
        self.tree.tag_configure("even", background=PAPER_4)

    def on_show(self):
        self.load()

    def load(self):
        platform = self.app.platform
        self.tree.delete(*self.tree.get_children())
        self.paths.clear()
        if not platform:
            return
        cls = load(platform)
        out_dir = report_dir(self.app.cfg) / platform
        files = sorted(out_dir.glob("report_*.html"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for index, path in enumerate(files):
            stamp = datetime.fromtimestamp(path.stat().st_mtime)
            iid = str(path)
            self.paths[iid] = path
            size = path.stat().st_size
            size_text = f"{size / 1024:.0f} KB" if size < 1024 * 1024 \
                else f"{size / 1024 / 1024:.1f} MB"
            self.tree.insert("", "end", iid=iid,
                             values=(stamp.strftime("%Y-%m-%d %H:%M"),
                                     path.name, size_text),
                             tags=("even" if index % 2 else "odd",))
        self.count_lbl.configure(text=f"{len(files)} 份 · 保留最近 {self.app.cfg.get('report_days', 30)} 天口径")
        self.sub_lbl.configure(
            text=f"{cls.label} · 输出 {out_dir.relative_to(report_dir(self.app.cfg).parent)}/"
                 if out_dir.exists() else f"{cls.label} · 尚未生成报告")
        self.gen_title.configure(text=f"{cls.label} · 回看 {self.app.cfg.get('report_days', 30)} 天")

    def selected_path(self) -> Path | None:
        selection = self.tree.selection()
        return self.paths.get(selection[0]) if selection else None

    def generate(self):
        if not self.app.platform:
            return
        self.app.generate_report(self.app.platform, preview=True)

    def preview_selected(self):
        path = self.selected_path()
        if not path:
            self.app.toast("先在列表中选择一份报告", "busy")
            return
        self.preview(path)

    def open_path(self):
        path = self.selected_path()
        if not path:
            self.app.toast("先在列表中选择一份报告", "busy")
            return
        webbrowser.open(path.resolve().as_uri())

    def copy_path(self):
        path = self.selected_path()
        if not path:
            self.app.toast("先在列表中选择一份报告", "busy")
            return
        self.clipboard_clear()
        self.clipboard_append(str(path.resolve()))
        self.app.toast("报告路径已复制", "ok")

    def delete_selected(self):
        path = self.selected_path()
        if not path:
            self.app.toast("先在列表中选择一份报告", "busy")
            return
        out_dir = report_dir(self.app.cfg) / self.app.platform
        try:
            path.resolve().relative_to(out_dir.resolve())
        except ValueError:
            self.app.toast("只能删除当前平台报告目录内的文件", "error")
            return
        if not messagebox.askyesno("删除报告",
                                   f"删除 {path.name}？此操作不可撤销。",
                                   parent=self.winfo_toplevel()):
            return
        try:
            path.unlink()
        except OSError as e:
            self.app.toast(f"删除失败：{e}", "error", 6000)
            return
        self.app.toast("报告已删除", "ok")
        self.load()

    def preview(self, path):
        report_path = Path(path)
        if not report_path.is_file():
            self.load()
            self.app.toast("报告已不存在，列表已刷新", "error")
            return
        ReportPreview(self.app.root, report_path)


KPI_RE = re.compile(
    r'<div class="kpi"><div class="v">(.*?)</div><div class="l">(.*?)</div></div>',
    re.S)


def _plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


class ReportPreview(tk.Toplevel):
    """应用内简化预览：KPI + 结构说明，完整图形仍在浏览器。"""

    def __init__(self, master, path: Path):
        super().__init__(master)
        self.path = path
        self.title("报告预览 · x 观测台")
        self.configure(bg=PAPER)
        self.geometry("780x560")
        self.minsize(680, 480)
        apply_style(self)
        tk.Frame(self, bg=INK, height=4).pack(fill="x")
        page = tk.Frame(self, bg=PAPER, padx=28, pady=18)
        page.pack(fill="both", expand=True)

        eyebrow(page, "Report Preview · 简化预览").pack(anchor="w")
        tk.Label(page, text=path.name, bg=PAPER, fg=INK, font=FONT_TITLE,
                 anchor="w").pack(anchor="w", pady=(4, 0))
        try:
            stamp = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            messagebox.showwarning("报告不存在", f"{path.name} 已不存在或无法读取。",
                                   parent=self)
            self.destroy()
            return
        tk.Label(page, text=f"生成于 {stamp:%Y-%m-%d %H:%M} · 完整图表在浏览器查看",
                 bg=PAPER, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            anchor="w", pady=(2, 10))
        rule(page).pack(fill="x")

        kpis = self.read_kpis()
        grid = tk.Frame(page, bg=PAPER_2, highlightthickness=1,
                        highlightbackground=HAIRLINE, padx=14, pady=12)
        grid.pack(fill="x", pady=(14, 12))
        if kpis:
            for index, (value, label) in enumerate(kpis):
                cell = tk.Frame(grid, bg=PAPER_2)
                cell.grid(row=0, column=index, sticky="nsew")
                grid.columnconfigure(index, weight=1)
                tk.Label(cell, text=value, bg=PAPER_2, fg=INK,
                         font=FONT_NUM_BIG, anchor="w").pack(anchor="w")
                tk.Label(cell, text=label, bg=PAPER_2, fg=MUTED, font=FONT_LABEL,
                         anchor="w", wraplength=130).pack(anchor="w")
        else:
            tk.Label(grid, text="未能读取报告指标，请直接在浏览器打开",
                     bg=PAPER_2, fg=MUTED, font=FONT_SMALL).pack(anchor="w")

        structure = tk.Frame(page, bg=PAPER)
        structure.pack(fill="x", pady=(4, 0))
        tk.Label(structure, text="报告结构", bg=PAPER, fg=INK,
                 font=FONT_MEDIUM).pack(anchor="w", pady=(0, 4))
        for index, title in PLATES:
            row = tk.Frame(structure, bg=PAPER)
            row.pack(fill="x")
            tk.Label(row, text=index, bg=PAPER, fg=VERMILION,
                     font=FONT_LABEL).pack(side="left")
            tk.Label(row, text=title, bg=PAPER, fg=INK_SOFT,
                     font=FONT_SMALL).pack(side="left", padx=(8, 0))
            rule(structure).pack(fill="x")

        foot = tk.Frame(page, bg=PAPER)
        foot.pack(side="bottom", fill="x", pady=(12, 0))
        tk.Label(foot, text=str(path.resolve()), bg=PAPER, fg=MUTED,
                 font=FONT_SMALL, anchor="w").pack(side="left")
        action_button(foot, "浏览器打开", self.open_browser).pack(side="right")
        action_button(foot, "关闭", self.destroy, "secondary").pack(
            side="right", padx=(0, 8))
        center_window(self, 780, 560)

    def read_kpis(self):
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        return [(_plain(value), _plain(label))
                for value, label in KPI_RE.findall(text)]

    def open_browser(self):
        webbrowser.open(self.path.resolve().as_uri())


def main(page: str = "overview"):
    root = tk.Tk()
    App(root, page)
    root.mainloop()


if __name__ == "__main__":
    main()
