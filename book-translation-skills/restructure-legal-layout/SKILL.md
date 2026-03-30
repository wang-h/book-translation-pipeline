---
name: restructure-legal-layout
description: >-
  Legal-book structural normalization: rebuild chapter hierarchy and enforce
  render-ready legal bilingual blocks before LaTeX.
---

# Restructure Legal Layout

## Overview

This skill is the legal-specialized wrapper for TOC/structure normalization.
It should be used together with `restructure-book-toc`.

## What It Does

1. Rebuild chapter/section/subsection hierarchy from repaired markdown.
2. Normalize heading depth for typesetting.
3. Ensure legal article bilingual blocks use `:::law-bilingual` format.

## Recommended Execution

```bash
cd workspace

# A) Rebuild canonical TOC (shared for all book types)
python ../book-translation-skills/scripts/rebuild_toc.py \
  --md work/p2_repaired/full_repaired.md \
  --output-json work/p3_toc/chapter_structure.json \
  --output-md work/p3_toc/toc.md

# B) During translation, keep legal article source+translation in :::law-bilingual
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p5_translated \
  --glossary work/p4_terminology/glossary.json \
  --domain legal \
  --law-bilingual
```

## Output

- `work/p3_toc/chapter_structure.json`
- `work/p3_toc/toc.md`
- Legal-ready translated markdown containing `:::law-bilingual` blocks

