---
name: ocr-book-with-mineru-api
description: >-
  Use MinerU v4 cloud AI standard API to OCR an entire book PDF into structured
  Markdown and JSON. Use when processing full-book PDFs, submitting MinerU tasks,
  polling OCR results, or downloading parsed book content.
---

# OCR Book with MinerU Cloud AI API

## Overview

This skill converts a full-book PDF into structured Markdown and JSON using the MinerU v4 cloud AI standard API exclusively. Local MinerU CLI is never used. The Agent lightweight API is also excluded due to its strict page/size limits.

For shared conventions (directory layout, secrets path, chunking rules), see [REFERENCE.md](../../REFERENCE.md).

## Prerequisites

- `local.secrets.json` must exist at the pipeline project root with valid `mineru.token`.
- Input PDF placed in `<project_root>/input/`.

## Workflow

### Step 1: Read credentials

```python
import json, pathlib
secrets = json.loads(pathlib.Path("local.secrets.json").read_text())
MINERU_TOKEN = secrets["mineru"]["token"]
MINERU_BASE = secrets["mineru"]["base_url"]
```

### Step 2: Submit task

Use the batch file-upload endpoint for local PDFs, or the single-URL endpoint if the PDF is already hosted.

**File upload flow:**

```
POST {MINERU_BASE}/file-urls/batch
Authorization: Bearer {MINERU_TOKEN}
Content-Type: application/json

{
  "files": [{"name": "<filename>.pdf"}],
  "model_version": "vlm",
  "enable_formula": true,
  "enable_table": true,
  "is_ocr": true,
  "extra_formats": ["latex"]
}
```

Then PUT the file body to the returned `file_url`.

**URL flow:**

```
POST {MINERU_BASE}/extract/task
Authorization: Bearer {MINERU_TOKEN}

{
  "url": "<public_pdf_url>",
  "model_version": "vlm",
  "enable_formula": true,
  "enable_table": true,
  "is_ocr": true,
  "extra_formats": ["latex"]
}
```

Default parameters:
- `model_version`: `vlm` (highest accuracy for complex layouts and formulas).
- `enable_formula`: `true`.
- `enable_table`: `true`.
- `is_ocr`: `true` for scanned documents; `false` for born-digital PDFs.
- `extra_formats`: include `["latex"]` when the book has many formulas/tables.

### Step 3: Poll for results

```
GET {MINERU_BASE}/extract/task/{task_id}
Authorization: Bearer {MINERU_TOKEN}
```

Recognize states: `pending`, `running`, `converting`, `done`, `failed`.

Poll every 10 seconds. Log `extracted_pages / total_pages` progress when `running`.

### Step 4: Download results

When `state == "done"`, download `full_zip_url`. Unzip into `work/ocr/`:
- `full.md` — primary Markdown output.
- `content_list.json` — structured content with bounding boxes.
- `images/` — extracted images.
- `middle.json`, `model.json` — intermediate results for debugging.

### Step 5: Validate

- Confirm `full.md` is non-empty and contains expected chapter headings.
- Count pages in manifest vs `total_pages` from API.
- Spot-check a few pages for garbled text or missing tables.

## Error Handling

| Error code | Meaning | Action |
|-----------|---------|--------|
| `-60005` | File too large (>200MB) | Split PDF by page ranges, submit multiple tasks |
| `-60006` | Too many pages (>600) | Submit with `page_ranges` parameter in chunks |
| `-60007` | Model service unavailable | Wait 5 minutes and retry |
| `-60010` | Parse failed | Retry with `model_version=pipeline`; if still fails, split page ranges |
| `-60017` | Retry limit reached | Wait for model upgrade, or try different `page_ranges` |
| timeout | No `done` after 30 min | Re-check task status; if stuck at `running`, submit a new task |

All error recovery stays within the cloud API. Never fall back to local CLI.

## Outputs

- `work/ocr/full.md`
- `work/ocr/content_list.json`
- `work/ocr/images/`
- `config/chapter_manifest.json` (generated from headings in `full.md`)

## Helper Scripts

- `scripts/mineru_submit.py` — submit task and save `task_id`.
- `scripts/mineru_poll.py` — poll status and download results.
