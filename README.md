# Book Translation Pipeline

端到端整书翻译流水线（PDF/Markdown -> 术语一致翻译 -> LaTeX/PDF）。

这个项目把整书翻译拆成可恢复、可并行、可审计的阶段，重点解决三件事：
- 大文档稳定处理（分块、断点续跑、失败重试）
- 全书术语一致（术语冻结 + 约束翻译）
- 法律/专业类书籍结构稳定（目录重构 + 法条双语块）

## 核心能力

- OCR 与解析统一入口（MinerU cloud API）
- OCR 后处理（补漏 + Markdown 结构修复）
- 目录重构（章/节/小节）
- 术语提取与冻结（支持多语言对）
- 翻译支持 `source_lang -> target_lang`（不再写死日->中）
- 法律模式 `:::law-bilingual`（法条原文/译文同块输出）
- LaTeX 排版与 PDF 精修

## 流水线

```text
P1 OCR
 -> P2 OCR后处理
 -> P2.5 目录重构
 -> P3 术语提取
 -> P4 翻译（多语言对）
 -> P5 LaTeX排版
 -> P6 PDF精修
```

## 仓库结构

```text
book-translation-pipeline/
├── README.md
├── SKILL.md
├── REFERENCE.md
├── workspace/
│   ├── input/
│   ├── work/
│   │   ├── p1_ocr/
│   │   ├── p2_repair_chunks/
│   │   ├── p2_repaired/
│   │   ├── p3_toc/
│   │   ├── p3_terminology/
│   │   ├── p4_translate_chunks_v2/
│   │   └── p4_translated/
│   └── output/
│       ├── latex/
│       └── pdf/
└── book-translation-skills/
    ├── scripts/
    ├── ocr-book-with-mineru-api/
    ├── supplement-ocr-missing/
    ├── repair-book-markdown/
    ├── restructure-book-toc/
    ├── extract-book-terminology/
    ├── translate-book-to-zh/
    ├── restructure-legal-layout/
    ├── typeset-book-latex/
    └── polish-book-pdf/
```

## 快速开始

### 1) 安装依赖

```bash
pip install -r book-translation-skills/requirements.txt
```

可选排版依赖（XeLaTeX）：

```bash
sudo apt-get install -y texlive-xetex texlive-latex-extra texlive-lang-chinese fonts-noto-cjk
```

### 2) 配置密钥

```bash
cp secrets.example.json workspace/local.secrets.json
# 填入 mineru/openai 配置
```

### 3) 最小可运行链路（推荐先烟测）

```bash
cd workspace

# P2.5 目录重构（基于已有修复稿）
python ../book-translation-skills/scripts/rebuild_toc.py \
  --md work/p2_repaired/full_repaired.md \
  --output-json work/p3_toc/chapter_structure.json \
  --output-md work/p3_toc/toc.md

# P4 分块
python ../book-translation-skills/scripts/split_md_paragraphs.py \
  work/p2_repaired/full_repaired.md \
  --output-dir work/p4_translate_chunks_v2 \
  --batch-chars 10000

# P4 翻译（legal）
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

## 多语言对示例

英文 -> 中文：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated_en2zh \
  --glossary work/p3_terminology/glossary.json \
  --source-lang en \
  --target-lang zh-CN \
  --domain general \
  --no-law-bilingual \
  --limit 1
```

中文 -> 英文：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated_zh2en \
  --glossary work/p3_terminology/glossary.json \
  --source-lang zh-CN \
  --target-lang en \
  --domain general \
  --no-law-bilingual \
  --limit 1
```

## 文档

- 详细操作手册：[`docs/USAGE.md`](docs/USAGE.md)
- 流程编排规范：[`SKILL.md`](SKILL.md)
- 共享约定：[`REFERENCE.md`](REFERENCE.md)

## 注意事项

- 不要把真实密钥提交到仓库。
- 全量翻译建议用 `--resume`，避免中断后重复计费。
- 法律模式下建议始终保留 `--law-bilingual`。
- 目录重构建议在翻译前固定一次，避免下游结构漂移。
