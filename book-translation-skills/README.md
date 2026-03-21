# book-translation-skills

整书 PDF 翻译流水线的 **Agent Skills** + **脚本**，可单独发布到 GitHub。

## 目录

```
book-translation-skills/
├── requirements.txt
├── scripts/                    # 流水线辅助脚本
├── ocr-book-with-mineru-api/   # Stage 1
├── supplement-ocr-missing/     # Stage 2a
├── repair-book-markdown/       # Stage 2b
├── extract-book-terminology/   # Stage 3
├── translate-book-to-zh/       # Stage 4
├── typeset-book-latex/         # Stage 5
└── polish-book-pdf/            # Stage 6
```

## 使用

搭配 `book-translation-pipeline` 仓库使用：

```bash
git clone <this-repo> book-translation-pipeline/book-translation-skills
```

详细编排见 `book-translation-pipeline/SKILL.md`。
