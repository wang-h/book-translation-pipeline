---
name: translate-book-to-zh
description: >-
  Translate a full book with configurable language pairs (not only JA→ZH),
  chapter by chapter, using a frozen glossary to ensure terminology consistency.
  Supports legal and general modes.
---

# Translate Book (Flexible Language Pairs)

## Overview

This skill translates repaired Markdown with configurable source/target language
codes, enforcing the frozen glossary produced by `extract-book-terminology`.
Default model is `gemini-3.1-pro-preview` via an OpenAI-compatible API.

For shared conventions, see [REFERENCE.md](../../REFERENCE.md).

## Hard Constraints

- **Glossary is mandatory.** Before translating any chunk, load `work/p4_terminology/glossary.json` and inject all frozen terms into the system prompt.
- **Preserve structure.** Heading levels, footnote order, list hierarchy, table layout, and formula placeholders must survive translation intact.
- **Configurable language pair.** Use `--source-lang` and `--target-lang`.
- **Legal originals retained (optional).** In legal mode, keep source + target together using `:::law-bilingual`.
- **No paragraph merging.** Each source paragraph maps to one translated paragraph.
- **Retain original on first use.** For terms with `retain_original: true`, parenthetically include the English on its first appearance per chapter.
- **Unregistered terms.** If translation encounters a significant term not in the glossary, record it in `term_candidates.json` with `status: "new"` and use the best available translation for now. Do NOT stop the workflow.

## Input

- `work/p2_repaired/ch*.md` or `work/p2_repaired/full_repaired.md` — repaired source-language markdown.
- `work/p4_terminology/glossary.json` — frozen glossary.
- `config/chapter_manifest.json` — chapter metadata.

## Workflow

### Step 1: Load glossary and credentials

```python
import json, pathlib

secrets = json.loads(pathlib.Path("local.secrets.json").read_text())
glossary = json.loads(pathlib.Path("work/p4_terminology/glossary.json").read_text())
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

### Step 3: Translate chapter by chapter (structured JSON workflow)

1. Split chapter markdown into paragraph entries + batches:
```bash
python ../book-translation-skills/scripts/split_md_paragraphs.py \
  work/p2_repaired/ch01.md \
  --output-dir work/p4_translate_chunks_v2 \
  --batch-chars 10000
```
2. Run translation:
```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p5_translated \
  --glossary work/p4_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN \
  --domain legal \
  --law-bilingual
```
3. For non-legal books, use `--domain general --no-law-bilingual`.

### Step 4: Post-translation consistency check

After all chapters are translated:
1. Scan all `work/translated/ch*.md` files for glossary terms.
2. Flag any instance where a frozen term is translated differently from `preferred_translation`.
3. Flag any use of `forbidden_translations`.
4. Report findings. If drift is found, re-translate only the affected chunks with reinforced glossary prompts.

### Step 5: Handle new terms

Collect all terms recorded as `status: "new"` in `term_candidates.json`. Present them to the user for review. Optionally re-run terminology extraction on just these terms and merge into `glossary.json`.

## Output

- `work/p5_translated/ch01.md` (assembled markdown from translated entries)
- `work/p5_translated/translated.json` (entry-level translation result)
- `work/p5_translated/progress.json` (batch progress)
- Updated `config/chapter_manifest.json` with `translation_status: "done"` per chapter.
- Updated `work/p4_terminology/term_candidates.json` with any new terms found during translation.

## Error Handling

- If GPT returns incomplete or structurally broken output, retry that chunk (max 2 retries).
- If a chunk consistently fails, mark as `translation_status: "needs_review"` and continue.
- Never re-translate the entire book for a single chunk failure.
