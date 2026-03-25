"""Extract book table of contents from PDF pages using vision LLM.

Usage:
    python extract_toc.py <pdf_path> \
      --toc-pages 2-10 \
      --output work/p3_toc/chapter_structure.json

Renders specified PDF pages as images, sends them to a vision model
(e.g. Gemini 3.1 Pro), and extracts a structured 3-level TOC:
  chapter / section / subsection
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys
import time

import fitz  # pymupdf
import requests

from book_translation_paths import resolve_workspace

SECRETS_CANDIDATES = ("local.secrets.json", "secrets.json")

SYSTEM_PROMPT = """\
You are a book structure analyst. You will receive images of a Japanese book's \
table of contents (目次) pages.

Extract the COMPLETE table of contents as a structured JSON with exactly 3 levels:

{
  "chapters": [
    {
      "title": "章标题（原文日语）",
      "page": 起始页码(int),
      "type": "chapter",
      "sections": [
        {
          "title": "节标题（原文日语）",
          "page": 起始页码(int),
          "type": "section",
          "subsections": [
            {
              "title": "小节/条文标题（原文日语）",
              "page": 起始页码(int),
              "type": "subsection"
            }
          ]
        }
      ]
    }
  ]
}

Rules:
1. The top level (chapter) should include:
   - 序 (preface)
   - 執筆者紹介 (author introductions)
   - Each major law name as its own chapter: 教育基本法, 学校教育法, \
地方教育行政の組織及び運営に関する法律, 教育公務員特例法, 社会教育法, \
子どもの権利条約, 関係法規概説, etc.
   - Any other standalone top-level sections

2. The second level (section) includes:
   - [第X章] chapter divisions within a law
   - [総説] overviews
   - [概説] summaries
   - Named topic sections

3. The third level (subsection) includes:
   - Individual articles: 第X条, 前文, etc.
   - <第X節> sub-sections within a chapter
   - Specific topic subsections

4. page numbers should be integers matching what appears in the TOC
5. Keep ALL entries — do not skip or summarize
6. Keep titles in their ORIGINAL Japanese form exactly as printed
7. Return ONLY valid JSON. No text outside the JSON object."""


def resolve_secrets_path() -> pathlib.Path | None:
    root = resolve_workspace()
    for name in SECRETS_CANDIDATES:
        p = root / name
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def load_api_cfg():
    path = resolve_secrets_path()
    if path is None:
        print("No secrets.json / local.secrets.json", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    oa = data.get("openai") or {}
    base = (oa.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    key = oa.get("api_key")
    if not key:
        print("openai.api_key missing in secrets", file=sys.stderr)
        sys.exit(1)
    return base, key


def parse_page_range(s: str) -> list[int]:
    """Parse '2-10' or '2,3,5-8' into a list of 1-based page numbers."""
    pages: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


def render_pages(pdf_path: str, pages: list[int], dpi: int = 150) -> list[str]:
    """Render PDF pages to base64 JPEG strings. Pages are 1-indexed."""
    doc = fitz.open(pdf_path)
    images: list[str] = []
    for p in pages:
        idx = p - 1
        if idx < 0 or idx >= len(doc):
            print(f"  Warning: page {p} out of range, skipping", file=sys.stderr)
            continue
        pix = doc[idx].get_pixmap(dpi=dpi)
        jpeg_bytes = pix.tobytes("jpeg", jpg_quality=60)
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        images.append(b64)
        print(f"  Rendered page {p} ({len(jpeg_bytes)//1024}KB)", file=sys.stderr)
    doc.close()
    return images


def extract_toc_via_vision(
    base: str,
    key: str,
    model: str,
    images_b64: list[str],
    max_retries: int = 3,
) -> dict:
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    content_parts: list[dict] = [
        {"type": "text", "text": "以下是一本日语教育法书籍的目录（目次）页面。请提取完整的目录结构。"},
    ]
    for b64 in images_b64:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    payload = {
        "model": model,
        "temperature": 0.1,
        "max_completion_tokens": 16384,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content_parts},
        ],
    }

    last_err = None
    for attempt in range(max_retries):
        try:
            print(f"  Calling {model} (attempt {attempt+1}) …", file=sys.stderr, flush=True)
            r = requests.post(url, headers=headers, json=payload, timeout=300)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:500]}"
                time.sleep(5 * (attempt + 1))
                continue

            content = r.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[: content.rfind("```")]
            content = content.strip()

            result = json.loads(content)
            if isinstance(result, dict) and "chapters" in result:
                return result
            last_err = f"Unexpected JSON structure: {list(result.keys()) if isinstance(result, dict) else type(result)}"
        except json.JSONDecodeError as e:
            last_err = f"JSON parse error: {e}"
        except Exception as e:
            last_err = str(e)
        time.sleep(3 * (attempt + 1))

    raise RuntimeError(f"TOC extraction failed after {max_retries} retries: {last_err}")


def print_toc_summary(toc: dict) -> None:
    chapters = toc.get("chapters", [])
    total_sections = 0
    total_subsections = 0
    for ch in chapters:
        sections = ch.get("sections", [])
        total_sections += len(sections)
        for sec in sections:
            total_subsections += len(sec.get("subsections", []))

    print(f"\nTOC Summary:", file=sys.stderr)
    print(f"  Chapters: {len(chapters)}", file=sys.stderr)
    print(f"  Sections: {total_sections}", file=sys.stderr)
    print(f"  Subsections: {total_subsections}", file=sys.stderr)
    print(f"\nChapter list:", file=sys.stderr)
    for ch in chapters:
        page = ch.get("page", "?")
        n_sec = len(ch.get("sections", []))
        print(f"  [{page:>3}] {ch['title']}  ({n_sec} sections)", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Extract TOC from PDF via vision LLM")
    parser.add_argument("pdf_path", help="Path to the book PDF")
    parser.add_argument("--toc-pages", required=True, help="Page range for TOC, e.g. '2-10'")
    parser.add_argument("--output", default="work/p3_toc/chapter_structure.json", help="Output JSON path")
    parser.add_argument("--model", default="gemini-3.1-pro-preview", help="Vision model name")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for page rendering")
    args = parser.parse_args()

    pages = parse_page_range(args.toc_pages)
    print(f"PDF: {args.pdf_path}", file=sys.stderr)
    print(f"TOC pages: {pages}", file=sys.stderr)
    print(f"Model: {args.model}", file=sys.stderr)

    images_b64 = render_pages(args.pdf_path, pages, dpi=args.dpi)
    if not images_b64:
        print("No pages rendered", file=sys.stderr)
        sys.exit(1)

    base, key = load_api_cfg()
    toc = extract_toc_via_vision(base, key, args.model, images_b64)

    print_toc_summary(toc)

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(toc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nSaved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
