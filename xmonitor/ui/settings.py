"""设置：整页双栏表单（平台列表 / 分区字段），桌宠仍以模态复用同一页面。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from ..core.config import data_dir, save_config
from ..platforms import (available, clean_session_value, extra_cookie_names,
                         load, session_cookie_name, user_id_required)
from .browser_login import BrowserLoginDialog
from .theme import (FONT, FONT_LABEL, FONT_SMALL,
                    FONT_TITLE, HAIRLINE, INK, INK_SOFT, MUTED, PAPER, PAPER_2,
                    TEAL, VERMILION, CheckRow, Field, ScopeRow, action_button,
                    apply_style, eyebrow, rule, section_head)

PLATFORM_FIELDS = ("enabled", "account_name", "platform_user_id", "session_id",
                   "cookies", "max_posts", "filters")

SESSION_GUIDES = {
    "x": ("获取锚点：点「浏览器登录」自动读取 auth_token 与 ct0；也可在 x.com 登录后，"
          "开发者工具 → Application → Cookies 复制 auth_token。\n"
          "账号名称：个人主页 handle（不含 @）。\n"
          "用户 ID：无需填写，程序自动解析。"),
    "instagram": ("获取锚点：点「浏览器登录」自动读取 sessionid；也可在 instagram.com "
                  "登录后，开发者工具 → Cookies 复制 sessionid。\n"
                  "账号名称：用户名。\n"
                  "用户 ID：无需填写，程序自动解析。"),
    "xiaohongshu": ("获取锚点：点「浏览器登录」自动读取 web_session；也可在 xiaohongshu.com "
                    "登录后，开发者工具 → Cookies 复制 web_session。\n"
                    "账号名称：昵称。\n"
                    "用户 ID：个人主页链接 /user/profile/<ID> 中的 ID。"),
    "weibo": ("获取锚点：点「浏览器登录」自动读取 SUB；也可在 weibo.com 登录后，"
              "开发者工具 → Cookies 复制 SUB。\n"
              "账号名称：昵称。\n"
              "用户 ID：个人主页链接 weibo.com/u/<UID> 中的数字 UID。"),
    "pixiv": ("获取锚点：点「浏览器登录」自动读取 PHPSESSID；也可在 pixiv.net 登录后，"
              "开发者工具 → Cookies 复制 PHPSESSID。\n"
              "账号名称：昵称。\n"
              "用户 ID：个人主页链接 pixiv.net/users/<数字ID> 中的数字。"),
    "tiktok": ("获取锚点：点「浏览器登录」自动读取 sessionid 与 tt_chain_token；也可在 tiktok.com "
               "登录后，开发者工具 → Cookies 复制 sessionid。\n"
               "账号名称：主页 handle（不含 @）。\n"
               "用户 ID：无需填写，程序自动解析。"),
}


def split_keywords(text: str) -> list[str]:
    """把逗号分隔的过滤词转为列表，空项丢弃。"""
    return [word.strip() for word in text.split(",") if word.strip()]


def _as_int(text: str) -> int | None:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    if not value.is_integer():
        return None
    return int(value)


class SettingsPage(tk.Frame):
    """05 设置：左平台列表、右分区表单、底部保存条。"""

    def __init__(self, parent, cfg: dict, on_saved=None):
        super().__init__(parent, bg=PAPER)
        self.cfg = cfg
        self.on_saved = on_saved
        self.platforms = available()
        self.selected = self.platforms[0] if self.platforms else ""
        self.staged: dict[str, dict] = {}
        self._loading = False
        self.plat_rows: dict[str, ScopeRow] = {}
        self.vars = {
            "enabled": tk.BooleanVar(value=False),
            "account": tk.StringVar(),
            "uid": tk.StringVar(),
            "session": tk.StringVar(),
            "cookies": tk.StringVar(),
            "max_posts": tk.StringVar(value="50"),
            "include": tk.StringVar(),
            "exclude": tk.StringVar(),
            "exclude_reposts": tk.BooleanVar(value=False),
            "only_changed": tk.BooleanVar(value=False),
            "interval": tk.StringVar(
                value=str(cfg.get("collect_interval_minutes", 30))),
        }
        self.build()
        for var in self.vars.values():
            var.trace_add("write", lambda *_a: self._on_change())
        if self.selected:
            self._load_platform(self.selected)
        self._refresh_rows()
        self._refresh_dirty()

    # ---------- 布局 ----------
    def build(self):
        head = tk.Frame(self, bg=PAPER)
        head.pack(fill="x")
        left = tk.Frame(head, bg=PAPER)
        left.pack(side="left", anchor="n")
        eyebrow(left, "Settings · 本机配置").pack(anchor="w")
        tk.Label(left, text="采集设置", bg=PAPER, fg=INK, font=FONT_TITLE,
                 anchor="w").pack(anchor="w", pady=(3, 0))

        right = tk.Frame(head, bg=PAPER)
        right.pack(side="right", anchor="n")
        self.dirty_lbl = tk.Label(right, text="", bg=PAPER, fg=MUTED,
                                  font=FONT_LABEL, anchor="e")
        self.dirty_lbl.pack(side="left", padx=(0, 12))

        rule(self).pack(fill="x", pady=(12, 0))

        self.build_footer()
        body = tk.Frame(self, bg=PAPER)
        body.pack(fill="both", expand=True, pady=(12, 0))
        body.columnconfigure(0, minsize=184)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)

        left_col = tk.Frame(body, bg=PAPER)
        left_col.grid(row=0, column=0, sticky="ns", padx=(0, 18))
        tk.Frame(body, bg=HAIRLINE, width=1).grid(row=0, column=1, sticky="ns")
        form = tk.Frame(body, bg=PAPER)
        form.grid(row=0, column=2, sticky="nsew", padx=(18, 0))
        form.columnconfigure(0, weight=1, uniform="form")
        form.columnconfigure(1, weight=1, uniform="form")
        form.rowconfigure(0, weight=1)
        self.form = form

        self.build_sidebar(left_col)
        self.build_account_section(form)
        self.build_credential_section(form)
        self.build_filter_section(form, column=1)
        self.build_policy_section(form, column=1)

    def build_footer(self):
        foot = tk.Frame(self, bg=PAPER)
        foot.pack(side="bottom", fill="x", pady=(8, 0))
        self.foot_hint = tk.Label(
            foot, text="凭据只保存在本机，请勿分享 config.json",
            bg=PAPER, fg=MUTED, font=FONT_SMALL, anchor="w")
        self.foot_hint.pack(side="left")
        self.btn_save = action_button(foot, "保存设置", self.save, "primary")
        self.btn_save.pack(side="right")
        action_button(foot, "还原", self.discard, "secondary").pack(
            side="right", padx=(0, 8))
        rule(self).pack(side="bottom", fill="x", pady=(0, 8))

    def build_sidebar(self, parent):
        tk.Label(parent, text="平台范围", bg=PAPER, fg=MUTED,
                 font=FONT_LABEL, anchor="w").pack(fill="x")
        for platform in self.platforms:
            row = ScopeRow(parent, load(platform).label,
                           command=lambda p=platform: self.focus_platform(p))
            row.pack(fill="x")
            self.plat_rows[platform] = row

        rule(parent).pack(fill="x", pady=(12, 10))
        tk.Label(parent, text="采集间隔（分钟）", bg=PAPER, fg=MUTED,
                 font=FONT_SMALL, anchor="w").pack(fill="x")
        self.interval_entry = tk.Entry(
            parent, textvariable=self.vars["interval"], width=6, bd=0,
            relief="flat", bg=PAPER_2, fg=INK, insertbackground=INK,
            font=FONT, justify="center", highlightthickness=1,
            highlightbackground=HAIRLINE, highlightcolor=VERMILION)
        self.interval_entry.pack(anchor="w", pady=(4, 0), ipady=4, ipadx=4)
        self.err_interval = tk.Label(parent, text="", bg=PAPER, fg=VERMILION,
                                     font=FONT_SMALL, anchor="w", wraplength=176,
                                     justify="left")
        self.err_interval.pack(fill="x", pady=(2, 0))
        tk.Label(parent, text="5 – 240 分钟 · 平台之间串行采集",
                 bg=PAPER, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            fill="x", pady=(2, 0))

    def _section(self, parent, index: str, title: str, note: str = ""):
        head = section_head(parent, index, title, note, bg=PAPER)
        head.pack(fill="x", pady=(0, 4))
        rule(parent).pack(fill="x", pady=(0, 8))

    def build_account_section(self, parent):
        box = tk.Frame(parent, bg=PAPER)
        box.grid(row=0, column=0, sticky="new", pady=(0, 16))
        self._section(box, "01", "平台与账号", "未启用的平台不参与调度")

        flags = tk.Frame(box, bg=PAPER)
        flags.pack(fill="x", pady=(0, 10))
        CheckRow(flags, "启用该平台", self.vars["enabled"]).pack(side="left")
        self.enabled_state = tk.Label(flags, text="", bg=PAPER, fg=MUTED,
                                      font=FONT_SMALL, anchor="e")
        self.enabled_state.pack(side="right")

        grid = tk.Frame(box, bg=PAPER)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="account")
        grid.columnconfigure(1, weight=1, uniform="account")
        Field(grid, "账号名称（不含 @）", self.vars["account"]).grid(
            row=0, column=0, sticky="ew", padx=(0, 16))
        self.uid_field = Field(grid, "平台用户 ID（必填）", self.vars["uid"])
        self.uid_field.grid(row=0, column=1, sticky="ew")
        self.uid_note = tk.Label(
            grid, text="该平台无需填写用户 ID，采集时自动解析",
            bg=PAPER, fg=MUTED, font=FONT_SMALL, anchor="w")
        self.uid_note.grid(row=0, column=1, sticky="ew")
        Field(box, "每轮采集上限（1 – 200）", self.vars["max_posts"], width=8).pack(
            fill="x", pady=(12, 0))
        self.err_max = tk.Label(box, text="", bg=PAPER, fg=VERMILION,
                                font=FONT_SMALL, anchor="w")
        self.err_max.pack(fill="x")

    def build_credential_section(self, parent):
        box = tk.Frame(parent, bg=PAPER)
        box.grid(row=1, column=0, sticky="new")
        self.section_head = section_head(box, "02", "会话与凭据", "", bg=PAPER)
        self.section_head.pack(fill="x", pady=(0, 4))
        self.session_note = tk.Frame(box, bg=PAPER)
        self.session_note.pack(fill="x")
        self.session_label = tk.Label(self.session_note, text="会话锚点",
                                      bg=PAPER, fg=MUTED, font=FONT_SMALL,
                                      anchor="w")
        self.session_label.pack(side="left")
        self.show_btn = action_button(self.session_note, "显示", self.toggle_session)
        self.show_btn.pack(side="right")
        rule(box).pack(fill="x", pady=(4, 0))

        self.session_entry = tk.Entry(
            box, textvariable=self.vars["session"], show="*", bd=0, relief="flat",
            bg=PAPER, fg=INK, insertbackground=INK, font=FONT,
            highlightthickness=0)
        self.session_entry.pack(fill="x", pady=(6, 0))
        line = tk.Frame(box, bg=HAIRLINE, height=1)
        line.pack(fill="x", pady=(3, 0))
        line.pack_propagate(False)
        self.session_entry.bind("<FocusIn>", lambda _e: line.configure(bg=VERMILION))
        self.session_entry.bind("<FocusOut>", lambda _e: line.configure(bg=HAIRLINE))

        actions = tk.Frame(box, bg=PAPER)
        actions.pack(fill="x", pady=(8, 0))
        action_button(actions, "浏览器登录", self.open_browser_login).pack(side="left")

        self.hint_lbl = tk.Label(box, text="", bg=PAPER, fg=MUTED, font=FONT_SMALL,
                                 wraplength=360, justify="left", anchor="w")
        self.hint_lbl.pack(fill="x", pady=(10, 0))

    def build_filter_section(self, parent, column: int):
        box = tk.Frame(parent, bg=PAPER)
        box.grid(row=0, column=column, sticky="new", padx=(18, 0), pady=(0, 16))
        self._section(box, "03", "过滤规则", "留空表示不过滤")
        Field(box, "标题 / 正文包含词（逗号分隔）", self.vars["include"]).pack(fill="x")
        Field(box, "排除词（逗号分隔）", self.vars["exclude"]).pack(
            fill="x", pady=(10, 0))
        flags = tk.Frame(box, bg=PAPER)
        flags.pack(fill="x", pady=(10, 0))
        CheckRow(flags, "排除转发", self.vars["exclude_reposts"]).pack(side="left")
        CheckRow(flags, "仅保留有变化的帖子", self.vars["only_changed"]).pack(
            side="left", padx=(18, 0))

    def build_policy_section(self, parent, column: int):
        box = tk.Frame(parent, bg=PAPER)
        box.grid(row=1, column=column, sticky="new", padx=(18, 0))
        self._section(box, "04", "运行策略", "只读")
        rows = (
            ("平台调度", "串行 · 单平台请求间隔 ≥ 3 秒"),
            ("失败重试", "按平台配置 · 指数退避"),
            ("冷却策略", f"连续失败 {self.cfg.get('max_consecutive_failures', 3)} 次"
                       f"后冷却 {self.cfg.get('cooldown_minutes', 60)} 分钟"),
            ("报告回看", f"{self.cfg.get('report_days', 30)} 天 · reports/<平台>/"),
            ("数据落盘", "临时文件 + 原子替换，无数据库"),
        )
        table = tk.Frame(box, bg=PAPER)
        table.pack(fill="x")
        for label, value in rows:
            row = tk.Frame(table, bg=PAPER)
            row.pack(fill="x")
            tk.Label(row, text=label, bg=PAPER, fg=MUTED, font=FONT_SMALL,
                     anchor="w").pack(side="left", pady=5)
            tk.Label(row, text=value, bg=PAPER, fg=INK_SOFT, font=FONT_SMALL,
                     anchor="e", wraplength=210, justify="right").pack(
                side="right", pady=5)
            rule(table).pack(fill="x")

    # ---------- 表单状态 ----------
    def _snapshot(self) -> dict:
        return {
            "enabled": bool(self.vars["enabled"].get()),
            "account_name": self.vars["account"].get(),
            "platform_user_id": self.vars["uid"].get(),
            "session_id": self.vars["session"].get(),
            "cookies": self.vars["cookies"].get(),
            "max_posts": self.vars["max_posts"].get(),
            "filters": {
                "include_keywords": split_keywords(self.vars["include"].get()),
                "exclude_keywords": split_keywords(self.vars["exclude"].get()),
                "exclude_reposts": bool(self.vars["exclude_reposts"].get()),
                "only_changed": bool(self.vars["only_changed"].get()),
            },
        }

    def _cfg_snapshot(self, platform: str) -> dict:
        block = (self.cfg.get("platforms") or {}).get(platform) or {}
        filters = block.get("filters") or {}
        return {
            "enabled": bool(block.get("enabled")),
            "account_name": str(block.get("account_name") or ""),
            "platform_user_id": str(block.get("platform_user_id") or ""),
            "session_id": str(block.get("session_id") or ""),
            "cookies": str(block.get("cookies") or ""),
            "max_posts": str(block.get("max_posts") or 50),
            "filters": {
                "include_keywords": list(filters.get("include_keywords") or []),
                "exclude_keywords": list(filters.get("exclude_keywords") or []),
                "exclude_reposts": bool(filters.get("exclude_reposts")),
                "only_changed": bool(filters.get("only_changed")),
            },
        }

    def _load_platform(self, platform: str):
        if not platform:
            return
        self._loading = True
        self.selected = platform
        block = (self.cfg.get("platforms") or {}).get(platform) or {}
        snap = self.staged.get(platform)
        if snap:
            filters = snap["filters"]
            self.vars["enabled"].set(bool(snap["enabled"]))
            self.vars["account"].set(str(snap["account_name"]))
            self.vars["uid"].set(str(snap["platform_user_id"]))
            self.vars["session"].set(str(snap["session_id"]))
            self.vars["cookies"].set(str(snap["cookies"]))
            self.vars["max_posts"].set(str(snap["max_posts"]))
            self.vars["include"].set(", ".join(filters["include_keywords"]))
            self.vars["exclude"].set(", ".join(filters["exclude_keywords"]))
            self.vars["exclude_reposts"].set(bool(filters["exclude_reposts"]))
            self.vars["only_changed"].set(bool(filters["only_changed"]))
        else:
            filters = block.get("filters") or {}
            self.vars["enabled"].set(bool(block.get("enabled")))
            self.vars["account"].set(str(block.get("account_name") or ""))
            self.vars["uid"].set(str(block.get("platform_user_id") or ""))
            self.vars["session"].set(str(block.get("session_id") or ""))
            self.vars["cookies"].set(str(block.get("cookies") or ""))
            self.vars["max_posts"].set(str(block.get("max_posts") or 50))
            self.vars["include"].set(", ".join(filters.get("include_keywords") or []))
            self.vars["exclude"].set(", ".join(filters.get("exclude_keywords") or []))
            self.vars["exclude_reposts"].set(bool(filters.get("exclude_reposts")))
            self.vars["only_changed"].set(bool(filters.get("only_changed")))
        self._loading = False

        cls = load(platform)
        anchor = cls.session_cookie or "—"
        need = "必填" if cls.requires_cookie else "可选"
        self.session_label.configure(text=f"会话锚点 · {anchor} · {need}")

        required_uid = user_id_required(platform)
        if required_uid:
            self.uid_field.grid()
            self.uid_note.grid_remove()
        else:
            self.uid_field.grid_remove()
            self.uid_note.grid()

        guide = SESSION_GUIDES.get(platform)
        if guide:
            self.hint_lbl.configure(text=f"{cls.label}｜{guide}")
        else:
            extras = extra_cookie_names(platform)
            auto = f"；{'、'.join(extras)} 由程序自动获取" if extras else ""
            self.hint_lbl.configure(
                text=f"{cls.label}：填写账号名称与会话锚点 {anchor}{auto}。")
        enabled = bool(snap["enabled"]) if snap else bool(block.get("enabled"))
        self.enabled_state.configure(
            text="参与调度" if enabled else "不参与调度",
            fg=TEAL if enabled else MUTED)
        self.session_entry.configure(show="*")
        self.show_btn.configure(text="显示")
        self._validate_current()

    def focus_platform(self, platform: str):
        if not platform or platform == self.selected:
            return
        self._stage_current()
        self._load_platform(platform)
        self._refresh_rows()
        self._refresh_dirty()

    def _stage_current(self):
        if not self.selected:
            return
        snap = self._snapshot()
        if snap != self._cfg_snapshot(self.selected):
            self.staged[self.selected] = snap
        else:
            self.staged.pop(self.selected, None)

    # ---------- 脏状态与校验 ----------
    def _on_change(self):
        if self._loading:
            return
        platform = self.selected
        if platform:
            self.enabled_state.configure(
                text="参与调度" if self.vars["enabled"].get() else "不参与调度",
                fg=TEAL if self.vars["enabled"].get() else MUTED)
        self._validate_current()
        self._refresh_dirty()

    def _validate_current(self) -> bool:
        ok = True
        interval = _as_int(self.vars["interval"].get())
        if interval is None or not 5 <= interval <= 240:
            self.err_interval.configure(text="需要 5 – 240 之间的整数")
            ok = False
        else:
            self.err_interval.configure(text="")
        max_posts = _as_int(self.vars["max_posts"].get())
        if max_posts is None or not 1 <= max_posts <= 200:
            self.err_max.configure(text="需要 1 – 200 之间的整数")
            ok = False
        else:
            self.err_max.configure(text="")
        return ok

    def _refresh_dirty(self):
        dirty = self.is_dirty()
        self.dirty_lbl.configure(
            text="● 未保存的更改" if dirty else "已与 config.json 同步",
            fg=VERMILION if dirty else MUTED)
        self.btn_save.configure(text="保存设置" + (" *" if dirty else ""))

    def is_dirty(self) -> bool:
        if self.staged:
            return True
        if not self.selected:
            return False
        if self._snapshot() != self._cfg_snapshot(self.selected):
            return True
        interval = _as_int(self.vars["interval"].get())
        return interval != _as_int(str(self.cfg.get("collect_interval_minutes", 30)))

    def discard(self):
        self.staged.clear()
        if self.selected:
            self._load_platform(self.selected)
        self._refresh_rows()
        self._refresh_dirty()

    def _refresh_rows(self):
        for platform, row in self.plat_rows.items():
            block = (self.cfg.get("platforms") or {}).get(platform) or {}
            staged = self.staged.get(platform)
            enabled = staged["enabled"] if staged else bool(block.get("enabled"))
            row.set("启用" if enabled else "停用",
                    "ok" if enabled else "muted",
                    platform == self.selected)

    # ---------- 凭据 ----------
    def toggle_session(self):
        hidden = bool(self.session_entry.cget("show"))
        self.session_entry.configure(show="" if hidden else "*")
        self.show_btn.configure(text="隐藏" if hidden else "显示")

    def open_browser_login(self):
        if not self.selected:
            return
        profile = data_dir(self.cfg) / "browser" / self.selected
        channel = (self.cfg.get("browser") or {}).get("channel", "auto")
        BrowserLoginDialog(self.winfo_toplevel(), self.selected, str(profile),
                           self._apply_session, channel=channel)

    def _apply_session(self, payload):
        value = (payload or {}).get("value") or ""
        extras = (payload or {}).get("extras") or {}
        self.vars["session"].set(value)
        self.vars["cookies"].set("; ".join(f"{k}={v}" for k, v in extras.items()))
        read = "、".join([session_cookie_name(self.selected), *extras])
        self.hint_lbl.configure(text=f"已读取 {read}，保存后生效")
        self.toggle_session()

    # ---------- 保存 ----------
    def _block_updates(self, platform: str, snap: dict) -> dict:
        return {
            "enabled": bool(snap["enabled"]),
            "account_name": str(snap["account_name"]).strip().lstrip("@"),
            "platform_user_id": (str(snap["platform_user_id"]).strip()
                                 if user_id_required(platform) else ""),
            "session_id": clean_session_value(platform,
                                              str(snap["session_id"])),
            "cookies": str(snap["cookies"]).strip(),
            "max_posts": _as_int(snap["max_posts"]) or 50,
            "filters": {
                "include_keywords": split_keywords(
                    ", ".join(snap["filters"]["include_keywords"])),
                "exclude_keywords": split_keywords(
                    ", ".join(snap["filters"]["exclude_keywords"])),
                "exclude_reposts": bool(snap["filters"]["exclude_reposts"]),
                "only_changed": bool(snap["filters"]["only_changed"]),
            },
        }

    def save(self) -> bool:
        if not self.selected:
            return False
        self._stage_current()
        interval = _as_int(self.vars["interval"].get())
        if interval is None or not 5 <= interval <= 240:
            self._validate_current()
            self.foot_hint.configure(text="采集间隔需要 5 – 240 之间的整数",
                                     fg=VERMILION)
            return False
        targets = {p: self.staged.get(p) or self._cfg_snapshot(p)
                   for p in self.platforms}
        missing_uid = [p for p, snap in targets.items()
                       if snap["enabled"] and user_id_required(p)
                       and not str(snap["platform_user_id"]).strip()]
        if missing_uid:
            target = missing_uid[0]
            if target != self.selected:
                self.focus_platform(target)
            self.uid_field.entry.focus_set()
            self.foot_hint.configure(
                text=f"{load(target).label} 需要填写平台用户 ID", fg=VERMILION)
            return False
        bad = [p for p, snap in self.staged.items()
               if not (lambda v: v is not None and 1 <= v <= 200)(
                   _as_int(snap["max_posts"]))]
        if bad:
            self.focus_platform(bad[0])
            self._validate_current()
            self.foot_hint.configure(
                text=f"{load(bad[0]).label} 的每轮上限需要 1 – 200 之间的整数",
                fg=VERMILION)
            return False

        platforms = {}
        for platform, snap in self.staged.items():
            platforms[platform] = self._block_updates(platform, snap)
        updates = {"collect_interval_minutes": interval}
        if platforms:
            updates["platforms"] = platforms
        save_config(self.cfg, updates)
        self.staged.clear()
        self._load_platform(self.selected)
        self._refresh_rows()
        self.foot_hint.configure(text="已保存到 config.json", fg=TEAL)
        self._refresh_dirty()
        if self.on_saved:
            self.on_saved(updates)
        return True


class SettingsDialog(tk.Toplevel):
    """桌宠等外部入口复用的模态版本，内容与整页设置完全一致。"""

    def __init__(self, master, cfg: dict, on_saved=None):
        super().__init__(master)
        self.cfg = cfg
        self.on_saved = on_saved

        self.title("设置 · x 观测台")
        self.configure(bg=PAPER)
        self.geometry("1100x700")
        self.minsize(1000, 640)
        self.transient(master)
        self.grab_set()
        apply_style(self)

        tk.Frame(self, bg=INK, height=4).pack(fill="x")
        shell = tk.Frame(self, bg=PAPER, padx=24, pady=14)
        shell.pack(fill="both", expand=True)
        self.page = SettingsPage(shell, cfg, on_saved=self._handle_saved)
        self.page.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _handle_saved(self, updates: dict):
        if self.on_saved:
            self.on_saved(updates)
        self.destroy()

    def _close(self):
        if self.page.is_dirty() and not messagebox.askyesno(
                "未保存的更改", "设置中有未保存的更改，关闭将丢失。仍要关闭？",
                parent=self):
            return
        self.destroy()
