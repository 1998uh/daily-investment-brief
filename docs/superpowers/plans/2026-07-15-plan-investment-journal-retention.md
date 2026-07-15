# Plan: 日报升级为个人投研工作台

**目标**：把现有每日投资简报从“信息汇总”升级为“信息输入 + 个人判断 + 假设验证 + 周/月复盘”的训练系统。  
**默认路径**：日报仍输出到 `reports/<date>/`，个人判断输出到 `journal/YYYY/MM/`。  
**第一阶段范围**：模板、脚本、归档结构和自动 journal 创建；不做复杂前端页面。

---

## Task 1: 日报模板加入训练模块

**文件**：`templates/final_brief_prompt.md`、`templates/daily_brief_prompt.md`、`templates/direct_brief_prompt.md`

- 在标题元信息后增加“今日三句话”
- 将“下期关注”升级为可证伪的“待验证假设”
- 在简报末尾增加空白“我的判断区”
- 明确要求 AI 不代填个人判断区

**验证**：生成的 `daily-brief.md` 包含“今日三句话”“待验证假设”“我的判断区”。

---

## Task 2: 新增个人判断 journal

**文件**：`pipeline/workstation.py`、`scripts/new_journal_entry.py`

- 新增 `journal/YYYY/MM/YYYY-MM-DD.md`
- 每天生成固定个人判断模板
- 已存在文件默认不覆盖，避免覆盖手写内容

**验证**：

```powershell
python scripts/new_journal_entry.py --date 2026-07-15
```

---

## Task 3: 日报生成后自动创建 journal

**文件**：`pipeline/cli.py`

- `generate` 命令写出 Markdown/HTML 后自动创建当天 journal
- 命令行输出 journal 状态：`created` 或 `exists`
- 不影响 `--markdown-only`、`--from-batches` 等已有流程

**验证**：运行日报生成后，自动出现对应 `journal/YYYY/MM/YYYY-MM-DD.md`。

---

## Task 4: 新增周复盘和月复盘模板

**文件**：`pipeline/workstation.py`、`scripts/new_weekly_review.py`、`scripts/new_monthly_review.py`

- 周复盘输出到 `reviews/weekly/YYYY-Www.md`
- 月复盘输出到 `reviews/monthly/YYYY-MM.md`
- 周复盘自动索引当周已有日报和 journal
- 月复盘自动索引当月已有周复盘

**验证**：

```powershell
python scripts/new_weekly_review.py --week 2026-W29
python scripts/new_monthly_review.py --month 2026-07
```

---

## Task 5: 新增长期知识库模板

**文件**：`pipeline/workstation.py`、`scripts/init_knowledge_base.py`

- 新增主题模板：`knowledge/themes/_template.md`
- 新增公司模板：`knowledge/companies/_template.md`
- 新增错题模板：`knowledge/mistakes/_template.md`

**验证**：

```powershell
python scripts/init_knowledge_base.py
```

---

## 使用流程

### 每天

1. 生成日报
2. 阅读“今日三句话”和“待验证假设”
3. 用 5-10 分钟填写当天 journal

### 每周

1. 生成周复盘模板
2. 对照当周日报和 journal
3. 记录正确判断、错误判断和下周待验证假设

### 每月

1. 生成月复盘模板
2. 从周复盘中压缩长期判断
3. 更新 `knowledge/` 中的主题、公司和错题卡片

---

## 验收标准

- 现有测试通过
- 日报生成流程保持兼容
- 新日报包含训练模块
- journal 默认不覆盖用户手写内容
- 周/月复盘脚本能生成可直接填写的 Markdown
- 知识库初始化脚本能创建三类模板
