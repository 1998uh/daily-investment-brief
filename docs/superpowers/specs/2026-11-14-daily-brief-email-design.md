# 每日日报自动生成并邮件投递 — 设计

日期：2026-11-14
状态：待确认

## 意图

每天早上 8 点多，用户打开邮箱就能看到当天的投资日报，不需要手动说“生成日报”。
无论当天是否采集到内容、生成是否成功，都必须收到一封邮件：成功时是完整报告，失败时是失败说明。

## 目标

- 每天 08:10 自动启动一次日报生成，08:20 前后投递到 `1824127670@qq.com`
- 日报正文严格按 `AGENTS.md`、`skill/daily-investment-brief/SKILL.md`、`templates/direct_brief_prompt.md` 由模型原生撰写
- 邮件正文内嵌 HTML 报告，附件附带 `.md` 和 `.html`
- 任一环节失败都发送失败通知邮件，说明卡在哪一步、当天各平台采集数量
- SMTP 凭证只存本机 `.env`，不进入 Git

## 非目标

- 不做 PDF、不做多收件人订阅、不做网页版归档
- 不在失败后自动重试整篇写作（只重试邮件发送）
- 不接管已有的人工“生成日报”流程；两者可并存，人工生成会覆盖当日产物

## 反目标（即使技术可行也算失败）

- 某天静默不发邮件
- 用项目内 `generate`、fallback 或外部 LLM 代写正文
- 把昨天的日报当成今天的发出去
- 把 SMTP 授权码写进仓库、日志或邮件内容

## 时间线

| 时间 | 任务 | 作用 |
|---|---|---|
| 全天每 30 分钟 | Docker `social-collector` | 雪球/微博持续采集 |
| 07:30 | `DailyInvestmentBrief-Collect` | 微信/抖音批量采集，07:40 前完成 |
| 08:00 | **`DailyInvestmentBrief-Email`（新增）** | 尾段补采 + `materialize` + `prepare` → 原生写作 → 渲染 HTML → 门禁 → 发邮件，目标 08:10 前送达 |

原 08:05 的 `DailyInvestmentBrief-Prepare` 计划任务取消，其步骤合并进 08:00 任务，避免两次等待。

## 组成

### 1. `pipeline/mailer.py`

标准库 `smtplib` + `email.message.EmailMessage`，不新增依赖。

```python
def send_report_email(*, report_date, md_path, html_path, settings) -> None
def send_failure_email(*, report_date, stage, detail, coverage, settings) -> None
```

- 成功邮件：主题 `投资日报 YYYY-MM-DD`；HTML 作为 `alternative` 正文；`daily-brief.md`、`daily-brief.html` 作为附件
- 失败邮件：主题 `[失败] 投资日报 YYYY-MM-DD`；纯文本 + 简单 HTML；附 `stage`、错误摘要（脱敏）、各平台采集条数、日志路径
- SMTP：`smtp.qq.com:465`，SSL，登录名 = 发件邮箱，密码 = QQ 邮箱授权码
- 发送失败重试 3 次，间隔 10/30 秒；仍失败则写日志并非零退出

### 2. `scripts/daily_email.ps1`

08:00 计划任务入口，流程：

1. 获取命名互斥量 `Global\DailyInvestmentBrief-Prepare`，防止与手动运行或补跑并发读写 `sources/<date>`
2. 按 SKILL.md 顺序无条件执行 `social-health`、微信/抖音尾段采集、`materialize`、`prepare`（约 1 分钟）
3. 若当天已有 `daily-brief.md`（当天 00:00 之后写入且非 `-Force`），直接复用它；否则调用 headless Claude Code 原生写作
4. 用 `pipeline/html.py::wrap_html` 直接机械渲染 `daily-brief.html`（不调用 `validate` 生成 HTML）
5. 执行轻量内容门禁（见下）
6. 调用 `pipeline/mailer.py` 发送成功邮件
7. 任一步失败 → 调用失败邮件；邮件本身失败 → 写日志并保留退出码

日志：`data/logs/daily-email-<date>.log`，headless 原始输出另存 `data/logs/daily-email-claude-<date>.log`

### 内容门禁

`validate --report-only` 只检查 `daily-brief.md` 是否存在，无法拦住截断、错日期或缺少模板章节的报告。因此新增 `pipeline/report_gate.py`，在发送前检查：

- `daily-brief.md` 非空且正文长度 ≥ 3000 字符
- 一级标题包含 `<date>`（防止把昨天的报告当成今天的发出去）
- 存在模板要求的章节关键词：`今日三句话`、`博主持仓`、`看好方向`、`注意事项`、`数据覆盖`
- 渲染出的 `daily-brief.html` 非空

任一项不通过 → 不发送成功邮件，改发失败邮件，并附上草稿路径与未通过项。

### 部分数据政策

用户已明确要求“无论是否与否都要看到日报”，视为对无人值守日报的长期授权：若雪球/微博/微信公众号任一平台为 0，或 `social-health` 非 0，仍生成并发送日报，但标题与邮件正文必须显著标注“数据源不完整”并列出缺失平台；不得描述为“当日无观点”或“市场静默”。只有写作或门禁整体失败时才发失败邮件。

### 3. Headless 写作契约

```powershell
claude -p "<prompt>" `
  --permission-mode acceptEdits `
  --allowedTools "Read,Write,Edit,Glob,Grep" `
  --output-format text
```

Prompt 固定要求：

- 完整读取 `AGENTS.md`、`skill/daily-investment-brief/SKILL.md`、`templates/direct_brief_prompt.md`、`reports/<date>/codex-context.json`、`reports/<date>/article-pack.md`
- **无人值守覆盖**：采集、`social-health`、`materialize`、`prepare` 已由外层脚本完成；不要运行任何命令，不要尝试采集或重建目录
- 只写 `reports/<date>/daily-brief.md`，不生成 HTML（HTML 由 Python 机械渲染）
- 不调用 `generate`、fallback、外部 LLM
- 若文章包显示某平台为 0，仍按长期授权写作，但必须在标题与覆盖章节标注“数据源不完整”及缺失平台
- 完成后输出 `DONE`

不授予 Bash 与 Skill 权限，模型只负责读文件与写 Markdown。

### 修正 SKILL.md 的硬编码路径

`skill/daily-investment-brief/SKILL.md` 第 8 行写的是不存在的 `D:\ai-project\daily-investment-brief`。
改为当前仓库实际路径 `D:\project\daily-investment-brief`，避免 headless 或交互式会话把产物写到错误目录。

### 4. 配置（`.env`，已 gitignore）

```env
BRIEF_SMTP_HOST=smtp.qq.com
BRIEF_SMTP_PORT=465
BRIEF_SMTP_USER=发件QQ邮箱
BRIEF_SMTP_AUTH_CODE=QQ邮箱授权码
BRIEF_MAIL_TO=1824127670@qq.com
```

缺少任一变量时，脚本不进入写作阶段，直接尝试发失败邮件（若凭证本身缺失则只能写日志）。

### 5. 计划任务

- 名称：`DailyInvestmentBrief-Email`
- 时间：每天 08:00
- 脚本：`scripts/daily_email.ps1`
- 设置：`StartWhenAvailable`、允许电池运行、单次上限 45 分钟
- 运行身份：当前用户、交互式（与 Docker Desktop / Claude Code 登录态一致）
- 重复运行：发送成功后写 `reports/<date>/.email-sent.json`（含时间与 Message-ID）；再次触发默认跳过，手动 `-Force` 可重发。若当天已有当天 00:00 之后生成的人工日报，自动化任务直接复用它，不重新写作

## 失败矩阵

| 失败点 | 行为 |
|---|---|
| 文章包缺失 | 先补跑 materialize + prepare；仍失败则发失败邮件 |
| headless 写作超时/非零退出 | 发失败邮件，附退出码与日志尾 |
| `daily-brief.md` 缺失或为空 | 发失败邮件 |
| `validate --report-only` 不通过 | 发失败邮件，附校验错误 |
| SMTP 失败 | 重试 3 次；仍失败写日志，退出码非零 |
| SMTP 凭证缺失 | 写日志；无法发信 |

## 安全

- 授权码只在 `.env`，不进日志；mailer 对异常信息做脱敏
- headless 只授予 Read/Write/Edit/Glob/Grep，不授予 Bash
- 收件人固定为配置值，不接受运行参数注入

## 测试

- `tests/test_mailer.py`：用 fake SMTP 验证主题、收件人、HTML 正文、附件、失败重试、脱敏
- `tests/test_daily_email_prompt.py`（或等效）：验证 headless prompt 包含必需文件和 `DONE` 约束
- 端到端：手动执行一次 `daily_email.ps1`，确认收到成功邮件；再人为破坏文章包确认失败邮件

## 留给实现者的决定

- 邮件外壳的具体 HTML 样式（需在 QQ 邮箱手机端可读）
- 日志保留天数
- headless 使用的模型（默认跟随本机 Claude Code 配置）

## 待用户提供

1. 发件 QQ 邮箱地址（默认按收件邮箱同地址自发自收）
2. QQ 邮箱 SMTP 授权码（邮箱设置 → 账户 → 开启 POP3/SMTP → 生成授权码）
