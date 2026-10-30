"""CSV 数据仓库：代码目录下的 data/ 文件夹，无数据库。

- data/posts.csv          帖子当前值 + 是否采集（每次采集合并写回）
- data/snapshots-YYYY-MM.csv  30 分钟快照，按月分文件（长期积累）
- data/runs.csv           采集轮次
- data/meta.json          账号等杂项
"""

from __future__ import annotations

import csv
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import METRICS

METRIC_COLS = tuple(METRICS)
POST_FIELDS = ["tweet_id", "created_at", "text", *METRIC_COLS,
               "enabled", "added_at", "updated_at"]
SNAP_FIELDS = ["tweet_id", "slot", *METRIC_COLS]
RUN_FIELDS = ["started_at", "new_posts", "snapshots", "note"]
SLOT_MINUTES = 30

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


class DataStore:
    def __init__(self, data_dir: str = "data"):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.posts_path = self.dir / "posts.csv"
        self.runs_path = self.dir / "runs.csv"
        self.meta_path = self.dir / "meta.json"

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

    # ---------- 帖子 ----------
    def _posts(self) -> dict[str, dict]:
        out = {}
        for r in self._read(self.posts_path, POST_FIELDS):
            for c in METRIC_COLS:
                r[c] = int(r[c] or 0)
            r["enabled"] = 1 if str(r["enabled"]).strip().lower() in ("1", "true", "yes", "") else 0
            out[r["tweet_id"]] = r
        return out

    def posts_recent(self, limit: int = 200) -> list[dict]:
        rows = sorted(self._posts().values(), key=lambda r: r["created_at"], reverse=True)
        return rows[:limit]

    def upsert_posts(self, rows: list[dict], now: datetime) -> int:
        if not rows:
            return 0
        ts = iso_utc(now)
        with LOCK:
            posts = self._posts()
            for r in rows:
                tid = r["tweet_id"]
                old = posts.get(tid)
                item = {
                    "tweet_id": tid,
                    "created_at": iso_utc(r["created_at"]),
                    "text": r.get("text") or (old["text"] if old else ""),
                    "enabled": old["enabled"] if old else 1,
                    "added_at": (old["added_at"] if old and old["added_at"] else ts),
                    "updated_at": ts,
                }
                for c in METRIC_COLS:
                    item[c] = int(r.get(c) or 0)
                posts[tid] = item
            self._write(self.posts_path, POST_FIELDS, posts.values())
        return len(rows)

    def set_tracked(self, tweet_id: str, enabled: bool) -> None:
        with LOCK:
            posts = self._posts()
            row = posts.get(tweet_id)
            if not row:
                return
            row["enabled"] = 1 if enabled else 0
            row["updated_at"] = iso_utc(datetime.now(timezone.utc))
            self._write(self.posts_path, POST_FIELDS, posts.values())

    def max_tweet_id(self) -> str | None:
        ids = [r["tweet_id"] for r in self._posts().values() if r["tweet_id"].isdigit()]
        return max(ids, key=int) if ids else None

    def enabled_ids(self, days: int, limit: int) -> list[str]:
        since = iso_utc(datetime.now(timezone.utc) - timedelta(days=days))
        rows = [r for r in self._posts().values() if r["enabled"] and r["created_at"] >= since]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [r["tweet_id"] for r in rows[:limit]]

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
            existing = {(r["tweet_id"], r["slot"]): r for r in self._read(path, SNAP_FIELDS)}
            for r in rows:
                item = {"tweet_id": r["tweet_id"], "slot": slot}
                for c in METRIC_COLS:
                    item[c] = int(r.get(c) or 0)
                existing[(r["tweet_id"], slot)] = item
            self._write(path, SNAP_FIELDS, existing.values())
        return len(rows)

    def snapshots_since(self, since_iso: str) -> list[dict]:
        out = []
        start = datetime.fromisoformat(since_iso)
        now = datetime.now(timezone.utc)
        cursor = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while cursor <= now:
            path = self._month_path(cursor)
            if path.exists():
                for r in self._read(path, SNAP_FIELDS):
                    if r["slot"] >= since_iso:
                        r["slot_dt"] = datetime.fromisoformat(r["slot"])
                        for c in METRIC_COLS:
                            r[c] = int(r[c] or 0)
                        out.append(r)
            month = cursor.month + 1
            year = cursor.year + (1 if month > 12 else 0)
            cursor = cursor.replace(year=year, month=(month - 1) % 12 + 1)
        return out

    # ---------- 运行记录 / 杂项 ----------
    def record_run(self, new_posts: int, snapshots: int, note: str = "",
                   started_at: datetime | None = None) -> None:
        with LOCK:
            rows = self._read(self.runs_path, RUN_FIELDS)
            rows.append({
                "started_at": iso_utc(started_at or datetime.now(timezone.utc)),
                "new_posts": new_posts,
                "snapshots": snapshots,
                "note": note,
            })
            self._write(self.runs_path, RUN_FIELDS, rows)

    def get_meta(self, key: str) -> str | None:
        if not self.meta_path.exists():
            return None
        data = json.loads(self.meta_path.read_text(encoding="utf-8"))
        value = data.get(key)
        return str(value) if value is not None else None

    def set_meta(self, key: str, value: str) -> None:
        with LOCK:
            data = {}
            if self.meta_path.exists():
                data = json.loads(self.meta_path.read_text(encoding="utf-8"))
            data[key] = value
            self.meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")

    def stats(self) -> dict:
        posts = self._posts()
        snaps = sum(len(self._read(p, SNAP_FIELDS)) for p in self.month_files())
        runs = self._read(self.runs_path, RUN_FIELDS)
        return {
            "posts": len(posts),
            "enabled": sum(1 for r in posts.values() if r["enabled"]),
            "snapshots": snaps,
            "runs": len(runs),
            "last_run": runs[-1] if runs else None,
        }
