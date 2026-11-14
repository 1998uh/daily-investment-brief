你正在无人值守模式下生成 {{DATE}} 的投资日报。

必读文件（按顺序完整读取）：
- AGENTS.md
- skill/daily-investment-brief/SKILL.md
- templates/direct_brief_prompt.md
- reports/{{DATE}}/codex-context.json
- reports/{{DATE}}/article-pack.md

无人值守覆盖：
- 采集、social-health、materialize、prepare 已由外层脚本完成。不要运行任何命令，不要尝试自行采集或重建目录。
- 只写 reports/{{DATE}}/daily-brief.md，不要生成 HTML。
- 不要调用 generate、fallback 或任何外部模型。

当日各平台文章数：{{COUNTS}}。
若任一平台为 0，仍按用户长期授权正常写作，但必须在标题元信息和数据覆盖章节显著标注“数据源不完整”，并列出缺失平台；不得写成“当日无观点”或“市场静默”。

完成后只输出一行 DONE。
