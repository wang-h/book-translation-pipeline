---
name: supplement-ocr-missing
description: >-
  Supplement missing OCR text by sending PDF page screenshots + current text to a
  vision-capable model (GPT-5.4 mini). Use when MinerU misses lines, drops
  fragments, leaves dotted placeholders, or has obvious gaps in Markdown. Keywords:
  补识别, 漏识别, 缺字, 缺段, OCR missing text, 查漏补缺.
---

# Supplement OCR Missing Text (Vision-based)

## Overview

This skill repairs **missing OCR content** that MinerU did not capture, using a
**multimodal (vision) approach**: render the PDF page as a screenshot, send it
alongside the current OCR text to a vision-capable model, and let the model fill
in what's missing by comparing image vs text.

### Why vision?

Text-only models cannot reliably recover content that was replaced by dots or
simply omitted — they have no source of truth. A vision model can *read* the
original PDF page image and fill in the gaps.

### Model policy

- Default model: `gpt-5.4-mini` (supports vision via OpenAI-compatible API).
- Configurable via `--model` flag or `openai.supplement_model` in secrets.json.

## Hard Constraints

- **Never translate.** Keep original source language.
- **Never paraphrase.** Recover missing text only.
- **Never invent content.** Only fill what is visible in the PDF image.
- **Do not rewrite correct text.** The model must preserve already-correct content.

## Inputs

- Source PDF: `workspace/input/<book>.pdf`
- OCR/repaired Markdown: `workspace/work/repaired/chXX.md` (or `work/ocr/full.md`)
- Page numbers to process (1-based)

## Output

- Supplemented Markdown: `workspace/work/supplemented/chXX.md`
- Patch log: `workspace/work/supplemented/chXX.patch_log.json`

## Script

```
book-translation-skills/scripts/supplement_ocr_vision.py
```

### Usage

```bash
# Process specific pages (1-based page numbers)
python scripts/supplement_ocr_vision.py \
  --pdf workspace/input/book.pdf \
  --md  workspace/work/repaired/ch01.md \
  --pages 3-5 \
  --output workspace/work/supplemented/ch01.md

# Single page
python scripts/supplement_ocr_vision.py \
  --pdf workspace/input/book.pdf \
  --md  workspace/work/repaired/ch01.md \
  --pages 3 \
  --output workspace/work/supplemented/ch01_page3.md

# Override model
python scripts/supplement_ocr_vision.py \
  --pdf workspace/input/book.pdf \
  --md  workspace/work/repaired/ch01.md \
  --pages 1-10 \
  --output workspace/work/supplemented/ch01.md \
  --model gpt-5.4-mini

# Higher DPI for small text
python scripts/supplement_ocr_vision.py \
  --pdf workspace/input/book.pdf \
  --md workspace/work/repaired/ch01.md \
  --pages 3 \
  --output workspace/work/supplemented/ch01.md \
  --dpi 300
```

### Arguments

| Flag | Required | Description |
|------|----------|-------------|
| `--pdf` | Yes | Source PDF file path |
| `--md` | Yes | Current Markdown file to supplement |
| `--pages` | Yes | PDF pages (1-based): `"3"`, `"3-5"`, `"3,5,7"` |
| `--output` | Yes | Output supplemented Markdown path |
| `--model` | No | Vision model override (default: `gpt-5.4-mini`) |
| `--dpi` | No | Screenshot render DPI (default: 200, use 300 for small text) |

## Workflow

### Step 1: Identify pages with missing content

Look for high-signal omission patterns in the Markdown:

- Long dotted fillers (`……`, `······`, `···`) where names/titles should be
- Abrupt sentence breaks with no ending
- Footnote markers with missing footnote text
- List/table rows that skip obvious items
- Headings with incomplete first paragraphs

Cross-reference with `content_list_v2.json` or `layout.json` to find the
PDF page indices (0-based in JSON → 1-based for the `--pages` flag).

### Step 2: Run the vision supplement script

The script:
1. Renders each specified PDF page to PNG at the configured DPI using pymupdf.
2. Encodes the image as base64 and sends it with the current full Markdown text
   to the vision model.
3. The model compares the image against the text and returns corrected Markdown
   with missing content filled in.
4. Writes the patched output and a JSON patch log.

### Step 3: Review the diff

```bash
diff workspace/work/repaired/ch01.md workspace/work/supplemented/ch01.md
```

Verify:
- Filled content matches what's visible in the PDF
- No accidental translation
- No hallucinated content
- Markdown formatting preserved

### Step 4: Accept or iterate

If satisfied, use the supplemented file as the new base for downstream stages
(translation, etc.). If some pages still have issues, re-run with higher DPI or
different pages.

## Decision Rules

- **Few pages with gaps:** run this script on those pages only.
- **Many pages with gaps:** run on all pages (may take longer due to per-page API calls).
- **Entire book missing large sections:** consider re-running MinerU OCR with targeted `page_ranges` first, then use this skill for leftovers.
- **Vision model also fails:** mark content as `[[UNCERTAIN]]` for manual review.

## Integration in Pipeline

This skill fits after OCR and repair:

```
OCR (MinerU) → Markdown Repair → **Supplement Missing (this skill)** → Terminology Extraction → Translation
```

Or as a targeted correction at any point when gaps are discovered.

## Dependencies

- `pymupdf` (fitz) — PDF page rendering
- `requests` — API calls
- `book_translation_paths.py` — workspace resolution
