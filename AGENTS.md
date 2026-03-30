# Repository Guidelines

## Project Structure & Module Organization
- Core docs live at repository root: `README.md`, `docs/USAGE.md`, `SKILL.md`, `REFERENCE.md`.
- Execution scripts are in `book-translation-skills/scripts/` (OCR, repair, TOC rebuild, term extraction, translation, LaTeX/PDF).
- **Reference corpus** for terminology extraction: `book-translation-skills/reference_corpus/`
  - Contains master glossaries with definitions, forbidden translations, and usage notes
  - Example: `forest_law_master_glossary.json` for fr→zh forest law translation
- Runtime data is under `workspace/`:
  - `workspace/input/` source files
  - `workspace/work/` staged artifacts (`p1_ocr` ... `p5_translated`)
  - `workspace/output/` LaTeX and PDFs
- Keep generated artifacts out of Git unless explicitly required for release snapshots.

## Build, Test, and Development Commands
- Install deps: `pip install -r book-translation-skills/requirements.txt`
- Enter workspace: `cd workspace`
- Split translation entries:  
  `python ../book-translation-skills/scripts/split_md_paragraphs.py work/p2_repaired/full_repaired.md --output-dir work/p4_translate_chunks_v2 --batch-chars 10000`
- Run translation (with provider selection):  
  `python ../book-translation-skills/scripts/openai_translate_md.py --entries-dir work/p5_translate_chunks_v2 --output-dir work/p5_translated --glossary work/p4_terminology/glossary.json --source-lang fr --target-lang zh-CN --domain legal --no-law-bilingual --provider kimi`
- Coverage gate:  
  `python ../book-translation-skills/scripts/check_translation_coverage.py --entries .../entries.json --translated .../translated.json --report .../coverage_report.json`
- Terminology compliance check:  
  `python ../book-translation-skills/scripts/check_terminology_compliance.py --glossary ../book-translation-skills/reference_corpus/forest_law_master_glossary.json --translated work/p5_translated/translated.json`
- Build PDF (XeLaTeX):  
  `python ../book-translation-skills/scripts/build_latex.py work/p5_translated --title "Book" && cd output/latex && xelatex -interaction=nonstopmode book.tex && xelatex -interaction=nonstopmode book.tex`

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, UTF-8, type hints preferred.
- Use snake_case for files/functions/CLI flags; keep stage-like directory names (`p1_ocr`, `p5_translated`).
- Prefer small, script-first changes; keep commands reproducible and resume-safe (`--resume`).

## Testing Guidelines
- No dedicated unit-test suite currently; use pipeline quality gates:
  - `check_translation_coverage.py` must report no `missing/empty/failed`.
  - **Terminology compliance check**: `check_terminology_compliance.py` validates against forbidden translations.
  - Manual legal review before typesetting (sample beginning/middle/end + high-risk clauses).
  - PDF acceptance checks after build (TOC continuity, contamination scan, layout sanity).

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history: `fix: ...`, `add: ...`, `refactor: ...`, `improve: ...`.
- Keep commits scoped to one concern (docs, script logic, workflow gate, etc.).
- PRs should include:
  - objective and changed stages (e.g., P4/P5)
  - exact commands used to validate
  - key output paths (e.g., `workspace/output/pdf/...`)
  - screenshots/pages for layout-impacting PDF changes.

## Security & Configuration Tips
- Never commit real keys. Use `secrets.example.json` and local `workspace/local.secrets.json`.
- Validate that target-language-only deliverables do not leak source-language residue unless explicitly requested.
