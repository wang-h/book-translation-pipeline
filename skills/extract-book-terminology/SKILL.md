---
name: extract-book-terminology
description: >-
  Extract and freeze a glossary of key terms, proper nouns, abbreviations,
  institution names, person names, and fixed phrases from a repaired book
  Markdown before translation begins. Use when extracting terminology, building
  a glossary, or preparing a translation memory for book translation.
---

# Extract Book Terminology

## Overview

This skill scans the entire repaired Markdown of a book and produces a frozen glossary (`glossary.json`) and a human-readable translation memory (`translation_memory.md`). These assets must be created **before** translation begins to ensure term consistency across all chapters.

For shared conventions, see [REFERENCE.md](../../REFERENCE.md).

## Hard Constraints

- **Must run before translation.** The `translate-book-to-zh` skill requires `glossary.json` as input.
- **One term, one preferred translation.** Every entry must have exactly one `preferred_translation`.
- **Forbidden translations must be listed.** Common mistranslations should be explicitly blocked.
- **Retain original form.** For important terms, mark `retain_original: true` so translators parenthetically include the English original on first use.

## Input

- `work/repaired/ch*.md` — all repaired chapter files.
- `config/chapter_manifest.json` — chapter metadata.

## Workflow

### Step 1: Collect term candidates

Use `scripts/extract_terms.py` to do a first pass:
1. Extract all capitalized multi-word phrases, abbreviations, quoted terms, and italicized terms.
2. Count frequency across chapters.
3. Group variants (e.g., "Due Process" / "due process" / "DUE PROCESS").
4. Output `work/terminology/term_candidates.json`.

### Step 2: Classify and translate candidates with GPT-5.4

For each batch of candidates (50-100 terms), call GPT-5.4:

```
You are a professional translator and terminologist. Given the following list
of English terms extracted from a book about [BOOK_SUBJECT], provide for each:

1. preferred_translation: The best Chinese translation.
2. alternatives: Other acceptable translations (array).
3. forbidden_translations: Common mistranslations to avoid (array).
4. part_of_speech_or_type: One of "legal_term", "person_name",
   "institution", "abbreviation", "book_title", "concept", "other".
5. retain_original: true if the English should appear in parentheses on
   first use.
6. notes: Any usage guidance.

Return JSON array. No explanations outside the JSON.
```

Include 2-3 chapter context sentences for each term to improve translation quality.

### Step 3: Human review checkpoint

Output `work/terminology/term_candidates.json` with `status: "candidate"` for all entries. The user may review and override translations before freezing.

### Step 4: Freeze glossary

After review (or immediately if user opts to skip review):
- Copy approved entries to `work/terminology/glossary.json` with `status: "frozen"`.
- Generate `work/terminology/translation_memory.md` — a human-readable table:

```markdown
| English Term | Chinese Translation | Type | Notes |
|-------------|--------------------|----- |-------|
| due process | 正当程序 | legal_term | 首次出现括注英文 |
```

## Output

- `work/terminology/term_candidates.json` — full candidate list with frequencies and chapter sources.
- `work/terminology/glossary.json` — frozen glossary for translation.
- `work/terminology/translation_memory.md` — human-readable reference.

## glossary.json Entry Format

See [REFERENCE.md](../../REFERENCE.md) for the canonical entry schema.

## Error Handling

- If GPT returns malformed JSON for a batch, retry that batch only.
- If a term has conflicting translations across batches, flag it as `status: "conflict"` for human resolution.
