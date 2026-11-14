from argparse import Namespace
from datetime import date

from pipeline import cli


def test_skips_when_snapshot_exists_without_force(tmp_path, monkeypatch):
    (tmp_path / "market-metrics.json").write_text("{}", encoding="utf-8")
    (tmp_path / "market-trend.png").write_bytes(b"png")
    called = []
    monkeypatch.setattr(cli, "fetch_market_inputs", lambda **k: called.append(k))
    args = Namespace(date="2026-11-14", days=20, force=False, out_dir=str(tmp_path))

    assert cli.market_snapshot_command(args) == 0
    assert called == []


def test_writes_json_and_chart_with_force(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli,
        "fetch_market_inputs",
        lambda **k: {
            "turnover": {date(2026, 11, 13): 1.65e12},
            "margin": {},
            "etf_store": {},
            "etf_snapshot": None,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        cli,
        "render_market_trend",
        lambda points, path, **k: path.write_bytes(b"png"),
    )
    args = Namespace(date="2026-11-14", days=20, force=True, out_dir=str(tmp_path))

    assert cli.market_snapshot_command(args) == 0
    assert (tmp_path / "market-metrics.json").exists()
    assert (tmp_path / "market-trend.png").exists()


def test_rejects_bad_date(tmp_path):
    args = Namespace(date="not-a-date", days=20, force=False, out_dir=str(tmp_path))
    assert cli.market_snapshot_command(args) == 2
