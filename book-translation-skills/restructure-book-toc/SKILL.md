---
name: restructure-book-toc
description: >-
  Rebuild and normalize a complete chapter/section/subsection TOC for any book
  before translation/typesetting. Use for legal and non-legal books when the
  heading hierarchy is messy or missing.
---

# Restructure Book TOC

## Overview

This stage reconstructs a stable TOC tree (chapter/section/subsection) for the
whole book. It works for legal books and general books.

Inputs can come from:
1. Repaired markdown headings (`work/p2_repaired/*.md` or `full_repaired.md`)
2. Optional visual TOC extraction from PDF (`extract_toc.py`)

Output is a canonical TOC JSON used by downstream splitting/translation/typeset.

## Input

- `work/p2_repaired/full_repaired.md` (preferred) or merged chapter markdown
- Optional: TOC extraction JSON from `scripts/extract_toc.py`

## Output

- `work/p3_toc/chapter_structure.json`
- `work/p3_toc/toc.md`

## Workflow

### Step 1 (optional): Extract TOC pages from PDF

```bash
cd workspace
python ../book-translation-skills/scripts/extract_toc.py \
  input/book.pdf \
  --toc-pages 2-10 \
  --output work/p3_toc/chapter_structure_raw.json
```

### Step 2: Rebuild normalized TOC from markdown

```bash
cd workspace
python ../book-translation-skills/scripts/rebuild_toc.py \
  --md work/p2_repaired/full_repaired.md \
  --output-json work/p3_toc/chapter_structure.json \
  --output-md work/p3_toc/toc.md \
  --toc-json work/p3_toc/chapter_structure_raw.json
```

If no visual TOC JSON is available, omit `--toc-json`.

### Step 3: Checkpoint

- Verify every major chapter is present.
- Verify chapter/section nesting is logical (no obvious jumps).
- Confirm `chapter_structure.json` is the single source of truth for downstream stages.

