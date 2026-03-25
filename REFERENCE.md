# 整书翻译共享参考

本文件定义所有 book-translation-pipeline 子 Skill 共享的目录约定、分块规则、一致性资产、质量红线和失败回退策略。每个子 Skill 的 `SKILL.md` 只写自身职责，共性约束统一引用此文件。

## 目录约定

所有翻译项目使用统一的工作目录结构，根目录由调用者指定（默认为当前工作区）：

```
<project_root>/
├── input/                      # 原始 PDF
├── work/
│   ├── p1_ocr/                 # MinerU 产出（full.md、content_list.json、images/）
│   ├── p2_repair_chunks/       # 修复阶段临时分块（可选）
│   ├── p2_repaired/            # OCR 修复后的 Markdown（按章节）
│   ├── p3_toc/                 # 目录重构结果（chapter_structure.json、toc.md）
│   ├── p3_terminology/         # glossary.json、term_candidates.json、translation_memory.md
│   ├── p4_translate_chunks/    # 翻译阶段临时分块（可选）
│   ├── p4_translated/          # 中文译稿 Markdown（按章节）
│   └── p5_supplemented/        # 视觉补漏产出（历史/可选；阶段已弃用）
├── output/
│   ├── latex/                  # book.tex、chapters/*.tex、preamble.tex
│   └── pdf/                    # 最终 PDF
└── config/
    └── chapter_manifest.json   # 章节清单与元数据
```

## 密钥读取约定

所有需要调用外部 API 的 Skill 和脚本，统一从以下路径读取凭据：

```
<pipeline_root>/local.secrets.json
```

其中 `<pipeline_root>` 是本项目（`book-translation-pipeline`）的根目录。字段格式见 `secrets.example.json`。禁止将真实密钥写入 `SKILL.md`、示例代码或任何可共享文件。

## 分块策略

1. 优先按目录/标题切块：以 `#`、`##` 级标题为块边界。
2. 若单块超过 token 上限（建议 3000-4000 tokens），在段落边界二次切分。
3. 禁止切断：脚注、表格、公式块、有序/无序列表、引用块。
4. 每个 chunk 必须携带：`chunk_id`、`chapter_id`、`source_file`、`start_line`、`end_line`。

## 一致性资产

| 资产文件 | 位置 | 用途 |
|---------|------|------|
| `glossary.json` | `work/p3_terminology/` | 冻结版术语表，翻译阶段必须读取 |
| `term_candidates.json` | `work/p3_terminology/` | 术语候选（未冻结），供人工审核 |
| `translation_memory.md` | `work/p3_terminology/` | 人工可读的术语记忆，含上下文示例 |
| `chapter_manifest.json` | `config/` | 章节清单：编号、标题、页码范围、状态 |

### glossary.json 条目格式

```json
{
  "source": "due process",
  "target": "正当程序",
  "alternatives": ["正当法律程序"],
  "forbidden_translations": ["适当程序"],
  "part_of_speech_or_type": "法律术语",
  "retain_original": true,
  "chapter_examples": [
    {"chapter": "ch03", "context": "...the right to due process..."}
  ],
  "notes": "首次出现时括注英文原文",
  "status": "frozen"
}
```

兼容旧字段：`source_term` / `preferred_translation` / `ja` / `zh` 仍可读取，但新产物建议统一为 `source` / `target`。

## 质量检查清单

- 章节数一致：OCR -> 修复 -> 翻译 -> LaTeX 每个阶段的章节数必须相同。
- 标题层级一致：翻译不得改变标题深度。
- 脚注数一致：原文脚注数 == 译文脚注数。
- 漏译检测：原文段落数与译文段落数比对，差异超过 10% 需人工确认。
- 术语漂移检查：同一 `source_term` 在不同章节的译法必须与 glossary 一致。
- 禁用译法检查：译文中不得出现 glossary 标记为 `forbidden_translations` 的译法。
- 目录页码稳定性：二次编译后目录页码不变。
- 分页异常：标题不落页尾、无孤行寡行。
- 浮动体检查：图片和表格不漂到错误章节。

## 失败回退策略

| 阶段 | 失败类型 | 回退方式 |
|------|---------|---------|
| MinerU OCR | API 返回 failed | 按 `page_ranges` 分段重跑；切换 `pipeline`/`vlm` 参数；延迟重试 |
| MinerU OCR | 超时 | 增大轮询间隔，最多等待 30 分钟 |
| GPT 修复/术语/翻译 | 输出格式异常 | 仅重做当前 chunk，不重跑全书 |
| GPT 翻译 | 术语漂移 | 将漂移术语加入 glossary 后重译该 chunk |
| LaTeX 编译 | 编译错误 | 最小化定位出错章节，单独修复后增量编译 |
| PDF 优化 | 版面异常 | 回改 LaTeX 源并重编译，不做 PDF 层手工修补 |
