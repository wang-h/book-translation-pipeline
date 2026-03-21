# Book Translation Pipeline

端到端的整书翻译流水线：PDF → OCR → 修复 → 术语提取 → 翻译 → LaTeX 排版 → PDF 精修。

## 流水线阶段

```
PDF ─→ [1] OCR ─→ [2] Markdown修复 ─→ [3] 术语提取 ─→ [4] 翻译 ─→ [5] LaTeX排版 ─→ [6] PDF精修
```

| # | Skill | 说明 |
|---|-------|------|
| 1 | `ocr-book-with-mineru-api` | 通过 MinerU v4 云端 API 将 PDF 转为结构化 Markdown |
| 2 | `repair-book-markdown` | 修复 OCR 产物中的断段、错级标题、页眉页脚污染等问题 |
| 3 | `extract-book-terminology` | 提取并冻结术语表，确保全书译名一致 |
| 4 | `translate-book-to-zh` | 基于冻结术语表逐章翻译为中文 |
| 5 | `typeset-book-latex` | 将中文译稿转换为 LaTeX 项目并编译 PDF |
| 6 | `polish-book-pdf` | 精修版面：孤行寡行、脚注溢出、浮动体偏移、CJK 排版 |

## 项目结构

```
book-translation-pipeline/
├── README.md                   # 本文件
├── REFERENCE.md                # 共享约定（目录结构、分块策略、质量红线）
├── secrets.example.json        # 密钥模板
├── local.secrets.json          # 实际密钥（不入版本控制）
├── requirements.txt            # Python 依赖
├── skills/                     # 各阶段 Skill 定义
│   ├── ocr-book-with-mineru-api/SKILL.md
│   ├── repair-book-markdown/SKILL.md
│   ├── extract-book-terminology/SKILL.md
│   ├── translate-book-to-zh/SKILL.md
│   ├── typeset-book-latex/SKILL.md
│   └── polish-book-pdf/SKILL.md
└── scripts/                    # 辅助脚本
    ├── mineru_submit.py        # 提交 MinerU OCR 任务
    ├── mineru_poll.py          # 轮询并下载 OCR 结果
    ├── split_book.py           # 按标题/token 切分 Markdown
    ├── extract_terms.py        # 提取术语候选
    ├── build_latex.py          # Markdown → LaTeX 转换
    └── pdf_layout_check.py     # LaTeX 编译日志检查
```

## 快速开始

### 1. 配置密钥

```bash
cp secrets.example.json local.secrets.json
# 编辑 local.secrets.json，填入 MinerU token 和 OpenAI API key
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行 OCR

```bash
python scripts/mineru_submit.py input/book.pdf --ocr
python scripts/mineru_poll.py <task_id> --batch
```

### 4. 后续阶段

每个阶段的详细步骤见对应的 `skills/*/SKILL.md`。全局约定见 `REFERENCE.md`。

## 工作目录结构（运行时生成）

```
<project_root>/
├── input/                      # 原始 PDF
├── work/
│   ├── ocr/                    # MinerU 产出
│   ├── repaired/               # OCR 修复后的 Markdown
│   ├── terminology/            # 术语表
│   └── translated/             # 中文译稿
├── output/
│   ├── latex/                  # LaTeX 项目
│   └── pdf/                    # 最终 PDF
└── config/
    └── chapter_manifest.json   # 章节清单
```

## 外部依赖

- **MinerU v4 云端 API** — PDF OCR（需 token）
- **OpenAI 兼容 API**（aihubmix）— GPT-5.4 用于修复/术语/翻译
- **XeLaTeX + ctex** — 中文 PDF 排版
- **Noto CJK 字体** — 推荐的中文字体族
