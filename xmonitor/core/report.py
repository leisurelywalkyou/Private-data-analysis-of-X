"""HTML 报告：KPI、热力图、分析曲线（纸本观测风格）。"""

from __future__ import annotations

import html
import itertools
from pathlib import Path

_UID = itertools.count(1)

CSS = """
:root{
  --paper:#efe9db; --sheet:#faf6ec; --ink:#1e1b16; --ink-soft:#4a4337;
  --muted:#8a8071; --hair:#ded5c2; --red:#b3402a; --teal:#2f6159; --gold:#a98a4b;
  --serif:"Georgia","Cambria","Songti SC","SimSun","Noto Serif SC",serif;
  --sans:"Segoe UI","Microsoft YaHei UI","PingFang SC",sans-serif;
  --mono:"Consolas","SFMono-Regular","Menlo",monospace;
}
*{box-sizing:border-box}
body{margin:0;padding:30px 20px 64px;color:var(--ink);font:14px/1.7 var(--sans);
  background-color:var(--paper);
  background-image:repeating-linear-gradient(to bottom,transparent 0 31px,rgba(30,27,22,.045) 31px 32px);}
.sheet{max-width:1060px;margin:0 auto;background:var(--sheet);border:1px solid var(--hair);
  box-shadow:0 1px 0 rgba(255,255,255,.7) inset,0 26px 60px -34px rgba(30,27,22,.45);
  padding:0 48px 30px;}
.masthead{padding:40px 0 24px;border-bottom:2px solid var(--ink)}
.kicker{display:flex;justify-content:space-between;gap:20px;
  font:10px/1.5 var(--mono);letter-spacing:.2em;text-transform:uppercase;color:var(--muted)}
.kicker b{color:var(--red);font-weight:400}
h1{font-family:var(--serif);font-size:clamp(34px,5.2vw,54px);line-height:1.04;
  margin:20px 0 10px;font-weight:700;letter-spacing:-.015em}
h1 .at{color:var(--red);font-weight:400;font-style:italic;font-size:.68em;margin-left:.1em}
.dek{margin:0;font-size:13.5px;color:var(--ink-soft)}
.dek .sep{color:var(--hair);margin:0 10px}
.notice{margin-top:18px;border:1px dashed var(--hair);padding:11px 16px;
  font:10.5px var(--mono);letter-spacing:.08em;color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid var(--hair)}
.kpi{padding:24px 20px 22px;border-left:1px solid var(--hair)}
.kpi:first-child{border-left:0;padding-left:0}
.kpi .v{font-family:var(--serif);font-size:clamp(24px,3vw,34px);font-weight:700;
  letter-spacing:-.03em;line-height:1;font-variant-numeric:tabular-nums}
.kpi .l{margin-top:9px;font:9px/1.5 var(--mono);letter-spacing:.16em;
  text-transform:uppercase;color:var(--muted)}
.plate{padding:30px 0 26px;border-bottom:1px solid var(--hair)}
.plate:last-of-type{border-bottom:0}
.plate-head{display:flex;align-items:baseline;gap:12px;margin-bottom:18px}
.idx{font:10px var(--mono);letter-spacing:.14em;color:var(--red)}
h2{font-family:var(--serif);font-size:19px;font-weight:700;margin:0;letter-spacing:-.01em}
.meta{font:9px/1.6 var(--mono);letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);margin-left:auto;text-align:right}
.heat-scroll{overflow-x:auto}
.heat{display:grid;grid-template-columns:44px repeat(24,minmax(24px,1fr));
  gap:2px;min-width:800px;margin-top:2px}
.heat .lbl{font:9px var(--mono);color:var(--muted);display:flex;align-items:center;
  justify-content:center;letter-spacing:.04em}
.heat .lbl.day{justify-content:flex-end;padding-right:8px}
.cell{height:26px;display:flex;align-items:center;justify-content:center;
  font:9.5px var(--mono);color:var(--ink)}
.cell.void{background:transparent;border:1px dashed rgba(138,128,113,.25);
  color:rgba(138,128,113,.5)}
.legend-heat{display:flex;align-items:center;gap:10px;margin-top:14px;
  font:9px var(--mono);letter-spacing:.1em;color:var(--muted)}
.legend-heat .bar{width:160px;height:6px;
  background:linear-gradient(90deg,rgba(179,64,42,.12),rgba(179,64,42,.95))}
.legend-heat .tail{margin-left:auto;letter-spacing:.12em}
.caption{margin:14px 0 0;font-size:12px;color:var(--muted);line-height:1.7}
.caption b{color:var(--ink-soft);font-weight:600}
.chart{margin:2px 0 0}
.chart svg{width:100%;height:auto;display:block}
.chart text{font-family:var(--mono);font-size:10px;letter-spacing:.05em;fill:var(--muted)}
.chart .line{stroke-linejoin:round;stroke-linecap:round}
.chart .dot{stroke:none}
.series{display:flex;flex-wrap:wrap;gap:8px 26px;margin:0 0 14px;
  font:10px var(--mono);color:var(--muted);letter-spacing:.05em}
.series .row{display:flex;align-items:center;gap:8px}
.series i{display:block;width:18px;height:2px}
.series .val{color:var(--ink);font-weight:700}
.empty{border:1px dashed var(--hair);padding:26px;text-align:center;
  font:10px var(--mono);letter-spacing:.12em;color:var(--muted)}
.colophon{margin-top:30px;padding-top:16px;border-top:1px solid var(--hair);
  display:flex;justify-content:space-between;gap:24px;
  font:9px var(--mono);letter-spacing:.1em;color:var(--muted)}
@media (max-width:760px){
  body{padding:16px 10px 40px}
  .sheet{padding:0 22px 22px}
  .kpis{grid-template-columns:repeat(2,1fr)}
  .kpi{border-left:0;border-top:1px solid var(--hair);padding-left:0}
  .plate-head{flex-wrap:wrap}
  .meta{margin-left:0;width:100%;text-align:left}
  .colophon{flex-direction:column;gap:6px}
}
@media print{
  body{background:#fff;padding:0}
  .sheet{border:0;box-shadow:none;max-width:none;padding:0 24px}
  .plate{break-inside:avoid}
}
"""

COLORS = ("#b3402a", "#2f6159", "#a98a4b")


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
    head = ['<div class="lbl"></div>']
    head += [f'<div class="lbl">{h:02d}</div>' for h in range(24)]
    cells = []
    for w, row in enumerate(matrix):
        cells.append(f'<div class="lbl day">{labels[w]}</div>')
        for h, v in enumerate(row):
            if cov[w][h] == 0:
                cells.append('<div class="cell void" title="未采集">·</div>')
                continue
            alpha = 0.1 + 0.9 * (v / mx)
            ink = "#fbf7ec" if alpha > 0.55 else "#1e1b16"
            cells.append(
                f'<div class="cell" style="background:rgba(179,64,42,{alpha:.2f});'
                f'color:{ink}" title="{labels[w]} {h:02d}:00 · 互动增益 {fmt(v)}">'
                f'{round(v)}</div>')
    return (f'<div class="heat-scroll"><div class="heat">'
            f'{"".join(head)}{"".join(cells)}</div></div>')


def line_chart(labels: list[str], series: list[dict], height: int = 180) -> str:
    n = max(len(labels), 2)
    mx = max([max(s["values"], default=0) for s in series] + [1])
    W, H, L, R, T, B = 1000, height, 56, 20, 20, 34
    pw, ph = W - L - R, H - T - B

    def x(i: int) -> float:
        return L + pw * (i / (n - 1))

    def y(v: float) -> float:
        return T + ph - ph * (v / mx)

    uid = f"grad{next(_UID)}"
    defs = ""
    if len(series) == 1:
        defs = (f'<defs><linearGradient id="{uid}" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0%" stop-color="{series[0]["color"]}" stop-opacity=".24"/>'
                f'<stop offset="100%" stop-color="{series[0]["color"]}" stop-opacity="0"/>'
                f'</linearGradient></defs>')

    grid = []
    for k in range(4):
        gv = mx * k / 3
        gy = y(gv)
        grid.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{W - R}" y2="{gy:.1f}" '
                    f'stroke="#1e1b16" stroke-opacity=".1"/>')
        grid.append(f'<text x="{L - 12}" y="{gy + 3.5:.1f}" text-anchor="end">'
                    f'{axis_num(gv)}</text>')

    count = min(n, 7)
    ticks = sorted({round(i * (n - 1) / (count - 1)) for i in range(count)})
    xaxis = "".join(
        f'<text x="{x(i):.1f}" y="{H - 12}" text-anchor="middle">'
        f'{html.escape(labels[i])}</text>' for i in ticks
    )

    paths = []
    for s in series:
        pts = [(x(i), y(v)) for i, v in enumerate(s["values"])]
        if len(series) == 1 and pts:
            area = (f'M {pts[0][0]:.1f} {T + ph:.1f} L '
                    + " L ".join(f"{px:.1f} {py:.1f}" for px, py in pts)
                    + f' L {pts[-1][0]:.1f} {T + ph:.1f} Z')
            paths.append(f'<path d="{area}" fill="url(#{uid})"/>')
        points = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        paths.append(f'<polyline class="line" fill="none" stroke="{s["color"]}" '
                     f'stroke-width="2.4" points="{points}"/>')
        dots = "".join(
            f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="2.4" fill="{s["color"]}"/>'
            for (px, py), v in zip(pts, s["values"]) if v
        )
        paths.append(dots)
        last = max((i for i, v in enumerate(s["values"]) if v), default=None)
        if len(series) == 1 and last is not None:
            px, py = pts[last]
            above = py - 12 > T + 6
            ty = py - 9 if above else py + 17
            anchor = "end" if px > W * 0.72 else "start"
            lx = px - 6 if anchor == "end" else px + 6
            paths.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="3.6" '
                         f'fill="{s["color"]}"/>')
            paths.append(
                f'<text x="{lx:.1f}" y="{ty:.1f}" text-anchor="{anchor}" '
                f'style="fill:{s["color"]};font-weight:700;paint-order:stroke;'
                f'stroke:#faf6ec;stroke-width:3px;stroke-linejoin:round">'
                f'{fmt(s["values"][last])}</text>')

    legend = "".join(
        f'<span class="row"><i style="background:{s["color"]}"></i>'
        f'{html.escape(s["name"])}</span>' for s in series)
    return (f'<div class="series">{legend}</div>'
            f'<div class="chart"><svg viewBox="0 0 {W} {H}" '
            f'preserveAspectRatio="xMidYMid meet" role="img">'
            f'{defs}{"".join(grid)}'
            f'<line x1="{L}" y1="{T + ph}" x2="{W - R}" y2="{T + ph}" '
            f'stroke="#1e1b16" stroke-opacity=".2"/>'
            f'{xaxis}{"".join(paths)}</svg></div>')


def growth_chart(items: list[dict], height: int = 220) -> str:
    if not items:
        return ""
    all_ts = [p[0] for item in items for p in item["points"]]
    t0, t1 = min(all_ts), max(all_ts)
    span = max((t1 - t0).total_seconds(), 1)
    mx = max([max(p[1] for p in item["points"]) for item in items] + [1])
    W, H, L, R, T, B = 1000, height, 56, 20, 20, 34
    pw, ph = W - L - R, H - T - B

    def tx(t) -> float:
        return L + pw * ((t - t0).total_seconds() / span)

    def y(v: float) -> float:
        return T + ph - ph * (v / mx)

    grid = []
    for k in range(4):
        gv = mx * k / 3
        gy = y(gv)
        grid.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{W - R}" y2="{gy:.1f}" '
                    f'stroke="#1e1b16" stroke-opacity=".1"/>')
        grid.append(f'<text x="{L - 12}" y="{gy + 3.5:.1f}" text-anchor="end">'
                    f'{axis_num(gv)}</text>')

    xaxis = "".join(
        f'<text x="{tx(t0 + (t1 - t0) * i / 4):.1f}" y="{H - 12}" '
        f'text-anchor="{"start" if i == 0 else "end" if i == 4 else "middle"}">'
        f'{(t0 + (t1 - t0) * i / 4).strftime("%m-%d %H:%M")}</text>' for i in range(5)
    )

    paths = []
    rows = []
    for idx, item in enumerate(items):
        color = COLORS[idx % len(COLORS)]
        pts = [(tx(t), y(v)) for t, v in item["points"]]
        points = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        paths.append(f'<polyline class="line" fill="none" stroke="{color}" '
                     f'stroke-width="2.2" points="{points}"/>')
        if pts:
            px, py = pts[-1]
            paths.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="3.4" '
                         f'fill="{color}"/>')
        rows.append(
            f'<span class="row"><i style="background:{color}"></i>'
            f'{html.escape(item["label"])}'
            f'<span class="val">{fmt(item["points"][-1][1])}</span></span>')

    return (f'<div class="series">{"".join(rows)}</div>'
            f'<div class="chart"><svg viewBox="0 0 {W} {H}" '
            f'preserveAspectRatio="xMidYMid meet" role="img">'
            f'{"".join(grid)}'
            f'<line x1="{L}" y1="{T + ph}" x2="{W - R}" y2="{T + ph}" '
            f'stroke="#1e1b16" stroke-opacity=".2"/>'
            f'{xaxis}{"".join(paths)}</svg></div>')


def build_html(data: dict, username: str) -> str:
    ov = data["overview"]
    name, _, handle = username.partition(" @")
    handle_html = f'<span class="at">@{html.escape(handle)}</span>' if handle else ""

    def kpi(value: str, label: str) -> str:
        return f'<div class="kpi"><div class="v">{value}</div><div class="l">{label}</div></div>'

    kpis = "".join([
        kpi(fmt(ov["posts"]), "追踪帖子 / Posts"),
        kpi(fmt(ov["total_engagement"]), "总互动 / Engagement"),
        kpi(fmt(ov["total_impressions"]), "总浏览 / Impressions"),
        kpi(fmt(ov["avg_engagement"]), "单条均互动 / Average"),
        kpi(str(ov["days_seen"]), f"有效采集 / {ov['runs']} 轮"),
    ])

    notice = ""
    if not ov["posts"]:
        notice = ('<div class="notice">当前区间没有帖子数据 · '
                  '先运行采集，再生成下一次报告</div>')

    peak = data["peak"]
    peak_txt = (f'热力图峰值 <b>{peak["weekday"]} {peak["hour"]:02d}:00</b>，'
                f'约 <b>{peak["value"]}</b> 次互动增益') if ov["posts"] else "暂无数据"

    heat = (heatmap(data["heatmap"], data["heatmap_coverage"], data["weekday_labels"])
            + '<div class="legend-heat"><span>低</span><span class="bar"></span>'
              '<span>高</span><span class="tail">30 MIN 快照差分 · 本地时段</span></div>')

    daily_eng = line_chart(data["daily"]["labels"],
                           [{"name": "互动增益", "values": data["daily"]["engagement"],
                             "color": COLORS[0]}])
    daily_imp = line_chart(data["daily"]["labels"],
                           [{"name": "浏览增益", "values": data["daily"]["impressions"],
                             "color": COLORS[1]}])
    hourly = line_chart(data["hourly"]["labels"],
                        [{"name": "平均互动增益 / 天", "values": data["hourly"]["avg_engagement"],
                          "color": COLORS[2]}])
    growth = (growth_chart(data["growth"])
              or '<div class="empty">快照不足 · 继续积累后显示单帖增长曲线</div>')

    def plate(index: str, title: str, meta: str, body: str, caption: str = "") -> str:
        cap = f'<p class="caption">{caption}</p>' if caption else ""
        return (f'<section class="plate"><div class="plate-head">'
                f'<span class="idx">{index}</span><h2>{title}</h2>'
                f'<span class="meta">{meta}</span></div>{body}{cap}</section>')

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(username)} · 长期数据分析</title><style>{CSS}</style></head>
<body><main class="sheet">
<header class="masthead">
  <div class="kicker"><span>Observation Ledger · 长期数据分析</span>
  <span><b>No.</b> {data['days']}D · {data['generated_at']:%Y.%m.%d}</span></div>
  <h1>{html.escape(name)}{handle_html}</h1>
  <p class="dek">区间 {data['range_start']:%Y-%m-%d} — {data['range_end']:%Y-%m-%d}
  <span class="sep">/</span>{data['days']} 天
  <span class="sep">/</span>数据源 本地 CSV</p>
  {notice}
</header>
<div class="kpis">{kpis}</div>
{plate("01", "星期 × 小时互动热力图", "Weekly × Hourly", heat,
       caption=f"{peak_txt}。空白格为未采集时段，长期运行后覆盖会更完整。")}
{plate("02", "每日互动增益曲线", "Daily Engagement", daily_eng)}
{plate("03", "每日浏览增益曲线", "Daily Impressions", daily_imp)}
{plate("04", "每小时平均互动增益", "Hourly Average · Per Day", hourly)}
{plate("05", "Top 3 帖子累计互动曲线", "Post Growth · Cumulative", growth)}
<div class="colophon">
  <span>DATA · data/platforms/&lt;平台&gt;/ · posts.csv / snapshots / runs.csv</span>
  <span>生成于 {data['generated_at']:%Y-%m-%d %H:%M} · 本地离线报告</span>
</div>
</main></body></html>"""


def write_report(data: dict, username: str, out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html_text = build_html(data, username)
    stamp = data["generated_at"].strftime("%Y%m%d_%H%M%S")
    html_path = out / f"report_{stamp}.html"
    index = 1
    while html_path.exists():
        html_path = out / f"report_{stamp}_{index}.html"
        index += 1
    html_path.write_text(html_text, encoding="utf-8")
    latest = out / "latest.html"
    latest.write_text(html_text, encoding="utf-8")
    return {"html": html_path, "latest": latest}


def generate(cfg: dict, platform: str, tz, days: int | None = None,
             top_n: int = 3) -> dict:
    """生成某平台报告（CLI、面板、桌宠共用），返回分析数据与输出路径。"""
    # 延迟导入：避免 core 包在初始化时形成 report -> collector -> platforms 的循环
    from ..platforms import load
    from . import analysis
    from .collector import make_store
    from .config import report_dir

    store = make_store(cfg, platform)
    data = analysis.build(store, tz, days=int(days or cfg.get("report_days", 30)),
                          top_n=top_n)
    account = store.get_account()
    title = f"{load(platform).label} @{account.get('account_name') or 'me'}"
    paths = write_report(data, title, str(report_dir(cfg) / platform))
    return {"data": data, "paths": paths, "title": title}
