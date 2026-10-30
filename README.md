# X 账号长期数据采集与分析

基于 Python 的 X（Twitter）个人账号数据采集工具：小窗口常驻运行，每 30 分钟通过官方 API 拉取自己帖子的互动数据，长期累积到本地 CSV，并生成「KPI + 热力图 + 分析曲线」的可视化报告。

- 无数据库，全部数据以 CSV 存储在代码目录下的 `data/` 文件夹
- 无第三方界面依赖（tkinter 为 Python 标准库），仅需 `requests`
- 只读取自己的公开帖子数据，需自备 X 开发者凭据

## 功能

- 启动后自动采集，默认每 30 分钟一轮，可改为 5–240 分钟
- 帖子列表逐条勾选：只采集勾选帖子的指标，取消勾选后停止该帖采集（历史数据保留）
- 30 分钟粒度快照，按月分文件长期积累，自动跨月新建
- 白底 + 蓝色主色界面；本轮互动增量与较上月同期变化直接显示，上涨标红、下降标绿
- 「打开主页采集」按钮：一键用 Google Chrome 打开自己的 X 主页，同时触发一次 API 采集
- 报告只包含：KPI 指标卡、星期 × 小时互动热力图、每日/每小时/单帖分析曲线
- 提供 CLI，可配合计划任务后台长期运行

## 目录结构

```text
x自动脚本/
├─ app.py            小窗口程序（推荐入口）
├─ main.py           CLI 入口
├─ collector.py      采集核心逻辑（界面与 CLI 共用）
├─ csvstore.py       CSV 数据仓库：读写、合并更新、按月快照、统计
├─ analysis.py       数据分析：KPI、热力图、曲线数据
├─ report.py         HTML 报告生成
├─ x_api.py          X API v2 客户端（分页、限流等待、重试）
├─ config.py         配置加载与指标字段映射
├─ config.json       配置文件
├─ requirements.txt  依赖（requests）
├─ 启动.bat          Windows 双击启动（pythonw，无控制台窗口）
├─ data/             运行后自动生成的数据目录
└─ reports/          生成的报告（latest.html 为最新一份）
```

## 环境

- Python 3.9+（使用 `zoneinfo`，已在 3.12 验证）
- 安装依赖：

```powershell
pip install -r requirements.txt
```

## 配置

编辑 `config.json`，或在小窗口点「设置」填写账号与 Token（会写回同一文件）。

| 字段 | 说明 | 默认 |
| --- | --- | --- |
| `username` | 自己的 X 账号（可带或不带 @） | 空 |
| `bearer_token` | X 开发者后台的 Bearer Token | 空 |
| `user_access_token` | 可选，OAuth2 用户 Token（读取受限时使用） | 空 |
| `timezone` | 本地时区，用于热力图与时间显示 | `Asia/Shanghai` |
| `collect_interval_minutes` | 小窗口自动采集间隔（分钟） | 30 |
| `track_recent_days` | 只刷新最近 N 天发布的帖子 | 7 |
| `max_snapshot_tweets` | 每轮最多刷新多少条帖子 | 200 |
| `exclude_retweets` | 是否排除转推 | true |
| `exclude_replies` | 是否排除回复 | false |
| `include_impressions` | 保留字段（曝光由 API 决定是否返回） | true |
| `data_dir` | CSV 数据目录 | `data` |
| `report_days` | 报告默认回看天数 | 30 |
| `report_dir` | 报告输出目录 | `reports` |

也可用环境变量覆盖，避免把密钥写进文件：

- `X_BEARER_TOKEN`、`X_USER_TOKEN`、`X_USERNAME`、`X_TIMEZONE`
- `X_API_BASE`（默认 `https://api.x.com/2`）

## 使用

### 小窗口（推荐）

双击 `启动.bat`，或执行：

```powershell
pythonw app.py
```

界面说明：

- 顶部：账号与「打开主页采集」按钮（用 Google Chrome 打开自己的 X 主页并立即触发一次采集），以及帖子数、已勾选数、快照数、上次/下次采集时间
- 变化量：`本轮互动` 为最近两个快照槽的互动增量；`较上月同期` 为最近 30 天增益相对前 30 天的变化
  - 上涨（正数）标红，下降（负数）标绿，无变化为灰色；历史不足 30 天时显示“数据不足”
- 按钮：立即采集、生成报告、设置、刷新列表；右侧为自动采集开关与间隔
- 帖子列表：`☑/☐` 为采集状态、发布时间、赞、转、评、曝光、内容
  - 单击行：切换是否采集
  - 双击行：在浏览器打开原帖
  - 「全选 / 全不选」批量切换
- 底部状态栏显示采集结果与错误

启动后立即采集一次，之后按间隔自动执行；关闭窗口即停止。

### 命令行

```powershell
python main.py collect                # 单次采集
python main.py daemon --interval 30   # 常驻，每 30 分钟
python main.py report --days 30       # 生成 HTML 报告
python main.py status                 # 查看本地数据量
```

长期运行可用 Windows 计划任务定时执行 `collect`，或让 `daemon` 常驻。

## 数据文件

### data/posts.csv

帖子当前值与采集开关，每轮采集合并更新（保留勾选状态与首次登记时间）。

```text
tweet_id, created_at, text, likes, retweets, replies, quotes, impressions,
bookmarks, enabled, added_at, updated_at
```

- `created_at` / `added_at` / `updated_at`：UTC ISO 时间
- `enabled`：1 采集，0 停止

### data/snapshots-YYYY-MM.csv

按月分文件的 30 分钟快照，长期累积；同一 `(tweet_id, slot)` 重复采集会覆盖，不重复计数。

```text
tweet_id, slot, likes, retweets, replies, quotes, impressions, bookmarks
```

`slot` 为对齐到 00/30 分的 UTC 时间。

### data/runs.csv

```text
started_at, new_posts, snapshots, note
```

### data/meta.json

保存 `user_id`、`username`、`followers` 等账号信息。

所有写入均为「临时文件 + 原子替换」，避免中途中断损坏 CSV。

## 报告

`reports/latest.html`（同时保留带时间戳的副本），内容：

1. KPI：追踪帖子、总互动、总曝光、单条平均互动、有效采集天数/轮次
2. 星期 × 小时互动热力图：未采集的格子显示 `·`，并标注峰值时段
3. 每日互动增益曲线、每日曝光增益曲线
4. 每小时平均互动增益曲线（按有采集的天数取平均）
5. Top 3 帖子累计互动曲线

报告为单文件 HTML，无外部依赖，可离线打开。

## 统计口径

- 互动 = 赞 + 转 + 回复 + 引用 + 书签
- 互动增益 = 相邻两次快照的指标差值；跨多个 30 分钟槽时按槽均摊，再归集到发帖本地时区的星期与小时
- 每小时平均曲线 = 该小时的增益总和 / 有采集的天数
- 曝光 `impression_count` 由 API 返回，通常对本人帖子较完整；缺失时按 0 处理

## 注意事项

- 读取用户时间线需要开发者账号具备相应读取额度；免费档通常只支持发帖，读数据一般需 Basic 及以上
- 401：Bearer Token 无效或过期；403：权限不足，可尝试配置 `user_access_token`
- 触发限流时客户端会按 `x-rate-limit-reset` 等待后重试，超过阈值则报错并在下一轮重试
- 采集间隔越短、持续越久，热力图与曲线越稳定；关机或程序未运行时的小时在热力图中显示为未采集
- 数据只存本地，不会上传；`data/` 与 `config.json` 含账号信息，分享代码前注意清理
