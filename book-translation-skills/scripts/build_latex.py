"""Convert translated Chinese Markdown chapters into a LaTeX book project.

Usage:
    python build_latex.py <translated_dir> [--output-dir output/latex] [--manifest config/chapter_manifest.json]

Generates book.tex, preamble.tex, frontmatter.tex, and chapters/*.tex.
"""

import argparse
import json
import pathlib
import re
import shutil
import sys


HEADING_MAP = {
    1: "\\chapter",
    2: "\\section",
    3: "\\subsection",
    4: "\\subsubsection",
}

KANJI_DIGITS = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}

LANG_NAMES_ZH: dict[str, str] = {
    "ja": "日语",
    "fr": "法语",
    "en": "英语",
    "de": "德语",
    "es": "西班牙语",
    "pt": "葡萄牙语",
    "ko": "韩语",
    "it": "意大利语",
    "ru": "俄语",
    "ar": "阿拉伯语",
}


def _lang_display_name(code: str) -> str:
    """Return Chinese display name for a language code, fallback to the code itself."""
    return LANG_NAMES_ZH.get(code.split("-")[0].lower(), code)


def _int_to_kanji(num: int) -> str:
    if num == 0:
        return "零"
    units = ["", "十", "百", "千", "万"]
    s = str(num)
    out = []
    length = len(s)
    for i, ch in enumerate(s):
        d = int(ch)
        pos = length - i - 1
        if d == 0:
            continue
        # 10~19 => "十X" (not "一十X")
        if d == 1 and pos > 0 and not out:
            out.append(units[pos])
        else:
            out.append(KANJI_DIGITS[ch] + units[pos])
    return "".join(out)


def normalize_legal_numbering_prefix(text: str) -> str:
    """Normalize leading '第5章/第12条' to kanji numbers: '第五章/第十二条'."""
    def repl(m: re.Match) -> str:
        raw_num = m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        unit = m.group(2)
        try:
            n = int(raw_num)
        except ValueError:
            return m.group(0)
        return f"第{_int_to_kanji(n)}{unit}"

    return re.sub(r"^第\s*([0-9０-９]+)\s*([章节条])", repl, text)


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


_LAW_BOX_SOURCE_LANG = "ja"


def set_law_box_source_lang(lang: str) -> None:
    global _LAW_BOX_SOURCE_LANG
    _LAW_BOX_SOURCE_LANG = lang


def _format_law_bilingual_box(jp_lines: list[str], zh_lines: list[str]) -> str:
    """Render source original + ZH translation in a boxed layout."""
    jp = "\n".join(escape_latex(inline_format(x)) for x in jp_lines if x.strip())
    zh = "\n".join(escape_latex(inline_format(x)) for x in zh_lines if x.strip())
    if not jp and not zh:
        return ""
    src_name = _lang_display_name(_LAW_BOX_SOURCE_LANG)
    use_japfont = _LAW_BOX_SOURCE_LANG.startswith("ja")
    font_open = "{\\japfont\n" if use_japfont else ""
    font_close = "}\n" if use_japfont else ""
    return (
        "\\begin{tcolorbox}[colback=black!3,colframe=black!70,title=法条原文与译文]\n"
        f"\\textbf{{法条原文（{src_name}）}}\\\\\n"
        f"{font_open}"
        f"{jp}\n"
        f"{font_close}\n"
        "\\vspace{0.6em}\n"
        "\\textbf{法条译文（中文）}\\\\\n"
        f"{zh}\n"
        "\\end{tcolorbox}"
    )


def md_to_latex(text: str) -> str:
    """Convert Markdown text to LaTeX body content.

    Heading hierarchy is trusted from the Markdown source (set by LLM in P2 repair).
    No content-specific rules here — pure mechanical mapping.
    """
    lines = text.split("\n")
    # Merge standalone legal article markers ("第九条") with the next text line,
    # so they can be formatted as "\textbf{第九条} ..." consistently.
    merged_lines: list[str] = []
    article_only = re.compile(r"^第\s*[0-9０-９〇零一二三四五六七八九十百千万两]+\s*条$")
    i = 0
    while i < len(lines):
        cur = lines[i]
        cur_s = normalize_legal_numbering_prefix(cur.strip())
        if article_only.match(cur_s):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                nxt = lines[j].strip()
                if not re.match(r"^#{1,6}\s+", nxt) and not nxt.startswith("|") and not re.match(r"^[-*]\s+|^\d+\.\s+", nxt):
                    merged_lines.append(f"{cur_s} {lines[j].lstrip()}")
                    i = j + 1
                    continue
            merged_lines.append(cur)
            i += 1
            continue
        merged_lines.append(cur)
        i += 1
    lines = merged_lines
    output = []

    in_list = None
    in_table = False
    table_rows = []
    in_author_section = False
    author_lines_buf = []
    prev_heading_level = 0
    in_toc_section = False
    toc_heading_level = 0
    in_law_bilingual = False
    law_jp_lines: list[str] = []
    law_zh_lines: list[str] = []
    law_mode: str | None = None

    # "目录型行"：一行内出现多个法条+页码（例如“第1条…79 第2条…80”）。
    # 这些行应视为目录内容而非正文，避免 PDF 看起来像“只有章节没有正文”。
    toc_like_line = re.compile(r"(第\s*\d+\s*条.{0,30}\d{1,4}){2,}")
    chapter_like_bold = re.compile(r"^第\s*[0-9０-９一二三四五六七八九十百千万两]+\s*章\b")
    section_like_bold = re.compile(r"^第\s*[0-9０-９一二三四五六七八九十百千万两]+\s*节\b")

    for line in lines:
        stripped = line.strip()
        bold_wrapped = False
        plain_stripped = stripped
        # Some DOCX-derived markdown uses "**第一章 ...**" instead of "# 第一章 ...".
        # Promote those lines to structural headings so TOC can be generated.
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            bold_wrapped = True
            plain_stripped = stripped[2:-2].strip()

        if stripped == ":::law-bilingual":
            in_law_bilingual = True
            law_jp_lines = []
            law_zh_lines = []
            law_mode = None
            continue

        if in_law_bilingual:
            if stripped == ":::":
                box = _format_law_bilingual_box(law_jp_lines, law_zh_lines)
                if box:
                    output.append(box)
                in_law_bilingual = False
                law_mode = None
                continue
            if stripped in ("【法条原文（JP）】", "【法条原文】"):
                law_mode = "jp"
                continue
            if stripped in ("【法条译文（ZH）】", "【法条译文】"):
                law_mode = "zh"
                continue
            if law_mode == "jp":
                law_jp_lines.append(line)
            elif law_mode == "zh":
                law_zh_lines.append(line)
            continue

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
            # 防止层级跳跃（如 # 后直接 ###），避免目录编号出现 3.0.1 这类异常。
            if prev_heading_level > 0 and level > prev_heading_level + 1:
                level = prev_heading_level + 1
            title = stripped.lstrip("#").strip()
            title = normalize_legal_numbering_prefix(title)

            # Enter/leave source TOC section (目次/目录). We keep the heading, skip its body lines.
            if in_toc_section:
                if level <= toc_heading_level and ("目录" not in title and "目次" not in title):
                    in_toc_section = False
                else:
                    # Still inside TOC hierarchy; keep heading structure but skip body lines later.
                    pass

            cmd = HEADING_MAP.get(level, "\\subsubsection")
            output.append(f"{cmd}{{{escape_latex(title)}}}")
            prev_heading_level = level
            if "目录" in title or "目次" in title:
                in_toc_section = True
                toc_heading_level = level
            if "执笔者介绍" in title or "執筆者紹介" in title:
                in_author_section = True
                author_lines_buf = []
            continue

        if bold_wrapped and chapter_like_bold.match(plain_stripped):
            if in_list:
                output.append(f"\\end{{{in_list}}}")
                in_list = None
            plain_stripped = normalize_legal_numbering_prefix(plain_stripped)
            output.append(f"\\chapter{{{escape_latex(plain_stripped)}}}")
            prev_heading_level = 1
            continue

        if bold_wrapped and section_like_bold.match(plain_stripped):
            if in_list:
                output.append(f"\\end{{{in_list}}}")
                in_list = None
            plain_stripped = normalize_legal_numbering_prefix(plain_stripped)
            output.append(f"\\section{{{escape_latex(plain_stripped)}}}")
            prev_heading_level = 2
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
            if in_toc_section:
                continue
            # 跳过目录型条目行（只列条文名与页码，无正文叙述）。
            if toc_like_line.search(stripped):
                continue
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
    text = normalize_legal_numbering_prefix(text)
    # Emphasize legal article lead-ins like "第一条 ...":
    # force bold on "第X条" and keep one space after it for readability.
    text = re.sub(
        r"^(第\s*[0-9０-９〇零一二三四五六七八九十百千万两]+\s*条)\s*(?=\S)",
        r"\\textbf{\1} ",
        text,
    )
    text = re.sub(
        r"^(第\s*[0-9０-９〇零一二三四五六七八九十百千万两]+\s*条)\s*$",
        r"\\textbf{\1}",
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
    text = re.sub(r"`(.+?)`", r"\\texttt{\1}", text)
    return text


PREAMBLE = r"""\usepackage[fontset=none]{ctex}
\usepackage{fontspec}
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
\usepackage[most]{tcolorbox}

% Noto CJK: pan-CJK font covering Chinese + Japanese + Korean
\setCJKmainfont{Noto Serif CJK SC}
\setCJKsansfont{Noto Sans CJK SC}
\setCJKmonofont{Noto Sans Mono CJK SC}
\setmainfont{Noto Serif CJK SC}
% Japanese font for law article originals (proper JP glyph variants)
\newCJKfontfamily\japfont{Noto Serif CJK JP}

\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE,RO]{\thepage}
\fancyhead[RE]{\leftmark}
\fancyhead[LO]{\rightmark}
\renewcommand{\headrulewidth}{0.4pt}

\titleformat{\chapter}[display]
  {\normalfont\huge\bfseries}{}{0pt}{\Huge}
\titlespacing*{\chapter}{0pt}{-20pt}{30pt}
\setcounter{secnumdepth}{-1}
\setcounter{tocdepth}{2}

\setlength{\parindent}{2em}
\setlength{\parskip}{0.3em}
\linespread{1.5}

\widowpenalty=10000
\clubpenalty=10000
\tolerance=1000
\emergencystretch=3em
"""

TYPE_LABELS = {
    "law_name": "法律名称",
    "institution": "机构名称",
    "role": "职务与角色",
    "abbreviation": "缩略语",
    "concept": "核心概念",
    "person_name": "人名",
    "legal_phrase": "法律用语",
    "other": "其他",
}

GLOSSARY_TYPES_ORDER = [
    "law_name", "institution", "role", "abbreviation",
    "concept", "legal_phrase", "person_name", "other",
]

# PDF 附录只展示高价值术语；完整 glossary.json 仍用于翻译阶段。
APPENDIX_TYPES_ORDER = [
    "law_name",
    "institution",
    "role",
    "person_name",
    "abbreviation",
]


_TRIVIAL_PATTERNS = [
    re.compile(r"^第\s*[\d０-９一二三四五六七八九十百千]+\s*[章条項项節节編编款号部]"),
    re.compile(r"^平\s*[\d０-９]+"),
    re.compile(r"^昭\s*[\d０-９]+"),
    re.compile(r"^平成\s*[\d０-９]+"),
    re.compile(r"^昭和\s*[\d０-９]+"),
    re.compile(r".+法\s*[\d０-９]+\s*条"),
]


def _is_trivial_term(t: dict) -> bool:
    """Filter out legal citation refs, document numbers, and single-char terms."""
    ja = (t.get("ja") or t.get("source") or t.get("term") or "").strip()
    if len(ja) <= 1:
        return True
    for pat in _TRIVIAL_PATTERNS:
        if pat.match(ja):
            return True
    return False


def _keep_for_appendix(t: dict) -> bool:
    """Select terms suitable for reader-facing appendix."""
    tp = t.get("type", "other")
    if tp not in APPENDIX_TYPES_ORDER:
        return False
    return not _is_trivial_term(t)


def build_glossary_appendix(glossary_path: pathlib.Path, source_lang: str = "ja") -> str:
    """Build a LaTeX appendix chapter from glossary.json."""
    with open(glossary_path, encoding="utf-8") as f:
        data = json.load(f)
    terms = data.get("terms", [])
    if not terms:
        return ""

    by_type: dict[str, list[dict]] = {}
    for t in terms:
        if not _keep_for_appendix(t):
            continue
        tp = t.get("type", "other")
        by_type.setdefault(tp, []).append(t)

    lines = [
        "\\chapter{翻译术语对照表}",
        "",
        "\\begin{small}",
        "",
    ]

    total_terms = sum(len(v) for v in by_type.values())
    lines.insert(1, f"\\noindent 共收录 {total_terms} 条核心术语（供读者检索）。")
    lines.insert(2, "")

    for tp in APPENDIX_TYPES_ORDER:
        group = by_type.get(tp)
        if not group:
            continue
        label = TYPE_LABELS.get(tp, tp)
        group.sort(key=lambda t: t.get("ja") or t.get("source") or "")

        lines.append(f"\\section{{{label}}}（共 {len(group)} 条）")
        lines.append("")
        lines.append("\\begin{longtable}{@{}p{0.42\\textwidth}p{0.52\\textwidth}@{}}")
        lines.append("\\toprule")
        src_label = _lang_display_name(source_lang) + "原文"
        lines.append(f"\\textbf{{{src_label}}} & \\textbf{{中文译文}} \\\\")
        lines.append("\\midrule")
        lines.append("\\endhead")

        for t in group:
            src = escape_latex(t.get("ja") or t.get("source") or "")
            zh = escape_latex(t.get("zh") or t.get("target") or t.get("preferred_translation") or "")
            if source_lang.startswith("ja"):
                src_cell = "{\\japfont " + src + "}"
            else:
                src_cell = src
            lines.append(f"{src_cell} & {zh} \\\\")

        lines.append("\\bottomrule")
        lines.append("\\end{longtable}")
        lines.append("")

    lines.append("\\end{small}")
    return "\n".join(lines)


def infer_title_from_markdown(md_text: str) -> str | None:
    """Infer book title from chapter markdown (prefer first bold heading-like line)."""
    for raw in md_text.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = re.match(r"^\*\*(.+?)\*\*$", s)
        if m:
            title = m.group(1).strip()
            if title and not title.startswith("（") and "目 次" not in title and "目录" not in title and "目次" not in title:
                return title
        if s.startswith("#"):
            title = s.lstrip("#").strip()
            if title and "目录" not in title and "目次" not in title:
                return title
    return None


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
    parser.add_argument("--title", default="", help="Book title for cover page (empty = auto infer)")
    parser.add_argument("--images-dir", default=None, help="Path to images directory (copied into output for Overleaf)")
    parser.add_argument("--glossary", default=None, help="Path to glossary.json for terminology appendix")
    parser.add_argument("--source-lang", default="ja", help="Source language code (ja, fr, en, …) for display labels")
    args = parser.parse_args()

    translated_dir = pathlib.Path(args.translated_dir)
    output_dir = pathlib.Path(args.output_dir)
    chapters_dir = output_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    set_law_box_source_lang(args.source_lang)

    md_files = sorted(translated_dir.glob("ch*.md"))
    if not md_files:
        print(f"Error: no ch*.md files found in {translated_dir}", file=sys.stderr)
        sys.exit(1)

    (output_dir / "preamble.tex").write_text(PREAMBLE, encoding="utf-8")

    inferred_title = None
    first_md_text = md_files[0].read_text(encoding="utf-8")
    inferred_title = infer_title_from_markdown(first_md_text)
    final_title = args.title.strip() if args.title else ""
    if not final_title:
        final_title = inferred_title or "Book Title"

    frontmatter = FRONTMATTER.replace("BOOK_TITLE", final_title)
    (output_dir / "frontmatter.tex").write_text(frontmatter, encoding="utf-8")

    # Overleaf needs .latexmkrc to select XeLaTeX
    (output_dir / ".latexmkrc").write_text(
        "$pdf_mode = 5;\n",  # 5 = xelatex
        encoding="utf-8",
    )

    chapter_inputs = []
    for md_file in md_files:
        md_text = md_file.read_text(encoding="utf-8")
        latex_body = md_to_latex(md_text)
        tex_name = md_file.stem + ".tex"
        (chapters_dir / tex_name).write_text(latex_body, encoding="utf-8")
        chapter_inputs.append(f"\\input{{chapters/{md_file.stem}}}")
        print(f"  Converted {md_file.name} -> chapters/{tex_name}", file=sys.stderr)

    glossary_input = ""
    if args.glossary:
        glossary_path = pathlib.Path(args.glossary)
        if glossary_path.exists():
            glossary_tex = build_glossary_appendix(glossary_path, source_lang=args.source_lang)
            (output_dir / "glossary.tex").write_text(glossary_tex, encoding="utf-8")
            glossary_input = "\n\\appendix\n\\input{glossary}"
            print(f"  Generated glossary appendix from {glossary_path}", file=sys.stderr)

    book_tex = "\\documentclass[12pt, a4paper, openany]{book}\n\\input{preamble}\n\\begin{document}\n\\input{frontmatter}\n\\tableofcontents\n\\mainmatter\n"
    book_tex += "\n".join(chapter_inputs)
    book_tex += glossary_input
    book_tex += "\n\\end{document}\n"
    (output_dir / "book.tex").write_text(book_tex, encoding="utf-8")

    # Copy images directory (real files, not symlinks) for Overleaf compatibility
    if args.images_dir:
        images_src = pathlib.Path(args.images_dir)
        images_dst = output_dir / "images"
        if images_src.exists():
            if images_dst.is_symlink():
                images_dst.unlink()
            if images_dst.exists():
                shutil.rmtree(images_dst)
            shutil.copytree(images_src, images_dst)
            print(f"  Copied images: {images_src} -> {images_dst}", file=sys.stderr)

    print(f"LaTeX project generated at {output_dir}", file=sys.stderr)
    print(f"Compile with: cd {output_dir} && xelatex book.tex && xelatex book.tex", file=sys.stderr)


if __name__ == "__main__":
    main()
