# Book Translation Pipeline

端到端的整书翻译流水线：PDF → OCR → OCR后处理（补漏+修复）→ 术语提取 → 翻译 → LaTeX 排版 → PDF 精修。

## 流水线阶段

```
PDF ─→ [1] OCR ─→ [2] OCR后处理(补漏+修复) ─→ [3] 术语提取 ─→ [4] 翻译 ─→ [5] LaTeX排版 ─→ [6] PDF精修
```

| # | Skill | 说明 |
|---|-------|------|
| 1 | `ocr-book-with-mineru-api` | 通过 MinerU v4 云端 API 将 PDF 转为结构化 Markdown |
| 2 | `supplement-ocr-missing` + `repair-book-markdown` | OCR后处理：先定点补漏（模型可配置），再做结构化修复 |
| 3 | `extract-book-terminology` | 提取并冻结术语表，确保全书译名一致 |
| 4 | `translate-book-to-zh` | 基于冻结术语表逐章翻译为中文 |
| 5 | `typeset-book-latex` | 将中文译稿转换为 LaTeX 项目并编译 PDF |
| 6 | `polish-book-pdf` | 精修版面：孤行寡行、脚注溢出、浮动体偏移、CJK 排版 |

## 在 Cursor 中使用（Skill 模式）

本项目内置了 Cursor Agent Skill。配置好后，在 Cursor 中直接对 AI 说自然语言即可触发对应阶段：

| 你说的话 | 触发阶段 |
|---------|---------|
| "翻译这本书" / "帮我翻译 @xxx.pdf" | 全流程 P1→P5 |
| "OCR 这个 PDF" / "识别这本书" | P1: OCR |
| "修复 Markdown" / "清理 OCR 结果" | P2: 修复 |
| "提取术语" / "做术语表" | P3: 术语 |
| "翻译第X章" | P4: 翻译 |
| "生成 PDF" / "排版" / "编译 LaTeX" | P5: PDF |
| "精修版面" / "优化 PDF" | P6: 精修 |

### Cursor Skill 配置

项目根目录的 `SKILL.md` 是主编排 Skill，它会自动调用 `book-translation-skills/*/SKILL.md` 中的子 Skill。只要在 Cursor 中打开本项目，Agent 就能识别这些 Skill 并按流程执行。

如果 Cursor 没有自动加载 Skill，检查 `.cursor/skills/` 是否指向本项目：

```bash
ls -la ~/.cursor/skills/book-translation-pipeline/
# 应指向 ~/book-translation-pipeline/
```

## 目录结构

```
book-translation-pipeline/
├── README.md
├── SKILL.md                        # Cursor Skill 主编排
├── REFERENCE.md                    # 共享约定
├── secrets.example.json            # 密钥模板
├── workspace/                      # 工作目录（不发布）
│   ├── local.secrets.json
│   ├── input/                      # 原始 PDF
│   ├── work/
│   │   ├── p1_ocr/                 # P1: MinerU OCR 输出
│   │   ├── p2_repair_chunks/       # P2: 修复分块
│   │   ├── p2_repaired/            # P2: 修复后 Markdown
│   │   ├── p3_terminology/         # P3: 术语表
│   │   ├── p4_translate_chunks/    # P4: 翻译分块
│   │   └── p4_translated/          # P4: 中文译文
│   ├── output/
│   │   ├── latex/                  # P5: LaTeX 项目
│   │   └── pdf/                    # P5: 最终 PDF
│   └── config/
│       └── chapter_manifest.json
└── book-translation-skills/        # 可单独发布到 GitHub
    ├── requirements.txt
    ├── scripts/
    │   ├── book_translation_paths.py
    │   ├── mineru_submit.py        # P1: 提交 OCR
    │   ├── mineru_poll.py          # P1: 轮询下载
    │   ├── generate_chapter_manifest.py  # P1: 生成章节清单
    │   ├── split_md_paragraphs.py  # P2/P4: 分块
    │   ├── split_book.py           # P2: 按标题拆章
    │   ├── openai_repair_md.py     # P2: LLM 修复
    │   ├── extract_terms.py        # P3: 术语提取
    │   ├── openai_translate_md.py  # P4: LLM 翻译
    │   ├── build_latex.py          # P5: Markdown→LaTeX
    │   ├── md_to_pdf.py            # P5: Markdown→PDF (WeasyPrint)
    │   └── pdf_layout_check.py     # P6: 版面 QA
    ├── ocr-book-with-mineru-api/   # Skill 定义
    ├── supplement-ocr-missing/
    ├── repair-book-markdown/
    ├── extract-book-terminology/
    ├── translate-book-to-zh/
    ├── typeset-book-latex/
    └── polish-book-pdf/
```

## 快速开始

### 1. 安装系统依赖

```bash
# LaTeX（XeLaTeX + 中文支持）
sudo apt-get install -y texlive-xetex texlive-latex-extra texlive-lang-chinese texlive-fonts-recommended

# CJK 字体（如未预装）
sudo apt-get install -y fonts-noto-cjk fonts-noto-cjk-extra
```

### 2. 安装 Python 依赖

```bash
pip install -r book-translation-skills/requirements.txt
```

### 3. 配置密钥

```bash
cp secrets.example.json workspace/local.secrets.json
# 编辑 workspace/local.secrets.json，填入 MinerU token 和 OpenAI API key
```

### 4. 一键跑完全流程

```bash
cd workspace

# P1: OCR
BATCH_ID=$(python ../book-translation-skills/scripts/mineru_submit.py input/book.pdf --ocr)
python ../book-translation-skills/scripts/mineru_poll.py "$BATCH_ID" --batch

# P2: 修复
python ../book-translation-skills/scripts/split_md_paragraphs.py work/p1_ocr/full.md --output-dir work/p2_repair_chunks --max-chars 12000
python ../book-translation-skills/scripts/openai_repair_md.py --chunks-dir work/p2_repair_chunks --output work/p2_repaired/ch01.md

# P3: 术语提取
python ../book-translation-skills/scripts/extract_terms.py work/p2_repaired --output work/p3_terminology/term_candidates.json

# P4: 翻译
python ../book-translation-skills/scripts/split_md_paragraphs.py work/p2_repaired/ch01.md --output-dir work/p4_translate_chunks --max-chars 10000
python ../book-translation-skills/scripts/openai_translate_md.py --chunks-dir work/p4_translate_chunks --output work/p4_translated/ch01.md --glossary work/p3_terminology/glossary.json

# P5: 生成 PDF（二选一）
# 方式 A: XeLaTeX（推荐，排版质量高）
python ../book-translation-skills/scripts/build_latex.py work/p4_translated --title "书名"
cd output/latex && xelatex -interaction=nonstopmode book.tex && xelatex -interaction=nonstopmode book.tex && cd ../..
# 方式 B: WeasyPrint（无需 LaTeX 环境）
python ../book-translation-skills/scripts/md_to_pdf.py work/p4_translated/ch01.md --output output/pdf/book.pdf --title "书名"
```

每个阶段的详细步骤见 `book-translation-skills/*/SKILL.md`，全局约定见 `REFERENCE.md`。

## 外部依赖

| 依赖 | 用途 | 安装 |
|------|------|------|
| MinerU v4 云端 API | PDF OCR（需 token） | 注册获取 |
| OpenAI 兼容 API（aihubmix） | GPT-5.4 用于修复、术语、翻译 | 配置 API key |
| XeLaTeX + ctex | 中文 PDF 排版（方式 A） | `sudo apt install texlive-xetex texlive-latex-extra texlive-lang-chinese` |
| WeasyPrint | 中文 PDF 排版（方式 B） | `pip install weasyprint` |
| Noto CJK 字体 | 推荐的中文字体族 | `sudo apt install fonts-noto-cjk` |
