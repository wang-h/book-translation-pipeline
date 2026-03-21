---
name: typeset-book-latex
description: >-
  Generate a complete LaTeX book project from translated Chinese Markdown
  chapters and compile it with XeLaTeX. Use when building LaTeX from translated
  text, compiling a book PDF, or setting up a Chinese book typesetting project.
---

# Typeset Book with LaTeX

## Overview

This skill takes translated Chinese Markdown chapters and assembles a complete LaTeX book project, then compiles it with XeLaTeX to produce a first-pass PDF. It focuses on structural correctness and stable compilation; fine-grained layout polish is handled by `polish-book-pdf`.

For shared conventions, see [REFERENCE.md](../../REFERENCE.md).

## Input

- `work/translated/ch*.md` — translated Chinese Markdown, one per chapter.
- `config/chapter_manifest.json` — chapter metadata.
- `work/terminology/glossary.json` — for any terms that need special LaTeX handling.

## Workflow

### Step 1: Generate LaTeX project structure

Create the following under `output/latex/`:

```
output/latex/
├── book.tex            # Main document
├── preamble.tex        # Packages, fonts, page geometry, headers/footers
├── frontmatter.tex     # Title page, copyright, TOC
└── chapters/
    ├── ch01.tex
    ├── ch02.tex
    └── ...
```

### Step 2: Write preamble.tex

Key settings for Chinese book typesetting:

```latex
\documentclass[12pt, a4paper, openright]{book}
\usepackage{ctex}
\usepackage{geometry}
\geometry{top=2.5cm, bottom=2.5cm, left=3cm, right=2.5cm}
\usepackage{fancyhdr}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{graphicx}
\usepackage{amsmath, amssymb}
\usepackage{footmisc}
\usepackage{enumitem}
\usepackage{xcolor}

% Chinese font configuration (uses system fonts via XeLaTeX)
\setCJKmainfont{Noto Serif CJK SC}[BoldFont={Noto Sans CJK SC Bold}]
\setCJKsansfont{Noto Sans CJK SC}
\setCJKmonofont{Noto Sans Mono CJK SC}

% Page headers and footers
\pagestyle{fancy}
\fancyhead[LE]{\leftmark}
\fancyhead[RO]{\rightmark}
\fancyfoot[C]{\thepage}

% Prevent widows and orphans
\widowpenalty=10000
\clubpenalty=10000
```

Adjust fonts based on what is installed on the system. Prefer Noto CJK fonts; fall back to system-available CJK fonts.

### Step 3: Convert Markdown to LaTeX chapters

For each `work/translated/ch*.md`:

1. Convert Markdown headings to `\chapter{}`, `\section{}`, `\subsection{}`.
2. Convert footnotes `[^N]` to `\footnote{}`.
3. Convert tables to `longtable` or `tabular` environments.
4. Convert `$...$` and `$$...$$` to LaTeX math mode (already LaTeX-compatible).
5. Convert images `![alt](path)` to `\includegraphics{}` with figure environments.
6. Convert block quotes to `\begin{quote}...\end{quote}`.
7. Convert ordered/unordered lists to `enumerate`/`itemize`.

Use `scripts/build_latex.py` for this conversion.

### Step 4: Assemble book.tex

```latex
\input{preamble}
\begin{document}
\input{frontmatter}
\tableofcontents
\mainmatter
\input{chapters/ch01}
\input{chapters/ch02}
% ...
\end{document}
```

### Step 5: Compile

```bash
cd output/latex
xelatex -interaction=nonstopmode book.tex
xelatex -interaction=nonstopmode book.tex  # second pass for TOC/references
```

Two passes are needed for stable table of contents and cross-references.

### Step 6: Validate compilation

- Check that `book.pdf` is generated and non-empty.
- Parse the `.log` file for errors and warnings.
- Confirm page count is reasonable relative to source.
- Copy `book.pdf` to `output/pdf/book-draft.pdf`.

## Output

- `output/latex/` — complete LaTeX project.
- `output/pdf/book-draft.pdf` — first-pass compiled PDF.

## Error Handling

- If compilation fails, parse the `.log` to identify the offending chapter/line.
- Fix the specific chapter `.tex` file and recompile.
- Common issues: unescaped `#`, `%`, `&`, `_` characters; missing `\end{}` tags; font not found.
- If a CJK font is not installed, list available CJK fonts with `fc-list :lang=zh` and substitute.
