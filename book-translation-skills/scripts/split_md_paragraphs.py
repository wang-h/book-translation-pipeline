"""Split a Markdown file into paragraph-level entries with stable IDs.

Usage:
    python split_md_paragraphs.py <input.md> --output-dir work/p4_translate_chunks --batch-chars 10000

Outputs:
    entries.json          – full list: [{"id": 0, "text": "..."}, ...]
    batch_0000.json       – batched subsets for API calls
    batch_manifest.json   – batch index
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


def paragraph_blocks(text: str) -> list[str]:
    """Split on blank lines; keep non-empty blocks."""
    parts = re.split(r"\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def build_entries(blocks: list[str]) -> list[dict]:
    return [{"id": i, "text": b} for i, b in enumerate(blocks)]


def batch_entries(entries: list[dict], max_chars: int) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for e in entries:
        elen = len(e["text"]) + 20
        if current and size + elen > max_chars:
            batches.append(current)
            current = [e]
            size = elen
        else:
            current.append(e)
            size += elen
    if current:
        batches.append(current)
    return batches


def main():
    parser = argparse.ArgumentParser(description="Split MD into paragraph entries with IDs")
    parser.add_argument("input_file", help="Source Markdown")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--batch-chars", type=int, default=10000, help="Max chars per batch")
    args = parser.parse_args()

    inp = pathlib.Path(args.input_file)
    if not inp.is_file():
        print(f"Error: {inp} not found", file=sys.stderr)
        sys.exit(1)

    text = inp.read_text(encoding="utf-8")
    blocks = paragraph_blocks(text)
    entries = build_entries(blocks)
    batches = batch_entries(entries, args.batch_chars)

    out_dir = pathlib.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "entries.json").write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    manifest = []
    for i, batch in enumerate(batches):
        name = f"batch_{i:04d}.json"
        (out_dir / name).write_text(
            json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        manifest.append({
            "batch_file": name,
            "entry_count": len(batch),
            "entry_ids": [e["id"] for e in batch],
            "chars": sum(len(e["text"]) for e in batch),
        })

    (out_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {len(entries)} entries in {len(batches)} batches to {out_dir}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
