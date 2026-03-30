"""Convert translated Chinese Markdown to PDF via WeasyPrint.

Usage:
    python md_to_pdf.py work/p5_translated/ch01.md --output output/pdf/book.pdf --title "教育関係法（中文译本）"
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import markdown
from weasyprint import HTML


CSS = """
@page {
    size: A4;
    margin: 2.5cm 2.5cm 2.5cm 3cm;
    @bottom-center { content: counter(page); font-size: 10pt; color: #666; }
}
body {
    font-family: "Noto Serif CJK SC", "WenQuanYi Micro Hei", serif;
    font-size: 11pt;
    line-height: 1.8;
    color: #222;
}
h1 { font-size: 22pt; margin-top: 2em; margin-bottom: 0.8em; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 16pt; margin-top: 1.5em; margin-bottom: 0.5em; }
h3 { font-size: 13pt; margin-top: 1.2em; margin-bottom: 0.4em; }
p { text-indent: 2em; margin: 0.3em 0; text-align: justify; orphans: 3; widows: 3; }
blockquote { margin: 1em 2em; padding-left: 1em; border-left: 3px solid #ccc; color: #555; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 10pt; }
th, td { border: 1px solid #999; padding: 4px 8px; text-align: left; }
th { background: #f0f0f0; font-weight: bold; }
img { max-width: 90%; display: block; margin: 1em auto; }
code { font-family: "Noto Sans Mono CJK SC", monospace; background: #f5f5f5; padding: 1px 4px; font-size: 0.9em; }
pre { background: #f5f5f5; padding: 1em; overflow-x: auto; font-size: 0.9em; }
hr { border: none; border-top: 1px solid #ccc; margin: 2em 0; }
.cover { text-align: center; page-break-after: always; padding-top: 30%; }
.cover h1 { font-size: 28pt; page-break-before: avoid; }
.cover .subtitle { font-size: 14pt; color: #666; margin-top: 1em; }
"""


def build_cover(title: str) -> str:
    return f"""<div class="cover">
<h1>{title}</h1>
<p class="subtitle">中文翻译版</p>
</div>
"""


def main():
    parser = argparse.ArgumentParser(description="Convert translated Markdown to PDF")
    parser.add_argument("input_files", nargs="+", help="Translated Markdown file(s)")
    parser.add_argument("--output", default="output/pdf/book.pdf", help="Output PDF path")
    parser.add_argument("--title", default="教育関係法（中文译本）", help="Book title")
    args = parser.parse_args()

    md_parts = []
    for f in args.input_files:
        p = pathlib.Path(f)
        if not p.is_file():
            print(f"File not found: {p}", file=sys.stderr)
            sys.exit(1)
        md_parts.append(p.read_text(encoding="utf-8"))

    md_text = "\n\n".join(md_parts)

    extensions = ["tables", "fenced_code", "footnotes", "toc"]
    html_body = markdown.markdown(md_text, extensions=extensions)

    cover = build_cover(args.title)
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
{cover}
{html_body}
</body>
</html>"""

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating PDF: {out_path} …", file=sys.stderr, flush=True)
    HTML(string=full_html).write_pdf(str(out_path))
    size_kb = out_path.stat().st_size / 1024
    print(f"Done. {out_path} ({size_kb:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
