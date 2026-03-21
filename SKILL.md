---
name: book-translation-pipeline
description: >-
  End-to-end book translation pipeline: PDF → OCR → Markdown repair →
  terminology extraction → chapter-by-chapter translation → LaTeX typesetting
  → PDF polish. Use when translating a book, processing a book PDF, or
  running any stage of the book translation workflow.
---

# Book Translation Pipeline

## Overview

This is the master orchestration skill for translating a full book from PDF to polished Chinese PDF. It coordinates 6 sub-skills in sequence. The user only needs to provide a PDF and say "翻译这本书".

**Pipeline root:** `~/book-translation-pipeline`

All sub-skill definitions live under `skills/`, helper scripts under `scripts/`, and shared conventions in `REFERENCE.md` — all relative to the pipeline root above.

## Prerequisites

1. `local.secrets.json` exists at the pipeline root with valid MinerU and OpenAI credentials (copy from `secrets.example.json`).
2. XeLaTeX and ctex are installed for PDF compilation.
3. Noto CJK fonts (or equivalent) are installed.

## Full Workflow

When the user asks to translate a book, execute these stages in order. After each stage, confirm outputs before proceeding.

### Stage 1: OCR — `skills/ocr-book-with-mineru-api/SKILL.md`

**Input:** PDF file
**Output:** `work/ocr/full.md`, `work/ocr/content_list.json`, `work/ocr/images/`

1. Place the PDF in `input/`.
2. Read the sub-skill for detailed API steps.
3. Submit to MinerU v4 cloud API, poll until done, download and unzip results.
4. Generate `config/chapter_manifest.json` from detected headings.
5. **Checkpoint:** Confirm `full.md` is non-empty and chapter headings look correct.

### Stage 2: Markdown Repair — `skills/repair-book-markdown/SKILL.md`

**Input:** `work/ocr/full.md`
**Output:** `work/repaired/ch01.md`, `ch02.md`, ...

1. Split `full.md` into chunks using `scripts/split_book.py`.
2. Call GPT-5.4 to fix OCR artifacts (broken paragraphs, wrong headings, garbled chars, etc.).
3. Do NOT translate — keep original language.
4. **Checkpoint:** Chapter count matches manifest; heading hierarchy is consistent.

### Stage 3: Terminology Extraction — `skills/extract-book-terminology/SKILL.md`

**Input:** `work/repaired/ch*.md`
**Output:** `work/terminology/glossary.json`, `work/terminology/translation_memory.md`

1. Run `scripts/extract_terms.py` for a first-pass extraction of capitalized phrases, abbreviations, quoted terms.
2. Call GPT-5.4 to classify and translate term candidates.
3. **Human review checkpoint:** Present `term_candidates.json` to user. Ask if they want to review/override translations.
4. Freeze approved terms into `glossary.json`.
5. **Checkpoint:** Glossary exists and has `status: "frozen"` entries.

### Stage 4: Translation — `skills/translate-book-to-zh/SKILL.md`

**Input:** `work/repaired/ch*.md` + `work/terminology/glossary.json`
**Output:** `work/translated/ch01.md`, `ch02.md`, ...

1. Load frozen glossary and inject into every translation prompt.
2. Translate chapter by chapter, chunk by chunk, using GPT-5.4.
3. Post-translation consistency check: scan for glossary drift and forbidden translations.
4. Record any new unregistered terms.
5. **Checkpoint:** All chapters translated; paragraph count roughly matches source; no glossary violations.

### Stage 5: LaTeX Typesetting — `skills/typeset-book-latex/SKILL.md`

**Input:** `work/translated/ch*.md`
**Output:** `output/latex/`, `output/pdf/book-draft.pdf`

1. Run `scripts/build_latex.py` to convert Markdown → LaTeX.
2. Generate `preamble.tex`, `frontmatter.tex`, `book.tex`, and `chapters/*.tex`.
3. Compile twice with `xelatex`.
4. **Checkpoint:** `book-draft.pdf` exists; no critical compilation errors.

### Stage 6: PDF Polish — `skills/polish-book-pdf/SKILL.md`

**Input:** `output/pdf/book-draft.pdf` + `output/latex/`
**Output:** `output/pdf/book-final.pdf`

1. Run `scripts/pdf_layout_check.py` for automated checks.
2. Fix layout issues: widows/orphans, footnote overflow, float problems, CJK spacing.
3. Recompile and verify.
4. Run through final QA checklist.
5. **Checkpoint:** `book-final.pdf` is publication-ready.

## Partial Runs

The user may request a single stage. Match their request to the right stage:

| User says | Stage |
|-----------|-------|
| "OCR 这本书" / "识别这个 PDF" | Stage 1 |
| "修复 Markdown" / "清理 OCR 结果" | Stage 2 |
| "提取术语" / "做术语表" | Stage 3 |
| "翻译这本书" / "翻译第X章" | Stage 4 (assumes 1-3 done) |
| "排版" / "生成 PDF" / "编译 LaTeX" | Stage 5 (assumes 1-4 done) |
| "优化版面" / "精修 PDF" | Stage 6 (assumes 1-5 done) |
| "翻译这本书"（从 PDF 开始） | Full pipeline 1-6 |

## Working Directory

All stages operate relative to a **book project directory** (the user's current workspace or a specified path). The pipeline root (`~/book-translation-pipeline`) holds skill definitions and scripts; actual book data lives in the book project directory.

When starting a new book, create the standard directory structure:

```bash
mkdir -p input work/{ocr,repaired,terminology,translated} output/{latex,pdf} config
```

## Error Recovery

- Each stage is independently resumable — check `config/chapter_manifest.json` for per-chapter status.
- Failed chunks can be retried individually without rerunning the full stage.
- See `REFERENCE.md` for the complete failure recovery table.

## Key Rules

1. **Never skip Stage 3** (terminology) before Stage 4 (translation). Glossary consistency is non-negotiable.
2. **Always read the sub-skill SKILL.md** before executing a stage — it has detailed prompts and constraints.
3. **Checkpoint after every stage** — don't blindly chain all 6 stages without user confirmation.
4. **Secrets** are at the pipeline root: `~/book-translation-pipeline/local.secrets.json`.
