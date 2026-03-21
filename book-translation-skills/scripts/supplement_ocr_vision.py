"""Supplement missing OCR text by sending PDF page screenshots + current text to a vision model.

Usage:
    python supplement_ocr_vision.py \\
        --pdf workspace/input/book.pdf \\
        --md  workspace/work/p2_repaired/ch01.md \\
        --pages 3-4 \\
        --output workspace/work/p2_repaired/ch01_supplemented.md

    # Or process a single page:
    python supplement_ocr_vision.py --pdf book.pdf --md ch01.md --pages 4 --output ch01_fixed.md

The script:
1. Renders specified PDF pages to PNG with pymupdf.
2. Splits the Markdown into paragraph blocks.
3. Sends each page image + the corresponding text blocks to a vision-capable
   model (default: gpt-5.4-mini via aihubmix) asking it to fill missing spans.
4. Writes a patched Markdown file + a patch log.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import sys
import time

import fitz  # pymupdf
import requests

from book_translation_paths import resolve_workspace

SECRETS_CANDIDATES = ("local.secrets.json", "secrets.json")

SYSTEM_PROMPT = """You are an OCR post-processor with vision. You will receive:
1. A screenshot of a PDF page from a Japanese legal-education book.
2. The current OCR-extracted Markdown text for that page (which may have missing words, broken names, dotted placeholders, or dropped lines).

Your task:
- Compare the image with the text carefully.
- Fill in ANY missing text that is visible in the image but absent or replaced by dots/placeholders in the Markdown.
- Fix garbled characters by matching them to what you see in the image.
- Do NOT translate. Keep the original Japanese.
- Do NOT rephrase or rewrite text that is already correct.
- Preserve all Markdown formatting (headings, lists, etc.).
- Return the COMPLETE corrected Markdown for this section. No explanations."""


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


def load_openai_cfg(model_override: str | None = None):
    path = resolve_secrets_path()
    if path is None:
        print("No secrets.json / local.secrets.json", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    oa = data.get("openai") or {}
    base = (oa.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    key = oa.get("api_key")
    model = model_override or oa.get("supplement_model") or "gpt-5.4-mini"
    if not key:
        print("openai.api_key missing in secrets", file=sys.stderr)
        sys.exit(1)
    return base, key, model


def render_page_to_base64(pdf_path: str, page_num: int, dpi: int = 200) -> str:
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(png_bytes).decode("ascii")


def parse_page_range(spec: str) -> list[int]:
    """Parse '3-5' or '3,5,7' or '4' into 0-based page indices."""
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            for p in range(int(a), int(b) + 1):
                pages.append(p - 1)
        else:
            pages.append(int(part) - 1)
    return pages


def call_vision_model(
    base: str,
    key: str,
    model: str,
    image_b64: str,
    text_block: str,
    max_retries: int = 3,
) -> str:
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_completion_tokens": 16384,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Below is the current OCR text for this page. Please correct and fill in any missing content based on the image above:\n\n{text_block}",
                    },
                ],
            },
        ],
    }
    last_err = None
    for attempt in range(max_retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:500]}"
                time.sleep(5 * (attempt + 1))
                continue
            data = r.json()
            choice = data["choices"][0]["message"]["content"]
            if not choice or not choice.strip():
                last_err = "empty completion"
                time.sleep(3)
                continue
            return choice.strip()
        except Exception as e:
            last_err = str(e)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(last_err or "vision call failed")


def split_md_by_page_markers(text: str) -> list[str]:
    """If the MD has no page markers, return as a single block."""
    return [text]


def main():
    parser = argparse.ArgumentParser(
        description="Supplement missing OCR text using PDF screenshots + vision model"
    )
    parser.add_argument("--pdf", required=True, help="Source PDF file")
    parser.add_argument("--md", required=True, help="Current Markdown file to supplement")
    parser.add_argument(
        "--pages",
        required=True,
        help='PDF pages to process (1-based, e.g. "3-5" or "3,4,5")',
    )
    parser.add_argument("--output", required=True, help="Output supplemented Markdown")
    parser.add_argument("--model", help="Vision model override (default: gpt-5.4-mini)")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI for screenshots")
    args = parser.parse_args()

    pdf_path = pathlib.Path(args.pdf)
    md_path = pathlib.Path(args.md)
    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    if not md_path.is_file():
        print(f"Markdown not found: {md_path}", file=sys.stderr)
        sys.exit(1)

    pages = parse_page_range(args.pages)
    md_text = md_path.read_text(encoding="utf-8")
    base, key, model = load_openai_cfg(args.model)

    print(f"Model: {model} | Pages: {[p+1 for p in pages]} | DPI: {args.dpi}", file=sys.stderr)

    doc = fitz.open(str(pdf_path))
    total_pages = doc.page_count
    doc.close()

    patches: list[dict] = []
    result_text = md_text

    for page_idx in pages:
        if page_idx < 0 or page_idx >= total_pages:
            print(f"  Skipping page {page_idx+1} (out of range, total={total_pages})", file=sys.stderr)
            continue

        print(f"  Processing page {page_idx+1}/{total_pages} …", file=sys.stderr, flush=True)
        img_b64 = render_page_to_base64(str(pdf_path), page_idx, args.dpi)

        fixed = call_vision_model(base, key, model, img_b64, result_text)

        if fixed and fixed != result_text:
            patches.append({
                "page": page_idx + 1,
                "status": "patched",
                "chars_before": len(result_text),
                "chars_after": len(fixed),
            })
            result_text = fixed
        else:
            patches.append({"page": page_idx + 1, "status": "no_change"})

    out_path.write_text(result_text, encoding="utf-8")
    print(f"Wrote {out_path} ({len(result_text)} chars)", file=sys.stderr)

    log_path = out_path.with_suffix(".patch_log.json")
    log_path.write_text(json.dumps(patches, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Patch log: {log_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
