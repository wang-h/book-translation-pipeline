"""Split a Markdown file into fixed-size paragraph-safe chunks (no heading-based fragmentation).

Usage:
    python split_md_paragraphs.py <input.md> --output-dir work/p2_repair_chunks --max-chars 12000
"""

import argparse
import json
import pathlib
import re
import sys


def paragraph_blocks(text: str) -> list[str]:
    """Split on blank lines; keep non-empty blocks."""
    parts = re.split(r"\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def merge_to_chunks(blocks: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for b in blocks:
        blen = len(b) + 2
        if current and size + blen > max_chars:
            chunks.append("\n\n".join(current))
            current = [b]
            size = blen
        else:
            current.append(b)
            size += blen
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Split MD into char-limited paragraph chunks")
    parser.add_argument("input_file", help="Source Markdown")
    parser.add_argument("--output-dir", required=True, help="Directory for chunk_000.md ...")
    parser.add_argument("--max-chars", type=int, default=12000, help="Max characters per chunk")
    args = parser.parse_args()

    inp = pathlib.Path(args.input_file)
    if not inp.is_file():
        print(f"Error: {inp} not found", file=sys.stderr)
        sys.exit(1)

    text = inp.read_text(encoding="utf-8")
    blocks = paragraph_blocks(text)
    chunks = merge_to_chunks(blocks, args.max_chars)

    out_dir = pathlib.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, ch in enumerate(chunks):
        name = f"chunk_{i:04d}.md"
        (out_dir / name).write_text(ch + "\n", encoding="utf-8")
        manifest.append({"chunk_id": name, "chars": len(ch)})

    (out_dir / "paragraph_chunk_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(chunks)} chunks to {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
