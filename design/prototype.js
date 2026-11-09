/* x 观测台 · 交互原型脚本
   所有数据均为示例，字段与 xmonitor/core 的 CSV / analysis 输出保持一致。 */

/* ---------------- 示例数据 ---------------- */
const METRIC_LABEL = { likes: "赞", comments: "评论", shares: "转发", saves: "收藏", views: "浏览" };

const PLATFORMS = [
  {
    id: "x", label: "X", handle: "lingxi_studio", flag: "on", enabled: true, configured: true,
    anchor: "auth_token", metrics: ["likes", "comments", "shares"],
    account: { followers: 1204, following: 312, posts_count: 486, likes_total: null },
    stats: { posts: 486, snapshots: 2148, runs: 96, coverage: "96%", delta: 128, last: "11-07 19:40", next: "20:10" },
    spark: [12, 34, 21, 46, 38, 57, 44, 68, 72, 96, 88, 128],
    runtime: { state: "idle", message: "" },
    posts: [
      { t: "11-07 22:14", likes: 486, comments: 32, shares: 18, text: "深夜草图：第 12 版角色动作终于顺了", sub: "图片" },
      { t: "11-07 18:02", likes: 312, comments: 21, shares: 9, text: "关于长期观测数据的一点碎碎念：不要只看单日峰值", sub: "长文" },
      { t: "11-06 23:40", likes: 274, comments: 18, shares: 12, text: "把桌面宠物和观测台拆成两个入口之后，终于不打架了", sub: "图片" },
      { t: "11-06 15:26", likes: 198, comments: 14, shares: 6, text: "试了一版纸本风格的仪表盘，数字用衬线体真的更稳", sub: "图片" },
      { t: "11-05 21:08", likes: 402, comments: 27, shares: 15, text: "六平台串行采集的限频策略整理（附冷却时间表）", sub: "长文" },
      { t: "11-05 12:31", likes: 156, comments: 9, shares: 4, text: "午休时画的小猫，参考了老账本的装订线", sub: "图片" },
      { t: "11-04 20:17", likes: 233, comments: 16, shares: 7, text: "把「本轮互动增量」做成心跳条，比七个数字平铺清楚多了", sub: "图片" },
      { t: "11-04 10:02", likes: 121, comments: 7, shares: 3, text: "周末准备把报告里的热力图搬到应用内", sub: "文字" }
    ]
  },
  {
    id: "instagram", label: "Instagram", handle: "", flag: "off", enabled: false, configured: false,
    anchor: "sessionid", metrics: ["likes", "comments", "views"],
    stats: { posts: 0, snapshots: 0, runs: 0, coverage: "—", delta: 0, last: "—", next: "—" },
    account: { followers: null, following: null, posts_count: null, likes_total: null },
    runtime: { state: "idle", message: "" }, posts: []
  },
  {
    id: "xiaohongshu", label: "小红书", handle: "", flag: "setup", enabled: true, configured: false,
    anchor: "web_session", metrics: ["likes", "comments", "shares", "saves"],
    stats: { posts: 0, snapshots: 0, runs: 0, coverage: "—", delta: 0, last: "—", next: "20:10" },
    account: { followers: null, following: null, posts_count: null, likes_total: null },
    runtime: { state: "setup", message: "账号与会话锚点缺失" }, posts: []
  },
  {
    id: "weibo", label: "微博", handle: "lingxi_studio", flag: "cool", enabled: true, configured: true,
    anchor: "SUB", metrics: ["likes", "comments", "shares"],
    account: { followers: 892, following: 204, posts_count: 212, likes_total: null },
    stats: { posts: 212, snapshots: 640, runs: 38, coverage: "88%", delta: -8, last: "11-07 18:20", next: "—" },
    spark: [42, 38, 51, 29, 33, 18, 26, 14, 9, 12, 4, -8],
    runtime: { state: "error", message: "LoginRequired：会话已过期", kind: "login", cool: "20:35" },
    posts: [
      { t: "11-07 16:40", likes: 88, comments: 12, shares: 6, text: "本周观察：晚上九点后的互动密度最高", sub: "文字" },
      { t: "11-06 11:20", likes: 65, comments: 8, shares: 3, text: "把采集间隔从 15 分钟调到 30 分钟，请求量降了一半", sub: "文字" },
      { t: "11-05 19:55", likes: 120, comments: 15, shares: 9, text: "纸本风格配色方案整理：纸面、墨线、朱红", sub: "图片" },
      { t: "11-04 09:12", likes: 47, comments: 5, shares: 2, text: "早起看了一眼昨天的快照覆盖率，96%", sub: "文字" }
    ]
  },
  { id: "pixiv", label: "pixiv", handle: "", flag: "off", enabled: false, configured: false, anchor: "PHPSESSID", metrics: ["likes", "comments", "saves", "views"], stats: { posts: 0, snapshots: 0, runs: 0, coverage: "—", delta: 0, last: "—", next: "—" }, account: { followers: null, following: null, posts_count: null, likes_total: null }, runtime: { state: "idle", message: "" }, posts: [] },
  { id: "tiktok", label: "TikTok", handle: "", flag: "off", enabled: false, configured: false, anchor: "sessionid", metrics: ["likes", "comments", "shares", "saves", "views"], stats: { posts: 0, snapshots: 0, runs: 0, coverage: "—", delta: 0, last: "—", next: "—" }, account: { followers: null, following: null, posts_count: null, likes_total: null }, runtime: { state: "idle", message: "" }, posts: [] }
];

const ACCOUNT_LABEL = { followers: "粉丝", following: "关注", posts_count: "帖子", likes_total: "获赞" };

const LOGS = [
  { t: "21:40:02", level: "INFO", plat: "X", msg: "采集中…" },
  { t: "21:40:14", level: "OK", plat: "X", msg: "新增 12 · 快照 48 · 字段覆盖 96% · 校验通过" },
  { t: "21:40:16", level: "WARN", plat: "小红书", msg: "已启用，但账号与会话锚点缺失，本轮跳过" },
  { t: "21:40:18", level: "ERR", plat: "微博", msg: "LoginRequired：会话已过期 · 已冷却 360 分钟" },
  { t: "21:40:20", level: "INFO", plat: "调度", msg: "本轮完成：成功 1 · 失败 1 · 跳过 1" }
];

const POLICY = [
  ["失败重试", "4 次 · 退避 2 → 60 秒"],
  ["平台调度", "串行 · 单平台请求间隔 ≥ 3 秒"],
  ["限频策略", "最长 20 次 / 分钟"],
  ["冷却策略", "连续失败 3 次后冷却 60 分钟"],
  ["报告回看", "30 天 · reports/<平台>/"],
  ["数据落盘", "临时文件 + 原子替换 · 无数据库"]
];

const NOTES = {
  overview: [
    { t: "动作分层", c: "采集当前升为唯一主按钮（墨底），采集全部/生成报告降为次按钮，设置改为文字按钮。对应 panel.py:74-82。" },
    { t: "统计拆两层", c: "库存（帖子/快照/轮次/覆盖）与时序（本轮互动/上次/下次）分开；数字改用衬线 28px，标签等宽 9px。对应 panel.py:122-146。" },
    { t: "账号指标上屏", c: "读取 accounts.csv 的 followers / following / posts_count / likes_total，平台不提供的指标显示「—」。对应 panel.py:225-227。" },
    { t: "表格工具条", c: "新增数量、搜索、动态列说明与「双击/↵ 打开原帖」；列头改用完整词义。对应 panel.py:147-183、251-256。" },
    { t: "空态分级", c: "区分未启用 / 未配置 / 已配置无数据三种空态，各给下一步动作。对应 panel.py:280-284。" },
    { t: "状态常驻", c: "底部状态条永久显示最近一条；吐司只承担「刚发生」，错误可跳运行监控。对应 panel.py:351-355、358-389。" }
  ],
  runs: [
    { t: "事件可视化", c: "把 scheduler.poll() 的 platform_status / done / error / skip / round_done 落到进度条与平台卡。对应 scheduler.py:137-158。" },
    { t: "冷却倒计时", c: "直接读取 platform_state()['cooldown_until']，显示「HH:MM 后重试」。对应 scheduler.py:160-174。" },
    { t: "双向编码", c: "状态同时用颜色与 INFO/OK/WARN/ERR 文字，避免只靠红绿区分。" },
    { t: "错误带动作", c: "login → 更新锚点；challenge → 可能触发风控；rate_limit → 已冷却。对应 panel.py:371-375。" },
    { t: "日志可追溯", c: "日志按级别筛选并可清空；完整记录仍在 runs.csv。对应 store.py:183-198。" }
  ],
  analysis: [
    { t: "分析前移", c: "把报告里的热力图与曲线搬进应用内，先看结论再决定导出。数据来自 analysis.build()。" },
    { t: "同一口径", c: "区间、峰值、有效采集天数与 report.py 一致，避免应用内与导出报告数字对不上。" },
    { t: "峰值显式化", c: "热力图右上直接写「峰值：周六 21:00 · 约 N 次互动增益」，不让用户从色块猜。" },
    { t: "实现提示", c: "tkinter 无法渲染 HTML，应用内图表用 tk.Canvas 重绘；report.py 继续作为导出权威版本。" }
  ],
  reports: [
    { t: "历史报告", c: "扫描 reports/<平台>/report_*.html 生成列表，不新增数据源。对应 report.write_report()。" },
    { t: "生成不打断", c: "生成后先落列表并给吐司，不再直接把用户丢进浏览器。对应 panel.py:323-340。" },
    { t: "应用内预览", c: "简化版预览展示 KPI 与热力条；完整版仍在浏览器打开。" },
    { t: "复制路径", c: "方便把报告附到笔记或工作汇报，无需打开资源管理器。" }
  ],
  settings: [
    { t: "双栏整页", c: "平台列表常驻左侧，右侧按 01–04 分区；不再用 800×720 模态。对应 settings.py:40-216。" },
    { t: "锚点可核对", c: "默认隐藏并提供「显示」切换，避免粘贴后无法确认。对应 settings.py:93-103、160。" },
    { t: "内联校验", c: "间隔 5–240、上限 1–200 在字段下方提示，不再用模态弹窗。对应 settings.py:290-294。" },
    { t: "脏状态", c: "底部保存条显示未保存更改、还原、保存；关闭前可提示。对应 settings.py:285-319。" },
    { t: "保持边界", c: "重试/限频/冷却保持只读，只展示 config.json 既有字段，不新增可编辑项。" }
  ]
};

/* ---------------- 工具 ---------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const fmt = n => (n === null || n === undefined || n === "" || Number.isNaN(n)) ? "—" : Number(n).toLocaleString("en-US");
const esc = s => String(s).replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const badge = (flag, text) => `<span class="badge ${flag}">${esc(text)}</span>`;

function rng(seed) {
  let s = seed % 2147483647 || 1;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}
const SEED = { x: 7, instagram: 11, xiaohongshu: 13, weibo: 17, pixiv: 19, tiktok: 23 };

function dayLabels(n) {
  const end = new Date(2026, 10, 7), out = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(end); d.setDate(end.getDate() - i);
    out.push(`${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
  }
  return out;
}

function seriesFor(id, n) {
  const r = rng(SEED[id] || 7), out = [];
  let base = 120 + r() * 60;
  for (let i = 0; i < n; i++) {
    base += (r() - 0.35) * 34;
    base = Math.max(30, base);
    out.push(Math.round(base * (0.8 + 0.4 * r())) + (i === n - 1 ? 24 : 0));
  }
  return out;
}

function heatData(id) {
  const r = rng((SEED[id] || 7) * 3), m = [], c = [];
  for (let w = 0; w < 7; w++) {
    const row = [], cov = [];
    for (let h = 0; h < 24; h++) {
      const night = h < 7;
      const on = night ? r() > 0.7 : r() > 0.04;
      const peak = Math.exp(-Math.pow((h - 21) / 2.4, 2)) + 0.55 * Math.exp(-Math.pow((h - 12) / 3.2, 2));
      const weekend = w >= 5 ? 1.25 : 1;
      cov.push(on ? 1 : 0);
      row.push(on ? Math.round(peak * weekend * (26 + r() * 52)) : 0);
    }
    m.push(row); c.push(cov);
  }
  return { m, c };
}

/* ---------------- 状态 ---------------- */
const S = {
  page: "overview", platform: "x", days: 30, wire: false, notes: false,
  running: false, search: "", logFilter: "all", dirty: false, logs: LOGS.slice(),
  reports: [
    { at: "11-07 19:40", range: "30D", posts: 486, eng: 12486, size: "96 KB" },
    { at: "11-06 19:40", range: "30D", posts: 471, eng: 12108, size: "95 KB" },
    { at: "11-05 19:40", range: "30D", posts: 458, eng: 11820, size: "94 KB" }
  ]
};
const cur = () => PLATFORMS.find(p => p.id === S.platform) || PLATFORMS[0];

/* ---------------- 状态条 / 吐司 ---------------- */
function setStatus(tone, text) {
  const chip = $("#globalStatus");
  const label = { ok: "就绪", busy: "运行中", error: "失败", muted: "待机" }[tone] || "待机";
  chip.innerHTML = `<i class="dot ${tone}"></i><b>${label}</b>`;
  $("#footDot").className = `dot ${tone}`;
  $("#footStatus").textContent = text;
}

function toast(title, text, tone = "") {
  const box = document.createElement("div");
  box.className = `toast ${tone}`;
  box.innerHTML = `<b>${esc(title)}</b>${esc(text)}`;
  $("#toasts").appendChild(box);
  setTimeout(() => box.remove(), 6200);
}

/* ---------------- 左栏 ---------------- */
function renderScope() {
  $("#scopeList").innerHTML = PLATFORMS.map(p => {
    const count = p.flag === "setup" ? "未配置" : p.stats.posts ? fmt(p.stats.posts) : "—";
    return `<button class="scope-row ${p.id === S.platform ? "active" : ""}" data-scope="${p.id}" data-flag="${p.flag}" title="${esc(p.label)}">
      <i class="scope-dot"></i><span class="scope-name">${esc(p.label)}</span><span class="scope-count">${count}</span>
    </button>`;
  }).join("");
}

function renderNav() {
  $$("#nav .nav-item").forEach(b => b.classList.toggle("active", b.dataset.page === S.page));
  const errs = S.logs.filter(l => l.level === "ERR" || l.level === "WARN").length;
  $("#navBadgeRuns").textContent = errs || "";
  $("#navBadgeRuns").hidden = !errs;
}

/* ---------------- 观测台 ---------------- */
function renderOverview() {
  const p = cur();
  $("#ovLede").textContent = p.configured
    ? `${p.label} @${p.handle} · 本轮互动 ${p.stats.delta >= 0 ? "+" : ""}${fmt(p.stats.delta)} · 上次 ${p.stats.last} · 下次 ${p.stats.next}`
    : `${p.label} · 尚未配置账号与会话锚点`;

  // 横幅
  const banner = $("#ovBanner");
  let bt = "", btx = "", bact = "", bActLabel = "";
  if (!p.enabled) { bt = "该平台未启用"; btx = "未启用的平台不参与调度，也不会写入本地数据。"; bActLabel = "去启用"; bAct = "settings"; }
  else if (!p.configured) { bt = "已启用，但缺少账号或会话锚点"; btx = "填写账号名称与会话锚点后，调度器才会把该平台加入采集队列。"; bActLabel = "去配置"; bAct = "settings"; }
  else if (p.runtime.state === "error") { bt = "上次采集失败"; btx = `${p.runtime.message} · 冷却至 ${p.runtime.cool}`; bActLabel = "查看运行监控"; bAct = "runs"; }
  if (bt) {
    banner.hidden = false;
    $("#ovBannerTitle").textContent = bt;
    $("#ovBannerText").textContent = " " + btx;
    $("#ovBannerAct").textContent = bActLabel;
    $("#ovBannerAct").dataset.go = bAct;
  } else banner.hidden = true;

  // 账号条
  const acc = p.account;
  const metrics = Object.keys(ACCOUNT_LABEL)
    .filter(k => k !== "likes_total" || p.id === "xiaohongshu" || p.id === "tiktok")
    .map(k => `<div class="account-item"><span>${ACCOUNT_LABEL[k]}</span>${fmt(acc[k])}</div>`).join("");
  const stateBadge = !p.enabled ? badge("setup", "未启用") : !p.configured ? badge("setup", "未配置")
    : p.runtime.state === "error" ? badge("err", "会话过期") : badge("ok", "会话有效");
  $("#accountStrip").innerHTML = `
    <div class="account-name">${esc(p.label)} ${p.handle ? `@${esc(p.handle)}` : '<span style="font-weight:400;color:var(--muted)">未配置账号</span>'}<em>${p.configured ? "本地 CSV" : "SETUP REQUIRED"}</em></div>
    ${metrics}
    <div class="account-badges">${p.enabled ? badge("ok", "已启用") : badge("setup", "停用")}${stateBadge}</div>`;

  // 库存
  const stock = [
    ["posts", "帖 子", "POSTS", p.stats.posts ? "已入库 · posts.csv" : "尚无数据"],
    ["snapshots", "快 照", "SNAPSHOTS", "30 分钟粒度 · 按月分文件"],
    ["runs", "采集轮次", "RUNS", "runs.csv 累计"],
    ["coverage", "字段覆盖", "COVERAGE", "本轮字段完整率"]
  ];
  $("#stockBand").innerHTML = stock.map(([k, l, la, c]) =>
    `<div class="band-cell"><div class="v">${k === "posts" || k === "snapshots" || k === "runs" ? fmt(p.stats[k]) : p.stats[k]}</div><div class="l">${l} · ${la}</div><div class="c">${c}</div></div>`).join("");

  // 心跳
  const d = p.stats.delta;
  const cls = d > 0 ? "up" : d < 0 ? "down" : "";
  $("#beatBand").innerHTML = `
    <div class="beat-cell"><div class="v ${cls}">${d > 0 ? "+" : ""}${fmt(d)}</div><div class="l">本轮互动 Δ</div>${sparkSVG(p.spark)}</div>
    <div class="beat-cell"><div class="v small">${p.stats.last}</div><div class="l">上次采集 · LAST</div><div class="c" style="font-size:10px;color:rgba(251,247,236,.55);margin-top:6px">${p.enabled ? "自动采集已开启" : "未启用"}</div></div>
    <div class="beat-cell"><div class="v small">${p.stats.next}</div><div class="l">下次采集 · NEXT</div><div class="c" style="font-size:10px;color:rgba(251,247,236,.55);margin-top:6px">间隔 30 分钟</div></div>`;

  renderPosts();
  $("#tableFootNote").textContent = p.configured ? "仅展示最近 200 条 · 缺失指标显示 —" : "配置完成后即可采集";
  $("#footMeta").textContent = `上次 ${p.stats.last} · 下次 ${p.stats.next} · 示例数据`;
}

function sparkSVG(values) {
  if (!values) return "";
  const w = 180, h = 22, min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 2 - ((v - min) / span) * (h - 4)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="#e79b84" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
}

function renderPosts() {
  const p = cur();
  const head = $("#postHead"), body = $("#postBody"), empty = $("#postEmpty");
  $("#postCount").textContent = p.posts.length ? `${p.posts.length} 条 · 最近 200 条` : "0 条";
  $("#metricHint").textContent = p.metrics.length ? `平台指标：${p.metrics.map(k => METRIC_LABEL[k]).join(" · ")}` : "平台指标：—";

  const canShow = p.posts.length > 0;
  head.parentElement.hidden = !canShow;
  empty.hidden = canShow;

  if (!canShow) {
    const configured = p.configured, enabled = p.enabled;
    $("#emptyTitle").textContent = !enabled ? "该平台未启用" : !configured ? "先完成账号配置" : "还没有帖子数据";
    $("#emptySub").textContent = !enabled ? "启用平台后才会参与调度，数据仍保存在 data/platforms/ 下。"
      : !configured ? "填写账号名称与会话锚点，保存后点「采集当前」跑第一轮。"
        : "账号已就绪，采集一轮后即可看到帖子流水与快照。";
    $("#emptySteps").hidden = !enabled;
    $("#emptyAct").textContent = !enabled ? "去启用平台" : "去设置账号";
    $("#emptyAct").dataset.go = "settings";
    return;
  }

  head.innerHTML = `<tr><th style="width:112px">发布时间</th>${p.metrics.map(k => `<th class="num" style="width:70px">${METRIC_LABEL[k]}</th>`).join("")}<th>内容</th><th style="width:40px"></th></tr>`;
  const rows = p.posts.filter(r => !S.search || r.text.toLowerCase().includes(S.search.toLowerCase()));
  body.innerHTML = rows.map(r => `<tr data-url="https://example.com/${p.id}/post">
      <td class="time">${r.t}</td>
      ${p.metrics.map(k => `<td class="num metric ${r[k] === undefined ? "missing" : ""}">${r[k] === undefined ? "—" : fmt(r[k])}</td>`).join("")}
      <td title="${esc(r.text)}"><span class="pt">${esc(r.text)}</span><span class="pt-sub">${esc(r.sub || "")}</span></td>
      <td class="row-arrow">↗</td>
    </tr>`).join("");
  if (!rows.length) body.innerHTML = `<tr><td colspan="${p.metrics.length + 3}" class="missing" style="padding:24px;text-align:center">没有匹配「${esc(S.search)}」的帖子</td></tr>`;
}

/* ---------------- 运行监控 ---------------- */
function renderRuns() {
  const cards = PLATFORMS.filter(p => p.enabled || p.configured);
  const stateMap = {
    idle: ["ok", "已完成"], busy: ["busy", "采集中"], error: ["err", "冷却中"],
    skip: ["skip", "已跳过"], setup: ["setup", "未配置"]
  };
  $("#runCards").innerHTML = cards.map(p => {
    const rt = p.runtime;
    const st = S.running && p.id === S.platform ? ["busy", "采集中"] : (stateMap[rt.state] || ["ok", "已完成"]);
    let err = "";
    if (!p.configured) err = `<div class="run-err"><span>SETUP</span>账号或会话锚点缺失 · 本轮跳过</div>`;
    else if (rt.state === "error") err = `<div class="run-err"><span>${esc(rt.kind === "login" ? "LOGIN REQUIRED" : "ERROR")}</span>${esc(rt.message)} · ${esc(rt.cool || "")} 后重试</div>`;
    const act = !p.configured ? `<button class="btn btn-small" data-act="go-settings">去设置</button>`
      : rt.state === "error" ? `<button class="btn btn-small" data-act="go-settings">更新会话锚点</button><button class="text-btn" data-act="retry">立即重试</button>`
        : `<button class="text-btn" data-act="retry">立即采集</button>`;
    return `<div class="run-card">
      <div class="run-card-head"><b>${esc(p.label)}</b>${badge(st[0], st[1])}</div>
      <div class="run-meta">上次 ${esc(p.stats.last)} · 间隔 30 分钟</div>
      <div class="run-line">新增 — · 快照 ${fmt(p.stats.snapshots)} · 覆盖 ${p.stats.coverage}</div>
      ${err}
      <div class="run-act">${act}</div>
    </div>`;
  }).join("");

  const segs = PLATFORMS.filter(p => p.enabled).map(p => {
    let cls = "done", label = "已完成";
    if (S.running && p.id === S.platform) { cls = "busy"; label = "采集中"; }
    else if (!p.configured) { cls = "skip"; label = "跳过"; }
    else if (p.runtime.state === "error") { cls = "err"; label = "失败"; }
    return `<div class="seg-plat ${cls}"><span>${esc(p.label)} · ${label}</span><i></i></div>`;
  }).join("");
  $("#runProgress").innerHTML = segs;

  if (S.running) {
    $("#runState").textContent = "运行中";
    $("#runState").className = "run-state busy";
    $("#runSub").textContent = `正在采集 ${cur().label} · 串行执行 · 单平台间隔 ≥ 3 秒`;
  } else {
    $("#runState").textContent = "本轮已完成";
    $("#runState").className = "run-state ok";
    $("#runSub").textContent = "成功 1 · 失败 1 · 跳过 1 · 下次 20:10";
  }

  renderLogs();
}

function renderLogs() {
  const rows = S.logs.filter(l => {
    if (S.logFilter === "all") return true;
    if (S.logFilter === "WARN") return l.level === "WARN" || l.level === "INFO";
    return l.level === S.logFilter;
  });
  const map = { INFO: "setup", OK: "ok", WARN: "busy", ERR: "err" };
  $("#logBody").innerHTML = rows.length ? rows.map(l =>
    `<tr class="${l.level === "ERR" ? "err" : ""}"><td>${esc(l.t)}</td><td>${badge(map[l.level] || "setup", l.level)}</td><td>${esc(l.plat)}</td><td class="msg">${esc(l.msg)}</td></tr>`).join("")
    : `<tr><td colspan="4" class="missing" style="padding:22px;text-align:center">没有符合筛选的日志</td></tr>`;
  $(".card-meta", $("#page-runs")).textContent = `scheduler.poll() · 本轮 ${S.logs.length} 条`;
  renderNav();
}

/* ---------------- 数据分析 ---------------- */
function renderAnalysis() {
  const p = cur();
  const n = S.days;
  const labels = dayLabels(n);
  const eng = seriesFor(p.id, n);
  const imp = eng.map(v => Math.round(v * (1.7 + (v % 5) / 10)));
  const total = eng.reduce((a, b) => a + b, 0);
  const totalImp = imp.reduce((a, b) => a + b, 0);
  const kpis = [
    [fmt(total), "总互动 / ENGAGEMENT"],
    [fmt(totalImp), "总浏览 / IMPRESSIONS"],
    [fmt(Math.round(total / Math.max(1, p.stats.posts))), "单条均互动 / AVERAGE"],
    [`28 天`, "有效采集 / 30 轮"]
  ];
  $("#analysisKpi").innerHTML = kpis.map(([v, l]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

  const { m, c } = heatData(p.id);
  const mx = Math.max(...m.flat(), 1);
  let peak = { w: 0, h: 0, v: 0 };
  const hours = Array.from({ length: 24 }, (_, h) => `<div class="hour">${String(h).padStart(2, "0")}</div>`).join("");
  const days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  const cells = m.map((row, w) => `<div class="day">${days[w]}</div>` + row.map((v, h) => {
    if (v > peak.v) peak = { w, h, v };
    if (!c[w][h]) return `<div class="heat-cell void" title="未采集">·</div>`;
    const a = 0.1 + 0.9 * (v / mx);
    const ink = a > 0.55 ? "#fbf7ec" : "#1e1b16";
    return `<div class="heat-cell" style="background:rgba(179,64,42,${a.toFixed(2)});color:${ink}" title="${days[w]} ${String(h).padStart(2, "0")}:00 · ${fmt(v)}">${v}</div>`;
  }).join("")).join("");
  $("#heatmap").innerHTML = hours + cells;
  $("#peakNote").innerHTML = `峰值 <b>${days[peak.w]} ${String(peak.h).padStart(2, "0")}:00</b> · 约 <b>${peak.v}</b> 次互动增益`;

  $("#chartDailyEng").innerHTML = lineChart(labels, [{ values: eng, color: "#b3402a" }], { area: true });
  $("#chartDailyImp").innerHTML = lineChart(labels, [{ values: imp, color: "#2f6159" }], { area: true });
  $("#chartHourly").innerHTML = lineChart(Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0")),
    [{ values: hourly(p.id), color: "#a98a4b" }]);
  $("#chartGrowth").innerHTML = growthChart(p);

  $("#capRange").textContent = `${labels[0]} — ${labels[labels.length - 1]}`;
  $("#capDays").textContent = "28";
}

function hourly(id) {
  const r = rng((SEED[id] || 7) * 5);
  return Array.from({ length: 24 }, (_, h) => Math.round((Math.exp(-Math.pow((h - 21) / 2.6, 2)) + 0.5 * Math.exp(-Math.pow((h - 12) / 3, 2))) * (10 + r() * 18) * 10) / 10);
}

function growthChart(p) {
  const r = rng((SEED[p.id] || 7) * 7);
  const labels = ["11-05", "11-05", "11-06", "11-06", "11-07", "11-07", "11-07", "11-07"];
  const base = [40, 80, 140, 210, 300, 380, 440, 486];
  const series = [0, 1, 2].map(i => ({
    color: ["#b3402a", "#2f6159", "#a98a4b"][i],
    values: base.map((v, k) => Math.round(v * (0.55 + i * 0.22) * (1 + (r() - 0.5) * 0.12) * (1 + k * 0.02)))
  }));
  const names = ["Top 1 · 406", "Top 2 · 312", "Top 3 · 246"];
  const legend = `<div class="series">${series.map((s, i) => `<span class="row" style="display:flex;align-items:center;gap:6px;font:9px var(--mono);color:var(--muted)"><i style="display:block;width:16px;height:2px;background:${s.color}"></i>${esc(names[i])}</span>`).join("")}</div>`;
  return legend + lineChart(labels, series, { tickCount: 4 });
}

function lineChart(labels, series, opt = {}) {
  const W = 620, H = 160, L = 44, R = 12, T = 14, B = 24;
  const pw = W - L - R, ph = H - T - B;
  const n = labels.length;
  const mx = Math.max(...series.flatMap(s => s.values), 1);
  const x = i => L + pw * (i / Math.max(1, n - 1));
  const y = v => T + ph - ph * (v / mx);
  let grid = "";
  for (let k = 0; k < 4; k++) {
    const gv = mx * k / 3, gy = y(gv);
    grid += `<line x1="${L}" y1="${gy.toFixed(1)}" x2="${W - R}" y2="${gy.toFixed(1)}" stroke="#1e1b16" stroke-opacity=".1"/>`;
    grid += `<text x="${L - 8}" y="${(gy + 3.4).toFixed(1)}" text-anchor="end">${axisNum(gv)}</text>`;
  }
  const ticks = Math.min(opt.tickCount || 5, n);
  const idx = Array.from({ length: ticks }, (_, k) => Math.round(k * (n - 1) / Math.max(1, ticks - 1)));
  const xaxis = idx.map(i => `<text x="${x(i).toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(labels[i])}</text>`).join("");
  const paths = series.map((s, si) => {
    const pts = s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    let out = "";
    if (opt.area && series.length === 1) {
      const gid = `g${si}-${Math.random().toString(36).slice(2, 6)}`;
      out += `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${s.color}" stop-opacity=".22"/><stop offset="100%" stop-color="${s.color}" stop-opacity="0"/></linearGradient></defs>`;
      out += `<path d="M ${pts[0]} L ${pts.slice(1).join(" L ")} L ${x(n - 1).toFixed(1)} ${T + ph} L ${x(0).toFixed(1)} ${T + ph} Z" fill="url(#${gid})"/>`;
    }
    out += `<polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="${pts.join(" ")}"/>`;
    out += s.values.map((v, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="2" fill="${s.color}" opacity="${i === n - 1 ? 1 : .55}"/>`).join("");
    return out;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img">${grid}
    <line x1="${L}" y1="${T + ph}" x2="${W - R}" y2="${T + ph}" stroke="#1e1b16" stroke-opacity=".2"/>${xaxis}${paths}</svg>`;
}

function axisNum(v) {
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`;
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return Math.round(v);
}

/* ---------------- 评估报告 ---------------- */
function renderReports() {
  const p = cur();
  $("#genPlatform").textContent = p.label;
  $("#genMeta").textContent = `回看 30 天 · 输出 reports/${p.id}/ · 最近一次 ${S.reports[0].at}`;
  $("#reportCount").textContent = `${S.reports.length} 份`;
  $("#reportBody").innerHTML = S.reports.map((r, i) => `<tr>
    <td class="time">2026-${esc(r.at)}</td><td>${r.range}</td><td class="num metric">${fmt(r.posts)}</td>
    <td class="num metric">${fmt(r.eng)}</td><td class="metric">${esc(r.size)}</td>
    <td><button class="text-btn" data-act="preview-report" data-index="${i}">预览</button>
        <button class="text-btn" data-act="open-report">浏览器打开</button>
        <button class="text-btn" data-act="copy-path" data-index="${i}">复制路径</button></td>
  </tr>`).join("");
  $("#reportMock").innerHTML = reportMock(p);
}

function reportMock(p) {
  const { m, c } = heatData(p.id);
  const mx = Math.max(...m.flat(), 1);
  const strip = m[5].map(v => `<i style="background:rgba(179,64,42,${(0.1 + 0.9 * v / mx).toFixed(2)})"></i>`).join("");
  return `<div class="mh"><div class="mk"><span>Observation Ledger · 长期数据分析</span><span><b>No.</b> 30D · 2026.11.07</span></div>
    <h4>${esc(p.label)} ${p.handle ? `<em>@${esc(p.handle)}</em>` : ""}</h4>
    <div class="md">区间 2026-10-09 — 2026-11-07 / 30 天 / 数据源 本地 CSV</div></div>
    <div class="mkpi">
      <div><div class="v">${fmt(p.stats.posts)}</div><div class="l">追踪帖子</div></div>
      <div><div class="v">${fmt(Math.max(1200, p.stats.posts * 26))}</div><div class="l">总互动</div></div>
      <div><div class="v">${fmt(p.stats.snapshots * 6)}</div><div class="l">总浏览</div></div>
      <div><div class="v">28</div><div class="l">有效采集</div></div>
    </div>
    <div class="mock-heat">${strip}</div>
    <div class="cap">01 星期 × 小时热力图 · 02 每日互动 · 03 每日浏览 · 04 每小时均值 · 05 Top3 增长</div>`;
}

/* ---------------- 设置 ---------------- */
function renderSettings() {
  const p = cur();
  $("#settingsPlat").innerHTML = PLATFORMS.map(x => {
    const st = x.flag === "setup" ? "未配置" : x.enabled ? "启用" : "停用";
    return `<div class="plt-row ${x.id === S.platform ? "active" : ""}" data-scope="${x.id}" data-flag="${x.flag}">
      <i class="scope-dot"></i><span class="plt-name">${esc(x.label)}</span><span class="plt-state">${st}</span></div>`;
  }).join("");

  $("#fEnabled").checked = p.enabled;
  $("#fAccount").value = p.handle || "";
  $("#fUid").value = p.id === "weibo" || p.id === "xiaohongshu" || p.id === "pixiv" ? "8291" : "";
  $("#fMaxPosts").value = "50";
  $("#fAnchorName").textContent = p.anchor;
  $("#fSession").type = "password";
  $("#revealBtn").textContent = "显示";
  $("#fSession").value = p.configured ? "9f2c8a1e7b6d4f0a3c5e8b2d7a1f6c9e" : "";
  $("#fCookies").value = "";
  $("#fInclude").value = "";
  $("#fExclude").value = "";
  $("#fExcludeReposts").checked = false;
  $("#fOnlyChanged").checked = false;
  $("#fInterval").value = "30";
  $("#fSetupState").textContent = p.configured ? "会话有效" : "未配置";
  $("#sessionHint").textContent = p.configured ? "锚点已保存 · 仅本机可见" : "未读取 · 首次使用需 pip install playwright";
  $("#policyRows").innerHTML = POLICY.map(([k, v]) => `<div class="ro-row"><span>${k}</span><span>${v}</span></div>`).join("");
  $("#fMaxErr").hidden = true;
  $("#fIntervalErr").hidden = true;
  setDirty(false);
}

function setDirty(on) {
  S.dirty = on;
  $("#dirtyFlag").hidden = !on;
}

/* ---------------- 页面切换 ---------------- */
const PAGE_META = {
  overview: ["账号数据观测", "01 · Overview"],
  runs: ["运行监控", "02 · Runs"],
  analysis: ["数据分析", "03 · Analysis"],
  reports: ["评估报告", "04 · Reports"],
  settings: ["采集设置", "05 · Settings"]
};

function goto(page) {
  S.page = page;
  $$(".page").forEach(p => p.hidden = p.id !== `page-${page}`);
  renderNav();
  const [name, kicker] = PAGE_META[page];
  $("#crumb").innerHTML = `${name} <span>/</span> ${kicker}`;
  if (page === "overview") renderOverview();
  if (page === "runs") renderRuns();
  if (page === "analysis") renderAnalysis();
  if (page === "reports") renderReports();
  if (page === "settings") renderSettings();
  if (S.notes) renderNotes();
  $("#viewport").scrollTop = 0;
}

/* ---------------- 改动说明抽屉 ---------------- */
function renderNotes() {
  const items = NOTES[S.page] || [];
  $("#notesTitle").textContent = `${PAGE_META[S.page][0]} · 改动说明`;
  $("#notesBody").innerHTML = items.map((n, i) => `<div class="note-item">
    <div class="note-num">${String(i + 1).padStart(2, "0")}</div>
    <div class="note-title">${esc(n.t)}</div>
    <div class="note-text">${n.c.replace(/`([^`]+)`/g, "<code>$1</code>")}</div></div>`).join("");
}

function openNotes() {
  S.notes = true;
  renderNotes();
  $("#notesDrawer").classList.add("open");
  $("#notesDrawer").setAttribute("aria-hidden", "false");
  $("#scrim").hidden = false;
}
function closeNotes() {
  S.notes = false;
  $("#notesDrawer").classList.remove("open");
  $("#notesDrawer").setAttribute("aria-hidden", "true");
  $("#scrim").hidden = true;
}

/* ---------------- 弹层 ---------------- */
function openModal(title, html) {
  $("#modalTitle").textContent = title;
  $("#modalBody").innerHTML = html;
  $("#modal").hidden = false;
}
function closeModal() { $("#modal").hidden = true; }

function browserLoginHTML(p) {
  return `<div class="steps">
    <div class="empty-steps" style="align-items:flex-start;text-align:left;gap:14px">
      <span><b>01</b> 启动独立浏览器 · <span style="color:var(--teal)">已完成</span></span>
      <span><b>02</b> 手动完成登录（含验证码）· <span style="color:var(--gold)">等待中</span></span>
      <span><b>03</b> 读取会话锚点 <b style="color:var(--muted)">${esc(p.anchor)}</b></span>
    </div>
  </div>
  <p class="caption" style="margin-top:16px">只读取 ${esc(p.label)} 域名下的 ${esc(p.anchor)}，其余 Cookie 丢弃；不注入脚本、不换代理、不处理验证码。</p>
  <div class="inline-actions" style="margin-top:18px">
    <button class="btn" data-act="close-modal">关闭浏览器</button>
    <button class="btn btn-primary" data-act="read-session">读取会话</button>
  </div>`;
}

/* ---------------- 采集模拟 ---------------- */
function simulateRun(p) {
  if (S.running) return toast("进行中", "当前已有一轮采集在运行，请等待完成。");
  if (!p.enabled) return toast("无法采集", `${p.label} 未启用，请先在设置中启用该平台。`, "err");
  if (!p.configured) { toast("缺少配置", `${p.label} 还没有账号与会话锚点，本轮跳过。`, "err"); goto("settings"); return; }

  S.running = true;
  p.runtime = { state: "busy", message: "" };
  setStatus("busy", `${p.label} 采集中… · 串行执行`);
  $("#footMeta").textContent = "本轮进行中 · 示例数据";
  renderOverview();
  renderRuns();
  toast(p.label, "开始采集，平台间串行执行…");

  setTimeout(() => {
    const now = new Date();
    const hit = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    p.stats.posts += 2;
    p.stats.snapshots += 48;
    p.stats.runs += 1;
    p.stats.delta += 12;
    p.stats.coverage = "97%";
    p.stats.last = hit;
    p.runtime = { state: "idle", message: "" };
    S.logs.unshift({ t: hit, level: "INFO", plat: p.label, msg: "采集中…" });
    S.logs.unshift({ t: hit, level: "OK", plat: p.label, msg: "新增 2 · 快照 48 · 字段覆盖 97% · 校验通过" });
    S.running = false;
    setStatus("ok", `${p.label}：新增 2 · 快照 48 · 字段覆盖 97%`);
    toast(p.label, "采集完成 · 新增 2 · 快照 48 · 覆盖 97%", "ok");
    if (S.page === "overview") renderOverview();
    if (S.page === "runs") renderRuns();
    if (S.page === "analysis") renderAnalysis();
    $("#footMeta").textContent = `上次 ${p.stats.last} · 下次 20:10 · 示例数据`;
  }, 1800);
}

function generateReport() {
  const p = cur();
  if (!p.configured) { toast("无法生成", `${p.label} 尚未配置，先完成采集再生成报告。`, "err"); goto("settings"); return; }
  if (!p.posts.length) { toast("无法生成", "当前平台没有帖子数据，先点「采集当前」。", "err"); return; }
  const now = new Date();
  const at = `${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  S.reports.unshift({ at, range: "30D", posts: p.stats.posts, eng: p.stats.delta * 97, size: "96 KB" });
  setStatus("ok", `报告已生成 · reports/${p.id}/latest.html`);
  renderReports();
  toast("报告已生成", `reports/${p.id}/report_${at.replace(/[-: ]/g, "")}.html`, "ok");
}

/* ---------------- 事件 ---------------- */
document.addEventListener("click", e => {
  const nav = e.target.closest("#nav .nav-item");
  if (nav) { goto(nav.dataset.page); return; }

  const scope = e.target.closest("[data-scope]");
  if (scope) {
    S.platform = scope.dataset.scope;
    S.search = ""; $("#postSearch").value = "";
    renderScope();
    goto(S.page);
    setStatus(cur().runtime.state === "error" ? "error" : "ok",
      `${cur().label} · ${cur().configured ? "会话有效" : "未配置账号"}`);
    return;
  }

  const act = e.target.closest("[data-act]");
  if (!act) {
    const go = e.target.closest("[data-go]");
    if (go) goto(go.dataset.go);
    return;
  }
  const a = act.dataset.act;
  const p = cur();

  if (a === "collect-one") simulateRun(p);
  else if (a === "collect-all") {
    toast("串行采集", "依次采集全部已启用平台；原型演示执行当前平台。");
    simulateRun(p);
  }
  else if (a === "make-report" || a === "generate-report") { generateReport(); if (a === "make-report") goto("reports"); }
  else if (a === "go-settings") goto("settings");
  else if (a === "retry") simulateRun(p);
  else if (a === "open-report" || a === "preview-report") {
    const i = act.dataset.index ? Number(act.dataset.index) : 0;
    const r = S.reports[i] || S.reports[0];
    openModal("报告预览 · " + p.label + " @" + (p.handle || "me"), `<div class="report-mock">${reportMock(p)}</div>
      <p class="caption" style="margin-top:14px">完整版：reports/${p.id}/report_*.html · 生成于 2026-${esc(r.at)} · ${esc(r.size)}</p>
      <div class="inline-actions"><button class="btn btn-primary" data-act="close-modal">在浏览器打开 ↗</button><button class="btn" data-act="close-modal">关闭</button></div>`);
  }
  else if (a === "copy-path") { toast("已复制", `reports/${p.id}/report_${(S.reports[Number(act.dataset.index) || 0].at)}.html`, "ok"); }
  else if (a === "browser-login") openModal("浏览器登录 · " + p.label, browserLoginHTML(p));
  else if (a === "import-cookie") {
    $("#fSession").value = "9f2c8a1e7b6d4f0a3c5e8b2d7a1f6c9e";
    $("#sessionHint").textContent = `已导入 ${p.anchor} · 保存后生效`;
    setDirty(true);
    toast("已导入", `只读取到 ${p.anchor}，其余 Cookie 已丢弃。`, "ok");
  }
  else if (a === "read-session") {
    $("#fSession").value = "9f2c8a1e7b6d4f0a3c5e8b2d7a1f6c9e";
    $("#sessionHint").textContent = `已读取 ${p.anchor} · 保存后生效`;
    setDirty(true); closeModal();
    toast("已读取会话", `${p.anchor} 已填入，记得点击保存。`, "ok");
  }
  else if (a === "close-modal") closeModal();
  else if (a === "save-settings") saveSettings();
  else if (a === "reset-form") { renderSettings(); toast("已还原", "表单恢复为 config.json 中的值。"); }
});

function saveSettings() {
  const max = Number($("#fMaxPosts").value);
  const interval = Number($("#fInterval").value);
  const maxOk = Number.isInteger(max) && max >= 1 && max <= 200;
  const intOk = Number.isInteger(interval) && interval >= 5 && interval <= 240;
  $("#fMaxErr").hidden = maxOk;
  $("#fIntervalErr").hidden = intOk;
  if (!maxOk || !intOk) { toast("未保存", "请先修正标红字段：每轮上限 1–200，采集间隔 5–240。", "err"); return; }
  const p = cur();
  p.enabled = $("#fEnabled").checked;
  p.handle = $("#fAccount").value.trim().replace(/^@/, "");
  p.configured = Boolean(p.handle || $("#fUid").value.trim()) && Boolean($("#fSession").value.trim());
  p.flag = !p.enabled ? "off" : p.configured ? (p.runtime.state === "error" ? "cool" : "on") : "setup";
  p.stats.next = p.enabled ? "20:10" : "—";
  setDirty(false);
  renderScope(); renderSettings(); renderOverview();
  setStatus(p.configured ? "ok" : "muted", `设置已保存 · ${p.label} ${p.configured ? "会话有效" : "未配置"}`);
  toast("设置已保存", "写入本机 config.json，凭据不会上传。", "ok");
}

/* 输入相关 */
$("#postSearch").addEventListener("input", e => { S.search = e.target.value; renderPosts(); });
$("#autoToggle").addEventListener("change", e => {
  setStatus(e.target.checked ? "ok" : "muted", e.target.checked ? "自动采集已开启 · 下一轮 20:10" : "自动采集已暂停 · 桌宠同步显示已暂停");
  toast("自动采集", e.target.checked ? "已开启，按间隔自动执行。" : "已暂停，可随时手动采集。");
});
$("#intervalInput").addEventListener("change", e => {
  const v = Number(e.target.value);
  if (!Number.isInteger(v) || v < 5 || v > 240) { e.target.value = "30"; toast("间隔无效", "采集间隔需为 5–240 分钟。", "err"); return; }
  toast("间隔已更新", `每 ${v} 分钟一轮，写入 config.json。`, "ok");
});
$$("#logFilter .seg-btn").forEach(b => b.addEventListener("click", () => {
  $$("#logFilter .seg-btn").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  S.logFilter = b.dataset.level;
  renderLogs();
}));
$("#clearLog").addEventListener("click", () => { S.logs = []; renderLogs(); renderRuns(); toast("日志已清空", "仅清空界面缓存，runs.csv 仍保留。"); });
$$("#rangeSeg .seg-btn").forEach(b => b.addEventListener("click", () => {
  $$("#rangeSeg .seg-btn").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  S.days = Number(b.dataset.days);
  renderAnalysis();
}));
$("#revealBtn").addEventListener("click", () => {
  const input = $("#fSession");
  input.type = input.type === "password" ? "text" : "password";
  $("#revealBtn").textContent = input.type === "password" ? "显示" : "隐藏";
});
$("#settingsForm").addEventListener("input", () => setDirty(true));
$("#settingsForm").addEventListener("change", () => setDirty(true));
$("#settingsForm").addEventListener("click", e => {
  const go = e.target.closest("[data-go]");
  if (go) goto(go.dataset.go);
});

/* 顶栏 / 抽屉 / 弹层 */
$("#wireBtn").addEventListener("click", () => {
  S.wire = !S.wire;
  document.body.classList.toggle("wire", S.wire);
  $("#wireBtn").textContent = S.wire ? "高保真" : "线框";
  toast("显示模式", S.wire ? "线框模式：仅保留结构与层级。" : "高保真：纸面 / 墨线 / 朱红。");
});
$("#notesBtn").addEventListener("click", () => S.notes ? closeNotes() : openNotes());
$("#notesClose").addEventListener("click", closeNotes);
$("#scrim").addEventListener("click", closeNotes);
$("#modalClose").addEventListener("click", closeModal);
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
$("#refreshBtn").addEventListener("click", () => { goto(S.page); toast("已刷新", "读取本地 CSV 与调度状态。"); });
$("#emptyAct").addEventListener("click", () => goto("settings"));

document.addEventListener("keydown", e => {
  if (e.key === "Escape") { closeModal(); closeNotes(); }
});

/* ---------------- 初始化 ---------------- */
renderScope();
renderNav();
goto("overview");
setStatus("ok", "就绪 · 上次 19:40 · 下次 20:10 · 示例数据");
