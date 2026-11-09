"""平台数据仓库：每个平台独立目录，缺失指标列不写入。"""

from __future__ import annotations

import csv
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..platforms.schema import account_columns, post_columns, snapshot_columns

SLOT_MINUTES = 30
RUN_FIELDS = ("platform", "started_at", "status", "new_posts", "snapshots",
              "note", "error", "verify")
LOCK = threading.RLock()


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def floor_slot(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    return dt.replace(minute=(dt.minute // SLOT_MINUTES) * SLOT_MINUTES,
                      second=0, microsecond=0)


def _atomic_write(path: Path, write_fn) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:
        write_fn(f)
    os.replace(tmp, path)


class PlatformStore:
    def __init__(self, data_dir: str, platform: str, *,
                 account_metrics: tuple[str, ...], post_metrics: tuple[str, ...]):
        self.platform = platform
        self.dir = Path(data_dir) / "platforms" / platform
        self.dir.mkdir(parents=True, exist_ok=True)
        self.account_fields = account_columns(account_metrics)
        self.post_fields = post_columns(post_metrics)
        self.snap_fields = snapshot_columns(post_metrics)
        self.post_metrics = tuple(post_metrics)
        self.account_path = self.dir / "accounts.csv"
        self.posts_path = self.dir / "posts.csv"
        self.runs_path = self.dir / "runs.csv"

    # ---------- 基础读写 ----------
    def _read(self, path: Path, fields: list[str]) -> list[dict]:
        if not path.exists():
            return []
        rows = []
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            for raw in csv.DictReader(f):
                rows.append({k: (raw.get(k) or "") for k in fields})
        return rows

    def _write(self, path: Path, fields: list[str], rows) -> None:
        def writer(f):
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        _atomic_write(path, writer)

    @staticmethod
    def _metric(value) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return int(float(value))
        except ValueError:
            return None

    # ---------- 帖子 ----------
    def load_posts(self) -> dict[str, dict]:
        out = {}
        for row in self._read(self.posts_path, self.post_fields):
            row["post_id"] = str(row["post_id"])
            for key in self.post_metrics:
                row[key] = self._metric(row.get(key))
            out[row["post_id"]] = row
        return out

    def posts_recent(self, limit: int = 200) -> list[dict]:
        rows = sorted(self.load_posts().values(),
                      key=lambda r: r.get("created_at") or "", reverse=True)
        return rows[:limit]

    def posts_since(self, since_iso: str) -> list[dict]:
        return [r for r in self.posts_recent(10000) if (r.get("created_at") or "") >= since_iso]

    def upsert_posts(self, rows: list[dict], now: datetime) -> int:
        if not rows:
            return 0
        ts = iso_utc(now)
        added = 0
        with LOCK:
            posts = self.load_posts()
            known = set(posts)
            for row in rows:
                post_id = str(row.get("post_id") or "")
                if not post_id:
                    continue
                old = posts.get(post_id) or {}
                item = {key: row.get(key, "") for key in self.post_fields}
                item["first_seen_at"] = old.get("first_seen_at") or ts
                item["updated_at"] = ts
                for key in self.post_metrics:
                    if item.get(key) in (None, "") and old.get(key) is not None:
                        item[key] = old.get(key)
                    elif item.get(key) is None:
                        item[key] = ""
                if not item.get("created_at") and old.get("created_at"):
                    item["created_at"] = old["created_at"]
                if not item.get("text") and old.get("text"):
                    item["text"] = old["text"]
                if not item.get("title") and old.get("title"):
                    item["title"] = old["title"]
                posts[post_id] = item
                if post_id not in known:
                    known.add(post_id)
                    added += 1
            self._write(self.posts_path, self.post_fields, posts.values())
        return added

    # ---------- 快照 ----------
    def _month_path(self, dt: datetime) -> Path:
        return self.dir / f"snapshots-{dt.astimezone(timezone.utc):%Y-%m}.csv"

    def month_files(self) -> list[Path]:
        return sorted(self.dir.glob("snapshots-*.csv"))

    def add_snapshots(self, rows: list[dict], captured_at: datetime) -> int:
        if not rows:
            return 0
        slot = iso_utc(floor_slot(captured_at))
        path = self._month_path(captured_at)
        with LOCK:
            existing = {(r["post_id"], r["slot"]): r
                        for r in self._read(path, self.snap_fields)}
            for row in rows:
                post_id = str(row.get("post_id") or "")
                if not post_id:
                    continue
                item = {"platform": self.platform, "post_id": post_id, "slot": slot}
                for key in self.post_metrics:
                    value = row.get(key)
                    item[key] = "" if value is None else value
                existing[(post_id, slot)] = item
            self._write(path, self.snap_fields, existing.values())
        return len(rows)

    def snapshots_since(self, since_iso: str) -> list[dict]:
        start = datetime.fromisoformat(since_iso)
        now = datetime.now(timezone.utc)
        out = []
        cursor = start.astimezone(timezone.utc).replace(day=1, hour=0, minute=0,
                                                        second=0, microsecond=0)
        while cursor <= now:
            path = self._month_path(cursor)
            if path.exists():
                for row in self._read(path, self.snap_fields):
                    if row["slot"] >= since_iso:
                        row["slot_dt"] = datetime.fromisoformat(row["slot"])
                        for key in self.post_metrics:
                            row[key] = self._metric(row.get(key))
                        out.append(row)
            month = cursor.month + 1
            year = cursor.year + (1 if month > 12 else 0)
            cursor = cursor.replace(year=year, month=(month - 1) % 12 + 1)
        return out

    # ---------- 账号 / 运行记录 ----------
    def set_account(self, row: dict) -> None:
        with LOCK:
            item = {key: row.get(key, "") for key in self.account_fields}
            self._write(self.account_path, self.account_fields, [item])

    def get_account(self) -> dict:
        rows = self._read(self.account_path, self.account_fields)
        return rows[-1] if rows else {}

    def record_run(self, *, status: str, new_posts: int = 0, snapshots: int = 0,
                   note: str = "", error: str = "", verify: str = "",
                   started_at: datetime | None = None) -> None:
        with LOCK:
            rows = self._read(self.runs_path, list(RUN_FIELDS))
            rows.append({
                "platform": self.platform,
                "started_at": iso_utc(started_at or datetime.now(timezone.utc)),
                "status": status,
                "new_posts": new_posts,
                "snapshots": snapshots,
                "note": note,
                "error": error,
                "verify": verify,
            })
            self._write(self.runs_path, list(RUN_FIELDS), rows)

    def stats(self) -> dict:
        posts = self.load_posts()
        snapshots = sum(len(self._read(p, self.snap_fields)) for p in self.month_files())
        runs = self._read(self.runs_path, list(RUN_FIELDS))
        return {
            "posts": len(posts),
            "snapshots": snapshots,
            "runs": len(runs),
            "last_run": runs[-1] if runs else None,
        }
