"""Split a Markdown file into chapter-sized chunks for repair/translation.

Usage:
    python split_book.py <input.md> [--output-dir <dir>] [--max-tokens 4000]

Splits by headings first, then by paragraph boundaries if a section exceeds
max-tokens. Outputs numbered chunk files and a manifest JSON.
"""

import argparse
import json
import pathlib
import re
import sys


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.5 tokens per CJK char, ~0.75 per Latin word."""
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    latin_words = len(re.findall(r"[a-zA-Z]+", text))
    return int(cjk_chars * 1.5 + latin_words * 0.75)


def split_by_headings(text: str) -> list[dict]:
    """Split Markdown text by top-level headings (# or ##)."""
    lines = text.split("\n")
    sections = []
    current_title = "frontmatter"
    current_lines = []
    current_start = 1

    for i, line in enumerate(lines):
        if re.match(r"^#{1,2}\s+", line):
            if current_lines:
                sections.append({
                    "title": current_title,
                    "text": "\n".join(current_lines),
                    "start_line": current_start,
                    "end_line": i,
                })
            current_title = line.strip("# ").strip()
            current_lines = [line]
            current_start = i + 1
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "title": current_title,
            "text": "\n".join(current_lines),
            "start_line": current_start,
            "end_line": len(lines),
        })

    return sections


def split_section_by_paragraphs(section: dict, max_tokens: int) -> list[dict]:
    """Further split a section by paragraph boundaries if it exceeds max_tokens."""
    text = section["text"]
    if estimate_tokens(text) <= max_tokens:
        return [section]

    paragraphs = re.split(r"\n\n+", text)
    chunks = []
    current_paras = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if current_tokens + para_tokens > max_tokens and current_paras:
            chunks.append({
                "title": section["title"],
                "text": "\n\n".join(current_paras),
                "start_line": section["start_line"],
                "end_line": section["end_line"],
                "is_partial": True,
            })
            current_paras = [para]
            current_tokens = para_tokens
        else:
            current_paras.append(para)
            current_tokens += para_tokens

    if current_paras:
        chunks.append({
            "title": section["title"],
            "text": "\n\n".join(current_paras),
            "start_line": section["start_line"],
            "end_line": section["end_line"],
            "is_partial": len(chunks) > 0,
        })

    return chunks


def main():
    parser = argparse.ArgumentParser(description="Split Markdown by headings and token limits")
    parser.add_argument("input_file", help="Input Markdown file")
    parser.add_argument("--output-dir", default="work/p2_repaired", help="Output directory for chunks")
    parser.add_argument("--max-tokens", type=int, default=4000, help="Max tokens per chunk")
    args = parser.parse_args()

    input_path = pathlib.Path(args.input_file)
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    sections = split_by_headings(text)

    chunks = []
    for section in sections:
        chunks.extend(split_section_by_paragraphs(section, args.max_tokens))

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"chunk_{i:03d}"
        filename = f"{chunk_id}.md"
        (output_dir / filename).write_text(chunk["text"], encoding="utf-8")
        manifest.append({
            "chunk_id": chunk_id,
            "title": chunk["title"],
            "filename": filename,
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"],
            "estimated_tokens": estimate_tokens(chunk["text"]),
            "is_partial": chunk.get("is_partial", False),
        })

    manifest_path = output_dir / "chunk_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Split into {len(chunks)} chunks, manifest at {manifest_path}", file=sys.stderr)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
