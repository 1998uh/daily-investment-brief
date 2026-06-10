from __future__ import annotations

import html
import re


def render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return escaped


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    i = 0

    def flush_paragraph() -> None:
        if paragraph:
            parts.append(f"<p>{render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            if in_code:
                parts.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        if stripped == "---":
            flush_paragraph()
            parts.append("<hr>")
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            parts.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            flush_paragraph()
            table_lines = [stripped, lines[i + 1].strip()]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            parts.append(_render_table(table_lines))
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            parts.append(f"<blockquote>{render_inline(' '.join(quote_lines))}</blockquote>")
            continue

        if re.match(r"^[-*]\s+", stripped):
            flush_paragraph()
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            parts.append("<ul>" + "".join(f"<li>{render_inline(item)}</li>" for item in items) + "</ul>")
            continue

        ordered = re.match(r"^\d+\.\s+", stripped)
        if ordered:
            flush_paragraph()
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            parts.append("<ol>" + "".join(f"<li>{render_inline(item)}</li>" for item in items) + "</ol>")
            continue

        paragraph.append(stripped)
        i += 1

    flush_paragraph()
    return "\n".join(parts)


def wrap_html(markdown: str, title: str) -> str:
    body = markdown_to_html(markdown)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #1f2933;
      --muted: #667085;
      --line: #d9dee7;
      --bg: #f7f8fa;
      --paper: #ffffff;
      --accent: #0f766e;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.72;
    }}
    article {{
      max-width: 920px;
      margin: 32px auto;
      padding: 40px;
      background: var(--paper);
      border: 1px solid var(--line);
    }}
    h1, h2, h3 {{ line-height: 1.25; }}
    h1 {{ font-size: 34px; margin-top: 0; }}
    h2 {{ margin-top: 42px; padding-top: 10px; border-top: 2px solid var(--line); }}
    h3 {{ margin-top: 26px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 18px 0; font-size: 14px; }}
    th, td {{ border: 1px solid var(--line); padding: 8px 10px; vertical-align: top; }}
    th {{ background: #eef5f4; text-align: left; }}
    blockquote {{ margin: 18px 0; padding: 10px 16px; border-left: 4px solid var(--accent); background: #f1f7f6; }}
    code, pre {{ background: #f0f2f5; }}
    code {{ padding: 1px 4px; }}
    pre {{ padding: 16px; overflow-x: auto; }}
    hr {{ border: 0; border-top: 1px solid var(--line); margin: 28px 0; }}
    @media (max-width: 720px) {{
      article {{ margin: 0; padding: 20px; border: 0; }}
      h1 {{ font-size: 28px; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <article>
{body}
  </article>
</body>
</html>
"""


def _is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.match(r"^:?-{3,}:?$", cell) for cell in cells)


def _render_table(lines: list[str]) -> str:
    header = _split_table_row(lines[0])
    rows = [_split_table_row(line) for line in lines[2:]]
    html_rows = [
        "<thead><tr>"
        + "".join(f"<th>{render_inline(cell)}</th>" for cell in header)
        + "</tr></thead>"
    ]
    html_rows.append(
        "<tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{render_inline(cell)}</td>" for cell in row) + "</tr>"
            for row in rows
        )
        + "</tbody>"
    )
    return "<table>" + "".join(html_rows) + "</table>"


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]
