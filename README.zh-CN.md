# Book Translation Pipeline（中文说明）

[English README](README.md)

面向生产的整书翻译流水线：支持术语一致性控制、法律文本结构处理，以及可复现的 PDF 输出。

## 项目解决的问题

传统整书翻译常见失败点：
- 长文档不稳定（中断、重试、断点恢复困难）
- 章节间术语漂移
- 法律/结构化文本在排版阶段失真

本项目通过分阶段流水线和结构化中间产物解决上述问题。

## 核心特性

- 全流程：OCR -> 修复 -> 目录重构 -> 术语 -> 翻译 -> PDF
- 多语言对翻译：`source_lang -> target_lang`
- 基于术语表约束翻译一致性
- 法律模式 `:::law-bilingual`（法条原文 + 译文）
- 批处理断点续跑（`--resume`）
- LaTeX 生成与版面 QA

## 流程阶段

| 阶段 | 名称 | 核心产物 |
|---|---|---|
| P1 | OCR | `work/p1_ocr/full.md` |
| P2 | OCR 修复 | `work/p2_repaired/full_repaired.md` |
| P2.5 | 目录重构 | `work/p3_toc/chapter_structure.json` |
| P3 | 术语提取 | `work/p3_terminology/glossary.json` |
| P4 | 翻译（多语言对） | `work/p4_translated/translated.json` + `ch01.md` |
| P5 | LaTeX 排版 | `output/latex/` + 草稿 PDF |
| P6 | PDF 精修 | 最终可发布 PDF |

## 模型与提供方支持

项目使用 OpenAI-compatible 接口（`/chat/completions`），因此不绑定单一网关。

可接入：
- GPT
- Gemini
- Claude

只要你的服务商提供兼容接口即可（例如 aihubmix、OpenRouter、私有网关）。

常见模型建议：
- 修复/术语：`gpt-5.4-mini` / `claude-sonnet-4` / `gemini-2.5-pro`
- 翻译：`gpt-5.4` / `claude-sonnet-4` / `gemini-2.5-pro`

## 快速开始

### 1) 安装依赖

```bash
pip install -r book-translation-skills/requirements.txt
```

可选（XeLaTeX 排版）：

```bash
sudo apt-get install -y texlive-xetex texlive-latex-extra texlive-lang-chinese fonts-noto-cjk
```

### 2) 配置密钥

```bash
cp secrets.example.json workspace/local.secrets.json
```

### 3) 烟测（推荐）

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

## 多语言示例

英文 -> 中文：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated_en2zh \
  --glossary work/p3_terminology/glossary.json \
  --source-lang en --target-lang zh-CN \
  --domain general --no-law-bilingual --limit 1
```

中文 -> 英文：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p4_translated_zh2en \
  --glossary work/p3_terminology/glossary.json \
  --source-lang zh-CN --target-lang en \
  --domain general --no-law-bilingual --limit 1
```

## 文档入口

- 英文：[`README.md`](README.md)
- 中文：[`README.zh-CN.md`](README.zh-CN.md)
- 详细使用手册：[`docs/USAGE.md`](docs/USAGE.md)
- 编排规范：[`SKILL.md`](SKILL.md)
- 共享约定：[`REFERENCE.md`](REFERENCE.md)

## Skill 导入（Cursor / Claude Code / Codex / KimiCode / OpenClaw）

请参考英文 README 对应章节，或 `docs/USAGE.md` 第 5 节。
