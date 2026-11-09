"""桌宠主程序：透明置顶的 GIF 角色，双击打开观测台，单击随机吐槽，右键管理采集。"""

from __future__ import annotations

import math
import queue
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path

from ..core import report
from ..core.config import PROJECT_ROOT, get_tz, load_config, save_config
from ..core.scheduler import MultiCollectScheduler
from ..platforms import available, enabled_ids, load
from .settings import SettingsDialog
from .theme import (FONT, FONT_SMALL, HAIRLINE, INK, PAPER_2, VERMILION,
                    apply_style)

W, H = 150, 208
CX = W // 2
SPRITE_W, SPRITE_H = 130, 115
SPRITE_X = (W - SPRITE_W) // 2
SPRITE_Y = 90
FRAME_MS = 60
FRAME_MS_BUSY = 35
BUBBLE_TOP = 8
BUBBLE_BOTTOM = 78
FRAME_DIR = PROJECT_ROOT / "assets" / "pet" / "frames"
CLICK_REPLIES = ("你点我作甚？", "你是小猪！", "猪猪快干活！", "你再这样我要哈气了！")


class PetWindow:
    def __init__(self, root: tk.Tk, autostart: bool = True):
        self.root = root
        self.cfg = load_config()
        self.tz = get_tz(self.cfg)
        self.scheduler = MultiCollectScheduler(self.cfg)
        self.ui_q: queue.Queue = queue.Queue()

        self.state = "idle"
        self.state_until = 0.0
        self.frame = 0
        self.bubble_text = ""
        self.bubble_until = 0.0
        self.drag = None
        self.moved = False
        self.topmost = True
        self.panel_proc = None
        self.anim_job = None
        self.click_job = None
        self.suppress_until = 0.0

        self.setup_window()
        apply_style(self.root)
        self.build_canvas()
        self.build_menu()

        pos = self.saved_position()
        self.root.geometry(f"{W}x{H}+{pos[0]}+{pos[1]}")

        if autostart:
            self.scheduler.start()
        self.anim_job = self.root.after(FRAME_MS, self.tick)
        self.root.after(200, self.poll)
        self.say("双击我 · 打开观测台", 8)

    # ---------- 窗口 ----------
    def setup_window(self):
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#ff00ff")
        if sys.platform == "win32":
            try:
                self.root.wm_attributes("-transparentcolor", "#ff00ff")
            except tk.TclError:
                pass
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_canvas(self):
        self.cv = tk.Canvas(self.root, width=W, height=H, bg="#ff00ff", bd=0,
                            highlightthickness=0, cursor="hand2")
        self.cv.pack()

        self.frames = self.load_frames()
        self.sprite = self.cv.create_image(SPRITE_X, SPRITE_Y, anchor="nw",
                                           image=self.frames[0])

        # 气泡：纸面 + 发丝线 + 书脊色条
        self.bubble_rect = self.cv.create_rectangle(
            8, BUBBLE_TOP, W - 8, BUBBLE_BOTTOM, fill=PAPER_2,
            outline=HAIRLINE, width=1, state="hidden")
        self.bubble_spine = self.cv.create_rectangle(
            9, BUBBLE_TOP + 1, 12, BUBBLE_BOTTOM - 1, fill=VERMILION,
            outline="", state="hidden")
        self.bubble_tip = self.cv.create_polygon(
            CX - 10, BUBBLE_BOTTOM - 2, CX + 10, BUBBLE_BOTTOM - 2,
            CX, BUBBLE_BOTTOM + 10, fill=PAPER_2, outline="", state="hidden")
        self.bubble_tip_l = self.cv.create_line(
            CX - 10, BUBBLE_BOTTOM, CX, BUBBLE_BOTTOM + 10,
            fill=HAIRLINE, width=1, state="hidden")
        self.bubble_tip_r = self.cv.create_line(
            CX + 10, BUBBLE_BOTTOM, CX, BUBBLE_BOTTOM + 10,
            fill=HAIRLINE, width=1, state="hidden")
        self.bubble_text_id = self.cv.create_text(
            CX + 2, (BUBBLE_TOP + BUBBLE_BOTTOM) / 2, width=W - 34, justify="center",
            fill=INK, font=FONT_SMALL, text="", state="hidden")
        self.bubble_bottom = BUBBLE_BOTTOM
        self.bubble_font = tkfont.Font(font=FONT_SMALL)
        self.bubble_key = None

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Double-Button-1>", self.on_double_click)
        self.cv.bind("<Button-3>", self.on_menu)

    def load_frames(self) -> list[tk.PhotoImage]:
        paths = sorted(FRAME_DIR.glob("pig_*.png"))
        if not paths:
            raise RuntimeError(f"缺少桌宠帧资源：{FRAME_DIR}")
        return [tk.PhotoImage(file=str(path)) for path in paths]

    def build_menu(self):
        self.auto_var = tk.BooleanVar(value=True)
        self.top_var = tk.BooleanVar(value=self.topmost)
        menu_opts = dict(tearoff=0, font=FONT, bg=PAPER_2, fg=INK,
                         activebackground=INK, activeforeground=PAPER_2,
                         activeborderwidth=0, bd=0, relief="flat",
                         selectcolor=PAPER_2, postcommand=self.rebuild_report_menu)
        self.menu = tk.Menu(self.root, **menu_opts)
        self.menu.add_command(label="打开观测台", command=self.open_panel)
        self.menu.add_command(label="运行监控",
                              command=lambda: self.open_panel("monitor"))
        self.menu.add_separator()
        self.menu.add_command(label="采集全部平台", command=self.collect_all)
        self.report_menu = tk.Menu(self.menu, **menu_opts)
        self.menu.add_cascade(label="生成报告", menu=self.report_menu)
        self.menu.add_separator()
        self.menu.add_command(label="设置", command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_checkbutton(label="自动采集", variable=self.auto_var,
                                  command=self.on_auto_toggle)
        self.menu.add_checkbutton(label="始终置顶", variable=self.top_var,
                                  command=self.on_topmost)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.on_close)

    def rebuild_report_menu(self):
        self.report_menu.delete(0, "end")
        targets = [p for p in available()
                   if ((self.cfg.get("platforms") or {}).get(p) or {}).get("enabled")]
        if not targets:
            self.report_menu.add_command(label="（未启用平台）", state="disabled")
            return
        for platform in targets:
            self.report_menu.add_command(
                label=f"{load(platform).label} 报告",
                command=lambda p=platform: self.make_report(p))

    def saved_position(self) -> tuple[int, int]:
        pet = self.cfg.get("pet") or {}
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        try:
            x, y = int(pet.get("x")), int(pet.get("y"))
            if 0 <= x <= sw - W and 0 <= y <= sh - H:
                return x, y
        except (TypeError, ValueError):
            pass
        return sw - W - 30, sh - H - 90

    def save_position(self):
        save_config(self.cfg, {"pet": {"x": self.root.winfo_x(),
                                       "y": self.root.winfo_y()}})

    # ---------- 交互 ----------
    def on_press(self, event):
        self.drag = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.moved = False

    def on_drag(self, event):
        if not self.drag:
            return
        x0, y0, wx, wy = self.drag
        dx, dy = event.x_root - x0, event.y_root - y0
        if abs(dx) + abs(dy) > 3:
            self.moved = True
        if self.moved:
            self.root.geometry(f"+{wx + dx}+{wy + dy}")

    def on_release(self, _event):
        if self.moved:
            self.save_position()
        elif time.time() >= self.suppress_until:
            self._cancel_click_job()
            self.click_job = self.root.after(300, self.on_single_click)
        self.drag = None

    def on_single_click(self):
        self.click_job = None
        self.say(random.choice(CLICK_REPLIES), 3)

    def on_double_click(self, _event):
        self.suppress_until = time.time() + 0.3
        self._cancel_click_job()
        self.open_panel()

    def _cancel_click_job(self):
        if self.click_job:
            try:
                self.root.after_cancel(self.click_job)
            except (tk.TclError, ValueError):
                pass
            self.click_job = None

    def on_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def on_auto_toggle(self):
        self.scheduler.set_auto(self.auto_var.get())
        self.say("已开启自动采集" if self.scheduler.auto else "已暂停自动采集", 4)

    def on_topmost(self):
        self.topmost = self.top_var.get()
        self.root.attributes("-topmost", self.topmost)

    # ---------- 菜单动作 ----------
    def collect_all(self):
        self.scheduler.trigger()
        self.say("开始采集", 3, "busy")

    def make_report(self, platform: str):
        self.say(f"正在生成 {load(platform).label} 报告…", 4, "busy")
        threading.Thread(target=self._report_worker, args=(platform,), daemon=True).start()

    def _report_worker(self, platform: str):
        try:
            paths = report.generate(self.cfg, platform, self.tz, top_n=3)["paths"]
            webbrowser.open(Path(paths["latest"]).resolve().as_uri())
            self.ui_q.put(("ok", f"{load(platform).label} 报告已生成"))
        except Exception as e:
            self.ui_q.put(("err", f"报告失败：{e}"))

    def open_panel(self, page: str | None = None):
        if self.panel_proc and self.panel_proc.poll() is None:
            self.say("观测台已在运行", 3)
            return
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--panel"]
        else:
            exe = Path(sys.executable)
            pythonw = exe.with_name("pythonw.exe")
            cmd = [str(pythonw if pythonw.is_file() else exe), "app.py"]
        if page:
            cmd.append(page)
        self.scheduler.set_auto(False)
        try:
            self.panel_proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
        except OSError as e:
            self.panel_proc = None
            self.scheduler.set_auto(True)
            self.say(f"打开失败：{e}", 8, "sad")
            return
        self.say("观测台已打开，桌宠暂停采集", 5)
        self.watch_panel()

    def watch_panel(self):
        if self.panel_proc and self.panel_proc.poll() is None:
            self.root.after(1000, self.watch_panel)
        else:
            self.panel_proc = None
            self.auto_var.set(True)
            self.scheduler.set_auto(True)
            self.say("观测台已关闭，恢复定时采集", 5)

    def open_settings(self):
        SettingsDialog(self.root, self.cfg, on_saved=self.on_settings_saved)

    def on_settings_saved(self, _updates: dict):
        self.tz = get_tz(self.cfg)
        self.scheduler.set_interval(self.cfg.get("collect_interval_minutes", 30))
        self.scheduler.trigger()
        self.say("设置已保存，开始采集", 5)

    def on_close(self):
        self.save_position()
        self._cancel_click_job()
        if self.anim_job:
            try:
                self.root.after_cancel(self.anim_job)
            except (tk.TclError, ValueError):
                pass
            self.anim_job = None
        self.scheduler.stop()
        self.root.destroy()

    # ---------- 气泡与状态 ----------
    def say(self, text: str, seconds: float = 5, state: str | None = None):
        self.bubble_text = text
        self.bubble_until = time.time() + seconds
        if state:
            self.state = state
            self.state_until = self.bubble_until

    def poll(self):
        for kind, payload in self.scheduler.poll():
            if kind == "platform_status":
                label = load(payload["platform"]).label
                self.say(f"{label} 采集中…", 120, "busy")
            elif kind == "platform_done":
                result = payload
                label = load(result["platform"]).label
                coverage = result["coverage"]
                coverage_text = "—" if coverage is None else f"{coverage}%"
                self.say(f"{label}：新增 {result['new']} · 快照 {result['snapshots']}"
                         f" · 覆盖 {coverage_text}", 6, "happy")
            elif kind == "platform_error":
                label = load(payload["platform"]).label
                self.say(f"{label} 失败：{payload['message']}", 8, "sad")
            elif kind == "platform_skip":
                self.say(f"{load(payload['platform']).label}：{payload['message']}", 5, "sad")
            elif kind == "need_config":
                self.say("右键 → 设置，填写账号与会话锚点", 10, "sad")
            elif kind == "round_done":
                if payload["ok"] == 0 and payload["failed"] == 0 and payload["skipped"] == 0:
                    self.say("本轮没有可采集的平台", 5)
        try:
            while True:
                kind, payload = self.ui_q.get_nowait()
                self.say(str(payload), 8 if kind == "err" else 6,
                         "sad" if kind == "err" else "happy")
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    # ---------- 动画 ----------
    def tick(self):
        now = time.time()
        if self.state != "idle" and now >= self.state_until:
            self.state = "idle"
        if self.state == "busy":
            self.bubble_text = "采集中" + "." * (self.frame // 8 % 4)
            self.bubble_until = now + 3
        self.frame = (self.frame + 1) % len(self.frames)
        self.cv.itemconfigure(self.sprite, image=self.frames[self.frame])
        self.show_bubble(now)
        delay = FRAME_MS_BUSY if self.state == "busy" else FRAME_MS
        self.anim_job = self.root.after(delay, self.tick)

    def show_bubble(self, now: float):
        visible = now < self.bubble_until and bool(self.bubble_text)
        if visible and self.bubble_key != self.bubble_text:
            self.bubble_key = self.bubble_text
            text = self.fit_bubble(self.bubble_text)
            lines = max(1, min(3, math.ceil(self.bubble_font.measure(text) / 108)))
            bottom = 48 + (lines - 1) * 15
            self.cv.coords(self.bubble_rect, 8, BUBBLE_TOP, W - 8, bottom)
            self.cv.coords(self.bubble_spine, 9, BUBBLE_TOP + 1, 12, bottom - 1)
            self.cv.coords(self.bubble_tip, CX - 10, bottom - 2, CX + 10, bottom - 2,
                           CX, bottom + 10)
            self.cv.coords(self.bubble_tip_l, CX - 10, bottom, CX, bottom + 10)
            self.cv.coords(self.bubble_tip_r, CX + 10, bottom, CX, bottom + 10)
            self.cv.coords(self.bubble_text_id, CX + 2, (BUBBLE_TOP + bottom) / 2)
            self.cv.itemconfigure(self.bubble_text_id, text=text)
        state = "normal" if visible else "hidden"
        for item in (self.bubble_rect, self.bubble_spine, self.bubble_tip,
                     self.bubble_tip_l, self.bubble_tip_r):
            self.cv.itemconfigure(item, state=state)
        self.cv.itemconfigure(self.bubble_text_id, state=state)

    def fit_bubble(self, text: str) -> str:
        limit = 108 * 3
        if self.bubble_font.measure(text) <= limit:
            return text
        text = text.rstrip()
        while text and self.bubble_font.measure(text + "…") > limit:
            text = text[:-1]
        return text.rstrip() + "…"


def selftest() -> int:
    """无交互自检：平台注册表、数据仓库、配置与桌宠窗口创建。"""
    platforms = available()
    print(f"平台适配器：{len(platforms)} 个 -> {', '.join(platforms)}")

    cfg = load_config()
    enabled = enabled_ids(cfg)
    print(f"已启用平台：{', '.join(enabled) if enabled else '无'}")

    root = tk.Tk()
    pet = PetWindow(root, autostart=False)
    pet.say("自检中", 2)
    root.withdraw()
    root.update_idletasks()
    root.update()
    root.after(800, root.destroy)
    root.mainloop()
    print("桌宠窗口：GIF 帧、动画与气泡渲染正常")
    return 0 if platforms else 1


def main():
    root = tk.Tk()
    PetWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
