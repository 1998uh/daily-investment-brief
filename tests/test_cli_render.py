from argparse import Namespace

from pipeline.cli import render_html_command


def test_render_html_writes_file_and_passes_check(tmp_path):
    out = tmp_path / "2026-11-14"
    out.mkdir()
    md = "# 📊 每日投资简报 — 2026年11月14日（周六·盘前）\n\n" + (
        "## 今日三句话\n## 一、💼 博主持仓信息\n## 二、📡 博主看好方向汇总\n"
        "## 三、⚡ 今日注意事项与投资总结\n## N-3、📋 数据覆盖情况\n" + "正文" * 1600
    )
    (out / "daily-brief.md").write_text(md, encoding="utf-8")
    code = render_html_command(Namespace(date="2026-11-14", out_dir=str(out), check=True))
    assert code == 0
    assert (out / "daily-brief.html").read_text(encoding="utf-8").startswith("<!doctype html>")
