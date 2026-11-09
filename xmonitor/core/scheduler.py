"""多平台串行采集调度：平台错误隔离、熔断冷却与统一事件队列。"""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timedelta

from ..platforms import available, enabled_ids, has_session
from .collector import collect_platform, record_error
from .http import ChallengeRequired, LoginRequired, RateLimited

MIN_INTERVAL = 5
MAX_INTERVAL = 240
COOLDOWN_LOGIN_MINUTES = 360
COOLDOWN_RATE_MINUTES = 30
COOLDOWN_CHALLENGE_MINUTES = 180


class MultiCollectScheduler:
    """界面通过 poll() 取事件；平台之间串行执行，避免并发请求触发风控。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.events: queue.Queue = queue.Queue()
        self.stop_evt = threading.Event()
        self.wake = threading.Event()
        self.auto = True
        self.force_all = True
        self.force_platforms: set[str] = set()
        self.interval = self._clamp(cfg.get("collect_interval_minutes", 30))
        self.last_run: datetime | None = None
        self.states = {p: {"failures": 0, "cooldown_until": None,
                          "last_run": None, "last_error": ""} for p in available()}
        self._thread = threading.Thread(target=self._loop, daemon=True)

    @staticmethod
    def _clamp(minutes) -> int:
        try:
            return max(MIN_INTERVAL, min(MAX_INTERVAL, int(float(minutes))))
        except (TypeError, ValueError):
            return 30

    # ---------- 控制 ----------
    def start(self):
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self):
        self.stop_evt.set()
        self.wake.set()

    def trigger(self, platform: str | None = None):
        if platform:
            self.force_platforms.add(platform)
        else:
            self.force_all = True
        self.wake.set()

    def set_auto(self, on: bool):
        self.auto = bool(on)
        if self.auto:
            self.force_all = True
            self.wake.set()

    def set_interval(self, minutes) -> int:
        self.interval = self._clamp(minutes)
        self.cfg["collect_interval_minutes"] = self.interval
        return self.interval

    def next_run(self) -> datetime | None:
        if not self.auto or not self.last_run:
            return None
        return self.last_run + timedelta(minutes=self.interval)

    def platform_state(self, platform: str) -> dict:
        return self.states.setdefault(
            platform, {"failures": 0, "cooldown_until": None,
                      "last_run": None, "last_error": ""})

    # ---------- 事件 ----------
    def poll(self) -> list[tuple[str, object]]:
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def _put(self, kind: str, payload=None) -> None:
        self.events.put((kind, payload))

    # ---------- 线程 ----------
    def _loop(self):
        while not self.stop_evt.is_set():
            if self.auto or self.force_all or self.force_platforms:
                forced = set(self.force_platforms)
                self.force_all = False
                self.force_platforms.clear()
                self._collect_round(forced)
            self._wait_next()

    def _collect_round(self, forced: set[str] | None = None):
        targets = enabled_ids(self.cfg)
        if not targets:
            self._put("need_config", {"platforms": available()})
            self.last_run = datetime.now()
            return

        ready = []
        for platform in targets:
            block = (self.cfg.get("platforms") or {}).get(platform) or {}
            has_account = bool(block.get("account_name") or block.get("platform_user_id"))
            if has_account and has_session(block, platform):
                ready.append(platform)
        if not ready:
            self._put("need_config", {"platforms": available(), "enabled": targets})
            self.last_run = datetime.now()
            return

        summary = {"ok": 0, "failed": 0, "skipped": 0}
        if forced:
            ready = [p for p in ready if p in forced] or ready
        for platform in ready:
            if self.stop_evt.is_set():
                return
            state = self.platform_state(platform)
            cooldown = state.get("cooldown_until")
            if cooldown and datetime.now() < cooldown:
                summary["skipped"] += 1
                self._put("platform_skip", {
                    "platform": platform,
                    "message": f"冷却中，{cooldown:%H:%M} 后重试",
                })
                continue

            self._put("platform_status", {"platform": platform, "message": "采集中…"})
            try:
                result = collect_platform(self.cfg, platform, log=self._log)
                state.update({"failures": 0, "cooldown_until": None, "last_error": "",
                              "last_run": result["at"]})
                summary["ok"] += 1
                self._put("platform_done", result)
            except Exception as e:
                summary["failed"] += 1
                minutes = self._register_failure(platform, e)
                record_error(self.cfg, platform, f"{type(e).__name__}: {e}")
                self._put("platform_error", {
                    "platform": platform,
                    "kind": getattr(e, "kind", "error"),
                    "message": str(e),
                    "cooldown_minutes": minutes,
                })
            if self.stop_evt.wait(1.5):
                return

        self.last_run = datetime.now()
        self._put("round_done", summary)

    def _register_failure(self, platform: str, error: Exception) -> int:
        state = self.platform_state(platform)
        state["last_error"] = f"{type(error).__name__}: {error}"
        state["last_run"] = datetime.now()
        if isinstance(error, LoginRequired):
            minutes = COOLDOWN_LOGIN_MINUTES
        elif isinstance(error, ChallengeRequired):
            minutes = COOLDOWN_CHALLENGE_MINUTES
        elif isinstance(error, RateLimited):
            minutes = COOLDOWN_RATE_MINUTES
        else:
            state["failures"] = int(state.get("failures") or 0) + 1
            minutes = min(2 ** state["failures"], int(self.cfg.get("cooldown_minutes", 60)))
        state["cooldown_until"] = datetime.now() + timedelta(minutes=minutes)
        return minutes

    def _log(self, message: str):
        self._put("log", message)

    def _wait_next(self):
        while not self.stop_evt.is_set():
            self.wake.wait(0.4)
            self.wake.clear()
            if self.force_all or self.force_platforms or self.stop_evt.is_set():
                return
            if self.auto and self.last_run:
                if (datetime.now() - self.last_run).total_seconds() >= self.interval * 60:
                    return
