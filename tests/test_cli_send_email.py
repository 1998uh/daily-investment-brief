import json
from argparse import Namespace

from pipeline import cli


def _args(tmp_path, **kw):
    base = dict(
        date="2026-11-14",
        out_dir=str(tmp_path),
        force=False,
        dry_run=False,
        failure_stage=None,
        failure_detail="",
    )
    base.update(kw)
    return Namespace(**base)


def test_send_email_skips_when_marker_exists(tmp_path, monkeypatch):
    (tmp_path / ".email-sent.json").write_text('{"message_id": "<1>"}', encoding="utf-8")
    called = []
    monkeypatch.setattr(cli, "send_report_email", lambda **k: called.append(k) or "<1>")
    assert cli.send_email_command(_args(tmp_path)) == 0
    assert called == []


def test_send_email_writes_marker_after_send(tmp_path, monkeypatch):
    md = "# 📊 每日投资简报 — 2026年11月14日\n\n" + (
        "## 今日三句话\n## 一、💼 博主持仓信息\n## 二、📡 博主看好方向汇总\n"
        "## 三、⚡ 今日注意事项与投资总结\n## N-3、📋 数据覆盖情况\n" + "正文" * 1600
    )
    (tmp_path / "daily-brief.md").write_text(md, encoding="utf-8")
    (tmp_path / "daily-brief.html").write_text("<html>ok</html>", encoding="utf-8")
    monkeypatch.setattr(cli, "send_report_email", lambda **k: "<mid@qq.com>")
    assert cli.send_email_command(_args(tmp_path)) == 0
    marker = json.loads((tmp_path / ".email-sent.json").read_text(encoding="utf-8"))
    assert marker["message_id"] == "<mid@qq.com>"


def test_send_email_returns_nonzero_when_smtp_fails(tmp_path, monkeypatch):
    md = "# 📊 每日投资简报 — 2026年11月14日\n\n" + (
        "## 今日三句话\n## 一、💼 博主持仓信息\n## 二、📡 博主看好方向汇总\n"
        "## 三、⚡ 今日注意事项与投资总结\n## N-3、📋 数据覆盖情况\n" + "正文" * 1600
    )
    (tmp_path / "daily-brief.md").write_text(md, encoding="utf-8")
    (tmp_path / "daily-brief.html").write_text("<html>ok</html>", encoding="utf-8")

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
