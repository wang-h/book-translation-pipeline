# Book Translation Pipeline

[![Status](https://img.shields.io/badge/status-active-1f6feb)](https://github.com/wang-h/book-translation-pipeline)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-2ea44f)](#)

Production-oriented pipeline for translating full-length books with terminology control, legal-structure handling, and reproducible PDF output.

## Why This Project

Most book translation workflows break on three problems:
- long-document instability (chunk failures, retries, resumability)
- terminology drift across chapters
- legal/structured text layout collapse during typesetting

This repo addresses those with staged processing, structured outputs, and deterministic checkpoints.

## Feature Highlights

- End-to-end workflow: OCR -> repair -> TOC rebuild -> terminology -> translation -> PDF
- Multilingual translation pairs: `source_lang -> target_lang`
- Glossary-constrained translation for consistency
- Legal mode with `:::law-bilingual` blocks
- Resume-safe batch translation (`--resume`)
- LaTeX project generation and layout QA checks

## Pipeline Stages

| Stage | Name | Core Output |
|---|---|---|
| P1 | OCR | `work/p1_ocr/full.md` |
| P2 | OCR Repair | `work/p2_repaired/full_repaired.md` |
| P2.5 | TOC Restructuring | `work/p3_toc/chapter_structure.json` |
| P3 | Terminology Extraction | `work/p3_terminology/glossary.json` |
| P4 | Translation (Multilingual) | `work/p4_translated/translated.json` + `ch01.md` |
| P5 | LaTeX Typesetting | `output/latex/` + draft PDF |
| P6 | PDF Polish | final publication-ready PDF |

## Provider & Model Support

The pipeline uses an OpenAI-compatible API contract (`/chat/completions`).

That means you can run GPT, Gemini, and Claude models through:
- direct compatible endpoints
- router/gateway providers (e.g. aihubmix, OpenRouter, custom internal gateway)

Typical model choices:
- Repair/Terms: `gpt-5.4-mini` / `claude-sonnet-4` / `gemini-2.5-pro`
- Translation: `gpt-5.4` / `claude-sonnet-4` / `gemini-2.5-pro`

## Quick Start

### 1) Install dependencies

```bash
pip install -r book-translation-skills/requirements.txt
```

Optional (XeLaTeX output):

```bash
sudo apt-get install -y texlive-xetex texlive-latex-extra texlive-lang-chinese fonts-noto-cjk
```

### 2) Configure secrets

```bash
cp secrets.example.json workspace/local.secrets.json
```

### 3) Smoke test (recommended)

```bash
cd workspace

python ../book-translation-skills/scripts/rebuild_toc.py \
  --md work/p2_repaired/full_repaired.md \
  --output-json work/p3_toc/chapter_structure.json \
  --output-md work/p3_toc/toc.md

python ../book-translation-skills/scripts/split_md_paragraphs.py \
  work/p2_repaired/full_repaired.md \
  --output-dir work/p4_translate_chunks_v2 \
  --batch-chars 10000

python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated \
  --glossary work/p3_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN \
  --domain legal \
  --law-bilingual \
  --limit 1
```

## Multilingual Examples

English -> Chinese:

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated_en2zh \
  --glossary work/p3_terminology/glossary.json \
  --source-lang en --target-lang zh-CN \
  --domain general --no-law-bilingual --limit 1
```

Chinese -> English:

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated_zh2en \
  --glossary work/p3_terminology/glossary.json \
  --source-lang zh-CN --target-lang en \
  --domain general --no-law-bilingual --limit 1
```

## Repository Layout

```text
book-translation-pipeline/
├── README.md
├── docs/USAGE.md
├── SKILL.md
├── REFERENCE.md
├── workspace/
└── book-translation-skills/
    ├── scripts/
    ├── restructure-book-toc/
    ├── translate-book-to-zh/
    ├── restructure-legal-layout/
    └── ...
```

## Operational Notes

- Use `--resume` for long jobs to avoid reprocessing and duplicate cost.
- Freeze glossary before full translation runs.
- Rebuild TOC once before translation to prevent hierarchy drift.
- Never commit real secrets.

## Documentation

- Full usage guide: [docs/USAGE.md](docs/USAGE.md)
- Orchestration skill: [SKILL.md](SKILL.md)
- Shared conventions: [REFERENCE.md](REFERENCE.md)

## Skill Integration (Cursor / Claude Code / Codex / KimiCode)

### Cursor

Cursor supports project skill loading best in this repo layout.

```bash
mkdir -p ~/.cursor/skills
ln -sfn /home/hao/book-translation-pipeline ~/.cursor/skills/book-translation-pipeline
```

Then in Cursor chat, reference stage intent directly (for example: "执行 P2.5 目录重构").

### Claude Code

Claude Code does not provide the same native skill directory mechanism as Cursor.
Recommended project-level integration:

1. Keep `SKILL.md` and `REFERENCE.md` at repo root (already present).
2. Start task with an explicit instruction:
   - "Read `SKILL.md` and execute Stage P4 with `source_lang=en target_lang=zh-CN`."
3. For stable behavior, put persistent agent rules in your project-level instruction file if your setup supports it.

### Codex

Codex also works via repository context + explicit stage prompts.
Recommended pattern:

1. Open this repository as workspace.
2. Start with:
   - "Follow `SKILL.md` and `book-translation-skills/*/SKILL.md` for this task."
3. Run stage scripts under `workspace/` exactly as documented in `docs/USAGE.md`.

### KimiCode

KimiCode integration is typically done via project knowledge/custom instruction, not a universal skill folder.
Recommended pattern:

1. Add `SKILL.md` + `REFERENCE.md` + `docs/USAGE.md` into project context.
2. Use stage-based prompts:
   - "按 P3 提取术语，语言对 en->zh-CN。"
3. Keep commands script-driven (same commands as this README/USAGE).
