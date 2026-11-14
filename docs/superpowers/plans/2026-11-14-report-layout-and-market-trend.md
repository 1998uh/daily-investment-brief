# 日报结构精简与大盘量能趋势 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把日报前部压缩成一页速览 + 量能趋势 + 注意事项，明细移到文末备查表，核心矛盾改表格，并新增每日成交额/两融/ETF 净流入的 20 日 PNG 趋势图随邮件送达。

**Architecture:** 新增 `pipeline/market_metrics.py`（BaoStock 成交额 + 东方财富两融/ETF，按报告日 clamp 后对齐）和 `pipeline/market_chart.py`（Pillow 三联图）；新增 `market-snapshot` CLI 写 `reports/<date>/market-metrics.json` 与 `market-trend.png`；`prepare` 把数据注入 `codex-context.json`；`render-html` 把 PNG 内联成 data URI；`send-email` 替换为 CID 内嵌图片；模板/AGENTS/SKILL/README 与门禁同步新结构。

**Tech Stack:** Python 3.10+、BaoStock（新依赖）、requests、Pillow、现有 email/html/prepare 体系、PowerShell 计划任务。

**Spec:** `docs/superpowers/specs/2026-11-14-report-layout-and-market-trend-design.md`

## Global Constraints

- 成交额口径：BaoStock `sh.000001` + `sz.399001`，单位元；图注「沪深两市，不含北证」。
- 报告日期 D 的行情固定取**严格早于 D 的最后一个交易日**，手动收盘后运行也不取 D 当日。
- `market-snapshot` 每个报告日只写一次；已存在默认跳过，`--force` 覆盖。
- 新日报不输出 mermaid；核心矛盾用 3–4 行维度表。
- 一页速览 5 条：持仓动作、方向共识（≥3 位作者）、主要分歧（最多 1 条）、今日机会（点名标的 ≥2 位作者；主题可单一作者但标注「单一作者，待验证」）、一句话风险。
- 正文前不再有独立「博主持仓信息」「博主看好方向汇总」；明细合并为文末「📋 作者持仓与方向明细（备查）」，保留 `### 博主看好方向汇总` 子标题。
- 取消「今日精选标的」。
- 条件章节 `## 零、✅ 上期观察点验证` 仅在 `verification_results` 非空时出现在今日三句话之前。
- 数据源失败不阻断日报；缺数据处明确标注。
- 邮件正文必须有 HTML；图片缺失时仍发送文字摘要。

## Review Focus

1. BaoStock 登录或查询失败——日报仍生成，量能面板标注「历史数据不可用」，不能整封失败。
2. 手动在交易日收盘后运行——必须 clamp 到 D-1，否则图表与正文讨论的日期不一致。
3. 复用已有日报时重跑——不得刷新图表；`-Force` 才同时重写正文和图表。
4. ETF 翻页中途失败——用已取部分求和并标注「ETF 数据不完整」，不能静默当全量。
5. 邮件 CID 内嵌失败或图片缺失——HTML 文本摘要仍送达，附件仍可打开。

---

### Task 1: 市场数据模块 `pipeline/market_metrics.py`

**Files:**
- Create: `pipeline/market_metrics.py`
- Modify: `pyproject.toml`（`collect` 依赖加 `baostock>=0.8.9`）
- Test: `tests/test_market_metrics.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) MarketPoint(date: date, turnover: float | None, margin_balance: float | None, etf_net_flow: float | None)`
  - `@dataclass(frozen=True) EtfSnapshot(date: date, net_flow: float, top: list[dict])`
  - `parse_baostock_rows(sh_rows: list[list[str]], sz_rows: list[list[str]]) -> dict[date, float]`
  - `parse_margin_payload(payload: dict) -> dict[date, float]`
  - `parse_etf_pages(pages: list[dict]) -> EtfSnapshot`
  - `build_market_metrics(*, report_date: date, turnover: dict[date, float], margin: dict[date, float], etf_store: dict[str, dict], etf_snapshot: EtfSnapshot | None, days: int = 20) -> dict`
  - `fetch_market_inputs(*, report_date: date, days: int = 20) -> dict`（返回 `turnover`、`margin`、`etf_store`、`etf_snapshot`）
  - `load_etf_store(path: Path) -> dict[str, dict]`
  - `save_etf_store(path: Path, store: dict[str, dict]) -> None`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from pipeline.market_metrics import EtfSnapshot, build_market_metrics, parse_baostock_rows

def test_baostock_rows_sum_sh_and_sz_by_date():
    sh = [["2026-11-12", "879537113560.40"], ["2026-11-13", "770614169983.60"]]
    sz = [["2026-11-12", "1052544765720.63"], ["2026-11-13", "885054041844.24"]]
    assert parse_baostock_rows(sh, sz)[date(2026, 11, 13)] == 770614169983.60 + 885054041844.24

def test_build_clamps_to_the_day_before_report_date():
    turnover = {date(2026, 11, 12): 1.9e12, date(2026, 11, 13): 1.65e12, date(2026, 11, 14): 9.9e12}
    margin = {date(2026, 11, 12): 2.3029e12}
    result = build_market_metrics(
        report_date=date(2026, 11, 14), turnover=turnover, margin=margin,
        etf_store={}, etf_snapshot=None,
    )
    assert result["as_of"] == "2026-11-13"
    assert result["turnover"]["latest"] == 1.65e12
    assert all(point["date"] < "2026-11-14" for point in result["points"])

def test_etf_snapshot_after_as_of_is_ignored_and_warned():
    turnover = {date(2026, 11, 13): 1.65e12}
    snap = EtfSnapshot(date=date(2026, 11, 14), net_flow=8.8e9, top=[])
    result = build_market_metrics(
        report_date=date(2026, 11, 15), turnover=turnover, margin={},
        etf_store={}, etf_snapshot=snap,
    )
    assert result["etf_flow"]["latest"] is None
    assert any("ETF" in item for item in result["warnings"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_metrics.py -q --basetemp=.pytest_tmp`
Expected: FAIL with `ModuleNotFoundError: pipeline.market_metrics`

- [ ] **Step 3: Implement the module**

- `parse_baostock_rows(sh_rows, sz_rows)`: sum the `amount` column by date; ignore empty/non-numeric values.
- `parse_margin_payload`: read `result.data` rows, `DIM_DATE` (first 10 chars) and `RZRQYE`.
- `parse_etf_pages`: each payload's `data.diff`; sum numeric `f62`; top 5 by `f62`; date from the first `f124` (Unix seconds, `Asia/Shanghai`). Return `EtfSnapshot`.
- `build_market_metrics`: filter `turnover` to dates `< report_date`; take the last `days`; `as_of` = max; `points` aligned with margin `<= point.date` and ETF from `etf_store[str(date)]` or the snapshot when its date equals the point date; warnings for empty turnover, missing margin/ETF, and an ETF snapshot later than `as_of` (ignored). Latest/prev/avg20 from the filtered series.
- `load_etf_store`/`save_etf_store`: JSON object keyed by `YYYY-MM-DD`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_market_metrics.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/market_metrics.py tests/test_market_metrics.py pyproject.toml
git commit -m "feat: add market metrics alignment and parsing"
```

---

### Task 2: 图表 `pipeline/market_chart.py`

**Files:**
- Create: `pipeline/market_chart.py`
- Test: `tests/test_market_chart.py`

**Interfaces:**
- Consumes: `MarketPoint` from Task 1.
- Produces: `render_market_trend(points: list[MarketPoint], out_path: Path, *, as_of: date, margin_date: date | None = None) -> Path`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from PIL import Image
from pipeline.market_chart import render_market_trend
from pipeline.market_metrics import MarketPoint

def test_renders_a_three_panel_png(tmp_path):
    points = [MarketPoint(date(2026, 11, d), 1.5e12 + d, 2.3e12 + d, 1e9 - d) for d in range(1, 21)]
    path = render_market_trend(points, tmp_path / "market-trend.png", as_of=date(2026, 11, 20), margin_date=date(2026, 11, 19))
    assert path.exists() and path.stat().st_size > 1000
    assert Image.open(path).size == (900, 560)

def test_missing_values_do_not_crash(tmp_path):
    points = [MarketPoint(date(2026, 11, 1), None, None, None)]
    path = render_market_trend(points, tmp_path / "chart.png", as_of=date(2026, 11, 1))
    assert path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market_chart.py -q --basetemp=.pytest_tmp`
Expected: FAIL with `ModuleNotFoundError: pipeline.market_chart`

- [ ] **Step 3: Implement `render_market_trend`**

- 900×560 white PNG; 3 stacked panels (成交额/两融/ETF 净流入), each with a title and y-axis min/max labels.
- Font: `BRIEF_CHART_FONT` env, else `C:\Windows\Fonts\msyh.ttc`, else `simhei.ttf`, else Pillow default.
- Turnover/margin lines (blue `#2563eb`, orange `#d97706`); ETF bars red `#c0392b` for positive, green `#27ae60` for negative.
- X labels every 5 dates; footer `数据来源：BaoStock / 东方财富；两融截至 <margin_date>`.
- Skip `None` points (gap, no interpolation).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_market_chart.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/market_chart.py tests/test_market_chart.py
git commit -m "feat: render 20-day market trend chart"
```

---

### Task 3: `market-snapshot` CLI

**Files:**
- Modify: `pipeline/cli.py`（parser、dispatch、handler）
- Test: `tests/test_cli_market_snapshot.py`

**Interfaces:**
- Consumes: Task 1 fetchers/builders and Task 2 `render_market_trend`.
- Produces: `market_snapshot_command(args) -> int`; subcommand `market-snapshot --date D [--days 20] [--force] [--out-dir DIR]`.

- [ ] **Step 1: Write the failing test**

```python
from argparse import Namespace
from pipeline import cli

def test_skips_when_snapshot_exists_without_force(tmp_path, monkeypatch):
    (tmp_path / "market-metrics.json").write_text("{}", encoding="utf-8")
    (tmp_path / "market-trend.png").write_bytes(b"png")
    called = []
    monkeypatch.setattr(cli, "fetch_market_inputs", lambda **k: called.append(k))
    args = Namespace(date="2026-11-14", days=20, force=False, out_dir=str(tmp_path))
    assert cli.market_snapshot_command(args) == 0
    assert called == []

def test_writes_json_and_chart_with_force(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "fetch_market_inputs", lambda **k: {
        "turnover": {__import__("datetime").date(2026, 11, 13): 1.65e12},
        "margin": {}, "etf_store": {}, "etf_snapshot": None,
    })
    monkeypatch.setattr(cli, "render_market_trend", lambda points, path, **k: path.write_bytes(b"png"))
    args = Namespace(date="2026-11-14", days=20, force=True, out_dir=str(tmp_path))
    assert cli.market_snapshot_command(args) == 0
    assert (tmp_path / "market-metrics.json").exists()
    assert (tmp_path / "market-trend.png").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_market_snapshot.py -q --basetemp=.pytest_tmp`
Expected: FAIL with `AttributeError: module 'pipeline.cli' has no attribute 'market_snapshot_command'`

- [ ] **Step 3: Implement the command**

- `fetch_market_inputs(*, report_date, days)` in `pipeline/market_metrics.py`: BaoStock login → query `sh.000001` and `sz.399001` for `[report_date - 40 days, report_date - 1 day]` → parse; Eastmoney margin → parse; Eastmoney ETF pages → parse; load the ETF store from `ROOT/data/market-metrics/etf-flow.json`; return the four inputs.
- `market_snapshot_command`: if both output files exist and not `force`, print skip and return 0; fetch (catch exceptions per source and carry warnings); build metrics; write JSON (`ensure_ascii=False, indent=2`); update the ETF store; render the chart when turnover points exist; print paths. Return 0 even with warnings; return 1 only if both JSON write and chart fail.
- Register the parser and dispatch.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_market_snapshot.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/cli.py pipeline/market_metrics.py tests/test_cli_market_snapshot.py
git commit -m "feat: add market-snapshot CLI"
```

---

### Task 4: `prepare` 注入 `market_metrics`

**Files:**
- Modify: `pipeline/hypothesis_workflow.py`
- Test: `tests/test_prepare_market_metrics.py`

**Interfaces:**
- Produces: context payload key `market_metrics` (the parsed JSON or `{"available": False, "warnings": [...]}`).

- [ ] **Step 1: Write the failing test**

```python
import json
from datetime import date
from pathlib import Path
from pipeline.hypothesis_workflow import _load_market_metrics

def test_loads_existing_snapshot(tmp_path):
    (tmp_path / "market-metrics.json").write_text(json.dumps({"available": True, "as_of": "2026-11-13"}), encoding="utf-8")
    assert _load_market_metrics(tmp_path)["as_of"] == "2026-11-13"

def test_missing_snapshot_is_marked_unavailable(tmp_path):
    assert _load_market_metrics(tmp_path)["available"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_prepare_market_metrics.py -q --basetemp=.pytest_tmp`
Expected: FAIL with `ImportError: cannot import name '_load_market_metrics'`

- [ ] **Step 3: Implement**

- Add `_load_market_metrics(out_dir: Path) -> dict`; read `out_dir / "market-metrics.json"`; on missing/invalid return `{"available": False, "warnings": ["market-metrics.json 不存在或无法读取"]}`.
- Add `"market_metrics": _load_market_metrics(out_dir)` to the context payload.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_prepare_market_metrics.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/hypothesis_workflow.py tests/test_prepare_market_metrics.py
git commit -m "feat: expose market metrics to the report context"
```

---

### Task 5: HTML 内联与邮件 CID

**Files:**
- Modify: `pipeline/html.py`, `pipeline/mailer.py`, `pipeline/cli.py`
- Test: `tests/test_html_inline.py`, `tests/test_mailer.py`

**Interfaces:**
- Produces: `inline_image_sources(html_text: str, base_dir: Path) -> str`; `build_report_email(..., chart_path: Path | None = None)`; `send_report_email(..., chart_path=None)`.

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path
from pipeline.html import inline_image_sources

def test_inlines_local_png_as_data_uri(tmp_path):
    (tmp_path / "market-trend.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    html = '<img alt="chart" src="market-trend.png" />'
    out = inline_image_sources(html, tmp_path)
    assert "data:image/png;base64," in out
    assert 'src="market-trend.png"' not in out
```

```python
from datetime import date
from pathlib import Path
from pipeline.mailer import MailConfig, build_report_email

CONFIG = MailConfig("smtp.qq.com", 465, "a@qq.com", "code", "b@qq.com")

def test_chart_becomes_cid_related_part(tmp_path):
    png = tmp_path / "market-trend.png"; png.write_bytes(b"\x89PNG\r\n\x1a\n")
    html = '<img src="data:image/png;base64,iVBORw0KGgo=" />'
    msg = build_report_email(report_date=date(2026, 11, 14), md_text="# t", html_text=html, config=CONFIG, chart_path=png)
    assert "cid:market-trend" in msg.get_body(preferencelist=("html",)).get_content()
    assert any(p.get("Content-ID") == "<market-trend>" for p in msg.walk())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_html_inline.py tests/test_mailer.py -q --basetemp=.pytest_tmp`
Expected: FAIL with missing `inline_image_sources` / `chart_path`

- [ ] **Step 3: Implement**

- `inline_image_sources`: regex `src="([^"]+\.png)"`; if the relative path exists under `base_dir`, replace with a base64 data URI; leave http(s) URLs alone.
- `render_html_command`: after `wrap_html`, call `inline_image_sources(html_text, out_dir)` before writing.
- `build_report_email`: accept `chart_path`; if it exists, read bytes, build the exact data URI, replace it (or `src="market-trend.png"`) with `src="cid:market-trend"`, then `set_content(html, subtype="html")`; `add_related(png_bytes, maintype="image", subtype="png", cid="<market-trend>", filename="market-trend.png")`; add attachments after.
- `send_report_email`: accept and forward `chart_path`.
- `send_email_command`: set `chart_path = out_dir / "market-trend.png"` if it exists, else `None`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_html_inline.py tests/test_mailer.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/html.py pipeline/mailer.py pipeline/cli.py tests/test_html_inline.py tests/test_mailer.py
git commit -m "feat: inline the market chart into HTML and email"
```

---

### Task 6: 模板、文档与门禁

**Files:**
- Modify: `templates/direct_brief_prompt.md`, `AGENTS.md`, `skill/daily-investment-brief/SKILL.md`, `README.md`
- Modify: `pipeline/report_gate.py`
- Test: `tests/test_report_gate.py`

**Interfaces:**
- Produces: `REQUIRED_SECTIONS = ("今日三句话", "一页速览", "大盘量能趋势", "今日注意事项", "数据覆盖情况", "博主看好方向汇总")`

- [ ] **Step 1: Write the failing test**

```python
def test_missing_one_page_summary_is_rejected():
    text = VALID.replace("一页速览", "今日摘要")
    failures = check_report(date(2026, 11, 14), text, "<html>ok</html>")
    assert any("一页速览" in item for item in failures)
```

Update the `VALID` fixture to include `一页速览`, `大盘量能趋势`, `数据覆盖情况`, `博主看好方向汇总`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_report_gate.py -q --basetemp=.pytest_tmp`
Expected: FAIL on the missing-section assertion

- [ ] **Step 3: Implement the template and gate changes**

- Template structure: conditional `## 零、✅ 上期观察点验证` → 今日三句话 → `## 一、⚡ 一页速览` → `## 二、📈 大盘量能趋势` → `## 三、⚡ 今日注意事项与投资总结` → dynamic event chapters → `## 📋 作者持仓与方向明细（备查）` with `### 博主看好方向汇总` → 数据覆盖 → 核心矛盾表 → 下期关注. Remove 博主持仓/方向 front sections, 今日精选标的, and mermaid.
- 一页速览 rules: the 5 bullets and thresholds from the spec.
- 大盘量能趋势 rules: read `market_metrics`; 3 summary bullets + `![大盘量能趋势](market-trend.png)` + last-5-day table; if unavailable, write the reason and skip the image.
- 持仓/方向 appendix rules: merged table, explicit disclosures only, quotes in event chapters, 未表态 footnote.
- 核心矛盾: 一句话 + 3–4 行维度表.
- Gate `REQUIRED_SECTIONS` as above.
- AGENTS.md item 8 new order; item 7/9 appendix/compact rules; SKILL.md checklist; README structure.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_report_gate.py -q --basetemp=.pytest_tmp`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/direct_brief_prompt.md AGENTS.md skill/daily-investment-brief/SKILL.md README.md pipeline/report_gate.py tests/test_report_gate.py
git commit -m "docs: restructure the daily brief and add the market trend section"
```

---

### Task 7: 08:00 脚本整合

**Files:**
- Modify: `scripts/daily_email.ps1`

- [ ] **Step 1: Reorder reuse and prep**

Move the `$reuse` check before the prep block. If `$reuse` and not `$Force`, skip collect/materialize/market-snapshot/prepare entirely; go to render/send.

- [ ] **Step 2: Add the market snapshot step**

In the non-reuse path, after `materialize` and before `prepare`:
```powershell
$marketArgs = @("-m", "pipeline.cli", "market-snapshot", "--date", $Date)
if ($Force) { $marketArgs += "--force" }
$market = Invoke-Step "market-snapshot" { & $python @marketArgs }
if ($market -ne 0) { Write-Log "market snapshot failed; continuing with degraded market section" }
```

- [ ] **Step 3: Syntax check and dry run**

Run: `powershell -NoProfile -Command "$null = [System.Management.Automation.Language.Parser]::ParseFile('D:\project\daily-investment-brief\scripts\daily_email.ps1',[ref]$null,[ref]$null); 'parse ok'"`
Expected: `parse ok`

- [ ] **Step 4: Commit**

```bash
git add scripts/daily_email.ps1
git commit -m "feat: generate the market snapshot in the 08:00 job"
```

---

### Task 8: 端到端验收

**Files:** 无代码改动

- [ ] **Step 1: Generate the snapshot**

Run: `python -m pipeline.cli market-snapshot --date 2026-11-13 --force`
Expected: `reports/2026-11-13/market-metrics.json` 与 `market-trend.png`；`as_of` 为 2026-11-12。

- [ ] **Step 2: Prepare and inspect the context**

Run: `python -m pipeline.cli prepare --date 2026-11-13` then inspect `codex-context.json` `market_metrics.as_of`.

- [ ] **Step 3: Generate a report without sending**

Run: `powershell -File scripts/daily_email.ps1 -Date 2026-11-13 -Force -SkipSend`
Expected: exit 0；`daily-brief.md` 含「一页速览」「大盘量能趋势」「作者持仓与方向明细」；核心矛盾无 mermaid；HTML 含 `data:image/png;base64`。

- [ ] **Step 4: Full suite**

Run: `pytest -q --basetemp=.pytest_tmp`
Expected: all pass.

- [ ] **Step 5: Commit**（如有验收产生的文档修正）

```bash
git add -A
git commit -m "test: validate market trend end to end"
```

---

## Self-Review

- Spec coverage: market data/clamp/write-once/ETF store/chart/HTML/email/prepare/template/gate/script all have tasks.
- Type consistency: `MarketPoint`, `EtfSnapshot`, `build_market_metrics`, `render_market_trend`, `inline_image_sources`, `chart_path` are used with the same names in later tasks.
- Review Focus 5 items: BaoStock failure (Task 1/3), clamp (Task 1), reuse/force (Task 7), partial ETF (Task 1/3), CID fallback (Task 5).
