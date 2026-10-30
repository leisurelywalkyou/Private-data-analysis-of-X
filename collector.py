"""采集核心逻辑：被 CLI（main.py）和小界面（app.py）共用。"""

from __future__ import annotations

from datetime import datetime, timezone

from x_api import XClient


def collect(cfg: dict, client: XClient, ds) -> dict:
    """抓取新帖 -> 只刷新被勾选帖子的指标 -> 写入 30 分钟快照（CSV）。"""
    started = datetime.now(timezone.utc)

    user = client.get_user(cfg["username"])
    ds.set_meta("user_id", user["id"])
    ds.set_meta("username", user["username"])
    ds.set_meta("followers", str(user["followers"]))

    many = client.get_user_tweets(
        user["id"],
        since_id=ds.max_tweet_id(),
        exclude_retweets=bool(cfg["exclude_retweets"]),
        exclude_replies=bool(cfg["exclude_replies"]),
    )
    if many:
        ds.upsert_posts(many, started)

    ids = ds.enabled_ids(int(cfg["track_recent_days"]), int(cfg["max_snapshot_tweets"]))
    refreshed = client.get_tweets_metrics(ids) if ids else []
    if refreshed:
        ds.upsert_posts(refreshed, started)
    snaps = ds.add_snapshots(refreshed, started)

    ds.record_run(len(many), snaps,
                  note=f"@{user['username']} enabled={len(ids)} followers={user['followers']}",
                  started_at=started)
    return {
        "new": len(many),
        "refreshed": len(refreshed),
        "snapshots": snaps,
        "enabled": len(ids),
        "followers": user["followers"],
        "username": user["username"],
        "at": started,
    }
