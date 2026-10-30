"""长期数据分析：KPI、星期×小时热力图、时间曲线。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from csvstore import SLOT_MINUTES, floor_slot, iso_utc

ENGAGEMENT_COLS = ("likes", "retweets", "replies", "quotes", "bookmarks")
WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def engagement(row: dict) -> int:
    return sum(int(row.get(c) or 0) for c in ENGAGEMENT_COLS)


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def build(ds, tz, days: int = 30, top_n: int = 3) -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    start_iso = iso_utc(start)

    posts = [p for p in ds.posts_recent(10000)
             if p["enabled"] and p["created_at"] >= start_iso]
    ids = {p["tweet_id"] for p in posts}

    snaps = [s for s in ds.snapshots_since(iso_utc(floor_slot(start)))
             if s["tweet_id"] in ids]

    series: dict[str, list[dict]] = defaultdict(list)
    for s in snaps:
        series[s["tweet_id"]].append(s)
    for rows in series.values():
        rows.sort(key=lambda r: r["slot"])

    # ---- 快照差分：30 分钟槽均摊，按本地小时/星期聚合 ----
    heat_eng = [[0.0] * 24 for _ in range(7)]
    heat_cov = [[0] * 24 for _ in range(7)]
    hourly_total = [0.0] * 24
    daily_eng: dict[str, float] = defaultdict(float)
    daily_imp: dict[str, float] = defaultdict(float)
    active_days: set[str] = set()

    for s in snaps:
        local = s["slot_dt"].astimezone(tz)
        heat_cov[local.weekday()][local.hour] += 1
        active_days.add(local.strftime("%Y-%m-%d"))

    for rows in series.values():
        for prev, cur in zip(rows, rows[1:]):
            prev_dt, cur_dt = parse_iso(prev["slot"]), parse_iso(cur["slot"])
            gaps = int((cur_dt - prev_dt).total_seconds() // (SLOT_MINUTES * 60))
            if gaps <= 0:
                continue
            d_eng = max(0, engagement(cur) - engagement(prev))
            d_imp = max(0, cur["impressions"] - prev["impressions"])
            for k in range(1, gaps + 1):
                slot_dt = prev_dt + timedelta(minutes=SLOT_MINUTES * k)
                local = slot_dt.astimezone(tz)
                part_eng, part_imp = d_eng / gaps, d_imp / gaps
                heat_eng[local.weekday()][local.hour] += part_eng
                hourly_total[local.hour] += part_eng
                daily_eng[local.strftime("%Y-%m-%d")] += part_eng
                daily_imp[local.strftime("%Y-%m-%d")] += part_imp

    # ---- 曲线数据 ----
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

    # ---- Top N 累计互动曲线 ----
    ranked = sorted(posts, key=engagement, reverse=True)[:top_n]
    growth = []
    for p in ranked:
        pts = [(s["slot_dt"].astimezone(tz), engagement(s)) for s in series.get(p["tweet_id"], [])]
        if len(pts) >= 2:
            growth.append({
                "tweet_id": p["tweet_id"],
                "label": (p["text"] or p["tweet_id"]).replace("\n", " ")[:22],
                "points": pts,
            })

    total_eng = sum(engagement(p) for p in posts)
    total_imp = sum(p["impressions"] for p in posts)
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
            "total_impressions": total_imp,
            "avg_engagement": round(total_eng / len(posts), 1) if posts else 0,
            "runs": ds.stats()["runs"],
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


def _engagement_series(snaps: list[dict]) -> dict[str, list[dict]]:
    series: dict[str, list[dict]] = defaultdict(list)
    for s in snaps:
        series[s["tweet_id"]].append(s)
    for rows in series.values():
        rows.sort(key=lambda r: r["slot_dt"])
    return series


def deltas(ds, tz) -> dict:
    """界面上展示的两组变化：
    - beat：最近两个快照槽的互动/曝光增量
    - mom：最近 30 天增益 vs 前 30 天增益（同比月份周期）
    均为正数标红、负数标绿由界面负责。
    """
    now = datetime.now(timezone.utc)
    snaps = ds.snapshots_since(iso_utc(now - timedelta(days=61)))
    series = _engagement_series(snaps)

    beat = {"available": False, "engagement": 0, "impressions": 0, "label": "—"}
    slots = sorted({s["slot"] for s in snaps})
    if len(slots) >= 2:
        last, prev = slots[-1], slots[-2]
        cur = {s["tweet_id"]: s for s in snaps if s["slot"] == last}
        old = {s["tweet_id"]: s for s in snaps if s["slot"] == prev}
        common = set(cur) & set(old)
        if common:
            beat = {
                "available": True,
                "engagement": sum(engagement(cur[i]) - engagement(old[i]) for i in common),
                "impressions": sum(cur[i]["impressions"] - old[i]["impressions"] for i in common),
                "label": parse_iso(last).astimezone(tz).strftime("%H:%M"),
            }

    def period_gain(start: datetime, end: datetime) -> tuple[float, float, int]:
        eng = imp = 0.0
        pairs = 0
        for rows in series.values():
            for a, b in zip(rows, rows[1:]):
                if a["slot_dt"] >= start and b["slot_dt"] <= end:
                    eng += max(0, engagement(b) - engagement(a))
                    imp += max(0, b["impressions"] - a["impressions"])
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
    print(f"帖子 {ov['posts']} 条 | 互动 {ov['total_engagement']:,} | 曝光 {ov['total_impressions']:,}"
          f" | 均互动 {ov['avg_engagement']} | 采集 {ov['runs']} 轮 / 覆盖 {ov['days_seen']} 天")
    if ov["posts"]:
        p = data["peak"]
        print(f"热力图峰值时段：{p['weekday']} {p['hour']:02d}:00（{p['value']} 次互动增益）")
    print("每日互动增益：" + " ".join(
        f"{lab}:{val}" for lab, val in zip(data["daily"]["labels"], data["daily"]["engagement"])
        if val))
