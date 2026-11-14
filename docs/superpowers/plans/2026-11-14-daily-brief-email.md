# 每日日报自动生成并邮件投递 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天 08:00 自动完成尾段采集、materialize、prepare，由模型原生写日报、渲染 HTML、门禁校验，并把成功或失败结果投递到 `1824127670@qq.com`。

**Architecture:** 新增 `report_gate`（内容门禁）、`mailer`（QQ SMTP 发送）和两个 CLI 子命令（`render-html`、`send-email`）；PowerShell 脚本负责编排采集、headless 写作与失败兜底；一个 08:00 计划任务取代原 08:05 准备任务。

**Tech Stack:** Python 3.10+ 标准库 `smtplib`/`email`、现有 `pipeline/html.py`、PowerShell 计划任务、Claude Code CLI（headless）。

**Spec:** `docs/superpowers/specs/2026-11-14-daily-brief-email-design.md`

## Global Constraints

- 邮件只发往 `BRIEF_MAIL_TO`，默认 `1824127670@qq.com`；SMTP 为 `smtp.qq.com:465` SSL。
- 授权码只从 `.env` 读取，任何日志、邮件正文和异常信息都必须脱敏。
- 正文只能由 headless Claude Code 读取 `article-pack.md` 后原生撰写；禁止调用 `generate`、fallback 或外部 LLM。
- HTML 只能由 `pipeline/html.py::wrap_html` 机械渲染，禁止用 `validate` 生成 HTML。
- 报告窗口固定为 `[前一日 08:00, 当日 08:00)`，由 `materialize` 保证。
- headless 只授予 `Read,Write,Edit,Glob,Grep`，不授予 Bash 或 Skill。
- 任一环节失败都要尝试发送 `[失败] 投资日报 <date>` 邮件。

## Review Focus

1. 中文主题、正文和附件名在 QQ 邮箱是否正确显示——编码错误会让整封信乱码。
2. 模型写出截断、错日期或缺章节的报告——门禁必须拦住，不能把坏报告发出去。
3. 重复触发（补跑、手动重跑）——同一日期默认只发一次，`-Force` 才重发。
4. 失败邮件把 SMTP 授权码或 cookie 写进正文/日志——必须脱敏。
5. headless 超时或非零退出——仍要发出失败邮件，不能静默。

---

### Task 1: 内容门禁 `pipeline/report_gate.py`

**Files:**
- Create: `pipeline/report_gate.py`
- Test: `tests/test_report_gate.py`

**Interfaces:**
- Produces: `REQUIRED_SECTIONS: tuple[str, ...]` 和 `check_report(report_date: date, md_text: str, html_text: str) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from pipeline.report_gate import check_report

VALID = "# 📊 每日投资简报 — 2026年11月14日（周六·盘前）\n\n" + (
    "## 今日三句话\n\n## 一、💼 博主持仓信息\n\n## 二、📡 博主看好方向汇总\n\n"
    "## 三、⚡ 今日注意事项与投资总结\n\n## N-3、📋 数据覆盖情况\n\n" + "正文" * 1600
)

def test_valid_report_has_no_failures():
    assert check_report(date(2026, 11, 14), VALID, "<html>ok</html>") == []

def test_wrong_date_is_rejected():
    failures = check_report(date(2026, 11, 15), VALID, "<html>ok</html>")
    assert any("日期" in item for item in failures)

def test_missing_section_is_rejected():
    text = VALID.replace("今日三句话", "今日摘要")
    failures = check_report(date(2026, 11, 14), text, "<html>ok</html>")
    assert any("今日三句话" in item for item in failures)

def test_short_or_empty_body_is_rejected():
    assert check_report(date(2026, 11, 14), "太短", "<html>ok</html>")
    assert check_report(date(2026, 11, 14), VALID, "   ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_gate.py -q --basetemp=.pytest_tmp`
Expected: FAIL with `ModuleNotFoundError: pipeline.report_gate`

- [ ] **Step 3: Implement `check_report`**

规则（每项失败返回一句中文说明）：正文 strip 后为空；长度 `< 3000`；第一个一级标题不同时包含 `YYYY年M月D日` 和 `YYYY-MM-DD` 两种写法中的一种；缺任一必需章节关键词；HTML strip 后为空。`REQUIRED_SECTIONS` 取 `("今日三句话", "博主持仓信息", "博主看好方向汇总", "今日注意事项", "数据覆盖情况")`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_gate.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/report_gate.py tests/test_report_gate.py
git commit -m "feat: add daily brief content gate"
```

---

### Task 2: 邮件发送 `pipeline/mailer.py`

**Files:**
- Create: `pipeline/mailer.py`
- Test: `tests/test_mailer.py`

**Interfaces:**
- Produces:
  - `MailConfig(host, port, user, auth_code, recipient)`（frozen dataclass）
  - `load_mail_config(environ=None) -> MailConfig`
  - `build_report_email(*, report_date: date, md_text: str, html_text: str, config: MailConfig) -> EmailMessage`
  - `build_failure_email(*, report_date: date, stage: str, detail: str, coverage: dict[str, int], config: MailConfig) -> EmailMessage`
  - `send_message(message, *, config, smtp_factory=None, retries=3, sleep=time.sleep) -> str`（返回 Message-ID）
  - `send_report_email(*, report_date, md_path, html_path, config=None, smtp_factory=None) -> str`
  - `send_failure_email(*, report_date, stage, detail, coverage, config=None, smtp_factory=None) -> str`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from email.message import EmailMessage
from pipeline.mailer import MailConfig, build_report_email, build_failure_email, send_message

CONFIG = MailConfig("smtp.qq.com", 465, "a@qq.com", "SECRET-CODE", "b@qq.com")

def test_report_email_has_html_body_and_two_attachments():
    msg = build_report_email(
        report_date=date(2026, 11, 14), md_text="# 标题\n正文",
        html_text="<h1>标题</h1>", config=CONFIG,
    )
    assert msg["Subject"] == "投资日报 2026-11-14"
    assert msg["To"] == "b@qq.com"
    parts = list(msg.walk())
    assert any(p.get_content_type() == "text/html" for p in parts)
    names = [p.get_filename() for p in parts if p.get_filename()]
    assert names == ["daily-brief.md", "daily-brief.html"]

def test_failure_email_redacts_auth_code():
    msg = build_failure_email(
        report_date=date(2026, 11, 14), stage="headless",
        detail="login failed SECRET-CODE", coverage={"雪球": 0}, config=CONFIG,
    )
    assert msg["Subject"] == "[失败] 投资日报 2026-11-14"
    assert "SECRET-CODE" not in msg.as_string()

def test_send_message_retries_then_returns_message_id():
    class FakeSMTP:
        attempts = 0
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, user, code): assert (user, code) == ("a@qq.com", "SECRET-CODE")
        def send_message(self, msg):
            FakeSMTP.attempts += 1
            if FakeSMTP.attempts < 2: raise OSError("temporary")
    msg = EmailMessage(); msg["Subject"] = "s"; msg["To"] = "b@qq.com"; msg.set_content("x")
    message_id = send_message(msg, config=CONFIG, smtp_factory=FakeSMTP, sleep=lambda _: None)
    assert message_id.startswith("<")
    assert FakeSMTP.attempts == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mailer.py -q --basetemp=.pytest_tmp`
Expected: FAIL with `ModuleNotFoundError: pipeline.mailer`

- [ ] **Step 3: Implement `pipeline/mailer.py`**

- `load_mail_config` 读取 `BRIEF_SMTP_HOST`（默认 `smtp.qq.com`）、`BRIEF_SMTP_PORT`（默认 465）、`BRIEF_SMTP_USER`、`BRIEF_SMTP_AUTH_CODE`、`BRIEF_MAIL_TO`；缺失后三项时抛 `ValueError`。
- 成功邮件：`Subject=f"投资日报 {report_date.isoformat()}"`，`To=config.recipient`，`set_content("请在支持 HTML 的客户端查看正文，或打开附件。")`，`add_alternative(html_text, subtype="html")`，再 `add_attachment(md_text.encode("utf-8"), maintype="text", subtype="markdown", filename="daily-brief.md")` 和 HTML 附件。
- 失败邮件：主题 `[失败] 投资日报 <date>`；正文含 `stage`、脱敏后的 `detail`、`coverage` 表格；同时提供纯文本和 HTML 两个 alternative，不附报告文件。
- 脱敏：把 `config.auth_code` 的所有出现替换为 `<redacted>`。
- `send_message` 用 `smtplib.SMTP_SSL(config.host, config.port, timeout=30)`，`login(user, auth_code)`，`send_message`；失败按 `retries` 重试，间隔用传入的 `sleep(10)` / `sleep(30)`；返回 `message["Message-ID"]`，缺失时用 `make_msgid()` 写入后再返回。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mailer.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/mailer.py tests/test_mailer.py
git commit -m "feat: add QQ SMTP mailer for daily brief"
```

---

### Task 3: CLI `render-html`

**Files:**
- Modify: `pipeline/cli.py`（`build_parser` 与 dispatch）
- Test: `tests/test_cli_render.py`

**Interfaces:**
- Consumes: `pipeline.html.wrap_html(markdown: str, title: str) -> str`、`pipeline.report_gate.check_report`
- Produces: 子命令 `render-html --date YYYY-MM-DD [--out-dir DIR] [--check]`

- [ ] **Step 1: Write the failing test**

```python
from argparse import Namespace
from pipeline.cli import render_html_command

def test_render_html_writes_file_and_passes_check(tmp_path):
    out = tmp_path / "2026-11-14"
    out.mkdir()
    md = "# 📊 每日投资简报 — 2026年11月14日（周六·盘前）\n\n" + (
        "## 今日三句话\n## 一、💼 博主持仓信息\n## 二、📡 博主看好方向汇总\n"
        "## 三、⚡ 今日注意事项与投资总结\n## N-3、📋 数据覆盖情况\n" + "正文" * 1600
    )
    (out / "daily-brief.md").write_text(md, encoding="utf-8")
    code = render_html_command(Namespace(date="2026-11-14", out_dir=str(out), check=True))
    assert code == 0
    assert (out / "daily-brief.html").read_text(encoding="utf-8").startswith("<!doctype html>")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_render.py -q --basetemp=.pytest_tmp`
Expected: FAIL with `ImportError: cannot import name 'render_html_command'`

- [ ] **Step 3: Implement subcommand and handler**

在 `build_parser` 增加 `render-html`（`--date` 必填，`--out-dir` 默认 `reports/<date>`，`--check` 开关）；在 dispatch 中调用 `render_html_command(args)`。处理逻辑：md 不存在返回 2；`wrap_html(markdown, "每日投资简报")` 写入 `daily-brief.html`；`--check` 时调用 `check_report`，失败项打印到 stderr 并返回 1。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_render.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/cli.py tests/test_cli_render.py
git commit -m "feat: add render-html CLI command"
```

---

### Task 4: CLI `send-email`

**Files:**
- Modify: `pipeline/cli.py`
- Test: `tests/test_cli_send_email.py`

**Interfaces:**
- Consumes: `pipeline.mailer.send_report_email` / `send_failure_email`、`pipeline.report_gate.check_report`
- Produces: 子命令 `send-email --date YYYY-MM-DD [--out-dir DIR] [--force] [--dry-run] [--failure-stage STAGE] [--failure-detail DETAIL]`

- [ ] **Step 1: Write the failing test**

```python
import json
from argparse import Namespace
from pipeline import cli

def _args(tmp_path, **kw):
    base = dict(date="2026-11-14", out_dir=str(tmp_path), force=False, dry_run=False,
                failure_stage=None, failure_detail="")
    base.update(kw)
    return Namespace(**base)

def test_send_email_skips_when_marker_exists(tmp_path, monkeypatch):
    (tmp_path / ".email-sent.json").write_text('{"message_id": "<1>"}', encoding="utf-8")
    called = []
    monkeypatch.setattr(cli, "send_report_email", lambda **k: called.append(k) or "<1>")
    assert cli.send_email_command(_args(tmp_path)) == 0
    assert called == []

def test_send_email_writes_marker_after_send(tmp_path, monkeypatch):
    md = "# 📊 每日投资简报 — 2026年11月14日\n\n" + (
        "## 今日三句话\n## 一、💼 博主持仓信息\n## 二、📡 博主看好方向汇总\n"
        "## 三、⚡ 今日注意事项与投资总结\n## N-3、📋 数据覆盖情况\n" + "正文" * 1600
    )
    (tmp_path / "daily-brief.md").write_text(md, encoding="utf-8")
    (tmp_path / "daily-brief.html").write_text("<html>ok</html>", encoding="utf-8")
    monkeypatch.setattr(cli, "send_report_email", lambda **k: "<mid@qq.com>")
    assert cli.send_email_command(_args(tmp_path)) == 0
    marker = json.loads((tmp_path / ".email-sent.json").read_text(encoding="utf-8"))
    assert marker["message_id"] == "<mid@qq.com>"

def test_send_email_blocks_when_gate_fails(tmp_path, monkeypatch):
    (tmp_path / "daily-brief.md").write_text("太短", encoding="utf-8")
    (tmp_path / "daily-brief.html").write_text("<html>ok</html>", encoding="utf-8")
    called = []
    monkeypatch.setattr(cli, "send_report_email", lambda **k: called.append(k) or "<1>")
    assert cli.send_email_command(_args(tmp_path)) == 1
    assert called == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_send_email.py -q --basetemp=.pytest_tmp`
Expected: FAIL with `AttributeError: module 'pipeline.cli' has no attribute 'send_email_command'`

- [ ] **Step 3: Implement subcommand and handler**

处理逻辑：`--failure-stage` 时从 `codex-context.json` 的 `coverage` 汇总 `{source: articles_total}`（文件不存在则空字典），调用 `send_failure_email`，不检查门禁；否则读取 md/html，调用 `check_report`，有失败项打印并返回 1；`--dry-run` 只打印主题与收件人；成功后写 `.email-sent.json`（`message_id`、`sent_at` ISO、`report_date`）。标记已存在且未 `--force` 时打印跳过并返回 0。`--out-dir` 默认 `reports/<date>`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_send_email.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/cli.py tests/test_cli_send_email.py
git commit -m "feat: add send-email CLI command with duplicate guard"
```

---

### Task 5: 编排脚本 `scripts/daily_email.ps1`

**Files:**
- Create: `scripts/daily_email.ps1`

**Interfaces:**
- Consumes: `render-html`、`send-email`、`pipeline.cli social-health/collect/materialize/prepare`
- Produces: 计划任务入口，参数 `-Root`、`-Date`、`-Force`、`-DryRun`、`-SkipPrepare`

- [ ] **Step 1: Write the script**

要点：
- 获取互斥量 `Global\DailyInvestmentBrief-Prepare`（`WaitOne(20 分钟)`），`finally` 中 `ReleaseMutex`。
- 非 `-SkipPrepare` 时依次执行 `social-health`（记录退出码，不中止）、`collect --platform wechat`、`collect --platform douyin`（输出到 `sources\_raw\<date>`）、`materialize`、`prepare`。
- 若 `reports\<date>\daily-brief.md` 的 `LastWriteTime` 在当天 00:00 之后且非 `-Force`，跳过 headless。
- headless：用 here-string 构造 prompt（包含日期、`article-pack.md` 路径、各平台计数、无人值守覆盖说明、“数据源不完整”标注要求），`Start-Job` 执行 `claude -p $prompt --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Glob,Grep" --output-format text`，`Wait-Job -Timeout 1200`；输出写入 `data\logs\daily-email-claude-<date>.log`；超时则 `Stop-Job` 并进入失败分支。
- 校验 md 存在且 `LastWriteTime` 晚于任务开始时间；否则失败。
- 运行 `render-html --date <date> --check`；再运行 `send-email --date <date> [--force]`。
- 失败分支：`send-email --date <date> --failure-stage <stage> --failure-detail <最后 2000 字日志>`。
- `-DryRun` 跳过 headless 与 SMTP，只做 prep、render 与门禁并打印结果。
- 日志 `data\logs\daily-email-<date>.log`，所有 `Add-Content -Encoding utf8`。

- [ ] **Step 2: Syntax check**

Run: `powershell -NoProfile -Command "$null = [System.Management.Automation.Language.Parser]::ParseFile('D:\project\daily-investment-brief\scripts\daily_email.ps1',[ref]$null,[ref]$null); 'parse ok'"`
Expected: `parse ok`

- [ ] **Step 3: Dry run**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\daily_email.ps1 -Date 2026-11-14 -DryRun`
Expected: exit 0，日志出现 prep 步骤、`render-html` 通过、`DRY-RUN` 字样，且不发信。

- [ ] **Step 4: Commit**

```bash
git add scripts/daily_email.ps1
git commit -m "feat: add daily brief email orchestration script"
```

---

### Task 6: 路径修正、文档与计划任务

**Files:**
- Modify: `skill/daily-investment-brief/SKILL.md:8`
- Modify: `README.md`（每日自动采集小节）
- Modify: Windows 计划任务

- [ ] **Step 1: Fix the skill root path**

把 `固定项目根目录：\`D:\ai-project\daily-investment-brief\`` 改为 `D:\project\daily-investment-brief`。

- [ ] **Step 2: Verify no stale path remains**

Run: `grep -n "ai-project" skill/daily-investment-brief/SKILL.md`
Expected: 无输出。

- [ ] **Step 3: Update README**

把 07:30 / 08:05 / 08:10 的时间线改为 07:30 采集、08:00 生成并邮件投递；说明 `reports/<date>/.email-sent.json` 去重和 `-Force` 重发。

- [ ] **Step 4: Re-register scheduled tasks**

注销 `DailyInvestmentBrief-Prepare`，注册 `DailyInvestmentBrief-Email` 每天 08:00（`StartWhenAvailable`、允许电池、45 分钟上限、当前用户交互式）。

- [ ] **Step 5: Verify**

Run: `Get-ScheduledTaskInfo -TaskName DailyInvestmentBrief-Email`
Expected: `State=Ready`，`NextRunTime` 为次日 08:00；`Get-ScheduledTask -TaskName DailyInvestmentBrief-Prepare` 报不存在。

- [ ] **Step 6: Commit**

```bash
git add skill/daily-investment-brief/SKILL.md README.md
git commit -m "docs: document automated daily brief email"
```

---

### Task 7: 端到端验收

**Files:** 无代码改动

- [ ] **Step 1: Real run**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\daily_email.ps1 -Date 2026-11-14 -Force`
Expected: 退出码 0；`reports\2026-11-14\daily-brief.md` 与 `.html` 存在；`.email-sent.json` 写入；日志含 `Sent:`。

- [ ] **Step 2: Verify the message reached QQ SMTP**

检查脚本日志中的 `Message-ID` 和 `send-email` 输出；请用户确认收件箱收到《投资日报 2026-11-14》。

- [ ] **Step 3: Verify duplicate guard**

Again run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\daily_email.ps1 -Date 2026-11-14`
Expected: 不发送第二封，日志显示跳过。

---

## Self-Review

- Spec coverage：内容门禁、SMTP、HTML 渲染、失败邮件、去重、08:00 时间线、SKILL.md 路径均有任务覆盖。
- 类型一致：`check_report(date, str, str) -> list[str]`、`MailConfig` 字段、`send_report_email(..., smtp_factory=None) -> str` 在各任务中一致。
- Review Focus 五项分别由 Task 2（编码/脱敏）、Task 1（坏报告）、Task 4（去重）、Task 5（headless 失败兜底）覆盖。
