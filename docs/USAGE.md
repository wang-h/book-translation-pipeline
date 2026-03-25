# 使用说明（Usage Guide）

本文档给出从输入文件到最终 PDF 的分阶段执行方式，适用于法律书和普通专业书。

## 0. 前置条件

1. 安装 Python 依赖
```bash
pip install -r book-translation-skills/requirements.txt
```

2. 如需 XeLaTeX 排版
```bash
sudo apt-get install -y texlive-xetex texlive-latex-extra texlive-lang-chinese fonts-noto-cjk
```

3. 配置密钥
```bash
cp secrets.example.json workspace/local.secrets.json
```

## 1. 标准流程

在 `workspace/` 下执行：

```bash
cd /home/hao/book-translation-pipeline/workspace
```

### P1 OCR

```bash
BATCH_ID=$(python ../book-translation-skills/scripts/mineru_submit.py input/book.pdf --ocr)
python ../book-translation-skills/scripts/mineru_poll.py "$BATCH_ID" --batch
```

### P2 OCR后处理（修复）

```bash
python ../book-translation-skills/scripts/split_book.py \
  work/p1_ocr/full.md \
  --output-dir work/p2_repair_chunks \
  --max-tokens 4000

python ../book-translation-skills/scripts/openai_repair_md.py \
  --chunks-dir work/p2_repair_chunks \
  --output work/p2_repaired/full_repaired.md
```

### P2.5 目录重构（新增）

```bash
python ../book-translation-skills/scripts/rebuild_toc.py \
  --md work/p2_repaired/full_repaired.md \
  --output-json work/p3_toc/chapter_structure.json \
  --output-md work/p3_toc/toc.md
```

可选：先用视觉模型提取 PDF 目录页，再合并页码

```bash
python ../book-translation-skills/scripts/extract_toc.py \
  input/book.pdf \
  --toc-pages 2-10 \
  --output work/p3_toc/chapter_structure_raw.json

python ../book-translation-skills/scripts/rebuild_toc.py \
  --md work/p2_repaired/full_repaired.md \
  --toc-json work/p3_toc/chapter_structure_raw.json \
  --output-json work/p3_toc/chapter_structure.json \
  --output-md work/p3_toc/toc.md
```

### P3 术语提取（支持多语言对）

```bash
python ../book-translation-skills/scripts/extract_terms.py \
  work/p2_repaired \
  --output work/p3_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN
```

### P4 翻译（支持多语言对）

先切分为结构化 entries/batches：

```bash
python ../book-translation-skills/scripts/split_md_paragraphs.py \
  work/p2_repaired/full_repaired.md \
  --output-dir work/p4_translate_chunks_v2 \
  --batch-chars 10000
```

法律模式（保留法条双语块）：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated \
  --glossary work/p3_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN \
  --domain legal \
  --law-bilingual
```

通用模式（不强制法条双语块）：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated \
  --glossary work/p3_terminology/glossary.json \
  --source-lang en \
  --target-lang zh-CN \
  --domain general \
  --no-law-bilingual
```

断点续跑：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated \
  --glossary work/p3_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN \
  --domain legal \
  --law-bilingual \
  --resume
```

覆盖率检查：

```bash
python ../book-translation-skills/scripts/check_translation_coverage.py \
  --entries work/p4_translate_chunks_v2/entries.json \
  --translated work/p4_translated/translated.json \
  --report work/p4_translated/coverage_report.json
```

### P5 排版生成 PDF

```bash
python ../book-translation-skills/scripts/build_latex.py work/p4_translated --title "书名"
cd output/latex
xelatex -interaction=nonstopmode book.tex
xelatex -interaction=nonstopmode book.tex
cd ../..
```

### P6 PDF 精修

```bash
python ../book-translation-skills/scripts/pdf_layout_check.py output/latex --manifest config/chapter_manifest.json
```

## 2. 常见语言对

- 日文 -> 简中：`--source-lang ja --target-lang zh-CN`
- 英文 -> 简中：`--source-lang en --target-lang zh-CN`
- 简中 -> 英文：`--source-lang zh-CN --target-lang en`

## 3. 建议测试策略

1. 先做烟测：`--limit 1`
2. 再做小批量：`--resume --limit 10`
3. 稳定后全量：`--resume` 不设 `--limit`

## 4. 产物检查

- 目录重构：`work/p3_toc/chapter_structure.json`
- 术语表：`work/p3_terminology/glossary.json`
- 翻译结果：`work/p4_translated/translated.json`、`work/p4_translated/ch01.md`
- 覆盖报告：`work/p4_translated/coverage_report.json`
- 最终 PDF：`output/pdf/book.pdf`

