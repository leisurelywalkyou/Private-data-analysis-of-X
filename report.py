"""HTML 报告：只保留 KPI、热力图、分析曲线。"""

from __future__ import annotations

import html
from pathlib import Path

CSS = """
:root{--bg:#0b0f14;--panel:#131a23;--line:#233040;--text:#e6edf3;--muted:#8b9bb0;--accent:#1d9bf0;--accent2:#00ba7c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:30px 20px 56px}
h1{font-size:21px;margin:0 0 4px}
h2{font-size:14px;margin:0 0 16px;font-weight:600}
h2 span{color:var(--muted);font-weight:400;font-size:12px;margin-left:8px}
.sub{color:var(--muted);font-size:12px;margin-bottom:22px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .v{font-size:22px;font-weight:700;letter-spacing:-.02em}
.kpi .l{color:var(--muted);font-size:12px;margin-top:2px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}
.heat{display:grid;grid-template-columns:54px repeat(24,1fr);gap:2px;font-size:10px}
.heat .lbl{color:var(--muted);display:flex;align-items:center;justify-content:center}
.cell{height:24px;border-radius:3px;background:#121a24;display:flex;align-items:center;justify-content:center;color:#c9d6e4}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:11px;color:var(--muted);margin-bottom:6px}
.legend i{display:inline-block;width:16px;height:3px;border-radius:2px;margin-right:6px;vertical-align:2px}
.chart svg{width:100%;height:auto;display:block}
.scale{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:4px}
.note{color:var(--muted);font-size:12px;line-height:1.7;margin-top:12px}
.empty{color:var(--muted);font-size:12px;padding:12px 0}
"""

COLORS = ("#1d9bf0", "#00ba7c", "#f5a623")


def fmt(v: float) -> str:
    if isinstance(v, float):
        return f"{v:,.1f}" if abs(v) < 100000 else f"{v:,.0f}"
    return f"{v:,}"


def axis_num(v: float) -> str:
    if v >= 100000000:
        return f"{v / 100000000:.1f}亿"
    if v >= 10000:
        return f"{v / 10000:.1f}万"
    if v >= 1000:
        return f"{v / 1000:.1f}k"
    return f"{v:.0f}" if v >= 10 else f"{v:.1f}"


def heatmap(matrix: list[list[float]], cov: list[list[int]], labels: list[str]) -> str:
    mx = max((max(row) for row in matrix), default=0) or 1
    cells = []
    for w, row in enumerate(matrix):
        cells.append(f'<div class="lbl">{labels[w]}</div>')
        for h, v in enumerate(row):
            if cov[w][h] == 0:
                cells.append('<div class="cell" style="color:#3b4a5c" title="无采集">·</div>')
            else:
                alpha = 0.12 + 0.88 * (v / mx)
                cells.append(
                    f'<div class="cell" style="background:rgba(29,155,240,{alpha:.2f});'
                    f'color:{"#06121c" if v / mx > .45 else "#c9d6e4"}" '
                    f'title="{labels[w]} {h:02d}:00 互动增益 {fmt(v)}">{round(v)}</div>'
                )
    head = ['<div class="lbl"></div>'] + [f'<div class="lbl">{h}</div>' for h in range(24)]
    return f'<div class="heat">{"".join(head)}{"".join(cells)}</div>'


def line_chart(labels: list[str], series: list[dict], height: int = 170) -> str:
    n = max(len(labels), 2)
    mx = max([max(s["values"], default=0) for s in series] + [1])
    W, H, L, R, T, B = 960, height, 46, 12, 14, 28
    pw, ph = W - L - R, H - T - B

    def x(i: int) -> float:
        return L + pw * (i / (n - 1))

    def y(v: float) -> float:
        return T + ph - ph * (v / mx)

    grid = []
    for k in range(4):
        gv = mx * k / 3
        gy = y(gv)
        grid.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{W - R}" y2="{gy:.1f}" '
                    f'stroke="#233040" stroke-width="1"/>')
        grid.append(f'<text x="{L - 8}" y="{gy + 4:.1f}" fill="#8b9bb0" font-size="10" '
                    f'text-anchor="end">{axis_num(gv)}</text>')

    step = max(1, n // 6)
    ticks = sorted(set(list(range(0, n, step)) + [n - 1]))
    xaxis = "".join(
        f'<text x="{x(i):.1f}" y="{H - 8}" fill="#8b9bb0" font-size="10" '
        f'text-anchor="middle">{html.escape(labels[i])}</text>' for i in ticks
    )

    paths = []
    for s in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(s["values"]))
        paths.append(f'<polyline fill="none" stroke="{s["color"]}" stroke-width="2.2" '
                     f'stroke-linejoin="round" points="{pts}"/>')
        paths.append("".join(
            f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="2.4" fill="{s["color"]}"/>'
            for i, v in enumerate(s["values"]) if v
        ))

    legend = "".join(f'<span><i style="background:{s["color"]}"></i>{html.escape(s["name"])}</span>'
                     for s in series)
    return (f'<div class="legend">{legend}</div>'
            f'<div class="chart"><svg viewBox="0 0 {W} {H}" preserveAspectRatio="none">'
            f'{"".join(grid)}{xaxis}{"".join(paths)}</svg></div>')


def growth_chart(items: list[dict], height: int = 190) -> str:
    all_ts = [p[0] for it in items for p in it["points"]]
    if not all_ts:
        return ""
    t0, t1 = min(all_ts), max(all_ts)
    span = max((t1 - t0).total_seconds(), 1)
    mx = max([max(p[1] for p in it["points"]) for it in items] + [1])
    W, H, L, R, T, B = 960, height, 46, 12, 14, 28
    pw, ph = W - L - R, H - T - B

    def y(v: float) -> float:
        return T + ph - ph * (v / mx)

    grid = []
    for k in range(4):
        gv = mx * k / 3
        gy = y(gv)
        grid.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{W - R}" y2="{gy:.1f}" '
                    f'stroke="#233040" stroke-width="1"/>')
        grid.append(f'<text x="{L - 8}" y="{gy + 4:.1f}" fill="#8b9bb0" font-size="10" '
                    f'text-anchor="end">{axis_num(gv)}</text>')

    paths = []
    for idx, it in enumerate(items):
        color = COLORS[idx % len(COLORS)]
        pts = " ".join(
            f"{L + pw * ((t - t0).total_seconds() / span):.1f},{y(v):.1f}"
            for t, v in it["points"]
        )
        paths.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.2" '
                     f'stroke-linejoin="round" points="{pts}"/>')
        paths.append(f'<circle cx="{L + pw * ((it["points"][-1][0] - t0).total_seconds() / span):.1f}" '
                     f'cy="{y(it["points"][-1][1]):.1f}" r="3" fill="{color}"/>')

    legend = "".join(
        f'<span><i style="background:{COLORS[i % len(COLORS)]}"></i>{html.escape(it["label"])}</span>'
        for i, it in enumerate(items)
    )
    return (f'<div class="legend">{legend}</div>'
            f'<div class="chart"><svg viewBox="0 0 {W} {H}" preserveAspectRatio="none">'
            f'{"".join(grid)}{"".join(paths)}</svg>'
            f'<div class="scale"><span>{html.escape(t0.strftime("%m-%d %H:%M"))}</span>'
            f'<span>{html.escape(t1.strftime("%m-%d %H:%M"))}</span></div></div>')


def build_html(data: dict, username: str) -> str:
    ov = data["overview"]

    def kpi(v: str, label: str) -> str:
        return f'<div class="kpi"><div class="v">{v}</div><div class="l">{label}</div></div>'

    kpis = "".join([
        kpi(fmt(ov["posts"]), "追踪帖子"),
        kpi(fmt(ov["total_engagement"]), "总互动"),
        kpi(fmt(ov["total_impressions"]), "总曝光"),
        kpi(fmt(ov["avg_engagement"]), "单条平均互动"),
        kpi(f"{ov['days_seen']} 天", f"有效采集 / {ov['runs']} 轮"),
    ])

    heat = heatmap(data["heatmap"], data["heatmap_coverage"], data["weekday_labels"])

    daily_eng = line_chart(data["daily"]["labels"],
                           [{"name": "互动增益", "values": data["daily"]["engagement"],
                             "color": COLORS[0]}])
    daily_imp = line_chart(data["daily"]["labels"],
                           [{"name": "曝光增益", "values": data["daily"]["impressions"],
                             "color": COLORS[1]}])
    hourly = line_chart(data["hourly"]["labels"],
                        [{"name": "平均互动增益/天", "values": data["hourly"]["avg_engagement"],
                          "color": COLORS[0]}])
    growth = growth_chart(data["growth"]) or '<div class="empty">快照不足，继续积累后显示单帖增长曲线。</div>'

    peak = data["peak"]
    peak_txt = (f"热力图峰值：{peak['weekday']} {peak['hour']:02d}:00，"
                f"约 {peak['value']} 次互动增益") if ov["posts"] else "暂无数据"

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>@{username} 长期数据分析</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>@{username} · 长期数据分析</h1>
<div class="sub">区间 {data['range_start']:%Y-%m-%d} ~ {data['range_end']:%Y-%m-%d}
（{data['days']} 天） · 生成于 {data['generated_at']:%Y-%m-%d %H:%M} · 数据来源：本地 CSV</div>
<div class="kpis">{kpis}</div>

<div class="card"><h2>星期 × 小时互动热力图 <span>按 30 分钟快照差分，归集到本地时段</span></h2>
{heat}<div class="note">{peak_txt}。空白格为未采集时段，长期运行后覆盖会更完整。</div></div>

<div class="card"><h2>每日互动增益曲线</h2>{daily_eng}</div>
<div class="card"><h2>每日曝光增益曲线</h2>{daily_imp}</div>
<div class="card"><h2>每小时平均互动增益 <span>按有采集的天数取平均</span></h2>{hourly}</div>
<div class="card"><h2>Top 3 帖子累计互动曲线</h2>{growth}</div>

<div class="note">数据保存在程序目录下的 data/ 文件夹（posts.csv、snapshots-年月.csv、runs.csv），
每轮采集会合并更新；分析结果基于相邻快照差值均摊，持续运行越久，趋势越稳定。</div>
</div></body></html>"""


def write_report(data: dict, username: str, out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html_text = build_html(data, username)
    stamp = data["generated_at"].strftime("%Y%m%d_%H%M")
    html_path = out / f"x_report_{stamp}.html"
    html_path.write_text(html_text, encoding="utf-8")
    latest = out / "latest.html"
    latest.write_text(html_text, encoding="utf-8")
    return {"html": html_path, "latest": latest}
