"""界面设计系统：纸面与墨色。

统一配色、字体、ttk 样式，以及面板 / 设置共用的小控件。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, TclError

# ---------- 色彩 ----------
PAPER = "#f3eee2"        # 页面底色
PAPER_2 = "#fbf7ec"      # 抬升表面
PAPER_3 = "#eae2d1"      # 悬停 / 斑马纹
PAPER_4 = "#f7f2e6"      # 表格偶数行
INK = "#1e1b16"          # 主文字
INK_SOFT = "#4a4337"
MUTED = "#8a8071"
HAIRLINE = "#dcd2bd"
HAIRLINE_SOFT = "#e7dfcc"
VERMILION = "#b3402a"    # 主强调
VERMILION_DARK = "#8d3120"
TEAL = "#2f6159"
GOLD = "#a98a4b"
UP = "#a5372a"
DOWN = "#2f6159"
WHITE = "#ffffff"

# 桌宠窗口的透明色键
KEY = "#ff00ff"

# ---------- 字体 ----------
FAMILY = "Microsoft YaHei UI"
MONO = "Consolas"

FONT = (FAMILY, 9)
FONT_BOLD = (FAMILY, 9, "bold")
FONT_MEDIUM = (FAMILY, 10, "bold")
FONT_TITLE = (FAMILY, 16, "bold")
FONT_DISPLAY = (FAMILY, 19, "bold")
FONT_SMALL = (FAMILY, 8)
FONT_BODY = (FAMILY, 9)
FONT_MONO_SMALL = (FAMILY, 9)
FONT_NUM = (FAMILY, 15, "bold")
FONT_NUM_BIG = (FAMILY, 18, "bold")
FONT_NUM_MID = (FAMILY, 13, "bold")
FONT_EYEBROW = (MONO, 8)
FONT_LABEL = (FAMILY, 8)


def apply_style(root) -> None:
    """把 clam 主题改造成纸面风格。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except TclError:
        pass

    root.option_add("*TCombobox*Listbox.background", PAPER_2)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", INK)
    root.option_add("*TCombobox*Listbox.selectForeground", PAPER_2)
    root.option_add("*TCombobox*Listbox.font", FONT)

    style.configure(".", background=PAPER, foreground=INK, fieldbackground=PAPER_2,
                    font=FONT, borderwidth=0, focuscolor=PAPER)
    style.configure("TFrame", background=PAPER)
    style.configure("TLabel", background=PAPER, foreground=INK, font=FONT)
    style.configure("Muted.TLabel", foreground=MUTED, background=PAPER, font=FONT_SMALL)
    style.configure("Eyebrow.TLabel", foreground=MUTED, background=PAPER, font=FONT_EYEBROW)
    style.configure("Title.TLabel", foreground=INK, background=PAPER, font=FONT_TITLE)

    style.configure("TButton", background=PAPER_2, foreground=INK, font=FONT_BOLD,
                    bordercolor=HAIRLINE, lightcolor=PAPER_2, darkcolor=PAPER_2,
                    padding=(12, 6), relief="flat", borderwidth=1)
    style.map("TButton",
              background=[("active", PAPER_3), ("disabled", PAPER_2)],
              foreground=[("active", VERMILION), ("disabled", MUTED)],
              bordercolor=[("active", VERMILION)])
    style.configure("Accent.TButton", background=INK, foreground=PAPER_2,
                    bordercolor=INK, lightcolor=INK, darkcolor=INK, padding=(14, 6))
    style.map("Accent.TButton",
              background=[("active", VERMILION), ("disabled", HAIRLINE)],
              foreground=[("disabled", MUTED)],
              bordercolor=[("active", VERMILION)])
    style.configure("Ghost.TButton", background=PAPER, foreground=MUTED,
                    bordercolor=PAPER, lightcolor=PAPER, darkcolor=PAPER, padding=(8, 5))
    style.map("Ghost.TButton",
              background=[("active", PAPER)],
              foreground=[("active", VERMILION)],
              bordercolor=[("active", PAPER)])

    style.configure("TCheckbutton", background=PAPER, foreground=INK, font=FONT,
                    indicatorcolor=PAPER_2, indicatorbackground=PAPER_2,
                    focuscolor=PAPER)
    style.map("TCheckbutton",
              background=[("active", PAPER)],
              foreground=[("active", VERMILION)],
              indicatorcolor=[("selected", VERMILION)])

    style.configure("TEntry", fieldbackground=PAPER_2, foreground=INK, insertcolor=INK,
                    bordercolor=HAIRLINE, lightcolor=PAPER_2, darkcolor=PAPER_2,
                    padding=(6, 4), relief="flat")
    style.map("TEntry", bordercolor=[("focus", VERMILION)])
    style.configure("TSpinbox", fieldbackground=PAPER_2, background=PAPER_2,
                    foreground=INK, arrowcolor=INK_SOFT, arrowsize=11, padding=(6, 3),
                    bordercolor=HAIRLINE, lightcolor=PAPER_2, darkcolor=PAPER_2)

    style.configure("Treeview", background=PAPER_2, fieldbackground=PAPER_2,
                    foreground=INK, rowheight=32, borderwidth=0, font=FONT)
    style.configure("Treeview.Heading", background=PAPER, foreground=MUTED,
                    relief="flat", borderwidth=0, font=FONT_EYEBROW, padding=(4, 6))
    style.map("Treeview.Heading", background=[("active", PAPER_3)])
    style.map("Treeview", background=[("selected", PAPER_3)],
              foreground=[("selected", INK)])

    style.configure("Vertical.TScrollbar", background=PAPER_3, troughcolor=PAPER,
                    bordercolor=PAPER, arrowcolor=INK_SOFT, lightcolor=PAPER_3,
                    darkcolor=PAPER_3, gripcount=0, arrowsize=11)
    style.map("Vertical.TScrollbar", background=[("active", HAIRLINE)])

    style.configure("TNotebook", background=PAPER, borderwidth=0, tabmargins=0)
    style.configure("TNotebook.Tab", background=PAPER, foreground=MUTED, padding=(14, 7),
                    font=FONT_BOLD)
    style.map("TNotebook.Tab", background=[("selected", PAPER_2)],
              foreground=[("selected", VERMILION)])


# ---------- 小控件 ----------
def rule(parent, color: str = HAIRLINE, height: int = 1) -> tk.Frame:
    """一条发丝线。"""
    line = tk.Frame(parent, bg=color, height=height, bd=0, highlightthickness=0)
    line.pack_propagate(False)
    return line


def vrule(parent, color: str = HAIRLINE) -> tk.Frame:
    line = tk.Frame(parent, bg=color, width=1, bd=0, highlightthickness=0)
    return line


def eyebrow(parent, text: str) -> tk.Label:
    return tk.Label(parent, text=text.upper(), bg=PAPER, fg=MUTED,
                    font=FONT_EYEBROW, anchor="w")


def action_button(parent, text: str, command=None, kind: str = "ghost", **kw) -> tk.Button:
    """扁平文字按钮：primary 墨底、secondary 纸底描边、ghost 纯文字。"""
    presets = {
        "primary": dict(bg=INK, fg=PAPER_2, activebackground=VERMILION,
                        activeforeground=WHITE, highlightbackground=INK,
                        padx=16, pady=6, font=FONT_BOLD, highlightthickness=0),
        "secondary": dict(bg=PAPER_2, fg=INK, activebackground=PAPER_3,
                          activeforeground=VERMILION, highlightbackground=HAIRLINE,
                          padx=14, pady=5, font=FONT_BOLD, highlightthickness=1),
        "ghost": dict(bg=PAPER, fg=MUTED, activebackground=PAPER,
                      activeforeground=VERMILION, highlightbackground=PAPER,
                      padx=6, pady=4, font=FONT_SMALL, highlightthickness=0),
    }
    opts = dict(presets[kind])
    opts.update(kw)
    return tk.Button(parent, text=text, command=command, bd=0, relief="flat",
                     cursor="hand2", disabledforeground=HAIRLINE, **opts)


class Field(tk.Frame):
    """标签 + 下划线输入框。"""

    def __init__(self, parent, label: str, var: tk.StringVar, show: str | None = None,
                 width: int = 0, hint: str = ""):
        super().__init__(parent, bg=PAPER)
        self.label = tk.Label(self, text=label, bg=PAPER, fg=MUTED, font=FONT_SMALL,
                              anchor="w")
        self.label.pack(fill="x")
        self.entry = tk.Entry(self, textvariable=var, show=show or "", bd=0,
                              relief="flat", bg=PAPER, fg=INK, insertbackground=INK,
                              font=FONT, highlightthickness=0, width=width)
        self.entry.pack(fill="x", pady=(4, 0))
        self.line = tk.Frame(self, bg=HAIRLINE, height=1)
        self.line.pack(fill="x", pady=(3, 0))
        self.line.pack_propagate(False)
        self.entry.bind("<FocusIn>", lambda _e: self.line.configure(bg=VERMILION))
        self.entry.bind("<FocusOut>", lambda _e: self.line.configure(bg=HAIRLINE))
        if hint:
            tk.Label(self, text=hint, bg=PAPER, fg=MUTED, font=FONT_SMALL,
                     anchor="w").pack(fill="x", pady=(4, 0))


class CheckRow(tk.Frame):
    """自绘方框勾选行。"""

    def __init__(self, parent, text: str, var: tk.BooleanVar, command=None):
        super().__init__(parent, bg=PAPER, cursor="hand2")
        self.var = var
        self.command = command
        self.box = tk.Canvas(self, width=15, height=15, bg=PAPER,
                             highlightthickness=0, cursor="hand2")
        self.box.pack(side="left")
        self.lbl = tk.Label(self, text=text, bg=PAPER, fg=INK_SOFT, font=FONT,
                            cursor="hand2")
        self.lbl.pack(side="left", padx=(8, 0))
        for widget in (self, self.box, self.lbl):
            widget.bind("<Button-1>", self.toggle)
        self.var.trace_add("write", lambda *_: self.draw())
        self.draw()

    def draw(self):
        self.box.delete("all")
        on = bool(self.var.get())
        self.box.create_rectangle(0, 0, 14, 14,
                                  outline=VERMILION if on else HAIRLINE, width=1)
        if on:
            self.box.create_line(3, 7, 6, 11, 12, 3, fill=VERMILION, width=2)
        self.lbl.configure(fg=INK if on else INK_SOFT)

    def toggle(self, _event=None):
        self.var.set(not self.var.get())
        if self.command:
            self.command()


class Toggle(tk.Canvas):
    """自绘开关：轨道与滑块使用固定内边距，避免开启态贴边裁切。"""

    W, H = 46, 22

    def __init__(self, parent, var: tk.BooleanVar, command=None, bg: str = PAPER):
        super().__init__(parent, width=self.W, height=self.H, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.var = var
        self.command = command
        self.bind("<Button-1>", self.click)
        self.var.trace_add("write", lambda *_: self.draw())
        self.draw()

    def draw(self):
        self.delete("all")
        on = bool(self.var.get())
        track = INK if on else HAIRLINE
        self.create_oval(2, 3, 18, 19, fill=track, outline="")
        self.create_oval(28, 3, 44, 19, fill=track, outline="")
        self.create_rectangle(10, 3, 36, 19, fill=track, outline="")
        left = 30 if on else 4
        self.create_oval(left, 5, left + 12, 17, fill=PAPER_2, outline="")

    def click(self, _event=None):
        self.var.set(not self.var.get())
        if self.command:
            self.command()


class TabBar(tk.Frame):
    """下划线式文字标签栏。"""

    def __init__(self, parent, items: list[tuple[str, str]], on_change=None,
                 font=FONT_BOLD, gap: int = 22):
        super().__init__(parent, bg=PAPER)
        self.on_change = on_change
        self.current = ""
        self.tabs: dict[str, tuple[tk.Label, tk.Frame]] = {}

        row = tk.Frame(self, bg=PAPER)
        row.pack(fill="x")
        for key, text in items:
            cell = tk.Frame(row, bg=PAPER, cursor="hand2")
            cell.pack(side="left", padx=(0, gap))
            lbl = tk.Label(cell, text=text, bg=PAPER, fg=MUTED, font=font,
                           cursor="hand2", pady=5)
            lbl.pack()
            bar = tk.Frame(cell, bg=PAPER, height=2)
            bar.pack(fill="x")
            bar.pack_propagate(False)
            for widget in (cell, lbl):
                widget.bind("<Button-1>", lambda _e, k=key: self.select(k, True))
                widget.bind("<Enter>", lambda _e, k=key: self.hover(k, True))
                widget.bind("<Leave>", lambda _e, k=key: self.hover(k, False))
            self.tabs[key] = (lbl, bar)
        self.rule = rule(self, HAIRLINE, 1)
        self.rule.pack(fill="x")
        if items:
            self.select(items[0][0], False)

    def select(self, key: str, notify: bool = True):
        self.current = key
        for item, (lbl, bar) in self.tabs.items():
            active = item == key
            lbl.configure(fg=INK if active else MUTED)
            bar.configure(bg=VERMILION if active else PAPER)
        if notify and self.on_change:
            self.on_change(key)

    def hover(self, key: str, entering: bool):
        if key == self.current:
            return
        lbl, _bar = self.tabs[key]
        lbl.configure(fg=VERMILION if entering else MUTED)


def card(parent, padx: int = 0, pady: int = 0, bg: str = PAPER_2) -> tk.Frame:
    """纸面卡片：1px 发丝线描边。"""
    frame = tk.Frame(parent, bg=bg, highlightthickness=1,
                     highlightbackground=HAIRLINE, padx=padx, pady=pady)
    return frame


def section_head(parent, index: str, title: str, note: str = "",
                 bg: str = PAPER) -> tk.Frame:
    """带序号的区块标题。"""
    head = tk.Frame(parent, bg=bg)
    tk.Label(head, text=index, bg=bg, fg=VERMILION, font=FONT_EYEBROW).pack(side="left")
    tk.Label(head, text=title, bg=bg, fg=INK, font=FONT_MEDIUM).pack(
        side="left", padx=(10, 0))
    if note:
        tk.Label(head, text=note, bg=bg, fg=MUTED, font=FONT_SMALL).pack(side="right")
    return head


class Pill(tk.Frame):
    """状态徽标：小圆点 + 文字，颜色仅作辅助。"""

    def __init__(self, parent, text: str = "", tone: str = "muted",
                 bg: str = PAPER_2):
        super().__init__(parent, bg=bg, highlightthickness=1,
                         highlightbackground=HAIRLINE)
        self._bg = bg
        self._dot = tk.Canvas(self, width=9, height=9, bg=bg,
                              highlightthickness=0)
        self._dot.pack(side="left", padx=(7, 0), pady=4)
        self._lbl = tk.Label(self, text=text, bg=bg, fg=MUTED, font=FONT_SMALL)
        self._lbl.pack(side="left", padx=(4, 8), pady=2)
        self.set(text, tone)

    def set(self, text: str, tone: str = "muted"):
        color = {"ok": TEAL, "busy": GOLD, "error": VERMILION,
                 "muted": MUTED}.get(tone, MUTED)
        self._dot.delete("all")
        self._dot.create_oval(1, 1, 8, 8, fill=color, outline="")
        self._lbl.configure(text=text, fg=color if tone != "muted" else MUTED)


class NavItem(tk.Frame):
    """左栏分区导航项：序号 + 标题 + 右侧计数。"""

    def __init__(self, parent, index: str, title: str, command=None,
                 bg: str = PAPER):
        super().__init__(parent, bg=bg, cursor="hand2")
        self.command = command
        self.bg = bg
        self.active = False

        self.bar = tk.Frame(self, bg=bg, width=2)
        self.bar.pack(side="left", fill="y")
        self.bar.pack_propagate(False)

        body = tk.Frame(self, bg=bg)
        body.pack(side="left", fill="x", expand=True, padx=(10, 12), pady=7)
        self.index_lbl = tk.Label(body, text=index, bg=bg, fg=MUTED,
                                  font=FONT_EYEBROW, width=2, anchor="w")
        self.index_lbl.pack(side="left")
        self.title_lbl = tk.Label(body, text=title, bg=bg, fg=INK_SOFT,
                                  font=FONT_BOLD, anchor="w")
        self.title_lbl.pack(side="left", padx=(6, 0))
        self.badge = tk.Label(body, text="", bg=bg, fg=VERMILION,
                              font=FONT_LABEL, anchor="e")
        self.badge.pack(side="right")

        for widget in (self, body, self.index_lbl, self.title_lbl, self.badge):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def _click(self, _event=None):
        if self.command:
            self.command()

    def _enter(self, _event=None):
        if not self.active:
            self.title_lbl.configure(fg=VERMILION)

    def _leave(self, _event=None):
        if not self.active:
            self.title_lbl.configure(fg=INK_SOFT)

    def set_active(self, active: bool):
        self.active = active
        self.bar.configure(bg=VERMILION if active else self.bg)
        self.title_lbl.configure(fg=INK if active else INK_SOFT,
                                 font=FONT_BOLD if active else FONT)
        self.index_lbl.configure(fg=VERMILION if active else MUTED)

    def set_badge(self, text: str):
        self.badge.configure(text=text)


class ScopeRow(tk.Frame):
    """平台范围行：状态点 + 名称 + 右侧计数/状态。"""

    def __init__(self, parent, label: str, command=None, bg: str = PAPER):
        super().__init__(parent, bg=bg, cursor="hand2")
        self.command = command
        self.bg = bg

        self.dot = tk.Canvas(self, width=10, height=10, bg=bg,
                             highlightthickness=0)
        self.dot.pack(side="left", padx=(4, 0), pady=6)
        self.name = tk.Label(self, text=label, bg=bg, fg=INK_SOFT, font=FONT,
                             anchor="w", cursor="hand2")
        self.name.pack(side="left", padx=(8, 0))
        self.meta = tk.Label(self, text="", bg=bg, fg=MUTED, font=FONT_LABEL,
                             anchor="e", cursor="hand2")
        self.meta.pack(side="right", padx=(4, 6))

        for widget in (self, self.dot, self.name, self.meta):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def _click(self, _event=None):
        if self.command:
            self.command()

    def _enter(self, _event=None):
        self.name.configure(fg=VERMILION)

    def _leave(self, _event=None):
        self.name.configure(fg=INK_SOFT)

    def set(self, meta: str, tone: str = "muted", active: bool = False):
        color = {"ok": TEAL, "busy": GOLD, "error": VERMILION,
                 "muted": HAIRLINE}.get(tone, HAIRLINE)
        self.dot.delete("all")
        if tone == "muted":
            self.dot.create_oval(2, 2, 8, 8, outline=HAIRLINE, width=1, fill="")
        else:
            self.dot.create_oval(1, 1, 9, 9, fill=color, outline="")
        self.name.configure(text=self.name.cget("text"), fg=INK if active else INK_SOFT,
                            font=FONT_BOLD if active else FONT)
        self.meta.configure(text=meta, fg=color if tone != "muted" else MUTED)


class Toast:
    """右下角瞬时提示：只承担“刚发生”的反馈，并跟随主窗口移动。"""

    def __init__(self, root):
        self.root = root
        self.win = None
        self.job = None
        self.size = (0, 0)
        self._place_job = None
        self.root.bind("<Configure>", self._on_root_configure, add="+")

    def _on_root_configure(self, event):
        if self.win is not None and event.widget is self.root:
            if self._place_job:
                try:
                    self.root.after_cancel(self._place_job)
                except (TclError, ValueError):
                    pass
            # 拖动时 Configure 连续触发，等布局稳定后再定位，避免落在中间位置
            self._place_job = self.root.after_idle(self._run_place)

    def _run_place(self):
        self._place_job = None
        self._place()

    def _place(self):
        if self.win is None:
            return
        w, h = self.size
        x = self.root.winfo_rootx() + self.root.winfo_width() - w - 26
        y = self.root.winfo_rooty() + self.root.winfo_height() - h - 58
        try:
            self.win.geometry(f"+{x}+{y}")
        except TclError:
            pass

    def show(self, text: str, tone: str = "muted", ms: int = 4200):
        self.hide()
        color = {"ok": TEAL, "busy": GOLD, "error": VERMILION,
                 "muted": HAIRLINE}.get(tone, HAIRLINE)
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except TclError:
            pass
        shell = tk.Frame(win, bg=color, padx=2, pady=2)
        shell.pack(fill="both", expand=True)
        inner = tk.Frame(shell, bg=PAPER_2, padx=16, pady=11)
        inner.pack(fill="both", expand=True)
        tk.Frame(inner, bg=color, width=2, height=14).pack(side="left", padx=(0, 10))
        tk.Label(inner, text=text, bg=PAPER_2, fg=INK_SOFT, font=FONT,
                 justify="left", wraplength=320, anchor="w").pack(side="left")
        win.update_idletasks()
        self.size = (win.winfo_reqwidth(), win.winfo_reqheight())
        self.win = win
        win.geometry(f"{self.size[0]}x{self.size[1]}")
        self._place()
        self.job = self.root.after(ms, self.hide)

    def hide(self):
        if self._place_job:
            try:
                self.root.after_cancel(self._place_job)
            except (TclError, ValueError):
                pass
            self._place_job = None
        if self.job:
            try:
                self.root.after_cancel(self.job)
            except (TclError, ValueError):
                pass
            self.job = None
        if self.win:
            try:
                self.win.destroy()
            except TclError:
                pass
            self.win = None
