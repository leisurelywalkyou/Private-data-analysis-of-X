"""独立小界面：启动即自动采集，30 分钟一轮，可勾选要采集的帖子。

运行：pythonw app.py（或用 启动.bat 双击）
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk, messagebox
import tkinter as tk

import analysis
import collector
import csvstore
import report
from config import get_tz, load_config
from x_api import XApiError, XClient

BG, PANEL, FG, MUTED, ACC = "#ffffff", "#f4f8fe", "#0b2545", "#66788c", "#2563eb"
UP, DOWN, LINE = "#d92b2b", "#138a36", "#d9e6f5"
FONT = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 9, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 11, "bold")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.tz = get_tz(self.cfg)
        self.ds = csvstore.DataStore(self.cfg.get("data_dir", "data"))

        self.q: queue.Queue = queue.Queue()
        self.stop_evt = threading.Event()
        self.wake = threading.Event()
        self.force = True  # 启动立即采集一次
        self.interval = int(self.cfg.get("collect_interval_minutes", 30))
        self.last_run = None
        self.last_error = None
        self.urls: dict[str, str] = {}
        self.enabled_cache: dict[str, bool] = {}

        self.auto_var = tk.BooleanVar(value=True)
        self.auto_enabled = True  # 供工作线程读取的普通变量，避免跨线程访问 tk 变量
        self.build_ui()
        self.refresh_list()
        self.refresh_stats()

        threading.Thread(target=self.worker_loop, daemon=True).start()
        self.root.after(150, self.poll)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- UI ----------
    def build_ui(self):
        self.root.title("X 数据监控")
        self.root.geometry("680x470")
        self.root.minsize(560, 400)
        self.root.configure(bg=BG)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=FG, fieldbackground="#ffffff",
                        font=FONT, borderwidth=0, focuscolor=BG)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=FONT)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", font=FONT_TITLE, foreground=ACC)
        style.configure("TButton", background="#e8f1ff", foreground="#1d4ed8",
                        bordercolor="#bcd7f8", lightcolor="#ffffff", darkcolor="#e8f1ff",
                        padding=(9, 3), relief="flat", borderwidth=0)
        style.map("TButton", background=[("active", "#d6e8ff")],
                  foreground=[("active", "#0b3d91")])
        style.configure("TCheckbutton", background=BG, foreground=FG, font=FONT)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TSpinbox", fieldbackground="#ffffff", background="#e8f1ff",
                        foreground=FG, arrowcolor=ACC, arrowsize=10, padding=2)
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff",
                        foreground="#10233d", rowheight=22, borderwidth=0, font=FONT)
        style.configure("Treeview.Heading", background="#e8f1ff", foreground="#1d4ed8",
                        relief="flat", font=("Microsoft YaHei UI", 8))
        style.map("Treeview", background=[("selected", "#cfe3ff")],
                  foreground=[("selected", "#0b2545")])
        style.configure("Vertical.TScrollbar", background="#e8f1ff", troughcolor=BG,
                        arrowcolor=ACC, borderwidth=0)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(4, weight=1)

        head = ttk.Frame(self.root, padding=(12, 10, 12, 2))
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="X 数据监控", style="Title.TLabel").pack(side="left")
        self.account_lbl = ttk.Label(head, text="", style="Muted.TLabel")
        self.account_lbl.pack(side="right")
        ttk.Button(head, text="打开主页采集",
                   command=self.open_profile_and_collect).pack(side="right", padx=(0, 8))

        stats = ttk.Frame(self.root, padding=(12, 2))
        stats.grid(row=1, column=0, sticky="ew")
        self.stat_vars = {}
        for key, text in (("posts", "帖子"), ("enabled", "已勾选"), ("snaps", "快照"),
                          ("last", "上次采集"), ("next", "下次")):
            box = ttk.Frame(stats)
            box.pack(side="left", padx=(0, 12))
            v = tk.StringVar(value="—")
            ttk.Label(box, textvariable=v, font=FONT_BOLD).pack(anchor="w")
            ttk.Label(box, text=text, style="Muted.TLabel", font=("Microsoft YaHei UI", 8)).pack(anchor="w")
            self.stat_vars[key] = v

        # 变化量：正数标红，负数（较上月同期下降）标绿
        delta_box = ttk.Frame(stats)
        delta_box.pack(side="left", padx=(0, 12))
        self.delta_lbl = ttk.Label(delta_box, text="—", font=FONT_BOLD, foreground=MUTED)
        self.delta_lbl.pack(anchor="w")
        ttk.Label(delta_box, text="本轮互动", style="Muted.TLabel",
                  font=("Microsoft YaHei UI", 8)).pack(anchor="w")

        mom_box = ttk.Frame(stats)
        mom_box.pack(side="left", padx=(0, 12))
        self.mom_lbl = ttk.Label(mom_box, text="—", font=FONT_BOLD, foreground=MUTED)
        self.mom_lbl.pack(anchor="w")
        ttk.Label(mom_box, text="较上月同期", style="Muted.TLabel",
                  font=("Microsoft YaHei UI", 8)).pack(anchor="w")

        bar = ttk.Frame(self.root, padding=(12, 6))
        bar.grid(row=2, column=0, sticky="ew")
        ttk.Button(bar, text="立即采集", command=self.run_now).pack(side="left")
        ttk.Button(bar, text="生成报告", command=self.make_report).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="设置", command=self.open_settings).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="刷新列表", command=self.refresh_list).pack(side="left", padx=(6, 0))

        ttk.Checkbutton(bar, text="自动采集", variable=self.auto_var,
                        command=self.on_auto_toggle).pack(side="right")
        self.interval_var = tk.StringVar(value=str(self.interval))
        spin = ttk.Spinbox(bar, from_=5, to=240, increment=5, width=4,
                           textvariable=self.interval_var, command=self.on_interval)
        spin.pack(side="right", padx=(0, 4))
        spin.bind("<FocusOut>", lambda e: self.on_interval())
        spin.bind("<Return>", lambda e: self.on_interval())
        ttk.Label(bar, text="间隔(分)", style="Muted.TLabel").pack(side="right", padx=(0, 4))

        list_head = ttk.Frame(self.root, padding=(12, 8, 12, 2))
        list_head.grid(row=3, column=0, sticky="ew")
        ttk.Label(list_head, text="我的帖子 · 点击行切换是否采集（双击打开原帖）",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(list_head, text="全不选", width=6,
                   command=lambda: self.set_all(False)).pack(side="right")
        ttk.Button(list_head, text="全选", width=6,
                   command=lambda: self.set_all(True)).pack(side="right", padx=(0, 4))

        body = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        body.grid(row=4, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        cols = ("on", "time", "like", "rt", "rep", "imp", "text")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="browse")
        heads = (("on", "采集", 40, "center"), ("time", "发布时间", 92, "center"),
                 ("like", "赞", 42, "center"), ("rt", "转", 38, "center"),
                 ("rep", "评", 38, "center"), ("imp", "曝光", 62, "center"),
                 ("text", "内容", 320, "w"))
        for key, label, width, anchor in heads:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "text"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("off", foreground="#98a8bd")
        self.tree.bind("<Button-1>", self.on_row_click)
        self.tree.bind("<Double-1>", self.on_row_open)

        foot = ttk.Frame(self.root, padding=(12, 4, 12, 8))
        foot.grid(row=5, column=0, sticky="ew")
        self.status_lbl = ttk.Label(foot, text="启动中…", style="Muted.TLabel")
        self.status_lbl.pack(side="left")
        ttk.Label(foot, text="数据保存在本地 data/ 目录", style="Muted.TLabel").pack(side="right")

    # ---------- 数据展示 ----------
    def refresh_stats(self):
        s = self.ds.stats()
        self.stat_vars["posts"].set(str(s["posts"]))
        self.stat_vars["enabled"].set(str(s["enabled"]))
        self.stat_vars["snaps"].set(str(s["snapshots"]))
        last = s["last_run"]
        if last:
            dt = datetime.fromisoformat(last["started_at"]).astimezone(self.tz)
            self.stat_vars["last"].set(dt.strftime("%H:%M"))
        user = self.ds.get_meta("username") or self.cfg.get("username") or "未配置"
        self.account_lbl.configure(text=f"@{user}" if user != "未配置" else "未配置账号 · 请点设置")
        self.update_deltas()

    def update_deltas(self):
        """本轮互动增量：正数红、负数绿；较上月同期：下降标绿。"""
        try:
            d = analysis.deltas(self.ds, self.tz)
        except Exception:
            self.delta_lbl.configure(text="—", foreground=MUTED)
            self.mom_lbl.configure(text="—", foreground=MUTED)
            return

        beat = d["beat"]
        if beat["available"]:
            v = beat["engagement"]
            self.delta_lbl.configure(text=f"{v:+,}", foreground=self.change_color(v))
        else:
            self.delta_lbl.configure(text="—", foreground=MUTED)

        mom = d["mom"]
        if mom["available"]:
            delta, pct = mom["delta"], mom["pct"]
            text = f"{pct:+.1f}%" if pct is not None else f"{delta:+,}"
            self.mom_lbl.configure(text=text, foreground=self.change_color(delta))
        else:
            self.mom_lbl.configure(text="数据不足", foreground=MUTED)

    @staticmethod
    def change_color(value: float) -> str:
        if value > 0:
            return UP
        if value < 0:
            return DOWN
        return MUTED

    def refresh_list(self):
        self.refresh_stats()
        self.tree.delete(*self.tree.get_children())
        self.enabled_cache = {}
        rows = self.ds.posts_recent(200)
        for r in rows:
            tid = r["tweet_id"]
            on = bool(r["enabled"])
            self.enabled_cache[tid] = on
            created = datetime.fromisoformat(r["created_at"]).astimezone(self.tz)
            text = (r["text"] or "").replace("\n", " ")
            self.urls[tid] = f"https://x.com/i/status/{tid}"
            self.tree.insert("", "end", iid=tid, tags=() if on else ("off",), values=(
                "☑" if on else "☐", created.strftime("%m-%d %H:%M"),
                r["likes"], r["retweets"], r["replies"], r["impressions"], text,
            ))
        self.stat_vars["enabled"].set(
            str(sum(1 for v in self.enabled_cache.values() if v)))

    def set_row(self, tid: str, on: bool):
        vals = list(self.tree.item(tid, "values"))
        vals[0] = "☑" if on else "☐"
        self.tree.item(tid, values=vals, tags=() if on else ("off",))
        self.enabled_cache[tid] = on
        self.stat_vars["enabled"].set(
            str(sum(1 for v in self.enabled_cache.values() if v)))

    def on_row_click(self, event):
        tid = self.tree.identify_row(event.y)
        if not tid:
            return
        on = not self.enabled_cache.get(tid, True)
        self.ds.set_tracked(tid, on)
        self.set_row(tid, on)
        self.status_lbl.configure(text=f"{'已启用' if on else '已停止'}采集：{tid[-6:]}")

    def on_row_open(self, event):
        tid = self.tree.identify_row(event.y)
        if tid and tid in self.urls:
            webbrowser.open(self.urls[tid])

    def set_all(self, on: bool):
        for tid in list(self.tree.get_children()):
            self.ds.set_tracked(tid, on)
            self.set_row(tid, on)
        self.status_lbl.configure(text="已全选" if on else "已全部取消勾选")

    # ---------- 采集调度 ----------
    def worker_loop(self):
        while not self.stop_evt.is_set():
            if self.auto_enabled or self.force:
                self.force = False
                self.q.put(("status", "采集中…"))
                try:
                    if not self.cfg.get("username") or not (
                            self.cfg.get("bearer_token") or self.cfg.get("user_access_token")):
                        self.q.put(("need_config", None))
                    else:
                        client = XClient(self.cfg["bearer_token"], self.cfg["user_access_token"],
                                         log=lambda m: self.q.put(("log", m)))
                        conn = csvstore.DataStore(self.cfg.get("data_dir", "data"))
                        res = collector.collect(self.cfg, client, conn)
                        self.q.put(("done", res))
                except XApiError as e:
                    self.q.put(("error", str(e)))
                except Exception as e:  # 网络等异常：不退出，等下一轮
                    self.q.put(("error", f"{type(e).__name__}: {e}"))
                self.last_run = datetime.now()

            while not self.stop_evt.is_set():
                self.wake.wait(0.4)
                self.wake.clear()
                if self.force:
                    break
                if self.stop_evt.is_set():
                    return
                if self.auto_enabled and self.last_run:
                    if (datetime.now() - self.last_run).total_seconds() >= self.interval * 60:
                        break

    def poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "done":
                    self.refresh_list()
                    self.status_lbl.configure(
                        text=f"采集完成 · 刷新 {payload['refreshed']} 条 / 快照 {payload['snapshots']} 条")
                    self.last_error = None
                elif kind == "error":
                    self.status_lbl.configure(text=f"采集失败：{payload}")
                    if payload != self.last_error:
                        messagebox.showwarning("采集失败", payload, parent=self.root)
                        self.last_error = payload
                elif kind == "need_config":
                    self.status_lbl.configure(text="请点“设置”填写账号与 Bearer Token")
                elif kind == "status":
                    self.status_lbl.configure(text=str(payload or ""))
                elif kind == "log":
                    self.status_lbl.configure(text=str(payload or ""))
        except queue.Empty:
            pass
        self.update_next()
        self.root.after(150, self.poll)

    def update_next(self):
        if not self.auto_enabled:
            self.stat_vars["next"].set("—")
            return
        if self.last_run:
            nxt = self.last_run + timedelta(minutes=self.interval)
            self.stat_vars["next"].set(nxt.strftime("%H:%M"))

    def run_now(self):
        self.force = True
        self.wake.set()
        self.status_lbl.configure(text="正在触发采集…")

    def open_profile_and_collect(self):
        """用 Chrome 打开自己的 X 主页，同时触发一次 API 采集。"""
        user = self.ds.get_meta("username") or self.cfg.get("username") or ""
        if not user:
            messagebox.showinfo("提示", "尚未配置账号，请先点“设置”填写账号。", parent=self.root)
            return
        url = f"https://x.com/{user}"
        self.status_lbl.configure(text=f"正在 Chrome 打开 @{user} 主页并触发采集…")
        self.open_in_chrome(url)
        self.run_now()

    @staticmethod
    def chrome_exe() -> str | None:
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
        return shutil.which("chrome") or shutil.which("chrome.exe")

    def open_in_chrome(self, url: str):
        exe = self.chrome_exe()
        try:
            if exe:
                subprocess.Popen([exe, url], close_fds=True)
            else:
                webbrowser.open(url)
        except OSError:
            webbrowser.open(url)

    def on_auto_toggle(self):
        self.auto_enabled = self.auto_var.get()
        if self.auto_enabled:
            self.force = True
            self.wake.set()
            self.status_lbl.configure(text="已开启自动采集")
        else:
            self.status_lbl.configure(text="自动采集已暂停（仍可点“立即采集”）")

    def on_interval(self):
        try:
            self.interval = max(5, min(240, int(float(self.interval_var.get()))))
            self.interval_var.set(str(self.interval))
            self.cfg["collect_interval_minutes"] = self.interval
            self.save_cfg()
        except (TypeError, ValueError):
            self.interval_var.set(str(self.interval))

    # ---------- 报告 / 设置 ----------
    def make_report(self):
        try:
            days = int(self.cfg.get("report_days", 30))
            data = analysis.build(self.ds, self.tz, days=days, top_n=3)
            username = self.ds.get_meta("username") or self.cfg.get("username") or "me"
            paths = report.write_report(data, username, self.cfg["report_dir"])
            webbrowser.open(Path(paths["latest"]).resolve().as_uri())
            self.status_lbl.configure(text=f"报告已生成并打开：{paths['latest']}")
        except Exception as e:
            messagebox.showerror("报告生成失败", str(e), parent=self.root)

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        fields = {}
        rows = (("username", "账号（不含@）"), ("bearer_token", " Bearer Token"),
                ("user_access_token", "User Access Token（可选）"))
        for i, (key, label) in enumerate(rows):
            ttk.Label(win, text=label).grid(row=i, column=0, sticky="w", padx=12,
                                            pady=(12 if i == 0 else 4, 0))
            var = tk.StringVar(value=str(self.cfg.get(key, "") or ""))
            ttk.Entry(win, textvariable=var, width=42).grid(row=i, column=1, sticky="ew",
                                                            padx=(6, 12), pady=(12 if i == 0 else 4, 0))
            fields[key] = var
        ttk.Label(win, text="Token 在 X 开发者后台生成；只保存在本机 config.json",
                  style="Muted.TLabel", font=("Microsoft YaHei UI", 8)).grid(
            row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(6, 0))

        def save():
            self.cfg.update({k: v.get().strip() for k, v in fields.items()})
            self.save_cfg()
            win.destroy()
            self.force = True
            self.wake.set()
            self.status_lbl.configure(text="设置已保存，开始采集…")

        btns = ttk.Frame(win)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", padx=12, pady=12)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="保存", command=save).pack(side="right", padx=(0, 6))

    def save_cfg(self):
        path = Path("config.json")
        raw = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        for k in ("username", "bearer_token", "user_access_token", "collect_interval_minutes"):
            if k in self.cfg:
                raw[k] = self.cfg[k]
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def on_close(self):
        self.stop_evt.set()
        self.wake.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
