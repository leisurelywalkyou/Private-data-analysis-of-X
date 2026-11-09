# 多平台账号数据采集与桌宠助手

基于 Python 的个人账号数据采集工具：以透明置顶的桌宠作为主程序，支持 X、Instagram、小红书、微博、pixiv、TikTok 六个平台的本人账号数据采集，长期累积到本地 CSV，并生成「KPI + 热力图 + 分析曲线」的可视化报告。双击桌宠打开观测台，查看数据与触发采集。

- 无数据库，数据按平台存储在 `data/platforms/` 下
- 界面使用 tkinter，仅需 `requests`；浏览器登录可选 `playwright`
- 只采集本人账号、低频串行请求；不实现登录伪装或验证码绕过

## 功能

- 桌宠主程序：透明置顶 GIF 角色、拖拽记忆位置、气泡播报、右键菜单
- 六平台采集：适配器独立模块、配置驱动、动态加载与卸载
- 平台数据隔离：每平台独立目录与指标列，平台不提供的指标不写入
- 采集稳定性：超时、重试、指数退避、限频、按错误类型冷却
- 浏览器会话桥接：打开独立浏览器由本人手动登录，只读取会话锚点 Cookie（pixiv 为 `PHPSESSID`）
- 采集准确性：统一字段归一化、必填校验、批次去重、快照幂等、账号数据交叉校验
- 监控面板：平台切换、帖子列表、字段覆盖度、本轮互动增量
- 报告：KPI、星期 × 小时热力图、每日/每小时曲线、Top 3 帖子曲线
- CLI：单平台采集、全平台常驻、按平台生成报告

## 目录结构

```text
猪群友桌宠/
├─ pet.py                桌宠主程序入口（默认）
├─ app.py                监控面板入口
├─ main.py               CLI 入口
├─ xmonitor/
│  ├─ core/              配置、HTTP、数据仓库、采集、分析、报告、调度
│  ├─ platforms/         六个平台适配器 + 动态注册表 + 统一字段
│  └─ ui/                桌宠、监控面板、设置
├─ assets/pet/           桌宠角色帧（source.gif 与去白底后的 frames/）
├─ tests/                离线单元测试
├─ design/               界面与交互设计说明、HTML 原型
├─ config.json           配置文件
├─ requirements.txt      依赖
├─ .gitignore            忽略运行时数据、日志与缓存
├─ 启动.bat              Windows 双击启动桌宠
├─ data/platforms/       运行后自动生成的分平台数据（已忽略）
├─ data/browser/<平台>/  浏览器登录态配置（敏感，已忽略）
└─ reports/<平台>/       生成的报告（latest.html 为最新一份，已忽略）
```

配置、数据与报告中的相对路径统一按项目根目录解析，因此从任意目录执行 `python main.py ...` 都能读写到正确位置。

## 环境

- Python 3.9+（已在 3.12 验证）
- 安装依赖：

```powershell
pip install -r requirements.txt
```

## 配置

编辑 `config.json`，或在桌宠/监控面板点「设置」按平台填写（会写回同一文件）。

### 平台配置

```json
"platforms": {
  "x": {
    "enabled": true,
    "account_name": "your_handle",
    "platform_user_id": "123456",
    "session_id": "粘贴 PHPSESSID / auth_token 等会话锚点值",
    "cookies": "",
    "max_posts": 50,
    "filters": {
      "include_keywords": [],
      "exclude_keywords": [],
      "exclude_reposts": false,
      "only_changed": false
    },
    "retry": {"max_attempts": 4, "backoff_seconds": 2, "backoff_max_seconds": 60},
    "rate_limit": {"min_interval_seconds": 3, "max_requests_per_minute": 20},
    "timeout": 20
  }
}
```

其余平台键为 `instagram`、`xiaohongshu`、`weibo`、`pixiv`、`tiktok`。字段说明：

| 字段 | 说明 |
| --- | --- |
| `enabled` | 是否参与调度 |
| `account_name` | 账号名称 / handle |
| `platform_user_id` | 平台用户 ID，仅小红书、微博、pixiv 必填；其余平台自动解析，设置里不显示该字段 |
| `session_id` | 会话锚点值，只保存这一项；锚点名见下表 |
| `cookies` | 程序自动获取的必需附加 Cookie（如 `ct0`、`tt_chain_token`），设置里不提供输入框 |
| `max_posts` | 每轮最多采集条数，默认 50 |
| `filters.include_keywords` | 仅保留标题/正文包含这些词的帖子 |
| `filters.exclude_keywords` | 排除包含这些词的帖子 |
| `filters.exclude_reposts` | 排除转发 |
| `filters.only_changed` | 只保留相对上次抓取指标有变化的帖子 |
| `retry.*` / `rate_limit.*` / `timeout` | 重试、限频与超时 |

各平台的会话锚点与自动获取的附加 Cookie：

| 平台 | 必填用户 ID | 锚点 Cookie | 自动获取 |
| --- | --- | --- | --- |
| X | 否 | `auth_token` | `ct0` |
| Instagram | 否 | `sessionid` | — |
| 小红书 | 是 | `web_session` | — |
| 微博 | 是 | `SUB` | — |
| pixiv | 是 | `PHPSESSID` | — |
| TikTok | 否 | `sessionid` | `tt_chain_token` |

设置里只填锚点值；X 的 `ct0`、TikTok 的 `tt_chain_token` 由「浏览器登录」一并读取，或在首次采集时向站点首页自动获取一次。

锚点值也可用环境变量覆盖：`X_SESSION_X`、`X_SESSION_INSTAGRAM`、`X_SESSION_XIAOHONGSHU`、`X_SESSION_WEIBO`、`X_SESSION_PIXIV`、`X_SESSION_TIKTOK`；`X_COOKIE_<平台>` 仍可用于补充附加 Cookie。

设置里的「浏览器登录」会打开独立浏览器窗口（Playwright + 本机 Chrome/Edge），由你手动完成登录（含验证码）后，程序只读取该平台域名下的会话锚点与必需附加 Cookie（如 X 的 `ct0`），其余 Cookie 丢弃；不注入反检测脚本、不换代理、不处理验证码。首次使用需 `pip install playwright`；本机已装 Chrome/Edge 时无需额外下载浏览器。浏览器配置文件保存在 `data/browser/<平台>/`。

### 全局配置

| 字段 | 说明 | 默认 |
| --- | --- | --- |
| `timezone` | 本地时区 | `Asia/Shanghai` |
| `collect_interval_minutes` | 全平台采集间隔 | 30 |
| `report_days` / `report_dir` | 报告回看天数与输出目录 | 30 / `reports` |
| `pet.x` / `pet.y` | 桌宠位置，退出时自动写入 | 空 |

## 使用

### 桌宠（默认入口）

双击 `启动.bat`，或执行：

```powershell
pythonw pet.py
```

- 双击桌宠：打开监控面板（已打开时仅提示）；单击：随机吐槽（你点我作甚？/ 你是小猪！/ 猪猪快干活！/ 你再这样我要哈气了！）
- 按住左键拖动：移动位置，退出时记住
- 右键菜单：打开观测台、采集全部平台、按平台生成报告、设置、自动采集、始终置顶、退出
- 采集结果用气泡播报；未配置账号或会话锚点时会提示
- 自检：`python pet.py --selftest`

### 监控面板

双击桌宠或右键「打开观测台」，也可执行 `pythonw app.py`：切换平台查看帖子与统计，触发采集或生成报告；「评估报告」页可预览、打开或删除单份历史报告（也可选中后按 Delete）。窗口关闭后桌宠自动恢复定时采集。

### 命令行

```powershell
python main.py platforms                    # 列出平台
python main.py collect --platform x        # 单平台采集
python main.py daemon --interval 30        # 常驻采集全部启用平台
python main.py report --platform x         # 生成报告
python main.py status                      # 各平台本地数据量
```

### 测试

```powershell
python -m unittest discover -s tests -v
```

## 数据文件

`data/platforms/<platform>/`：

- `accounts.csv`：账号当前指标
- `posts.csv`：帖子当前值与平台支持的指标列
- `snapshots-YYYY-MM.csv`：30 分钟快照，按月分文件，重复采集覆盖不重复计数
- `runs.csv`：每轮状态、错误、字段覆盖度与校验结果

平台不提供的指标不写入列，读取时按缺失处理。所有写入采用「临时文件 + 原子替换」。

## 平台能力

| 平台 | 账号指标 | 帖子指标 | 登录态 |
| --- | --- | --- | --- |
| x | 粉丝、关注、帖子数 | 赞、回复、转发 | 可选，遇登录墙必须 |
| instagram | 粉丝、关注、帖子数 | 赞、评论、播放 | 必须 |
| 小红书 | 粉丝、关注、帖子数、获赞与收藏 | 赞、评论、分享、收藏 | 必须 |
| 微博 | 粉丝、关注、帖子数 | 赞、评论、转发 | 必须 |
| pixiv | 作品数 | 赞、评论、收藏、浏览 | 必须 |
| tiktok | 粉丝、关注、作品数、获赞总数 | 赞、评论、分享、收藏、播放 | 必须 |

字段清单、限频配置、异常降级与风控边界详见 [多平台数据采集适配说明.md](./多平台数据采集适配说明.md)。

## 注意事项

- 网页采集可能违反平台服务条款，请先确认平台规则与当地法规；能申请官方 API 的平台优先用官方 API
- 本项目只采集本人账号，不采集他人数据、不抓取私信或关注列表
- 不实现登录伪装、验证码绕过、指纹伪造、代理轮换；遇到登录墙或 403 会停止并冷却
- `data/`、`reports/`、`*.log`（含 Chrome 生成的 `debug.log`）均为运行时产物，已在 `.gitignore` 中忽略；不要提交浏览器 profile
- `data/browser/<平台>/` 保存浏览器登录态配置，属于敏感数据，请勿分享
- `config.json` 含会话锚点与自动获取的附加 Cookie，分享代码前注意清理
- 网页接口结构会变化，解析失败会记录 `ParseError` 并进入冷却，不会静默写入错误数据
