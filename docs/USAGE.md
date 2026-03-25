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

`openai.base_url` 使用 OpenAI-compatible 接口即可，不绑定某一家网关。
也就是说你可以接 GPT / Gemini / Claude，只要该提供方支持兼容接口。

示例（节选）：

```json
{
  "openai": {
    "base_url": "https://your-compatible-endpoint/v1",
    "api_key": "YOUR_KEY",
    "extract_model": "gpt-5.4-mini",
    "translate_model": "gemini-2.5-pro"
  }
}
```

可替换模型示例：
- GPT: `gpt-5.4`, `gpt-5.4-mini`
- Gemini: `gemini-2.5-pro`
- Claude: `claude-sonnet-4`

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

## 5. 在不同 AI 编码工具中导入/使用 Skill

### Cursor（推荐）

```bash
mkdir -p ~/.cursor/skills
ln -sfn /home/hao/book-translation-pipeline ~/.cursor/skills/book-translation-pipeline
```

验证：

```bash
ls -la ~/.cursor/skills/book-translation-pipeline
```

在 Cursor 中可直接说：
- "执行 P2.5 目录重构"
- "执行 P4，语言对 en->zh-CN，general 模式"

### Claude Code

Claude Code 一般不走 Cursor 那套 `~/.cursor/skills` 导入方式。建议：

1. 保持仓库根目录有 `SKILL.md`、`REFERENCE.md`（本项目已提供）。
2. 每次任务开头显式要求：
   - "先读取 SKILL.md，再按 P4 执行。"
3. 如果你的 Claude Code 环境支持项目级指令文件，把上述规则固化。

### Codex

Codex 也是按“仓库上下文 + 显式规则”工作：

1. 打开本仓库为工作目录。
2. 首条指令写明：
   - "遵循 SKILL.md 与对应子 SKILL.md。"
3. 后续直接下达阶段命令（P1~P6）。

### KimiCode

KimiCode 常见做法是项目知识/提示词注入，而不是统一 skill 目录：

1. 把 `SKILL.md`、`REFERENCE.md`、本文件加入项目知识。
2. 用阶段化指令驱动：
   - "按 P3 提取术语，source=en target=zh-CN。"
3. 脚本执行命令与本手册保持一致。

### OpenClaw

OpenClaw 更适合“项目级规则注入”，而不是 Cursor 风格的全局 skill 软链接。

建议：

1. 在 OpenClaw 中打开本仓库作为项目。
2. 把以下文件设为常驻上下文/规则：
   - `SKILL.md`
   - `REFERENCE.md`
   - `docs/USAGE.md`
3. 用阶段指令驱动执行：
   - "执行 P2.5 目录重构"
   - "执行 P4，source=en target=zh-CN，general 模式"
4. 始终优先执行脚本命令（`book-translation-skills/scripts/*.py`）保证可复现。
