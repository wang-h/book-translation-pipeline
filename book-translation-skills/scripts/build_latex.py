"""Convert translated Chinese Markdown chapters into a LaTeX book project.

Usage:
    python build_latex.py <translated_dir> [--output-dir output/latex] [--manifest config/chapter_manifest.json]

Generates book.tex, preamble.tex, frontmatter.tex, and chapters/*.tex.
"""

import argparse
import pathlib
import re
import sys


HEADING_MAP = {
    1: "\\chapter",
    2: "\\section",
    3: "\\subsection",
    4: "\\subsubsection",
}


def _format_author_table(author_lines: list[str]) -> str:
    """Format author introduction lines as a two-column longtable."""
    entries = []
    for al in author_lines:
        m = re.match(r'^(.+?（[^）]+）)\s*[…·・\s]*\s*(.*)$', al)
        if m:
            name_reading = m.group(1).strip()
            affil = m.group(2).strip() or "——"
            entries.append((name_reading, affil))
        elif al.strip():
            entries.append((al.strip(), ""))
    if not entries:
        return ""
    lines = [
        "{\\small",
        "\\setlength{\\LTleft}{0pt}",
        "\\setlength{\\LTright}{0pt}",
        "\\begin{longtable}{@{}p{0.38\\textwidth}p{0.58\\textwidth}@{}}",
    ]
    for name, affil in entries:
        lines.append(f"{escape_latex(name)} & {escape_latex(affil)} \\\\[3pt]")
    lines.append("\\end{longtable}")
    lines.append("}")
    return "\n".join(lines)


def md_to_latex(text: str) -> str:
    """Convert Markdown text to LaTeX body content.

    Heading hierarchy is trusted from the Markdown source (set by LLM in P2 repair).
    No content-specific rules here — pure mechanical mapping.
    """
    lines = text.split("\n")
    output = []

    in_list = None
    in_table = False
    table_rows = []
    in_author_section = False
    author_lines_buf = []

    for line in lines:
        stripped = line.strip()

        if in_author_section:
            if re.match(r"^#{1,6}\s+", stripped):
                output.append(_format_author_table(author_lines_buf))
                in_author_section = False
                author_lines_buf = []
            elif stripped:
                author_lines_buf.append(stripped)
                continue
            else:
                continue

        if re.match(r"^#{1,6}\s+", stripped):
            if in_list:
                output.append(f"\\end{{{in_list}}}")
                in_list = None
            level = len(re.match(r"^(#+)", stripped).group(1))
            title = stripped.lstrip("#").strip()
            cmd = HEADING_MAP.get(level, "\\subsubsection")
            output.append(f"{cmd}{{{escape_latex(title)}}}")
            if "执笔者介绍" in title or "執筆者紹介" in title:
                in_author_section = True
                author_lines_buf = []
            continue

        if stripped.startswith("|") and not in_table:
            in_table = True
            table_rows = [stripped]
            continue
        elif in_table and stripped.startswith("|"):
            table_rows.append(stripped)
            continue
        elif in_table and not stripped.startswith("|"):
            in_table = False
            output.append(convert_table(table_rows))
            table_rows = []

        if re.match(r"^[-*]\s+", stripped):
            if in_list != "itemize":
                if in_list:
                    output.append(f"\\end{{{in_list}}}")
                output.append("\\begin{itemize}")
                in_list = "itemize"
            item_text = re.sub(r"^[-*]\s+", "", stripped)
            output.append(f"  \\item {escape_latex(inline_format(item_text))}")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            if in_list != "enumerate":
                if in_list:
                    output.append(f"\\end{{{in_list}}}")
                output.append("\\begin{enumerate}")
                in_list = "enumerate"
            item_text = re.sub(r"^\d+\.\s+", "", stripped)
            output.append(f"  \\item {escape_latex(inline_format(item_text))}")
            continue

        if in_list and stripped == "":
            output.append(f"\\end{{{in_list}}}")
            in_list = None

        if stripped.startswith("> "):
            quote_text = stripped[2:]
            output.append(f"\\begin{{quote}}\n{escape_latex(inline_format(quote_text))}\n\\end{{quote}}")
            continue

        if stripped.startswith("!["):
            match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
            if match:
                alt, path = match.groups()
                output.append(f"\\begin{{figure}}[htbp]\n\\centering\n\\includegraphics[width=0.8\\textwidth]{{{path}}}\n\\caption{{{escape_latex(alt)}}}\n\\end{{figure}}")
            continue

        footnote_pattern = r"\[\^(\d+)\]"
        if re.search(footnote_pattern, stripped):
            def replace_fn(m):
                return f"\\footnote{{{m.group(1)}}}"
            stripped = re.sub(footnote_pattern, replace_fn, stripped)

        if stripped:
            output.append(escape_latex(inline_format(stripped)))
        else:
            output.append("")

    if in_list:
        output.append(f"\\end{{{in_list}}}")
    if in_table:
        output.append(convert_table(table_rows))
    if in_author_section and author_lines_buf:
        output.append(_format_author_table(author_lines_buf))

    return "\n".join(output)


def convert_table(rows: list[str]) -> str:
    """Convert Markdown table rows to LaTeX longtable."""
    if len(rows) < 2:
        return ""

    cells = [r.strip("|").split("|") for r in rows]
    header = cells[0]
    ncols = len(header)
    col_spec = "l" * ncols

    lines = [
        f"\\begin{{longtable}}{{{col_spec}}}",
        "\\toprule",
        " & ".join(escape_latex(c.strip()) for c in header) + " \\\\",
        "\\midrule",
        "\\endhead",
    ]

    for row in cells[2:]:
        cleaned = [escape_latex(c.strip()) for c in row[:ncols]]
        while len(cleaned) < ncols:
            cleaned.append("")
        lines.append(" & ".join(cleaned) + " \\\\")

    lines.append("\\bottomrule")
    lines.append("\\end{longtable}")
    return "\n".join(lines)


def escape_latex(text: str) -> str:
    """Escape LaTeX special characters, preserving math and commands."""
    if not text:
        return text
    text = re.sub(r"(?<!\\)&", r"\\&", text)
    text = re.sub(r"(?<!\\)%", r"\\%", text)
    text = re.sub(r"(?<!\\)#", r"\\#", text)
    text = re.sub(r"(?<!\\)_(?![^$]*\$)", r"\\_", text)
    return text


def inline_format(text: str) -> str:
    """Convert Markdown inline formatting to LaTeX."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
    text = re.sub(r"`(.+?)`", r"\\texttt{\1}", text)
    return text


PREAMBLE = r"""\documentclass[12pt, a4paper, openany]{book}
\usepackage[fontset=none]{ctex}
\usepackage{geometry}
\geometry{top=2.5cm, bottom=2.5cm, left=2.5cm, right=2.5cm, headheight=15pt}
\usepackage{fancyhdr}
\usepackage{titlesec}
\usepackage[hidelinks]{hyperref}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{graphicx}
\usepackage{amsmath, amssymb}
\usepackage{footmisc}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{fontspec}

\setCJKmainfont{Noto Serif CJK SC}
\setCJKsansfont{Noto Sans CJK SC}
\setCJKmonofont{Noto Sans Mono CJK SC}
\setmainfont{Noto Serif CJK SC}

\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE,RO]{\thepage}
\fancyhead[RE]{\leftmark}
\fancyhead[LO]{\rightmark}
\renewcommand{\headrulewidth}{0.4pt}

\titleformat{\chapter}[display]
  {\normalfont\huge\bfseries}{}{0pt}{\Huge}
\titlespacing*{\chapter}{0pt}{-20pt}{30pt}

\setlength{\parindent}{2em}
\setlength{\parskip}{0.3em}
\linespread{1.5}

\widowpenalty=10000
\clubpenalty=10000
\tolerance=1000
\emergencystretch=3em
"""

FRONTMATTER = r"""\begin{titlepage}
\centering
\vspace*{3cm}
{\Huge\bfseries BOOK_TITLE \par}
\vspace{2cm}
{\Large 翻译版 \par}
\vfill
{\large \today \par}
\end{titlepage}
"""


def main():
    parser = argparse.ArgumentParser(description="Build LaTeX book from translated Markdown")
    parser.add_argument("translated_dir", help="Directory with translated ch*.md files")
    parser.add_argument("--output-dir", default="output/latex", help="Output LaTeX project directory")
    parser.add_argument("--manifest", default="config/chapter_manifest.json", help="Chapter manifest")
    parser.add_argument("--title", default="Book Title", help="Book title for cover page")
    args = parser.parse_args()

    translated_dir = pathlib.Path(args.translated_dir)
    output_dir = pathlib.Path(args.output_dir)
    chapters_dir = output_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    md_files = sorted(translated_dir.glob("ch*.md"))
    if not md_files:
        print(f"Error: no ch*.md files found in {translated_dir}", file=sys.stderr)
        sys.exit(1)

    (output_dir / "preamble.tex").write_text(PREAMBLE, encoding="utf-8")

    frontmatter = FRONTMATTER.replace("BOOK_TITLE", args.title)
    (output_dir / "frontmatter.tex").write_text(frontmatter, encoding="utf-8")

    chapter_inputs = []
    for md_file in md_files:
        md_text = md_file.read_text(encoding="utf-8")
        latex_body = md_to_latex(md_text)
        tex_name = md_file.stem + ".tex"
        (chapters_dir / tex_name).write_text(latex_body, encoding="utf-8")
        chapter_inputs.append(f"\\input{{chapters/{md_file.stem}}}")
        print(f"  Converted {md_file.name} -> chapters/{tex_name}", file=sys.stderr)

    book_tex = "\\input{preamble}\n\\begin{document}\n\\input{frontmatter}\n\\tableofcontents\n\\mainmatter\n"
    book_tex += "\n".join(chapter_inputs)
    book_tex += "\n\\end{document}\n"
    (output_dir / "book.tex").write_text(book_tex, encoding="utf-8")

    print(f"LaTeX project generated at {output_dir}", file=sys.stderr)
    print(f"Compile with: cd {output_dir} && xelatex book.tex && xelatex book.tex", file=sys.stderr)


if __name__ == "__main__":
    main()
