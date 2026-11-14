from pipeline.html import inline_image_sources


def test_inlines_local_png_as_data_uri(tmp_path):
    (tmp_path / "market-trend.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    html = '<img alt="chart" src="market-trend.png" />'

    out = inline_image_sources(html, tmp_path)

    assert "data:image/png;base64," in out
    assert 'src="market-trend.png"' not in out


def test_leaves_remote_images_alone(tmp_path):
    html = '<img src="https://example.com/chart.png" />'

    assert inline_image_sources(html, tmp_path) == html
