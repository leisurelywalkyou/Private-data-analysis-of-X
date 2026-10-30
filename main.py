"""CLI 入口：采集、常驻定时、生成报告、查看状态。

用法：
  python main.py collect              单次采集
  python main.py daemon --interval 30 常驻，每半小时采集（默认值）
  python main.py report --days 30     生成 HTML 分析报告
  python main.py status               查看本地 CSV 数据量
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta

import analysis
import collector
import csvstore
import report
from config import get_tz, load_config
from x_api import XApiError, XClient


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def cmd_collect(cfg: dict) -> int:
    client = XClient(cfg["bearer_token"], cfg["user_access_token"], log=log)
    ds = csvstore.DataStore(cfg["data_dir"])
    res = collector.collect(cfg, client, ds)
    log(f"新增 {res['new']} 条，刷新 {res['refreshed']} 条，快照 {res['snapshots']} 条"
        f"（粉丝 {res['followers']}）")
    return 0


def cmd_daemon(cfg: dict, interval: int, align: bool) -> int:
    client = XClient(cfg["bearer_token"], cfg["user_access_token"], log=log)
    ds = csvstore.DataStore(cfg["data_dir"])
    log(f"常驻模式启动，间隔 {interval} 分钟，账号 @{cfg['username']}，Ctrl+C 退出")
    while True:
        try:
            res = collector.collect(cfg, client, ds)
            log(f"采集完成：新增 {res['new']}，快照 {res['snapshots']}")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log(f"采集失败：{e}")

        now = datetime.now()
        if align:
            minutes = (now.hour * 60 + now.minute) // interval * interval + interval
            nxt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)
            if nxt <= now:
                nxt += timedelta(minutes=interval)
        else:
            nxt = now + timedelta(minutes=interval)
        sleep_s = max(30, int((nxt - now).total_seconds()))
        log(f"下次采集：{nxt:%Y-%m-%d %H:%M}（{sleep_s}s 后）")
        try:
            time.sleep(sleep_s)
        except KeyboardInterrupt:
            log("已停止")
            return 0


def cmd_report(cfg: dict, days: int) -> int:
    ds = csvstore.DataStore(cfg["data_dir"])
    data = analysis.build(ds, get_tz(cfg), days=days, top_n=3)
    username = ds.get_meta("username") or cfg["username"] or "me"
    paths = report.write_report(data, username, cfg["report_dir"])
    analysis.print_summary(data)
    print(f"\n报告已生成：{paths['html']}\n最新副本：{paths['latest']}")
    return 0


def cmd_status(cfg: dict) -> int:
    print(f"账号：@{cfg['username'] or '(未配置)'} | 时区：{cfg['timezone']} | CSV 目录：{cfg['data_dir']}")
    print(f"凭据：bearer={'已配置' if cfg['bearer_token'] else '缺失'} "
          f"| user_token={'已配置' if cfg['user_access_token'] else '未配置'}")
    ds = csvstore.DataStore(cfg["data_dir"])
    s = ds.stats()
    print(f"本地数据：帖子 {s['posts']}（启用 {s['enabled']}） | 快照 {s['snapshots']} | 采集 {s['runs']} 轮")
    if s["last_run"]:
        print(f"上次采集：{s['last_run']['started_at']} {s['last_run'].get('note', '')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="X 账号长期数据采集与分析")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("collect", help="执行一次采集")
    p_daemon = sub.add_parser("daemon", help="常驻定时采集")
    p_daemon.add_argument("--interval", type=int, default=30, help="采集间隔（分钟，默认 30）")
    p_daemon.add_argument("--align", action="store_true", help="对齐到整间隔")
    p_report = sub.add_parser("report", help="生成报告")
    p_report.add_argument("--days", type=int, default=30, help="统计天数（默认 30）")
    sub.add_parser("status", help="查看本地状态")

    args = parser.parse_args()
    cfg = load_config(args.config)

    if args.cmd in ("collect", "daemon"):
        if not cfg["username"]:
            print("请先在 config.json 填写 username（可带或不带 @）", file=sys.stderr)
            return 2
        if not (cfg["bearer_token"] or cfg["user_access_token"]):
            print("请先在 config.json 填写 bearer_token，或设置 X_BEARER_TOKEN", file=sys.stderr)
            return 2

    try:
        if args.cmd == "collect":
            return cmd_collect(cfg)
        if args.cmd == "daemon":
            return cmd_daemon(cfg, args.interval, args.align)
        if args.cmd == "report":
            return cmd_report(cfg, args.days)
        if args.cmd == "status":
            return cmd_status(cfg)
        parser.print_help()
        return 0
    except KeyboardInterrupt:
        log("已停止")
        return 0
    except XApiError as e:
        print(f"X API 错误：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
