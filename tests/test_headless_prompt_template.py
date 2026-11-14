from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "headless_daily_brief_prompt.md"


def test_template_names_all_required_inputs_and_guards():
    text = TEMPLATE.read_text(encoding="utf-8")
    required = (
        "AGENTS.md",
        "skill/daily-investment-brief/SKILL.md",
        "templates/direct_brief_prompt.md",
        "codex-context.json",
        "article-pack.md",
        "不要运行任何命令",
        "数据源不完整",
        "DONE",
        "{{DATE}}",
        "{{COUNTS}}",
    )
    for token in required:
        assert token in text
