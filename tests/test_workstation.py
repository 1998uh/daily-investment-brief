from __future__ import annotations

from datetime import date

from pipeline import workstation


def test_create_journal_entry_does_not_overwrite_existing(tmp_path):
    result = workstation.create_journal_entry(date(2026, 7, 15), root=tmp_path)
    assert result.created
    assert result.path.exists()
    assert "今日最重要信息" in result.path.read_text(encoding="utf-8")

    result.path.write_text("custom note", encoding="utf-8")
    second = workstation.create_journal_entry(date(2026, 7, 15), root=tmp_path)
    assert not second.created
    assert second.path.read_text(encoding="utf-8") == "custom note"


def test_create_weekly_review_indexes_existing_report_and_journal(tmp_path):
    report = tmp_path / "reports" / "2026-07-15" / "daily-brief.md"
    report.parent.mkdir(parents=True)
    report.write_text("# report", encoding="utf-8")
    workstation.create_journal_entry(date(2026, 7, 15), root=tmp_path)

    result = workstation.create_weekly_review("2026-W29", root=tmp_path)
    text = result.path.read_text(encoding="utf-8")

    assert result.created
    assert "2026-W29 投资复盘" in text
    assert "../../reports/2026-07-15/daily-brief.md" in text
    assert "../../journal/2026/07/2026-07-15.md" in text


def test_create_monthly_review_indexes_existing_weekly_review(tmp_path):
    weekly = tmp_path / "reviews" / "weekly" / "2026-W29.md"
    weekly.parent.mkdir(parents=True)
    weekly.write_text("# weekly", encoding="utf-8")

    result = workstation.create_monthly_review("2026-07", root=tmp_path)
    text = result.path.read_text(encoding="utf-8")

    assert result.created
    assert "2026-07 月度复盘" in text
    assert "../weekly/2026-W29.md" in text


def test_ensure_knowledge_base_creates_templates(tmp_path):
    results = workstation.ensure_knowledge_base(root=tmp_path)
    assert all(result.created for result in results)
    assert (tmp_path / "knowledge" / "themes" / "_template.md").exists()
    assert (tmp_path / "knowledge" / "companies" / "_template.md").exists()
    assert (tmp_path / "knowledge" / "mistakes" / "_template.md").exists()
