# 旧版与外部模型流程

仅在用户明确要求时使用。普通日报默认走 Codex 原生流程。

## 内部 LLM 全流程

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD
python -m pipeline.cli generate --date YYYY-MM-DD
```

## 导出完整外部 Prompt

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD --no-batches
```

输出 `reports/YYYY-MM-DD/prompt-for-external.md`，交给外部模型生成 Markdown。

## 只生成批次提炼

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD --batches-only
```

输出 `batch-summaries.json`。用 `templates/final_brief_prompt.md` 做最终合成。

## 外部合成后写回

把 Markdown 写入 `reports/YYYY-MM-DD/daily-brief.md`，然后运行：

```powershell
python -m pipeline.cli generate --date YYYY-MM-DD --from-batches
```

## 采集配置检查

```powershell
python -m pipeline.cli collect --date YYYY-MM-DD --dry-run
```

相关环境变量：`BRIEF_BASE_URL`、`BRIEF_MODEL`、`BRIEF_API_KEY`、
`BRIEF_BATCH_MAX_CHARS`、`BRIEF_MAX_CHARS_PER_ARTICLE`、
`BRIEF_LLM_BATCH_CONCURRENCY`。采集 Cookie 使用 `XUEQIU_COOKIE`、`WEIBO_COOKIE`、
`WECHAT_COOKIE`。
