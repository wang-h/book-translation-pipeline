---
name: law-book-translation
description: >-
  法律类图书（尤其日本法教参、逐条释义）从 PDF 到中文 PDF 的完整技能合集：OCR、
  目录结构提取、OCR 后处理、术语冻结、法条双语翻译、LaTeX 排版与 PDF 精修。
  在翻译日本法书籍、处理条文原文与中文对照、或需要与 book-translation-pipeline
  子 Skill 对齐时使用本合集。
---

# 法律类图书翻译技能合集（日本法 → 简体中文）

本文件是 **法律向** 的主索引：把 `book-translation-skills/` 下各子 Skill 串成一条可执行流水线，并补充 **条文、法令名、机构职务** 等与一般书籍不同的约定。全局路径与密钥约定仍以仓库根目录 `REFERENCE.md`、`SKILL.md` 为准。

## 适用场景

- 日本法学参考书、逐条释义、体系书（如教育関係法、各法「逐条解説」类）
- 正文中大量 **法令名、条文编号、官厅名称、略称**（教基法、学教法、地教行法等）
- 需要 **日语条文原文 + 中文译文** 并排或分块展示（版式由 LaTeX 法条框承接）
- 双栏扫描 PDF、MinerU 偶有漏段，需要补漏与结构化修复后再译

## 与子 Skill 的对应关系（合集 = 索引，细节在子 Skill）

| 阶段 | 子 Skill 目录 | 核心脚本（`scripts/`） | 法律向要点 |
|------|---------------|------------------------|------------|
| P1 OCR | `ocr-book-with-mineru-api` | `mineru_submit.py`, `mineru_poll.py`, `generate_chapter_manifest.py` | 全书结构化 Markdown + `content_list*.json`（含 bbox，可供后续标题层级参考） |
| P2 后处理 | `supplement-ocr-missing` + `repair-book-markdown` | `supplement_ocr_vision.py`, `split_md_paragraphs.py`, `openai_repair_md.py`, `split_book.py` | 补漏宜 **高 DPI 裁剪**；修复阶段应用 LLM **推断标题层级**，勿只靠手写规则 |
| **P2.5 目录/结构** | （本合集定义，脚本见下） | **`extract_toc.py`**, `fix_heading_levels.py`（可选） | 从 PDF **目次页** 用视觉模型抽 **chapter / section / subsection**；序言、執筆者紹介等单独成章；bbox 仅作 **校正** 而非唯一依据 |
| P3 术语 | `extract-book-terminology` | `extract_terms.py` | **质量优先**：宁可 200–500 条高价值术语，不要数千条「第X条」「文号」式噪声；全书翻译用完整表，PDF 附录可只收核心类型（见 `build_latex.py`） |
| P4 翻译 | `translate-book-to-zh` | `openai_translate_md.py`, `check_translation_coverage.py` | **冻结术语表**写入系统提示；条文用 `:::law-bilingual`；宜用 **结构化 JSON 逐段一一对应**（同长度 id 数组）避免整 chunk 漏译 |
| P5 排版 | `typeset-book-latex` | `build_latex.py`, `md_to_pdf.py` | 支持 `:::law-bilingual` → tcolorbox；日文在框内用 `\japfont`；Overleaf 注意 `book.tex` 为主文件、`.latexmkrc` 选 XeLaTeX |
| P6 精修 | `polish-book-pdf` | `pdf_layout_check.py` + 手工调 TeX | 孤行寡行、脚注、双栏转单栏后的浮动体与 CJK 标点 |

**说明：** 历史上单独的「4.5 结构重排」Skill 已弃用；**法条双语与标题层级**应在 **P2 修复 / P2.5 目录** 与 **P4 翻译输出** 中完成，不再单独设一阶段文件。

## 推荐目录结构（`workspace/work/`）

与主编排 `SKILL.md` 一致，法律书同样使用：

- `p1_ocr/` — MinerU 产出 `full.md`、`content_list_v2.json`、`images/`
- `p2_repaired/` — 修复后全书或分章 `.md`
- `p3_terminology/` — `glossary.json` / `glossary_v2.json`（冻结后勿改键名随意增删）
- `p4_translate_chunks/` 或 **JSON 分块目录** — 翻译输入
- `p4_translated/` — 译文 `.md`、`translated.json`（若用结构化翻译）、`coverage_report.json`
- `p3_toc/` — **`chapter_structure.json`**（目录提取结果）、可选渲染页图缓存

## P2.5：目录提取（翻译前）

**目的：** 在术语与翻译之前，固定 **章—节—小节** 三层结构，便于分章翻译与 LaTeX `\chapter`/`\section` 对齐。

**推荐做法：**

1. 用 PDF 中 **目次（日次）** 所在页码区间（需人工或粗扫确认，常见在全书前部连续数页）。
2. 运行（从 `workspace/` 起，路径按实际 PDF 调整）：

```bash
python ../book-translation-skills/scripts/extract_toc.py \
  "../你的书名.pdf" \
  --toc-pages 2-10 \
  --output work/p3_toc/chapter_structure.json \
  --model gemini-3.1-pro-preview \
  --dpi 150
```

3. 脚本将页面 **渲染为压缩 JPEG** 送入多模态模型，输出 JSON：`chapters[]` → `sections[]` → `subsections[]`（含 `title`, `page`, `type`）。
4. **序言（序）、執筆者紹介、凡例** 等：在提示中要求模型列为 **独立 chapter**，勿与正文第一大章混并。
5. 若 OCR 标题字号与目录不一致，可用 `fix_heading_levels.py` 结合 `content_list_v2.json` 的 bbox **辅助校正** 层级，**不替代** 目录逻辑。

## 法律翻译专项约定

### 1. 术语表（P3）

- 收录：**法令正式名与略称、机构、职务、判例/文献固定译法、易混概念**。
- **不收录**：纯「第X条」「第X章」、法令编号、行政文号日期串（除非作为固定简称有独立翻译价值）。
- 翻译阶段提示词中可只注入 **前 N 条** 高频术语（避免超长 context），全书级一致性仍以完整 `glossary.json` 为准。

### 2. 条文双语（P4）

译文中对 **条文正文** 使用统一围栏（与 `openai_translate_md.py` 系统提示一致）：

```markdown
:::law-bilingual
【法条原文（JP）】
（日语条文，与原文一致）

【法条译文（ZH）】
（简体中文译文）
:::
```

P5 由 `build_latex.py` 转为 `tcolorbox`；标签在模板内为「法条原文（日语）」「法条译文（中文）」。

### 3. 翻译完整性（P4）

- **推荐**：按 **段落/块 JSON 数组** 翻译，模型返回 **同 id、同长度** 的 JSON，缺失或空字段即判定失败并重试该条。
- 使用 `check_translation_coverage.py` 对 `entries.json` + `translated.json` 做 **条目级** 核对（缺 id、空译文、`[TRANSLATION_FAILED]`）。

### 4. PDF 附录术语表（P5）

- 全书 `glossary.json` 可较大；附录可只输出 **法律名、机构、职务、人名、略称** 等核心类型（见 `build_latex.py` 中附录类型过滤），避免附录数百页。

## 执行顺序速查（对用户话术）

| 用户意图 | 执行 |
|----------|------|
| 只译日本法这本书 | 自 P1 顺序执行至 P6，且 **不要跳过 P3** |
| 要先定章节再译 | 先做 **P2.5 `extract_toc.py`**，再 P3→P4 |
| 发现译文漏段 | 查结构化 `translated.json` + `check_translation_coverage.py`，补翻失败 id |
| 只要排版 | P5→P6，输入为已定稿的 `p4_translated/ch*.md` |

## 与主编排 Skill 的关系

- 仓库根目录 **`SKILL.md`**（`book-translation-pipeline`）负责 **通用** 端到端编排。
- **`law-book-translation`（本文件）** 在通用流程上叠加 **目录提取、条文双语、术语质量、覆盖率校验** 等法律书强约束。
- 执行某一具体步骤时，**仍应打开上表对应子目录下的 `SKILL.md`**，按其中的命令与提示词细节操作。

## 相关文档

- `../../README.md` — 流水线总览与 Cursor 使用说明  
- `../../REFERENCE.md` — 路径、密钥、失败恢复  
- `../../SKILL.md` — 主编排 Skill（阶段编号与 checkpoint）
