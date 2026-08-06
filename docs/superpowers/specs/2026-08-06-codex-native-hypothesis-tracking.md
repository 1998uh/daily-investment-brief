# Codex 原生结构化假设跟踪与自动验证实施计划

**日期：** 2026-08-06  
**状态：** 待实施  
**范围：** `pipeline/`、项目 Skill、测试和日报产物契约  
**目标版本：** 第一版 MVP

---

## 1. 背景

当前项目已经具备稳定的文章采集、缓存、覆盖率统计、Markdown/HTML 输出、资金日报和多模型生成能力。实际日常工作流已经发生变化：

1. 用户主要使用项目的采集命令获取雪球、微博和微信公众号文章。
2. 最终日报不再依赖项目内部 LLM 流程，而是由 Codex 直接读取素材、补充数据并完成写作。
3. 日报中的「下期关注」和「上期观察点验证」仍以自然语言 Markdown 形式传递。
4. 当前验证依赖上一自然日的报告和当日文章，由 LLM 进行解释性判断，无法稳定跨越周末、节假日、漏跑日期，也缺少确定性证据链。

因此，下一阶段不再扩建一个独立的 LLM Agent，而是围绕当前 Codex 工作流增加一层轻量、确定、可审计的假设账本和验证机制。

---

## 2. 核心决策

采用「Codex 负责语义工作，Python 负责确定性工作」的架构。

### Codex 负责

- 阅读当日原始文章。
- 理解作者观点、分歧、持仓与操作。
- 从观点中提取候选投资假设。
- 调用已连接的金融 MCP 获取行情、指数、板块、ETF、财务和资金流数据。
- 搜索并阅读官方公告、政策文件和权威事件来源。
- 写入符合项目契约的证据文件和新假设文件。
- 根据确定性验证结果生成最终日报。

### Python 负责

- 扫描和加载历史假设。
- 查找最近有效报告，不再只查上一自然日。
- 计算交易日和验证期限。
- 校验 JSON 文件结构、ID、单位、来源和字段完整性。
- 根据行情证据执行确定性验证规则。
- 管理假设状态转换。
- 阻止无证据的「已兑现」「已证伪」结论。
- 校验日报中的验证结果是否与结构化文件一致。
- 生成 HTML 和运行清单。

### 明确不做

- 不恢复完整的 FastAPI、Next.js、ChromaDB 或 LangGraph Agent 架构。
- 不重新实现 Codex 已具备的通用网页搜索和金融工具调用能力。
- 第一版不建设巨潮、交易所、政府网站的完整公告爬虫。
- 第一版不建设新的 LLM SDK 或多模型调度层。
- 第一版不引入新的数据库迁移系统。
- 第一版不自动评价作者投资能力或输出荐股结论。

---

## 3. 目标工作流

用户的使用方式保持不变：

```text
用户：生成今天的日报
```

项目 Skill 驱动 Codex 执行：

```text
检查 sources
  -> 必要时运行 collect
  -> daily-brief prepare
  -> Codex 读取 codex-context.json
  -> Codex 调用金融 MCP / 官方网页补证据
  -> Codex 写入 evidence.json
  -> daily-brief verify
  -> Codex 读取文章和 verification.json
  -> Codex 生成 daily-brief.md
  -> Codex 生成 hypotheses.json
  -> daily-brief validate
  -> 修复校验错误
  -> 生成 HTML 和 run-manifest.json
```

第一版新增三个 CLI 子命令：

```powershell
daily-brief prepare --date YYYY-MM-DD
daily-brief verify --date YYYY-MM-DD
daily-brief validate --date YYYY-MM-DD
```

保留现有 `generate` 命令用于兼容旧工作流，但项目 Skill 默认不再通过它生成日报。

---

## 4. 文件优先的数据设计

第一版不新增中心数据库，使用每日目录中的结构化 JSON 文件作为事实来源。

```text
reports/YYYY-MM-DD/
  daily-brief.md
  daily-brief.html
  codex-context.json
  evidence.json
  verification.json
  hypotheses.json
  run-manifest.json
```

选择文件优先方案的原因：

- 每天只有 3-5 条新假设，扫描历史目录的成本很低。
- JSON 易于人工检查、Git 对比和 Codex 读写。
- 字段在第一版仍会调整，避免过早固化数据库结构。
- 每期产物自包含，便于审计和重跑。
- 契约稳定后可以无损迁移到 SQLite。

---

## 5. 核心数据契约

### 5.1 `codex-context.json`

由 `prepare` 生成，只包含确定性上下文，不调用 LLM。

主要字段：

```json
{
  "schema_version": "1.0",
  "report_date": "2026-08-07",
  "timezone": "Asia/Shanghai",
  "source_dir": "sources/2026-08-07",
  "article_count": 96,
  "coverage": [],
  "active_hypotheses": [],
  "required_evidence": [],
  "previous_report_date": "2026-08-06",
  "generated_at": "2026-08-07T09:00:00+08:00"
}
```

`required_evidence` 必须描述每条历史假设仍缺少的数据，包括：

- 假设 ID。
- 数据类型。
- 标的名称和唯一代码。
- 日期范围。
- 指标名称。
- 单位。
- 推荐数据源。

### 5.2 `hypotheses.json`

由 Codex 在生成当日日报时写入，保存当日新增假设。

```json
{
  "schema_version": "1.0",
  "report_date": "2026-08-07",
  "hypotheses": [
    {
      "id": "H-20260807-001",
      "created_date": "2026-08-07",
      "claim": "国产半导体板块未来5个交易日跑赢沪深300至少2个百分点",
      "subject": {
        "type": "index",
        "name": "半导体板块",
        "thscode": "待消歧的唯一板块代码"
      },
      "sources": [
        {
          "author": "作者名",
          "article_id": "文章ID",
          "url": "原文URL",
          "quote": "与假设直接相关的作者原话"
        }
      ],
      "deadline": "2026-08-14",
      "verification_mode": "quantitative",
      "conditions": [],
      "falsification_conditions": [],
      "status": "pending"
    }
  ]
}
```

每条假设必须满足：

- ID 全局唯一并包含创建日期。
- 有明确、可理解的判断内容。
- 有原作者、原文引用和文章来源。
- 有验证期限。
- 有 `quantitative`、`event`、`hybrid` 或 `manual` 验证模式。
- 自动验证假设必须有唯一标的代码或明确的市场级实体。
- 必须同时存在支持条件和证伪条件；`manual` 模式可改为人工判断要求。
- 初始状态只能是 `pending`。

### 5.3 `evidence.json`

由 Codex 调用金融 MCP、官方网页或其他可信来源后写入。

行情证据示例：

```json
{
  "evidence_id": "E-20260807-001",
  "hypothesis_id": "H-20260806-001",
  "evidence_type": "market_metric",
  "metric": "index.close",
  "entity": {
    "name": "创业板指",
    "thscode": "399006.SZ"
  },
  "observed_date": "2026-08-07",
  "value": 3522.18,
  "unit": "point",
  "provider": "hithink-finance",
  "request_id": "上游请求ID",
  "source_url": "",
  "fetched_at": "2026-08-07T09:05:00+08:00"
}
```

事件证据示例：

```json
{
  "evidence_id": "E-20260807-002",
  "hypothesis_id": "H-20260806-002",
  "evidence_type": "event",
  "event_type": "policy_release",
  "title": "正式政策标题",
  "published_at": "2026-08-07",
  "source_level": "official",
  "publisher": "发布机构",
  "url": "官方URL",
  "quote": "与假设直接相关的原文",
  "supports": true,
  "fetched_at": "2026-08-07T09:10:00+08:00"
}
```

证据等级固定为：

```text
official       官方文件、交易所公告、公司公告
authoritative  官方发布会、权威统计或一手公开数据
media          主流媒体或行业媒体报道
social         雪球、微博、公众号等观点材料
```

只有 `official` 和符合规则的 `authoritative` 证据可以直接触发事件假设的确定性结论。`media` 和 `social` 默认只作为候选或辅助证据。

### 5.4 `verification.json`

由 `verify` 生成，不允许 Codex 直接编写最终状态。

```json
{
  "schema_version": "1.0",
  "report_date": "2026-08-07",
  "results": [
    {
      "hypothesis_id": "H-20260806-001",
      "previous_status": "pending",
      "status": "partially_confirmed",
      "conditions": [],
      "falsification_conditions": [],
      "reason": "指数条件已满足，成交额持续性不足。",
      "deterministic": true,
      "evaluated_at": "2026-08-07T09:15:00+08:00"
    }
  ]
}
```

### 5.5 `run-manifest.json`

保存本次运行的可审计信息：

- 报告日期和覆盖窗口。
- 输入文章数量及文件哈希。
- 上一期有效报告日期。
- 使用的 Skill 版本或契约版本。
- 金融数据 provider 和请求 ID。
- 官方事件来源 URL。
- `prepare`、`verify`、`validate` 执行时间和结果。
- 最终报告文件哈希。
- 是否存在数据缺失、人工判断或降级项。

第一版不强制记录 Codex token 和成本，但预留字段。

---

## 6. 假设状态机

第一版状态固定为：

```text
pending
partially_confirmed
confirmed
falsified
inconclusive
unavailable
expired
```

转换规则：

```text
pending
  -> partially_confirmed  部分支持条件满足，但持续时间或必要条件不足
  -> confirmed            所有必要支持条件在期限内满足
  -> falsified            命中强证伪条件
  -> inconclusive         到期时支持与反对证据冲突
  -> unavailable          必需数据持续不可用
  -> expired              到期且没有足够证据继续判断
```

约束：

- `confirmed` 和 `falsified` 必须由 `verify` 生成。
- 数据缺失不得被改写成方向性结论。
- 不允许 Codex 根据单日涨跌覆盖规则计算结果。
- `manual` 假设默认保持 `pending`，除非有明确人工确认记录。
- 任何状态更新必须保留此前状态和本次证据。

---

## 7. 第一版自动验证规则

MVP 只实现四类规则。

### 7.1 `price_threshold`

用于个股、ETF、指数或板块价格阈值。

```json
{
  "type": "price_threshold",
  "entity": "399006.SZ",
  "field": "close",
  "operator": ">",
  "value": 3486,
  "unit": "point",
  "required_days": 2
}
```

### 7.2 `relative_return`

用于标的相对基准的区间超额收益。

```json
{
  "type": "relative_return",
  "entity": "行业或板块代码",
  "benchmark": "000300.SH",
  "operator": ">=",
  "value": 2.0,
  "unit": "percentage_point",
  "window_trading_days": 5
}
```

### 7.3 `turnover_threshold`

用于全市场或标的成交额、成交量和换手率。

```json
{
  "type": "turnover_threshold",
  "entity": "A_SHARE",
  "field": "turnover",
  "operator": ">=",
  "value": 20000,
  "unit": "亿元",
  "required_days": 2
}
```

### 7.4 `capital_flow`

用于个股或板块资金流方向和连续性。

```json
{
  "type": "capital_flow",
  "entity": "个股或板块代码",
  "field": "main_net_inflow",
  "operator": ">",
  "value": 0,
  "unit": "元",
  "required_days": 3
}
```

暂不支持的自动规则统一标记为 `manual` 或 `hybrid`，不得为了提高自动化率进行近似判断。

---

## 8. CLI 设计

### 8.1 `daily-brief prepare`

职责：

- 验证日期和来源目录。
- 加载文章和覆盖率。
- 扫描历史 `hypotheses.json`。
- 应用后续 `verification.json`，重建每条假设的最新状态。
- 查找最近有效报告，而不是简单使用前一自然日。
- 根据交易日历计算活跃、到期和过期假设。
- 汇总每条假设所需证据。
- 写出 `codex-context.json`。

建议参数：

```powershell
daily-brief prepare --date YYYY-MM-DD
daily-brief prepare --date YYYY-MM-DD --source-dir PATH --out-dir PATH
```

### 8.2 `daily-brief verify`

职责：

- 加载活跃假设。
- 校验 `evidence.json`。
- 按规则和交易日执行确定性计算。
- 计算支持条件和证伪条件。
- 更新状态并写出 `verification.json`。
- 对缺失数据显式返回 `unavailable` 或继续 `pending`。

建议参数：

```powershell
daily-brief verify --date YYYY-MM-DD
daily-brief verify --date YYYY-MM-DD --evidence PATH --out-dir PATH
```

### 8.3 `daily-brief validate`

职责：

- 校验所有当日产物存在。
- 校验 JSON schema 和版本。
- 校验假设 ID 唯一性。
- 校验来源、引用、URL、期限和标的代码。
- 校验验证状态与证据一致。
- 禁止无确定性证据的 `confirmed` 或 `falsified`。
- 校验日报中的验证章节与 `verification.json` 一致。
- 校验新假设表与 `hypotheses.json` 一致。
- 生成 HTML。
- 写出 `run-manifest.json`。

建议参数：

```powershell
daily-brief validate --date YYYY-MM-DD
daily-brief validate --date YYYY-MM-DD --strict
```

`--strict` 下任何结构、来源或一致性错误都返回非零退出码。

---

## 9. 代码结构

第一版新增：

```text
pipeline/
  hypothesis_models.py       数据模型、枚举和基础校验
  hypothesis_io.py           每日产物读写和历史扫描
  hypothesis_rules.py        四类确定性验证规则
  hypothesis_workflow.py     prepare、verify、validate 编排
  report_validator.py        Markdown 与结构化产物一致性校验

skill/daily-investment-brief/references/
  hypothesis-contract.md     Codex 读写假设和证据时必须遵守的契约

tests/
  test_hypothesis_models.py
  test_hypothesis_io.py
  test_hypothesis_rules.py
  test_hypothesis_workflow.py
  test_report_validator.py
```

修改：

```text
pipeline/cli.py
skill/daily-investment-brief/SKILL.md
README.md
```

可选修改：

```text
pipeline/html.py
```

只有在验证章节需要特殊样式或锚点时才修改 HTML 层。

---

## 10. Skill 工作流调整

项目 Skill 中原有的默认生成步骤：

```text
collect -> generate
```

调整为：

```text
collect
  -> prepare
  -> Codex 补 evidence.json
  -> verify
  -> Codex 写 daily-brief.md 和 hypotheses.json
  -> validate
```

Skill 必须要求 Codex：

- 完整读取 `hypothesis-contract.md`。
- 先验证历史假设，再生成当日报告。
- 金融数据优先使用结构化金融 MCP。
- 名称必须先消歧成唯一 `thscode`。
- 公告和政策优先使用官方来源。
- 不得把社交媒体内容作为事实验证的最终依据。
- 不得直接编辑 `verification.json` 中的确定性状态。
- 校验失败时读取错误、修正产物并重跑。
- PART-B 继续保持独立，失败不得阻塞普通文章简报。

---

## 11. 行情与事件数据策略

### 第一版行情数据

Codex 直接调用已连接的金融 MCP 获取：

- A 股和 ETF 行情快照。
- A 股、ETF、指数和板块历史行情。
- 交易日历。
- 指数和板块成分。
- 估值和财务指标。
- 涨停、异动、热榜、龙虎榜。
- 项目已有资金流 MCP。

Codex 将实际观测值、数据源、请求 ID 和时间写入 `evidence.json`。

### 第一版公告和政策数据

由 Codex 搜索并阅读官方来源，不新增通用爬虫：

- 巨潮资讯。
- 上交所、深交所、北交所。
- 上市公司官网。
- 中国政府网。
- 人民银行、证监会、发改委、工信部、财政部、商务部等主管部门。
- 海外监管机构的正式文件页面。

只有高频、稳定且反复需要的官方来源，才在后续版本中实现项目内采集器。

### 明确边界

- 当前金融数据服务不覆盖分钟 K、tick、Level-2。
- 港股、美股、期货、期权和商品价格需要后续增加独立 provider。
- 行业价格、订单和供应链数据不能用股票涨跌近似代替。
- 缺少事实数据时必须保留 `pending`、`inconclusive` 或 `unavailable`。

---

## 12. 报告结构调整

日报继续保留现有结构，但「上期观察点验证」改为从 `verification.json` 渲染或严格转写。

建议表格：

```markdown
| 假设 | 验证期限 | 本期观测 | 状态 | 证据来源 |
|---|---|---|---|---|
| 科技修复具备持续性 | 3个交易日 | 创业板条件满足，成交额持续性不足 | ⚠ 部分兑现 | 同花顺行情 |
```

「下期关注」继续由 Codex 生成可读表格，但必须与当日 `hypotheses.json` 一一对应。

报告中不得出现以下不一致：

- Markdown 写「已兑现」，JSON 写 `pending`。
- Markdown 有新假设，但 `hypotheses.json` 不存在。
- JSON 有假设，但报告未展示。
- 报告引用具体数据，但 `evidence.json` 没有对应记录。

---

## 13. 首次迁移

以 `reports/2026-08-06/daily-brief.md` 为起点：

1. 读取其中的「下期关注」表格。
2. 将每条关注点转换为第一份 `hypotheses.json`。
3. 为可量化假设补充唯一证券、指数或板块代码。
4. 为暂时不能量化的政策和产业假设标记 `hybrid` 或 `manual`。
5. 不回溯重写所有历史报告。
6. 从下一期日报开始正式生成 `evidence.json` 和 `verification.json`。

迁移过程必须保留原报告文字和来源，不得为了适应规则而改变原始判断含义。

---

## 14. 测试计划

### 数据模型

- 拒绝重复假设 ID。
- 拒绝缺少原文来源的假设。
- 拒绝没有期限的假设。
- 拒绝自动验证假设缺少标的代码。
- 拒绝 `confirmed` 作为新假设初始状态。
- 拒绝未知 schema 版本和状态值。

### 历史扫描

- 跨周末找到最近有效报告。
- 跳过没有 `hypotheses.json` 的旧报告。
- 正确叠加多日 `verification.json` 更新。
- 重复运行结果保持一致。
- 漏跑一天不会丢失活跃假设。

### 验证规则

- 单日满足但连续天数不足时输出 `partially_confirmed`。
- 所有必要条件满足时输出 `confirmed`。
- 强证伪条件满足时优先输出 `falsified`。
- 支持和证伪条件同时出现时输出 `inconclusive`。
- 数据缺失时不生成方向性结果。
- 正确处理百分数、百分点、元、亿元和点位单位。
- 正确使用交易日而不是自然日。

### 报告校验

- Markdown 验证表与 `verification.json` 状态一致。
- Markdown 新假设与 `hypotheses.json` 一致。
- 每个行情数字存在对应证据记录。
- 官方事件结论存在官方 URL 和原文引用。
- 缺失文件或 schema 错误时返回非零退出码。

### 回归测试

- 现有 `collect`、`collect-one`、`capital-daily` 和 HTML 输出测试继续通过。
- 核心测试命令固定为 `pytest -q tests`。

---

## 15. 实施阶段

### 阶段一：契约与模型

- 新增数据模型和枚举。
- 定义五个 JSON 产物的 schema。
- 实现文件读写和历史扫描。
- 添加模型与 I/O 测试。

完成标准：可以读取历史目录并列出所有活跃假设。

### 阶段二：确定性验证

- 实现四类 MVP 规则。
- 实现状态机。
- 实现交易日窗口处理。
- 实现 `prepare` 和 `verify`。
- 添加规则和工作流测试。

完成标准：给定人工准备的 `evidence.json`，程序可以稳定生成 `verification.json`。

### 阶段三：报告校验与 CLI

- 实现 `validate`。
- 校验 Markdown 与结构化产物一致性。
- 生成 HTML 和 `run-manifest.json`。
- 补充 CLI 帮助和 README。

完成标准：不合格日报无法通过严格验证。

### 阶段四：Codex Skill 接入

- 新增 `hypothesis-contract.md`。
- 修改 Skill 默认日报工作流。
- 明确金融 MCP 和官方来源使用规则。
- 增加错误修复和重试步骤。

完成标准：用户只说「生成今天的日报」，Codex 能自动完成新流程。

### 阶段五：首批假设迁移

- 将 2026-08-06 下期关注转换为结构化假设。
- 用下一交易日数据完成首次验证。
- 检查报告可读性和证据完整性。

完成标准：连续两期报告形成完整的「提出 -> 获取证据 -> 验证 -> 新假设」闭环。

---

## 16. MVP 验收标准

功能验收：

- 用户日常仍只需发出一次「生成日报」请求。
- 每期生成 3-5 条结构化假设。
- 每条假设都有来源、原文、期限和反证条件。
- 可量化假设可以由真实行情证据自动验证。
- 周末、节假日和漏跑日期不影响历史假设延续。
- 所有 `confirmed` 和 `falsified` 结果可以回溯到结构化证据。
- 数据缺失不会被改写为多空结论。
- 日报、假设、证据和验证文件状态一致。

质量验收：

- 新增测试全部通过。
- 原有核心测试全部通过。
- 同一输入重复执行 `verify` 得到完全一致的结果。
- `validate --strict` 能阻止无来源、无期限、无证据或状态冲突的产物。
- 所有文件使用 UTF-8 和稳定字段顺序，便于人工审查和版本比较。

---

## 17. 后续扩展

MVP 稳定后再评估：

1. 将 JSON 假设账本迁移到 SQLite。
2. 接入高频官方公告采集器。
3. 增加财报指标、估值和事件规则。
4. 增加港股、美股、商品和期权数据 provider。
5. 自动生成周度、月度假设复盘。
6. 统计作者、主题和验证类型的历史表现。
7. 将用户个人判断和 AI 假设分开比较。
8. 增加本地只读假设看板。

作者统计必须按假设类型、期限、难度和数据可验证性分组，不得简单使用单一「命中率」评价投资能力。

---

## 18. 风险与控制

### Codex 写出错误结构

控制：使用严格 schema、`validate --strict` 和可操作的错误信息，失败后由 Codex 修正并重跑。

### 标的名称消歧错误

控制：自动验证规则必须保存唯一 `thscode`；无法唯一消歧时转为 `manual`，不得猜测。

### 数据源口径不一致

控制：证据必须保存 provider、单位、复权口径、日期和请求 ID；同一规则不得混用不兼容口径。

### 事件来源不可靠

控制：使用证据等级；媒体和社交材料不能独立触发正式结论。

### 为提高自动化率而错误量化

控制：第一版只允许四类明确规则，其他内容保留人工或混合验证。

### 日报写作覆盖确定性结果

控制：最终状态以 `verification.json` 为唯一事实来源，Markdown 只能转写和解释。

---

## 19. 最终原则

这套功能的目标不是让系统对所有投资观点给出机械评分，而是建立一条可靠的证据链：

```text
谁在什么时间
  -> 基于什么材料
  -> 提出了什么可证伪判断
  -> 需要观察哪些数据
  -> 实际发生了什么
  -> 最终状态如何变化
```

Codex 提供理解和写作能力，项目代码提供纪律、状态和可复现性。任何无法由可靠数据支持的结论，都必须明确保留为未知，而不是通过文字润色制造确定性。
