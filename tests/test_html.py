from pipeline.html import markdown_to_html, wrap_html


def test_mermaid_fence_becomes_renderable_container():
    rendered = markdown_to_html("```mermaid\nflowchart LR\n  A --> B\n```")

    assert '<div class="mermaid">' in rendered
    assert "flowchart LR" in rendered
    assert "<pre><code class=\"language-mermaid\">" not in rendered


def test_wrap_html_loads_mermaid_only_when_needed():
    mermaid_html = wrap_html("```mermaid\nflowchart LR\n  A --> B\n```", "Brief")
    plain_html = wrap_html("```text\nhello\n```", "Brief")

    assert "mermaid@11" in mermaid_html
    assert "mermaid@11" not in plain_html
    assert '<pre><code class="language-text">' in plain_html
