# Book Translation Pipeline Skill

## Overview
Production-oriented pipeline for translating full-length books with terminology control, legal-structure handling, and reproducible PDF output.

## Supported Providers (2026 Latest)
- **Kimi** (kimi-k2.5) - 256K context, best for Chinese legal texts
- **OpenAI** (gpt-5.4/gpt-5.4-mini) - Latest GPT-5.4 series
- **Gemini** (gemini-2.5-flash/gemini-3.1-pro) - 1M token context
- **Claude** (claude-sonnet-4.6/claude-opus-4.6) - Best for legal reasoning

## Quick Commands

### Translate a French Legal Book
```bash
cd workspace
python run_translation_pipeline.py --book codepenal --wait-p2
```

### Step-by-Step Manual Control

**P1: OCR**
```bash
python ../book-translation-skills/scripts/mineru_submit.py input/book.pdf --ocr
```

**P2: Repair**
```bash
python ../book-translation-skills/scripts/openai_repair_md.py \
  --chunks-dir work/p2_repair_chunks_book \
  --output work/p2_repaired_book/full_repaired.md \
  --provider kimi
```

**P3: TOC Restructure**
```bash
python ../book-translation-skills/scripts/rebuild_toc.py \
  --md work/p2_repaired_book/full_repaired.md \
  --output-json work/p3_toc_book/chapter_structure.json
```

**P4: Extract Terms**
```bash
python ../book-translation-skills/scripts/extract_terms.py \
  work/p2_repaired_book \
  --output work/p4_terminology_book/glossary.json \
  --source-lang fr --target-lang zh-CN \
  --provider kimi \
  --master-glossary ../reference_corpus/forest_law_master_glossary.json
```

**P5: Translate**
```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_book \
  --output-dir work/p5_translated_book \
  --glossary work/p4_terminology_book/glossary.json \
  --source-lang fr --target-lang zh-CN \
  --domain legal --provider kimi
```

## Configuration

Edit `workspace/local.secrets.json`:
```json
{
  "default_provider": "kimi",
  "kimi": {
    "base_url": "https://api.moonshot.cn/v1",
    "api_key": "your-key",
    "models": {
      "extract": "kimi-k2.5",
      "translate": "kimi-k2.5"
    }
  }
}
```

## Quality Gates

**Terminology Compliance Check:**
```bash
python ../book-translation-skills/scripts/check_terminology_compliance.py \
  --glossary ../reference_corpus/forest_law_master_glossary.json \
  --translated work/p5_translated_book/translated.json
```

## Currently Translating
| Book | Status | Provider |
|------|--------|----------|
| 马里刑法典 (Code Pénal) | P2 Repair (1/450) | Kimi |
| 毛里塔尼亚投资法 | P2 Repair (2/64) | Kimi |
