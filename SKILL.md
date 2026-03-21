---
name: book-translation-pipeline
description: >-
  End-to-end book translation pipeline: PDF → OCR → OCR post-processing
  (missing-text supplement + Markdown repair) → terminology extraction →
  chapter-by-chapter translation → LaTeX typesetting → PDF polish. Use when
  translating a book, processing a book PDF, or running any stage of the
  book translation workflow.
---

# Book Translation Pipeline

## Overview

This is the master orchestration skill for translating a full book from PDF to polished Chinese PDF. It coordinates 6 stages. The user only needs to provide a PDF and say "翻译这本书".

## Layout

```
book-translation-pipeline/
├── workspace/                  # 工作目录（密钥、PDF、OCR产出、译稿等）
└── book-translation-skills/    # 技能 + 脚本（可单独发布到 GitHub）
```

- **Skills + scripts:** `book-translation-skills/` — all `SKILL.md` definitions and `scripts/`.
- **Workspace:** `workspace/` — `local.secrets.json`, `input/`, `work/`, `output/`, `config/`.
- **Shared conventions:** `REFERENCE.md` at the pipeline root.

## Prerequisites

1. `workspace/local.secrets.json` (or `workspace/secrets.json`) exists with valid MinerU and OpenAI credentials (copy from `secrets.example.json`).
2. Python deps: `pip install -r book-translation-skills/requirements.txt`
3. System deps (PDF compilation): `sudo apt install texlive-xetex texlive-latex-extra texlive-lang-chinese fonts-noto-cjk`
4. Fallback PDF: WeasyPrint (`pip install weasyprint`) if XeLaTeX unavailable.

## Full Workflow

When the user asks to translate a book, execute these stages in order. After each stage, confirm outputs before proceeding.

### Stage 1: OCR — `book-translation-skills/ocr-book-with-mineru-api/SKILL.md`

**Input:** PDF file
**Output:** `workspace/work/p1_ocr/full.md`, `workspace/work/p1_ocr/content_list.json`, `workspace/work/p1_ocr/images/`

1. Place the PDF in `workspace/input/`.
2. Read the sub-skill for detailed API steps.
3. Submit to MinerU v4 cloud API, poll until done, download and unzip results.
4. Generate `workspace/config/chapter_manifest.json` from detected headings.
5. **Checkpoint:** Confirm `full.md` is non-empty and chapter headings look correct.

### Stage 2: OCR Post-Processing (Supplement + Repair)

**Input:** `workspace/work/p1_ocr/full.md`
**Output:** `workspace/work/p2_repaired/ch01.md`, `ch02.md`, ...

1. Run targeted missing-text supplementation first when MinerU omissions are visible, using `book-translation-skills/supplement-ocr-missing/SKILL.md` (model configurable, fast model recommended).
2. Run structural OCR cleanup using `book-translation-skills/repair-book-markdown/SKILL.md`.
3. Do NOT translate — keep original language.
4. **Checkpoint:** Chapter count matches manifest; heading hierarchy is consistent; missing-span patches are logged.

### Stage 3: Terminology Extraction — `book-translation-skills/extract-book-terminology/SKILL.md`

**Input:** `workspace/work/p2_repaired/ch*.md`
**Output:** `workspace/work/p3_terminology/glossary.json`, `workspace/work/p3_terminology/translation_memory.md`

1. Run `scripts/extract_terms.py` for a first-pass extraction of capitalized phrases, abbreviations, quoted terms.
2. Call GPT-5.4 to classify and translate term candidates.
3. **Human review checkpoint:** Present `term_candidates.json` to user. Ask if they want to review/override translations.
4. Freeze approved terms into `glossary.json`.
5. **Checkpoint:** Glossary exists and has `status: "frozen"` entries.

### Stage 4: Translation — `book-translation-skills/translate-book-to-zh/SKILL.md`

**Input:** `workspace/work/p2_repaired/ch*.md` + `workspace/work/p3_terminology/glossary.json`
**Output:** `workspace/work/p4_translated/ch01.md`, `ch02.md`, ...

1. Load frozen glossary and inject into every translation prompt.
2. Translate chapter by chapter, chunk by chunk, using GPT-5.4.
3. Post-translation consistency check: scan for glossary drift and forbidden translations.
4. Record any new unregistered terms.
5. **Checkpoint:** All chapters translated; paragraph count roughly matches source; no glossary violations.

### Stage 5: PDF 生成 — `book-translation-skills/typeset-book-latex/SKILL.md`

**Input:** `workspace/work/p4_translated/ch*.md`
**Output:** `workspace/output/pdf/book.pdf`

**方式 A — XeLaTeX（推荐）：**

1. Run `scripts/build_latex.py` to convert Markdown → LaTeX.
2. Generate `preamble.tex`, `frontmatter.tex`, `book.tex`, and `chapters/*.tex`.
3. Compile twice with `xelatex`.
4. **Checkpoint:** `book.pdf` exists; no critical compilation errors.

**方式 B — WeasyPrint（备选，无需 LaTeX）：**

1. Run `scripts/md_to_pdf.py work/p4_translated/ch01.md --output output/pdf/book.pdf --title "书名"`.
2. **Checkpoint:** `book.pdf` exists and页面排版正常。

### Stage 6: PDF Polish — `book-translation-skills/polish-book-pdf/SKILL.md`

**Input:** `workspace/output/pdf/book-draft.pdf` + `workspace/output/latex/`
**Output:** `workspace/output/pdf/book-final.pdf`

1. Run `scripts/pdf_layout_check.py` for automated checks.
2. Fix layout issues: widows/orphans, footnote overflow, float problems, CJK spacing.
3. Recompile and verify.
4. Run through final QA checklist.
5. **Checkpoint:** `book-final.pdf` is publication-ready.

## Partial Runs

| User says | Stage |
|-----------|-------|
| "OCR 这本书" / "识别这个 PDF" | Stage 1 |
| "MinerU 漏识别了" / "补 OCR 缺字缺段" / "补识别" | Stage 2 |
| "修复 Markdown" / "清理 OCR 结果" | Stage 2 |
| "提取术语" / "做术语表" | Stage 3 |
| "翻译这本书" / "翻译第X章" | Stage 4 (assumes 1-3 done) |
| "排版" / "生成 PDF" / "编译 LaTeX" | Stage 5 (assumes 1-4 done) |
| "优化版面" / "精修 PDF" | Stage 6 (assumes 1-5 done) |
| "翻译这本书"（从 PDF 开始） | Full pipeline 1-6 |

## Running Scripts

All scripts live in `book-translation-skills/scripts/`. Run from `workspace/`:

```bash
cd ~/book-translation-pipeline/workspace
python ../book-translation-skills/scripts/mineru_submit.py input/book.pdf --ocr
```

Scripts auto-detect `workspace/` by looking for `local.secrets.json` upward from cwd. You can also set `BOOK_TRANSLATION_WORKSPACE` explicitly.

### Available Scripts

| Script | Phase | Description |
|--------|-------|-------------|
| `mineru_submit.py` | P1 | Submit PDF to MinerU OCR |
| `mineru_poll.py` | P1 | Poll OCR status + download results |
| `generate_chapter_manifest.py` | P1 | Generate chapter manifest from headings |
| `split_md_paragraphs.py` | P2/P4 | Split Markdown into char-limited chunks |
| `split_book.py` | P2 | Split by headings into chapters |
| `openai_repair_md.py` | P2 | LLM-based OCR repair |
| `extract_terms.py` | P3 | Extract terminology candidates |
| `openai_translate_md.py` | P4 | LLM-based translation (JP→ZH) |
| `build_latex.py` | P5 | Markdown → LaTeX project |
| `md_to_pdf.py` | P5 | Markdown → PDF via WeasyPrint |
| `pdf_layout_check.py` | P6 | PDF layout QA checks |

## Error Recovery

- Each stage is independently resumable — check `workspace/config/chapter_manifest.json` for per-chapter status.
- Failed chunks can be retried individually without rerunning the full stage.
- See `REFERENCE.md` for the complete failure recovery table.

## Key Rules

1. **Never skip Stage 3** (terminology) before Stage 4 (translation). Glossary consistency is non-negotiable.
2. **Always read the sub-skill SKILL.md** before executing a stage — it has detailed prompts and constraints.
3. **Checkpoint after every stage** — don't blindly chain all 6 stages without user confirmation.
4. **Secrets** are at `workspace/local.secrets.json`.
