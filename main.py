"""CLI 入口：多平台采集、常驻调度、报告与状态。

用法：
  python main.py platforms            查看已安装平台
  python main.py collect --platform x 单次采集
  python main.py daemon --interval 30 常驻，全部启用平台
  python main.py report --platform x  生成 HTML 报告
  python main.py status               查看各平台本地数据量
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from xmonitor.core import analysis, report
from xmonitor.core.collector import collect_platform, make_store
from xmonitor.core.config import data_dir, get_tz, load_config
from xmonitor.core.scheduler import MultiCollectScheduler
from xmonitor.platforms import available, enabled_ids, load


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def cmd_platforms(cfg: dict) -> int:
    blocks = cfg.get("platforms") or {}
    for platform in available():
        cls = load(platform)
        block = blocks.get(platform) or {}
        state = "启用" if block.get("enabled") else "停用"
        account = block.get("account_name") or "未配置"
        print(f"{platform:<12} {cls.label:<10} {state}  账号={account}  "
              f"指标={','.join(cls.post_metrics)}")
    return 0


def cmd_collect(cfg: dict, platform: str) -> int:
    if platform not in available():
        print(f"未知平台：{platform}", file=sys.stderr)
        return 2
    try:
        res = collect_platform(cfg, platform, log=log)
    except Exception as e:
        log(f"{platform} 采集失败：{type(e).__name__}: {e}")
        return 1
    coverage = res["coverage"]
    coverage_text = "—" if coverage is None else f"{coverage}%"
    log(f"{platform}：新增 {res['new']}，快照 {res['snapshots']}，"
        f"字段覆盖 {coverage_text}，校验 {res['verification']}")
    return 0


def cmd_daemon(cfg: dict, interval: int) -> int:
    scheduler = MultiCollectScheduler(cfg)
    scheduler.set_interval(interval)
    log(f"常驻模式启动，间隔 {scheduler.interval} 分钟，平台：{enabled_ids(cfg) or '无'}")
    scheduler.start()
    try:
        while True:
            for kind, payload in scheduler.poll():
                if kind == "platform_done":
                    log(f"{payload['platform']} 完成：新增 {payload['new']}，"
                        f"快照 {payload['snapshots']}")
                elif kind == "platform_error":
                    log(f"{payload['platform']} 失败：{payload['message']}")
                elif kind == "round_done":
                    log(f"本轮完成：成功 {payload['ok']}，失败 {payload['failed']}，"
                        f"跳过 {payload['skipped']}")
                elif kind == "need_config":
                    log("没有已启用的平台，请先在设置中配置")
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("已停止")
        scheduler.stop()
        return 0


def cmd_report(cfg: dict, platform: str, days: int) -> int:
    if platform not in available():
        print(f"未知平台：{platform}", file=sys.stderr)
        return 2
    try:
        result = report.generate(cfg, platform, get_tz(cfg), days=days)
    except Exception as e:
        log(f"{platform} 报告生成失败：{type(e).__name__}: {e}")
        return 1
    analysis.print_summary(result["data"])
    paths = result["paths"]
    print(f"\n报告已生成：{paths['html']}\n最新副本：{paths['latest']}")
    return 0


def cmd_status(cfg: dict) -> int:
    print(f"时区：{cfg['timezone']} | 数据目录：{data_dir(cfg)}")
    if not available():
        print("未安装任何平台适配器")
    for platform in available():
        block = (cfg.get("platforms") or {}).get(platform) or {}
        state = "启用" if block.get("enabled") else "停用"
        store = make_store(cfg, platform)
        stats = store.stats()
        account = store.get_account()
        name = account.get("account_name") or block.get("account_name") or "未配置"
        last = stats.get("last_run") or {}
        print(f"{platform:<12} {state}  @{name:<16} 帖子 {stats['posts']} | "
              f"快照 {stats['snapshots']} | 采集 {stats['runs']} 轮 | "
              f"上次 {last.get('started_at', '—')} {last.get('status', '')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="多平台账号数据采集与分析")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("platforms", help="列出平台适配器")
    p_collect = sub.add_parser("collect", help="执行一次采集")
    p_collect.add_argument("--platform", default="x", help="平台标识，默认 x")
    p_daemon = sub.add_parser("daemon", help="常驻定时采集全部启用平台")
    p_daemon.add_argument("--interval", type=int, default=30, help="采集间隔（分钟）")
    p_report = sub.add_parser("report", help="生成报告")
    p_report.add_argument("--platform", default="x", help="平台标识，默认 x")
    p_report.add_argument("--days", type=int, default=30, help="统计天数")
    sub.add_parser("status", help="查看各平台本地状态")

    args = parser.parse_args()
    cfg = load_config(args.config)

    try:
        if args.cmd == "platforms":
            return cmd_platforms(cfg)
        if args.cmd == "collect":
            return cmd_collect(cfg, args.platform)
        if args.cmd == "daemon":
            return cmd_daemon(cfg, args.interval)
        if args.cmd == "report":
            return cmd_report(cfg, args.platform, args.days)
        if args.cmd == "status":
            return cmd_status(cfg)
        parser.print_help()
        return 0
    except KeyboardInterrupt:
        log("已停止")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
