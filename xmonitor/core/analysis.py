"""长期数据分析：KPI、星期×小时热力图、时间曲线（跨平台通用）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .store import SLOT_MINUTES, floor_slot, iso_utc

ENGAGEMENT_COLS = ("likes", "comments", "shares", "saves")
WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def engagement(row: dict) -> int:
    return sum(int(row.get(c) or 0) for c in ENGAGEMENT_COLS)


def views(row: dict) -> int:
    return int(row.get("views") or 0)


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def build(store, tz, days: int = 30, top_n: int = 3) -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    start_iso = iso_utc(start)

    posts = [p for p in store.posts_recent(10000)
             if (p.get("created_at") or "") >= start_iso]
    ids = {p["post_id"] for p in posts}

    snaps = [s for s in store.snapshots_since(iso_utc(floor_slot(start)))
             if s["post_id"] in ids]

    series: dict[str, list[dict]] = defaultdict(list)
    for snap in snaps:
        series[snap["post_id"]].append(snap)
    for rows in series.values():
        rows.sort(key=lambda r: r["slot"])

    heat_eng = [[0.0] * 24 for _ in range(7)]
    heat_cov = [[0] * 24 for _ in range(7)]
    hourly_total = [0.0] * 24
    daily_eng: dict[str, float] = defaultdict(float)
    daily_imp: dict[str, float] = defaultdict(float)
    active_days: set[str] = set()

    for snap in snaps:
        local = snap["slot_dt"].astimezone(tz)
        heat_cov[local.weekday()][local.hour] += 1
        active_days.add(local.strftime("%Y-%m-%d"))

    for rows in series.values():
        for prev, cur in zip(rows, rows[1:]):
            prev_dt, cur_dt = parse_iso(prev["slot"]), parse_iso(cur["slot"])
            gaps = int((cur_dt - prev_dt).total_seconds() // (SLOT_MINUTES * 60))
            if gaps <= 0:
                continue
            d_eng = max(0, engagement(cur) - engagement(prev))
            d_imp = max(0, views(cur) - views(prev))
            for k in range(1, gaps + 1):
                slot_dt = prev_dt + timedelta(minutes=SLOT_MINUTES * k)
                local = slot_dt.astimezone(tz)
                part_eng, part_imp = d_eng / gaps, d_imp / gaps
                heat_eng[local.weekday()][local.hour] += part_eng
                hourly_total[local.hour] += part_eng
                daily_eng[local.strftime("%Y-%m-%d")] += part_eng
                daily_imp[local.strftime("%Y-%m-%d")] += part_imp

    day_count = max((now.astimezone(tz) - start.astimezone(tz)).days, 1)
    date_labels = [(start.astimezone(tz) + timedelta(days=i)).strftime("%m-%d")
                   for i in range(day_count + 1)]
    date_keys = [(start.astimezone(tz) + timedelta(days=i)).strftime("%Y-%m-%d")
                 for i in range(day_count + 1)]
    daily = {
        "labels": date_labels,
        "engagement": [round(daily_eng.get(k, 0)) for k in date_keys],
        "impressions": [round(daily_imp.get(k, 0)) for k in date_keys],
    }

    days_seen = len(active_days) or 1
    hourly = {
        "labels": [f"{h:02d}" for h in range(24)],
        "avg_engagement": [round(hourly_total[h] / days_seen, 1) for h in range(24)],
    }

    ranked = sorted(posts, key=engagement, reverse=True)[:top_n]
    growth = []
    for post in ranked:
        points = [(s["slot_dt"].astimezone(tz), engagement(s))
                  for s in series.get(post["post_id"], [])]
        if len(points) >= 2:
            growth.append({
                "post_id": post["post_id"],
                "label": (post.get("title") or post.get("text") or post["post_id"])
                .replace("\n", " ")[:22],
                "points": points,
            })

    total_eng = sum(engagement(p) for p in posts)
    total_views = sum(views(p) for p in posts)
    peak = max((v, w, h) for w in range(7) for h in range(24)
               for v in [heat_eng[w][h]]) if snaps else (0, 0, 0)

    return {
        "generated_at": now.astimezone(tz),
        "days": days,
        "range_start": start.astimezone(tz),
        "range_end": now.astimezone(tz),
        "overview": {
            "posts": len(posts),
            "total_engagement": total_eng,
            "total_impressions": total_views,
            "avg_engagement": round(total_eng / len(posts), 1) if posts else 0,
            "runs": store.stats()["runs"],
            "slots": len({s["slot"] for s in snaps}),
            "days_seen": len(active_days),
        },
        "heatmap": heat_eng,
        "heatmap_coverage": heat_cov,
        "weekday_labels": WEEKDAYS,
        "peak": {"weekday": WEEKDAYS[peak[1]] if snaps else "—",
                 "hour": peak[2], "value": round(peak[0])},
        "daily": daily,
        "hourly": hourly,
        "growth": growth,
        "posts": posts,
    }


def _series(snaps: list[dict]) -> dict[str, list[dict]]:
    series: dict[str, list[dict]] = defaultdict(list)
    for snap in snaps:
        series[snap["post_id"]].append(snap)
    for rows in series.values():
        rows.sort(key=lambda r: r["slot_dt"])
    return series


def deltas(store, tz) -> dict:
    now = datetime.now(timezone.utc)
    snaps = store.snapshots_since(iso_utc(now - timedelta(days=61)))
    series = _series(snaps)

    beat = {"available": False, "engagement": 0, "impressions": 0, "label": "—"}
    slots = sorted({s["slot"] for s in snaps})
    if len(slots) >= 2:
        last, prev = slots[-1], slots[-2]
        current = {s["post_id"]: s for s in snaps if s["slot"] == last}
        old = {s["post_id"]: s for s in snaps if s["slot"] == prev}
        common = set(current) & set(old)
        if common:
            beat = {
                "available": True,
                "engagement": sum(engagement(current[i]) - engagement(old[i]) for i in common),
                "impressions": sum(views(current[i]) - views(old[i]) for i in common),
                "label": parse_iso(last).astimezone(tz).strftime("%H:%M"),
            }

    def period_gain(start: datetime, end: datetime) -> tuple[float, float, int]:
        eng = imp = 0.0
        pairs = 0
        for rows in series.values():
            for a, b in zip(rows, rows[1:]):
                if a["slot_dt"] >= start and b["slot_dt"] <= end:
                    eng += max(0, engagement(b) - engagement(a))
                    imp += max(0, views(b) - views(a))
                    pairs += 1
        return eng, imp, pairs

    cur_gain, cur_imp, cur_pairs = period_gain(now - timedelta(days=30), now)
    prev_gain, prev_imp, prev_pairs = period_gain(now - timedelta(days=60), now - timedelta(days=30))
    mom = {
        "available": prev_pairs > 0,
        "current": round(cur_gain),
        "previous": round(prev_gain),
        "delta": round(cur_gain - prev_gain),
        "imp_current": round(cur_imp),
        "imp_previous": round(prev_imp),
        "pct": round((cur_gain - prev_gain) / prev_gain * 100, 1) if prev_gain > 0 else None,
    }
    return {"beat": beat, "mom": mom}


def print_summary(data: dict) -> None:
    ov = data["overview"]
    print(f"区间：{data['range_start']:%Y-%m-%d} ~ {data['range_end']:%Y-%m-%d}（{data['days']} 天）")
    print(f"帖子 {ov['posts']} 条 | 互动 {ov['total_engagement']:,} | 浏览 {ov['total_impressions']:,}"
          f" | 均互动 {ov['avg_engagement']} | 采集 {ov['runs']} 轮 / 覆盖 {ov['days_seen']} 天")
    if ov["posts"]:
        peak = data["peak"]
        print(f"热力图峰值时段：{peak['weekday']} {peak['hour']:02d}:00（{peak['value']} 次互动增益）")
    print("每日互动增益：" + " ".join(
        f"{label}:{value}" for label, value in
        zip(data["daily"]["labels"], data["daily"]["engagement"]) if value))
