---
name: polish-book-pdf
description: >-
  Polish and quality-check a compiled book PDF by fixing layout issues like
  widows, orphans, bad page breaks, footnote overflow, table/figure float
  problems, and CJK punctuation spacing. Use when optimizing PDF layout,
  doing final book QA, or polishing a compiled LaTeX book.
---

# Polish Book PDF

## Overview

This skill takes a first-pass compiled book PDF and its LaTeX source, identifies layout problems, fixes them by editing the LaTeX source, recompiles, and performs a final quality check. The goal is a publication-ready PDF.

For shared conventions, see [REFERENCE.md](../../REFERENCE.md).

## Hard Constraints

- **Always fix LaTeX source, never patch PDF directly.** All changes must be traceable and reproducible.
- **Never alter translated content.** Only adjust layout, spacing, and typesetting commands.
- **Recompile after every batch of fixes** to verify each change.

## Input

- `output/pdf/book-draft.pdf` — first-pass PDF from `typeset-book-latex`.
- `output/latex/` — full LaTeX project (book.tex, preamble.tex, chapters/*.tex).
- Compilation log from previous build.

## Layout Issues to Check and Fix

### Page-level issues

| Issue | Detection | Fix |
|-------|-----------|-----|
| Widow lines (single line at top of page) | Visual inspection or `\widowpenalty` check | Increase `\widowpenalty`, add `\needspace` before paragraphs |
| Orphan lines (single line at bottom of page) | Visual inspection | Increase `\clubpenalty`, adjust paragraph spacing |
| Chapter title at page bottom | Check if `\chapter{}` falls in last 3 lines | Add `\clearpage` or `\needspace{4\baselineskip}` before chapter |
| Blank pages where not expected | Check for stray `\cleardoublepage` | Remove or replace with `\clearpage` |

### Footnote issues

| Issue | Detection | Fix |
|-------|-----------|-----|
| Footnotes overflowing page | Check for footnotes exceeding page bottom | Use `\interfootnotelinepenalty=10000`; split long footnotes |
| Footnote numbering reset | Verify sequential numbering | Ensure `\counterwithout{footnote}{chapter}` if book-wide numbering |

### Table and figure issues

| Issue | Detection | Fix |
|-------|-----------|-----|
| Table split awkwardly across pages | Check `longtable` page breaks | Add `\nopagebreak` within critical rows; adjust `longtable` settings |
| Figure floats to wrong chapter | Check figure appears near its reference | Use `[htbp]` placement; add `\FloatBarrier` at chapter boundaries |
| Image resolution/sizing | Visual check | Adjust `\includegraphics[width=]` parameters |

### Typography issues

| Issue | Detection | Fix |
|-------|-----------|-----|
| CJK-Latin spacing inconsistent | Visual check on mixed text | Ensure `\usepackage{xeCJK}` with `CJKecglue` settings |
| Punctuation at line start/end | Check for opening punctuation at line end | Configure `xeCJK` punctuation kerning rules |
| Inconsistent quote marks | Search for straight quotes | Replace with Chinese 「」 or "" consistently |
| Overfull/underfull hboxes | Parse `.log` for warnings | Adjust word breaks, add `\sloppy` locally, or reword LaTeX |

### TOC and cross-references

| Issue | Detection | Fix |
|-------|-----------|-----|
| TOC page numbers wrong | Compare TOC with actual pages | Recompile twice; check for `\phantomsection` issues |
| Hyperlinks broken | Click-test in PDF reader | Fix `\hyperref` targets |

## Workflow

### Step 1: Automated checks

Run `scripts/pdf_layout_check.py` on the draft PDF to detect:
- Page count anomalies
- Overfull/underfull hbox warnings from the `.log`
- Blank page sequences
- TOC entry count vs chapter count

### Step 2: Visual inspection pass

Open the PDF and check each chapter for the issues listed above. Record findings.

### Step 3: Batch fix LaTeX source

Group fixes by type and apply them to the `.tex` files. Common fixes:
- Add spacing/penalty commands in `preamble.tex`.
- Add `\FloatBarrier` at chapter boundaries.
- Adjust individual `\includegraphics` sizes.
- Fix punctuation and spacing in chapter files.

### Step 4: Recompile and verify

```bash
cd output/latex
xelatex -interaction=nonstopmode book.tex
xelatex -interaction=nonstopmode book.tex
```

Verify that fixes resolved the issues without introducing new ones.

### Step 5: Final QA checklist

Before declaring the book done, confirm:

- [ ] TOC page numbers are correct (stable across compilations)
- [ ] All chapters start on the correct page (odd page for `openright`)
- [ ] Page headers show correct chapter/section titles
- [ ] Page footers show correct page numbers
- [ ] No widow or orphan lines
- [ ] No chapter titles stranded at page bottom
- [ ] All footnotes render correctly and are numbered sequentially
- [ ] All tables are readable and not awkwardly split
- [ ] All figures appear near their references
- [ ] CJK-Latin mixed text has consistent spacing
- [ ] No overfull hbox warnings remain (or they are acceptable)
- [ ] PDF bookmarks/hyperlinks work

### Step 6: Produce final PDF

Copy the verified PDF to `output/pdf/book-final.pdf`.

## Output

- `output/pdf/book-final.pdf` — publication-ready PDF.
- Updated LaTeX source files with all layout fixes.

## Error Handling

- If a fix introduces new compilation errors, revert that specific change and try an alternative approach.
- If visual issues persist after 2 rounds of fixes, document them in `config/chapter_manifest.json` as `layout_notes` for manual resolution.
