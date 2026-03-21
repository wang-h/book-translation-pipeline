---
name: repair-book-markdown
description: >-
  Repair OCR noise in book-length Markdown produced by MinerU: fix broken
  paragraphs, heading levels, footnotes, formulas, tables, and page
  header/footer contamination. Use when cleaning up OCR output before
  translation, or when the user mentions OCR repair, paragraph fixing, or
  Markdown cleanup.
---

# Repair Book Markdown

## Overview

This skill takes raw Markdown from MinerU OCR and produces clean, structurally faithful Markdown ready for terminology extraction and translation. It uses GPT-5.4 via the aihubmix OpenAI-compatible API.

For shared conventions, see [REFERENCE.md](../../REFERENCE.md).

## Hard Constraints

- **Never translate.** The output must remain in the original language.
- **Never rewrite meaning.** Only fix OCR artifacts, not style or substance.
- **Preserve chapter structure.** Heading hierarchy from the original must be kept intact.
- **Preserve paragraph boundaries.** Do not merge or split paragraphs unless OCR clearly broke them.

## Input

- `work/p1_ocr/full.md` — raw MinerU Markdown.
- `work/p1_ocr/content_list.json` — structural reference for ambiguous cases.
- `config/chapter_manifest.json` — expected chapter list.

## Repair Targets

| Problem | Repair action |
|---------|--------------|
| Broken paragraphs | Rejoin lines that were split by OCR at page/column boundaries |
| Wrong heading levels | Normalize to consistent `#`/`##`/`###` hierarchy matching the book's TOC |
| Page header/footer contamination | Remove repeated headers, footers, page numbers embedded in body text |
| Broken footnotes | Reconnect footnote markers `[^N]` to their definitions |
| Formula wrapping | Ensure `$...$` and `$$...$$` delimiters are intact; fix broken LaTeX tokens |
| Table corruption | Restore Markdown table alignment; merge rows split across pages |
| Garbled characters | Fix common OCR substitutions (e.g. `l` ↔ `1`, `O` ↔ `0`) in context |
| Stray artifacts | Remove OCR confidence markers, bounding-box annotations, watermark text |

## Workflow

### Step 1: Read credentials and load input

Read `openai` credentials from `local.secrets.json` at the pipeline project root. Load `full.md` and `chapter_manifest.json`.

### Step 2: Split into chapters

Use `scripts/split_book.py` to split `full.md` by headings into chapter-sized chunks. Each chunk should be 3000-4000 tokens. Follow the chunking rules in REFERENCE.md.

### Step 3: Repair each chunk

For each chunk, call GPT-5.4 with the following system prompt structure:

```
You are an OCR post-processor. Your job is to fix OCR artifacts in the
following Markdown text. Do NOT translate. Do NOT rewrite content. Only fix:
- broken paragraphs (rejoin lines split by page breaks)
- heading levels (normalize to match TOC)
- page headers/footers embedded in body
- broken footnotes
- broken formula delimiters
- corrupted tables
- garbled characters (contextual correction only)
- stray OCR artifacts

Return the repaired Markdown only. No explanations.
```

### Step 4: Reassemble and validate

- Concatenate repaired chunks back into per-chapter files under `work/p2_repaired/`.
- Validate: chapter count matches manifest; heading hierarchy is consistent; footnote count matches raw input.

## Output

- `work/p2_repaired/ch01.md`, `work/p2_repaired/ch02.md`, ... — one file per chapter.
- Updated `config/chapter_manifest.json` with `repair_status: "done"` per chapter.

## Error Handling

- If GPT returns garbled or empty output for a chunk, retry that chunk only (max 2 retries).
- If a chunk consistently fails, flag it in the manifest as `repair_status: "needs_review"` and continue.
