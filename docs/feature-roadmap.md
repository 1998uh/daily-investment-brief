# Feature Roadmap

基于 2026-08-19 代码库深度分析的功能规划。

## 优先级

| 顺序 | 功能 | 难度 | 状态 |
|---|---|---|---|
| 1 | Cookie 健康检测 | 低 | 已完成 |
| 2 | 定时采集调度 | 低 | 待开发 |
| 3 | Journal 自动生成首稿 | 低 | 已完成 |
| 4 | 关注标的名单 + 自动标注 | 中 | 已完成 |
| 5 | 作者观点胜率统计 | 中 | 已完成 |
| 6 | 每日情绪温度计 | 中 | 已完成 |
| 7 | 低活跃作者智能补采 | 低 | 待开发 |
| 8 | 假设到期预警 | 低 | 已完成 |

---

## 功能详情

### 1. Cookie 健康检测（低难度）

在 `source-health` 命令以及 `collect` / `collect-one` 采集前置流程加入雪球、微博和抖音 Cookie 有效性检测：检查各平台关键登录 Cookie 是否存在、是否能成功请求第一页数据。失效时醒目输出对应平台的重新登录提示，并在采集前终止，避免生成不完整数据包。

**核心价值**：每天采集前先诊断，避免采了空包还不知道。  
**涉及文件**：`pipeline/collectors/xueqiu.py`、`pipeline/cli.py`

---

### 2. 定时采集调度（低难度）

新增 `schedule` 命令，自动生成 Windows Task Scheduler XML，每天早上 8:45 自动触发采集，打开 Codex 时内容已就位。

**核心价值**：把"每天记得运行"变成自动化，日报变成"开电脑就有"。  
**涉及文件**：`pipeline/cli.py`、新增 `pipeline/scheduler.py`

---

### 3. Journal 自动生成首稿（低难度）

每天 journal 是空模板，手动填很费时。生成日报后让 LLM 预填一个首稿：填入今日最重要信息、提取 2-3 个最强观点分歧，留空让用户填自己的判断。

**核心价值**：5 分钟 journal 变成 2 分钟校对，降低坚持门槛。  
**涉及文件**：`pipeline/workstation.py`、`pipeline/generator.py`、`templates/`

---

### 4. 关注标的名单 + 自动标注（中难度）

在 `config/watchlist.json` 维护关注标的，每次生成日报后扫描文中出现的标的，在相关段落旁加注"⭐ 关注标的"。

**核心价值**：持仓相关内容不用全文搜索，一眼看到。  
**涉及文件**：`pipeline/generator.py`、`pipeline/html.py`、新增 `config/watchlist.json`

---

### 5. 作者观点胜率统计（中难度）

在现有 `hypotheses.json` + `verification.json` 数据上，统计每位作者假设的最终状态（confirmed / falsified），计算胜率。看板增加“作者可信度”排行；联合署名会分别归因，未决、无结论和过期状态不纳入胜率。

**核心价值**：用历史数据告诉你读哪几个作者的判断更值钱。  
**涉及文件**：`pipeline/dashboard.py`、`pipeline/hypothesis_io.py`、`pipeline/html.py`

---

### 6. 每日情绪温度计（中难度）

对历史每天的日报提取作者看好/回避的标的和板块，构建"每日多空比"时序，在看板展示一周各板块情绪趋势。

实现口径：仅解析“博主看好方向汇总”表；按作者-日期-方向去重，保留同日多空冲突；净情绪分数为（看好数-回避数）/（看好数+回避数）；看板展示最近7个报告日活跃度最高的8个方向。

**核心价值**：一眼看出某板块连续 5 天被看多，避免被单日情绪带节奏。  
**涉及文件**：`reports/*/daily-brief.md` 解析、`pipeline/dashboard.py`、新增 `pipeline/sentiment.py`

---

### 7. 低活跃作者智能补采（低难度）

每天有些作者当天没发内容，自动扩窗 1-2 天补采近期内容，并在日报中标注"内容来自 N 天前"。

**核心价值**：减少"覆盖作者缺失"，让日报内容更完整。  
**涉及文件**：`pipeline/collectors/xueqiu.py`、`pipeline/collectors/runner.py`

---

### 8. 假设到期预警（低难度）

每次运行 `prepare` 时，扫描未来 1-3 天到期的假设，终端输出醒目提示：`[!] H-004 将于明天到期：存储回购抬升估值 — 建议今天收盘前检查证据`。

**核心价值**：把被动"有日报才想起验证"变成主动提醒。  
**涉及文件**：`pipeline/hypothesis_workflow.p y`、`pipeline/cli.py`
