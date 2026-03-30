"""Repair OCR noise in Japanese book Markdown via LLM API.

Supports multiple providers: OpenAI, Kimi, Gemini, Anthropic/Claude.

Usage:
    python openai_repair_md.py --chunks-dir work/p2_repair_chunks --output work/p2_repaired/ch01_repaired.md
    python openai_repair_md.py --chunks-dir work/p2_repair_chunks --output ... --resume  # skip existing progress
    python openai_repair_md.py --chunks-dir work/p2_repair_chunks --output ... --provider kimi
"""

import argparse
import json
import pathlib
import sys

from llm_client import create_client_from_secrets

from book_translation_paths import resolve_workspace

SYSTEM_JA = """You are an OCR post-processor for a Japanese legal-education book (教育関係法).
Fix OCR and layout-extraction artifacts only. Do NOT translate into Chinese or any other language.
Do NOT change legal meaning, argument structure, or substantive wording beyond obvious OCR errors.

== OCR Error Repair ==
- Inappropriate Chinese characters mixed into Japanese (replace with correct Japanese where obvious)
- Broken line breaks from page/column boundaries (rejoin into normal paragraphs)
- Repeated page headers/footers or running heads embedded in body text
- Broken footnote markers [^n], broken $...$ or $$...$$ math
- Corrupted Markdown tables
- Obvious character confusions (similar glyphs), stray OCR noise
- Remove stray original-book page numbers mixed into headings or body text

== Heading Hierarchy (IMPORTANT) ==
OCR may output ALL headings as `#`. You MUST infer the correct logical hierarchy and
output proper Markdown heading levels:
  # = Top-level part / major law name (e.g. "教育基本法", "学校教育法", "教育関係法")
  ## = Chapter / major section (e.g. "第1章 …", "前文", "執筆者紹介")
  ### = Sub-section / article group (e.g. "第1節 …", "[総説]", "[概説]")
  #### = Further subdivision if needed
Use your understanding of the book's logical structure to decide levels.
Do NOT leave everything as `#`.

== Special Sections ==
- Author listing (執筆者紹介): each author entry should be a single line.
  Format: `姓名（よみがな）……所属・職位`  (keep on one line, do not split)
- Table of contents (目次): keep but mark as `## 目次`
- Publisher ads / colophon / unrelated promotional text at start/end: remove entirely

== Preserve ==
- All meaningful Markdown structure, lists, block structure, image lines ![](...)
- Original Japanese phrasing when not clearly garbled

Return ONLY the repaired Markdown for this chunk. No explanations."""


def repair_chunk(client, model: str, user_text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_JA},
        {"role": "user", "content": user_text},
    ]
    
    response = client.call_with_retry(
        messages=messages,
        model=model,
        temperature=0.15,
        max_tokens=16384,
        max_retries=3,
    )
    
    content = response.content.strip()
    if not content:
        raise RuntimeError("empty completion")
    return content


def main():
    parser = argparse.ArgumentParser(description="Repair JP Markdown chunks via LLM API")
    parser.add_argument("--chunks-dir", required=True, help="Directory with chunk_*.md")
    parser.add_argument("--output", required=True, help="Concatenated repaired Markdown path")
    parser.add_argument("--resume", action="store_true", help="Append only missing chunks (by progress file)")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N chunks (0 = all)")
    parser.add_argument("--provider", help="LLM provider (openai, kimi, gemini, anthropic). Uses default_provider from secrets if not specified.")
    parser.add_argument("--model", help="Override model from secrets")
    args = parser.parse_args()

    chunks_dir = pathlib.Path(args.chunks_dir)
    chunk_files = sorted(chunks_dir.glob("chunk_*.md"))
    if not chunk_files:
        print(f"No chunk_*.md in {chunks_dir}", file=sys.stderr)
        sys.exit(1)

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path = out_path.with_suffix(out_path.suffix + ".progress.json")

    if args.resume and progress_path.is_file():
        done = set(json.loads(progress_path.read_text(encoding="utf-8")).get("completed", []))
    else:
        done = set()
        out_path.unlink(missing_ok=True)
        progress_path.unlink(missing_ok=True)

    # Create LLM client from secrets
    try:
        client, model = create_client_from_secrets(
            provider=args.provider,
            task="extract"
        )
    except Exception as e:
        print(f"Error initializing LLM client: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.model:
        model = args.model
    
    print(f"Provider: {client.provider}, Model: {model}", file=sys.stderr)

    limit = args.limit if args.limit > 0 else len(chunk_files)
    processed = 0
    file_mode = "a" if out_path.exists() else "w"

    with out_path.open(file_mode, encoding="utf-8") as out:
        for cf in chunk_files:
            if cf.name in done:
                continue
            if processed >= limit:
                break
            raw = cf.read_text(encoding="utf-8")
            print(f"[{processed + 1}/{limit or '…'}] {cf.name} ({len(raw)} chars) …", file=sys.stderr, flush=True)
            fixed = repair_chunk(client, model, raw)
            out.write(fixed)
            if not fixed.endswith("\n"):
                out.write("\n")
            out.write("\n")
            out.flush()
            done.add(cf.name)
            progress_path.write_text(json.dumps({"completed": sorted(done)}, indent=2), encoding="utf-8")
            processed += 1

    print(f"Done. Wrote {out_path} ({processed} chunks this run)", file=sys.stderr)


if __name__ == "__main__":
    main()
