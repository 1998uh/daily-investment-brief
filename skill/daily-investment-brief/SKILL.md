---
name: daily-investment-brief
description: Generate a daily A/H-share investment brief from manually imported Xueqiu, WeChat Official Account, and Weibo Markdown/JSON source articles.
---

# Daily Investment Brief Skill

Use this skill when the user wants to generate or adjust the daily investment brief project in this repository.

## Scope

- Inputs: automatically collected or manually imported Markdown/JSON articles under `sources/YYYY-MM-DD/`.
- Collectors: optional automatic collection from configured Xueqiu, WeChat, and Weibo accounts.
- Sources: 雪球、微信公众号、微博.
- Markets: A 股 + 港股.
- Time window: Beijing time `08:00 ~ next day 08:00`.
- Positioning: organize other authors' views; do not provide personalized buy/sell advice.
- Style: strong narrative, emoji, source attribution, author debates, core conflict diagram, next-watch list.

## Commands

Collect sources:

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD
```

Validate account config:

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD --dry-run
```

Generate a brief:

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD
```

Outputs:

```text
reports/YYYY-MM-DD/daily-brief.md
reports/YYYY-MM-DD/daily-brief.html
```

## Configuration

Read `.env` from the repository root.

Required for model generation:

```env
BRIEF_BASE_URL=https://api.deepseek.com/v1
BRIEF_MODEL=deepseek-chat
BRIEF_API_KEY=sk-...
```

If these values are missing, the CLI uses local fallback output for workflow verification.

Optional collector cookies:

```env
XUEQIU_COOKIE=
WEIBO_COOKIE=
WECHAT_COOKIE=
```

## Input Format

Recommended Markdown front matter:

```markdown
---
source: 雪球
author: 作者名
title: 文章标题
url: https://example.com/post
published_at: 2026-06-07 07:30
---

正文...
```

## Review Checklist

- Verify source counts and author coverage.
- Confirm each important claim has an author or account.
- Keep facts, author opinions, and editor synthesis separate.
- Remove duplicated articles before generation when obvious.
- Do not add direct buy/sell/position instructions.
- If the brief includes concrete market data, policy, filings, or prices, decide whether to run a separate fact-check pass.
