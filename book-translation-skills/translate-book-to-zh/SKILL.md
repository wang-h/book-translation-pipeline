---
name: translate-book-to-zh
description: >-
  Translate a full book from its source language to Chinese, chapter by chapter,
  using a frozen glossary to ensure terminology consistency. Use when translating
  an entire book, performing chapter-by-chapter translation, or applying a
  glossary-constrained translation workflow.
---

# Translate Book to Chinese

## Overview

This skill translates repaired source-language Markdown into Chinese, chapter by chapter, enforcing the frozen glossary produced by `extract-book-terminology`. It uses GPT-5.4 via the aihubmix OpenAI-compatible API.

For shared conventions, see [REFERENCE.md](../../REFERENCE.md).

## Hard Constraints

- **Glossary is mandatory.** Before translating any chunk, load `work/terminology/glossary.json` and inject all frozen terms into the system prompt.
- **Preserve structure.** Heading levels, footnote order, list hierarchy, table layout, and formula placeholders must survive translation intact.
- **No paragraph merging.** Each source paragraph maps to one translated paragraph.
- **Retain original on first use.** For terms with `retain_original: true`, parenthetically include the English on its first appearance per chapter.
- **Unregistered terms.** If translation encounters a significant term not in the glossary, record it in `term_candidates.json` with `status: "new"` and use the best available translation for now. Do NOT stop the workflow.

## Input

- `work/repaired/ch*.md` — repaired source-language chapters.
- `work/terminology/glossary.json` — frozen glossary.
- `config/chapter_manifest.json` — chapter metadata.

## Workflow

### Step 1: Load glossary and credentials

```python
import json, pathlib

secrets = json.loads(pathlib.Path("local.secrets.json").read_text())
glossary = json.loads(pathlib.Path("work/terminology/glossary.json").read_text())
```

### Step 2: Build glossary prompt segment

Format frozen terms into a compact table for the system prompt:

```
## Mandatory Terminology
| English | Chinese | Notes |
|---------|---------|-------|
| due process | 正当程序 | 首次出现括注英文 |
| ...     | ...     | ...   |

You MUST use these exact translations. Do NOT deviate.
```

### Step 3: Translate chapter by chapter

For each chapter, split into chunks (3000-4000 tokens) using `scripts/split_book.py`.

For each chunk, call GPT-5.4 with:

```
System: You are a professional book translator. Translate the following text
into Chinese. Follow these rules strictly:
1. Use the mandatory terminology table above — no deviations.
2. Preserve all Markdown structure: headings, footnotes, lists, tables, formulas.
3. Each source paragraph = one translated paragraph.
4. For terms marked "retain_original", include English in parentheses on first
   use in this chapter.
5. Use 「」for book titles, "" for quotes, maintain Chinese punctuation throughout.
6. Do not add, remove, or reorder content.

{glossary_prompt_segment}

User: {chunk_text}
```

Include a brief context summary from the previous chunk to maintain coherence across chunk boundaries.

### Step 4: Post-translation consistency check

After all chapters are translated:
1. Scan all `work/translated/ch*.md` files for glossary terms.
2. Flag any instance where a frozen term is translated differently from `preferred_translation`.
3. Flag any use of `forbidden_translations`.
4. Report findings. If drift is found, re-translate only the affected chunks with reinforced glossary prompts.

### Step 5: Handle new terms

Collect all terms recorded as `status: "new"` in `term_candidates.json`. Present them to the user for review. Optionally re-run terminology extraction on just these terms and merge into `glossary.json`.

## Output

- `work/translated/ch01.md`, `work/translated/ch02.md`, ... — one file per chapter.
- Updated `config/chapter_manifest.json` with `translation_status: "done"` per chapter.
- Updated `work/terminology/term_candidates.json` with any new terms found during translation.

## Error Handling

- If GPT returns incomplete or structurally broken output, retry that chunk (max 2 retries).
- If a chunk consistently fails, mark as `translation_status: "needs_review"` and continue.
- Never re-translate the entire book for a single chunk failure.
