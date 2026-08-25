# WeRead 公众号 Book ID 配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将用户提供的五个 WeRead 公众号详情链接解析出的完整 `MP_WXS_...` 标识写入微信账号配置。

**Architecture:** 复用现有 `config/accounts.json` 结构，把 WeRead `bookId` 放在采集器已读取的 `uid` 字段中。现有公众号保留原有字段，新公众号使用同样的账号结构；不修改采集器逻辑。

**Tech Stack:** JSON、Python 标准库、项目内 `pipeline.collectors.accounts.load_accounts`。

---

### Task 1: 更新 WeRead 账号配置

**Files:**
- Modify: `config/accounts.json:22-45`

- [ ] **Step 1: 补充现有四个账号的 `uid` 并新增第五个账号**

在 `wechat` 数组中写入以下映射，保持每项的 `urls`、`rss_url` 和 `enabled` 字段：

```json
{
  "name": "柯中投研笔记",
  "uid": "MP_WXS_3083440260",
  "urls": [],
  "rss_url": "",
  "enabled": true
}
```

```json
{
  "name": "三岁小怪兽",
  "uid": "MP_WXS_3572504738",
  "urls": [],
  "rss_url": "",
  "enabled": true
}
```

```json
{
  "name": "猫笔刀",
  "uid": "MP_WXS_3198966508",
  "urls": [],
  "rss_url": "",
  "enabled": true
}
```

```json
{
  "name": "ETF领航员",
  "uid": "MP_WXS_3911694450",
  "urls": [],
  "rss_url": "",
  "enabled": true
}
```

```json
{
  "name": "热点投研",
  "uid": "MP_WXS_3077802861",
  "urls": [],
  "rss_url": "",
  "enabled": true
}
```

- [ ] **Step 2: Validate JSON syntax**

Run:

```powershell
python -c "import json; json.load(open('config/accounts.json', encoding='utf-8-sig')); print('JSON OK')"
```

Expected: `JSON OK` and exit code 0.

- [ ] **Step 3: Validate project account loading and exact mappings**

Run:

```powershell
python -c "from pathlib import Path; from pipeline.collectors.accounts import load_accounts; actual={a.name:a.uid for a in load_accounts(Path('config/accounts.json')) if a.source == '微信公众号'}; expected={'柯中投研笔记':'MP_WXS_3083440260','三岁小怪兽':'MP_WXS_3572504738','猫笔刀':'MP_WXS_3198966508','ETF领航员':'MP_WXS_3911694450','热点投研':'MP_WXS_3077802861'}; assert actual == expected, (actual, expected); assert all(v.startswith('MP_WXS_') for v in actual.values()); print(actual)"
```

Expected: the five-name mapping is printed and exit code 0.

- [ ] **Step 4: Inspect the focused diff and preserve unrelated worktree changes**

Run:

```powershell
git diff --check -- config/accounts.json
git diff -- config/accounts.json
git status --short
```

Expected: only the intended `config/accounts.json` diff is shown for this task; pre-existing `README.md` and `reports/archive/2026-08/04-week-08-17-to-08-22.md` changes remain present and untouched.

- [ ] **Step 5: Commit the configuration change**

```powershell
git add -- config/accounts.json
git diff --cached --check
git commit -m "feat: configure WeRead public account ids"
```
