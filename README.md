# Daily Investment Brief

把雪球、微信公众号、微博的 Markdown/JSON 原文整理成每日投资简报。

第一版定位是“整理别人观点”，不主动给个性化买卖建议，也不默认做事实核验。它会保留作者立场、观点冲突、核心矛盾、下期关注和来源覆盖统计。

## 快速开始

1. 在项目目录创建本项目专属依赖环境 `.venv`：

```powershell
.\scripts\setup.ps1
```

如果需要采集雪球专栏/长文全文，安装采集扩展和 Playwright Chromium：

```powershell
.\scripts\setup.ps1 -InstallPlaywright
```

> `.venv/` 类似前端项目里的 `node_modules/`：依赖安装在当前项目目录，不提交到 Git，换电脑后重新运行 setup 脚本即可。

2. 激活本项目环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

3. 复制配置：

```powershell
Copy-Item .env.example .env
```

4. 在 `.env` 中填写 OpenAI-compatible API 和采集所需的 Cookie：

```env
BRIEF_BASE_URL=https://api.deepseek.com/v1
BRIEF_MODEL=deepseek-chat
BRIEF_API_KEY=sk-...

# 雪球 Cookie（必需，从浏览器 DevTools 复制）
XUEQIU_COOKIE=cookiesu=...; xq_a_token=...; u=...
# 微博 Cookie（可选）
WEIBO_COOKIE=
# 微信 Cookie（可选）
WECHAT_COOKIE=
```

5. 验证账号配置：

```powershell
daily-brief collect --date 2026-06-09 --dry-run
```

## 采集命令

### 全量采集（并行模式）

```powershell
daily-brief collect --date 2026-06-09
```

默认按平台分组并行采集（雪球 3 并发、微博 2 并发、微信 4 并发），运行过程中实时打印每个账号的进度：

```
[info] 并行模式: 雪球×3 | 微博×2 | 微信公众号×4
  ▶ 雪球/诸葛孔暗 ...
  ✓ 微信公众号/猫笔刀  2条  [1/25] 3s
  ✓ 雪球/诸葛孔暗  2条  [5/25] 45s
  ...
```

可选参数：

| 参数 | 说明 |
|------|------|
| `--sequential` | 关闭并行，串行逐个采集（调试用） |
| `--limit N` | 每个账号最多采集 N 条，默认 20 |
| `--include-undated` | 保留无法解析时间的条目 |
| `--and-generate` | 采集后直接生成简报 |
| `--dry-run` | 只验证配置，不实际采集 |

### 单博主采集

```powershell
daily-brief collect-one --name "诸葛孔暗" --date 2026-06-09
```

适合调试单个账号的采集效果。加 `--verbose` 可看到详细日志（API 请求、全文获取过程、Playwright 状态）：

```powershell
daily-brief collect-one --name "诸葛孔暗" --date 2026-06-09 --verbose
```

### 生成简报

```powershell
daily-brief generate --date 2026-06-09
```

采集 + 生成一步完成：

```powershell
daily-brief collect --date 2026-06-10 --and-generate
```

输出：

```text
reports/2026-06-09/daily-brief.md
reports/2026-06-09/daily-brief.html
```

没有配置 API key 时，CLI 会使用本地 fallback 摘要，便于先验证输入、统计和输出结构。

## 账号配置

复制示例配置：

```powershell
Copy-Item config/accounts.example.json config/accounts.json
```

格式示例：

```json
{
  "xueqiu": [
    {"name": "诸葛孔暗", "url": "https://xueqiu.com/u/用户ID", "uid": "用户ID", "enabled": true}
  ],
  "weibo": [
    {"name": "唐史主任司马迁", "url": "https://weibo.com/u/用户ID", "uid": "用户ID", "enabled": true}
  ],
  "wechat": [
    {"name": "中金宏观", "urls": ["https://mp.weixin.qq.com/s/文章ID"], "rss_url": "", "enabled": true}
  ]
}
```

- 雪球和微博必须填 `uid` 或含 uid 的 `url`
- 微信公众号支持 `urls`（文章直链）和 `rss_url`（RSSHub / WeWe RSS 等）
- 设置 `"enabled": false` 可临时跳过某账号

Cookie 在 `.env` 中配置，不要把账号密码写进项目：

```env
XUEQIU_COOKIE=cookiesu=...; xq_a_token=...   # 必需
WEIBO_COOKIE=                                   # 可选
WECHAT_COOKIE=                                  # 可选
```

## 雪球专栏/长文全文

雪球 type=3 专栏文章在 timeline API 中只返回 ~150 字摘要。系统会自动尝试多种方式获取全文：

1. `statuses/original/show.json` API
2. `v4/statuses/show.json` API
3. HTML 页面解析
4. **Playwright 浏览器内 fetch**（绕过阿里云 WAF JS 质询）

前三种方式可能被 WAF 拦截，**Playwright 是目前最可靠的方式**：

```powershell
.\scripts\setup.ps1 -InstallPlaywright
```

工作原理：启动无头 Chromium 访问雪球首页通过 WAF，然后在浏览器上下文内用 `fetch()` 请求 API，继承 WAF cookie。整个采集过程复用同一个浏览器实例。

> 未安装 Playwright 时不会报错，只是专栏文章降级为摘要。

## Markdown 输入格式

推荐使用 front matter：

```markdown
---
source: 雪球
author: 诸葛孔暗
title: A股盘后观察
url: https://example.com/post/1
published_at: 2026-06-07 07:30
---

正文内容...
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---:|---|
| source | 是 | `雪球`、`微信公众号`、`微博` |
| author | 否 | 作者或账号 |
| title | 否 | 文章标题 |
| url | 否 | 原文链接 |
| published_at | 否 | 发布时间 |

也支持 JSON：

```json
{
  "source": "微信公众号",
  "author": "某某投研",
  "title": "港股策略观察",
  "url": "https://example.com/article",
  "published_at": "2026-06-07 07:10",
  "content": "正文内容..."
}
```

## 目录

```text
config/                     账号清单
sources/                    原始输入，按日期放 Markdown/JSON
pipeline/                   生成流水线
  collectors/
    runner.py               并行/串行采集调度
    xueqiu.py               雪球采集（含全文获取）
    browser.py              Playwright WAF 绕过模块
    weibo.py                微博采集
    wechat.py               微信公众号采集
    accounts.py             账号加载
    writer.py               文件写入与去重
  cli.py                    命令行入口
  config.py                 配置加载（.env 读取）
templates/                  Prompt 和输出模板
reports/                    生成结果
scripts/                    调试脚本
```

## 审核清单

- 确认时间窗口是北京时间 `08:00-08:00`。
- 确认来源统计与实际文章数量一致。
- 确认每个观点都能追溯到作者或账号。
- 删除明显重复、无来源、纯情绪化但无信息量的内容。
- 简报只整理观点，不写成直接买卖建议。
- 如果出现具体价格、涨跌幅、政策、公告，人工决定是否补充事实核验。
