import json
from argparse import Namespace

from pipeline import cli

VALID_MD = "# 📊 每日投资简报 — 2026年11月14日\n\n" + (
    "## 今日三句话\n## 一、💼 博主持仓信息\n## 二、📡 博主看好方向汇总\n"
    "## 三、⚡ 今日注意事项与投资总结\n## N-3、📋 数据覆盖情况\n" + "正文" * 1600
)


def _args(tmp_path, **kw):
    base = dict(
        date="2026-11-14",
        out_dir=str(tmp_path),
        force=False,
        dry_run=False,
        failure_stage=None,
        failure_detail="",
        failure_log=[],
    )
    base.update(kw)
    return Namespace(**base)


def _write_report(tmp_path):
    (tmp_path / "daily-brief.md").write_text(VALID_MD, encoding="utf-8")
    (tmp_path / "daily-brief.html").write_text("<html>ok</html>", encoding="utf-8")


def test_send_email_skips_when_marker_exists(tmp_path, monkeypatch):
    (tmp_path / ".email-sent.json").write_text('{"message_id": "<1>"}', encoding="utf-8")
    called = []
    monkeypatch.setattr(cli, "send_report_email", lambda **k: called.append(k) or "<1>")
    assert cli.send_email_command(_args(tmp_path)) == 0
    assert called == []


def test_send_email_writes_marker_after_send(tmp_path, monkeypatch):
    _write_report(tmp_path)
    monkeypatch.setattr(cli, "send_report_email", lambda **k: "<mid@qq.com>")
    assert cli.send_email_command(_args(tmp_path)) == 0
    marker = json.loads((tmp_path / ".email-sent.json").read_text(encoding="utf-8"))
    assert marker["message_id"] == "<mid@qq.com>"


def test_send_email_returns_nonzero_when_smtp_fails(tmp_path, monkeypatch):
    _write_report(tmp_path)

    def boom(**kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(cli, "send_report_email", boom)
    assert cli.send_email_command(_args(tmp_path)) == 1


def test_send_email_blocks_when_gate_fails(tmp_path, monkeypatch):
    (tmp_path / "daily-brief.md").write_text("太短", encoding="utf-8")
    (tmp_path / "daily-brief.html").write_text("<html>ok</html>", encoding="utf-8")
    called = []
    monkeypatch.setattr(cli, "send_report_email", lambda **k: called.append(k) or "<1>")
    assert cli.send_email_command(_args(tmp_path)) == 1
    assert called == []


def test_failure_email_writes_only_the_failure_marker(tmp_path, monkeypatch):
    _write_report(tmp_path)
    monkeypatch.setattr(cli, "send_failure_email", lambda **k: "<failure@qq.com>")

    assert cli.send_email_command(_args(tmp_path, failure_stage="headless")) == 0

    assert (tmp_path / ".email-failure-sent.json").exists()
    assert not (tmp_path / ".email-sent.json").exists()


def test_report_email_is_not_blocked_by_failure_marker(tmp_path, monkeypatch):
    _write_report(tmp_path)
    (tmp_path / ".email-failure-sent.json").write_text('{"message_id": "<f>"}', encoding="utf-8")
    sent = []
    monkeypatch.setattr(cli, "send_report_email", lambda **k: sent.append(k) or "<mid>")

    assert cli.send_email_command(_args(tmp_path)) == 0

    assert len(sent) == 1
    assert (tmp_path / ".email-sent.json").exists()


def test_failure_email_reads_detail_from_log_file(tmp_path, monkeypatch):
    log = tmp_path / "failure.log"
    log.write_text("collect failed: boom", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(cli, "send_failure_email", lambda **k: captured.update(k) or "<f>")

    assert cli.send_email_command(
        _args(tmp_path, failure_stage="headless", failure_log=[str(log)])
    ) == 0

    assert "collect failed: boom" in captured["detail"]


def test_failure_email_is_deduped_by_failure_marker(tmp_path, monkeypatch):
    _write_report(tmp_path)
    (tmp_path / ".email-failure-sent.json").write_text('{"message_id": "<f>"}', encoding="utf-8")
    called = []
    monkeypatch.setattr(cli, "send_failure_email", lambda **k: called.append(k) or "<f2>")

    assert cli.send_email_command(_args(tmp_path, failure_stage="headless")) == 0

    assert called == []
