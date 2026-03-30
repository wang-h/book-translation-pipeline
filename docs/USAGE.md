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

### 多 LLM Provider 支持 (2025 最新)

所有脚本支持 `--provider` 参数切换不同 LLM，支持：
- **openai**: OpenAI API 或兼容接口
- **kimi**: 月之暗面 (Moonshot) API
- **gemini**: Google Gemini API
- **anthropic**: Claude API

#### 2026 最新模型配置

| Provider | 术语提取 (extract) | 翻译 (translate) | 特点 |
|---------|-------------------|-----------------|------|
| **Kimi** | `kimi-k2.5` | `kimi-k2.5` | 256K上下文，多模态，Agent能力最强 |
| **OpenAI** | `gpt-5.4-mini` | `gpt-5.4` | 最新GPT-5.4系列，推理能力大幅提升 |
| **Gemini** | `gemini-2.5-flash` | `gemini-3.1-pro` | Gemini 3.1 Pro，100万token上下文 |
| **Claude** | `claude-sonnet-4.6` | `claude-opus-4.6` | Claude 4.6系列，法律文本最强 |

配置示例（`secrets.json`）：

```json
{
  "default_provider": "kimi",
  
  "openai": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "models": {
      "extract": "gpt-5.4-mini",
      "translate": "gpt-5.4",
      "supplement": "gpt-5.4-mini",
      "polish": "gpt-5.4"
    }
  },
  
  "kimi": {
    "base_url": "https://api.moonshot.cn/v1",
    "api_key": "sk-...",
    "models": {
      "extract": "kimi-k2.5",
      "translate": "kimi-k2.5",
      "supplement": "kimi-k2.5",
      "polish": "kimi-k2.5"
    }
  },
  
  "gemini": {
    "api_key": "AIza...",
    "models": {
      "extract": "gemini-2.5-flash",
      "translate": "gemini-3.1-pro",
      "supplement": "gemini-2.5-flash",
      "polish": "gemini-3.1-pro"
    }
  },
  
  "anthropic": {
    "api_key": "sk-ant-...",
    "models": {
      "extract": "claude-sonnet-4-6-20260217",
      "translate": "claude-opus-4-6-20260205",
      "supplement": "claude-sonnet-4-6-20260217",
      "polish": "claude-sonnet-4-6-20260217"
    }
  }
}
```

#### 2026年模型选择建议

- **法律翻译首选 Claude 4.6/5**: Claude Opus 4.6 (2026年2月) 是目前法律文本理解最准确的模型
- **性价比首选 Kimi K2.5**: 月之暗面最新模型，256K上下文，中文理解优秀，价格仅为GPT-5.4的1/3
- **长文档首选 Gemini 3.1 Pro**: Google 2026年2月最新旗舰，100万token上下文，适合整书翻译
- **速度首选 OpenAI GPT-5.4-mini**: GPT-5.4系列轻量版，响应快，适合术语提取
- **最强编程翻译**: Claude Sonnet 4.6 (2026年2月)，SWE-bench 79.6%，适合技术文档

#### 各Provider 2026年最新模型发布时间线

| 时间 | Provider | 模型 | 亮点 |
|-----|----------|------|------|
| 2026-03 | OpenAI | GPT-5.4 | 最新旗舰 |
| 2026-02 | Anthropic | Claude Sonnet 4.6 | 性价比最佳 |
| 2026-02 | Anthropic | Claude Opus 4.6 | 推理最强 |
| 2026-02 | Google | Gemini 3.1 Pro | 最新旗舰 |
| 2026-01 | Moonshot | Kimi K2.5 | 多模态Agent |
| 2025-12 | Google | Gemini 3.0 Pro | (已弃用) |

使用方式：
```bash
# 使用默认 provider
python extract_terms.py work/p2_repaired --output work/p4_terminology/glossary.json

# 显式指定 provider
python extract_terms.py work/p2_repaired --output work/p4_terminology/glossary.json --provider kimi

# 指定 provider 并覆盖模型
python openai_translate_md.py --entries-dir ... --provider gemini --model gemini-2.5-pro
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

### P3 目录重构

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

### P4 术语提取（支持多语言对）

基础用法：

```bash
python ../book-translation-skills/scripts/extract_terms.py \
  work/p2_repaired \
  --output work/p4_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN
```

**使用主术语库参考（推荐用于专业领域）**：

```bash
python ../book-translation-skills/scripts/extract_terms.py \
  work/p2_repaired \
  --output work/p4_terminology/glossary.json \
  --source-lang fr \
  --target-lang zh-CN \
  --master-glossary ../book-translation-skills/reference_corpus/forest_law_master_glossary.json
```

主术语库 (`forest_law_master_glossary.json`) 包含：
- 专家审定的标准译法
- 定义和使用说明
- **禁用译法**（如禁止将"domaine national"译为"国有地带"）
- 示例句

这样 LLM 在提取术语时会参考权威术语库，而非凭空翻译。

### P5 翻译（支持多语言对）

先切分为结构化 entries/batches：

```bash
python ../book-translation-skills/scripts/split_md_paragraphs.py \
  work/p2_repaired/full_repaired.md \
  --output-dir work/p5_translate_chunks_v2 \
  --batch-chars 10000
```

法律模式（保留法条双语块）：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p5_translated \
  --glossary work/p4_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN \
  --domain legal \
  --law-bilingual
```

通用模式（不强制法条双语块）：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p5_translated \
  --glossary work/p4_terminology/glossary.json \
  --source-lang en \
  --target-lang zh-CN \
  --domain general \
  --no-law-bilingual
```

断点续跑：

```bash
python ../book-translation-skills/scripts/openai_translate_md.py \
  --entries-dir work/p4_translate_chunks_v2 \
  --output-dir work/p5_translated \
  --glossary work/p4_terminology/glossary.json \
  --source-lang ja \
  --target-lang zh-CN \
  --domain legal \
  --law-bilingual \
  --resume
```

覆盖率检查：

```bash
python ../book-translation-skills/scripts/check_translation_coverage.py \
  --entries work/p5_translate_chunks_v2/entries.json \
  --translated work/p5_translated/translated.json \
  --report work/p5_translated/coverage_report.json
```

**术语合规检查（检测禁用译法）**：

```bash
python ../book-translation-skills/scripts/check_terminology_compliance.py \
  --glossary ../book-translation-skills/reference_corpus/forest_law_master_glossary.json \
  --translated work/p5_translated/translated.json \
  --report work/p5_translated/terminology_compliance_report.json
```

此检查会扫描译文，如果发现使用了术语库中定义的"禁用译法"（如"国有地带"、"规费"等），会报错并指出具体位置。

建议在 P5 翻译完成后、进入 P6 排版前执行此检查。

### P5.5 人工校阅（强制）

在进入 LaTeX 前，必须完成人工校阅，不可跳过：

1. 抽检至少 5 个位置：开头/中段/末段 + 2 个高风险法条（定义条、处罚条、签署条）。
2. 校对术语一致性：术语表中高频术语（机构、角色、程序名）不得漂移。
3. 校对污染项：不得出现页眉页脚残片、目录残片、源语言签署段残留（如 `Fait à` / `Par le Président`）。
4. 如发现问题，回到 P5 修订后再重复本步骤。

### P6 排版生成 PDF

```bash
python ../book-translation-skills/scripts/build_latex.py work/p5_translated --title "书名"
cd output/latex
xelatex -interaction=nonstopmode book.tex
xelatex -interaction=nonstopmode book.tex
cd ../..
```

### P7 PDF 精修

```bash
python ../book-translation-skills/scripts/pdf_layout_check.py output/latex --manifest config/chapter_manifest.json
```

### P7.5 PDF 抽检（强制）

成品 PDF 必须人工抽检后才能交付：

1. 检查目录页：标题与页码是否连贯，是否有页码黏连（如 `1746`）。
2. 检查正文页：标题层级、条文编号连续性、段间距是否异常。
3. 全文脏词扫描：不得出现 `日语原文`、`翻译术语对照表`（若非明确要求附录）、`Fait à` 等残留。
4. 不通过则回到 P5/P6 返工。

## 2. 常见语言对

- 日文 -> 简中：`--source-lang ja --target-lang zh-CN`
- 英文 -> 简中：`--source-lang en --target-lang zh-CN`
- 简中 -> 英文：`--source-lang zh-CN --target-lang en`

## 3. 建议测试策略

1. 先做烟测：`--limit 1`
2. 再做小批量：`--resume --limit 10`
3. 稳定后全量：`--resume` 不设 `--limit`
4. 全量后必须执行：`覆盖率检查 -> 人工校阅 -> LaTeX -> PDF抽检`

## 4. 产物检查

- 目录重构：`work/p3_toc/chapter_structure.json`
- 术语表：`work/p4_terminology/glossary.json`
- 翻译结果：`work/p5_translated/translated.json`、`work/p5_translated/ch01.md`
- 覆盖报告：`work/p5_translated/coverage_report.json`
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
- "执行 P3 目录重构"
- "执行 P5，语言对 en->zh-CN，general 模式"

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
3. 后续直接下达阶段命令（P1~P7）。

### KimiCode

KimiCode 常见做法是项目知识/提示词注入，而不是统一 skill 目录：

1. 把 `SKILL.md`、`REFERENCE.md`、本文件加入项目知识。
2. 用阶段化指令驱动：
   - "按 P4 提取术语，source=en target=zh-CN。"
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
   - "执行 P3 目录重构"
   - "执行 P5，source=en target=zh-CN，general 模式"
4. 始终优先执行脚本命令（`book-translation-skills/scripts/*.py`）保证可复现。
