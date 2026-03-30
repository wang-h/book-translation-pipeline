---
name: extract-book-terminology
description: >-
  Extract and freeze a glossary of key terms from a repaired book Markdown
  before translation begins. Uses LLM to understand text semantics and identify
  terms that need consistent translation — law names, institutions, roles,
  abbreviations, proper nouns, fixed legal phrases, etc.
---

# Extract Book Terminology

## Overview

This skill uses an LLM to read repaired Markdown and extract terms that require consistent translation. The output is a frozen `glossary.json` used by P5. It supports configurable language pairs.

**Core principle:** Let the LLM understand the text and identify terms — don't rely on regex patterns.

## Hard Constraints

- **Must run before translation.** The `translate-book-to-zh` skill requires `glossary.json` as input.
- **One term, one preferred translation.** Every entry should map one `source` to one `target`.
- **LLM-driven extraction.** The script sends text chunks to the LLM and asks it to identify terms worth freezing.

## Input

- `workspace/work/p2_repaired/*.md` — repaired Markdown (one file or multiple chapters).

## Workflow

### Step 1: Split text into chunks and send to LLM

Run `scripts/extract_terms.py`:

```bash
cd workspace
python ../book-translation-skills/scripts/extract_terms.py work/p2_repaired \
  --output work/p4_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN
```

Default model: `gpt-5.4-mini` (fast, accurate enough for term extraction; override with `--model`).

The script:
1. Reads all `.md` files in the input directory.
2. Splits the combined text into chunks (~8000 chars each).
3. Sends each chunk to the LLM with a prompt asking it to extract terms that need consistent translation.
4. The LLM returns structured JSON with: source term, recommended Chinese translation, term type, and notes.
5. Merges results across all chunks: deduplicates, picks the most common translation for each term, aggregates frequency.

### Step 2: Human review (optional)

The script outputs the glossary directly. The user may review and edit `glossary.json` before proceeding to P5.

If the user wants to skip review, proceed directly to P4.

### Step 3: Use in translation

P5's `openai_translate_md.py` reads `glossary.json` and injects the term table into every translation prompt.

## Output

- `workspace/work/p4_terminology/glossary.json` — frozen glossary for translation.

## glossary.json Format

```json
{
  "meta": {
    "source_lang": "ja",
    "target_lang": "zh-CN",
    "status": "frozen",
    "book": "書名"
  },
  "terms": [
    {
      "source": "教育基本法",
      "target": "教育基本法",
      "type": "law_name",
      "notes": ""
    }
  ]
}
```

Backward compatibility: legacy fields `ja` / `zh` are still readable.

Term types: `law_name`, `institution`, `role`, `abbreviation`, `person_name`, `concept`, `legal_phrase`, `other`.

## Error Handling

- If LLM returns malformed JSON for a chunk, retry that chunk (up to 3 times).
- If a term appears in multiple chunks with different translations, pick the most frequent one and log the conflict.
