"""Build config/chapter_manifest.json from MinerU work/p1_ocr/full.md headings.

Usage:
    python generate_chapter_manifest.py [full.md] [--output config/chapter_manifest.json]

Uses the same heading boundaries as split_book.py (# / ## at line start).
"""

import argparse
import json
import pathlib
import re
import sys


def split_by_headings(text: str) -> list[tuple[str, int, int]]:
    lines = text.split("\n")
    sections: list[tuple[str, int, int]] = []
    current_title = "frontmatter"
    current_lines: list[str] = []
    current_start = 1

    for i, line in enumerate(lines):
        if re.match(r"^#{1,2}\s+", line):
            if current_lines:
                sections.append((current_title, current_start, i))
            current_title = line.strip("# ").strip()
            current_lines = [line]
            current_start = i + 1
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_start, len(lines)))

    return sections


def main():
    parser = argparse.ArgumentParser(description="Generate chapter_manifest.json from full.md")
    parser.add_argument(
        "full_md",
        nargs="?",
        default="work/p1_ocr/full.md",
        help="Path to MinerU full.md",
    )
    parser.add_argument("--output", default="config/chapter_manifest.json", help="Output JSON path")
    args = parser.parse_args()

    full_path = pathlib.Path(args.full_md)
    if not full_path.is_file():
        print(f"Error: {full_path} not found", file=sys.stderr)
        sys.exit(1)

    text = full_path.read_text(encoding="utf-8")
    sections = split_by_headings(text)

    manifest = {
        "book_title": sections[0][0] if sections else "",
        "source_pdf": "",
        "chapters": [],
    }

    for idx, (title, start_line, end_line) in enumerate(sections, start=1):
        ch_id = f"ch{idx:02d}"
        manifest["chapters"].append({
            "chapter_id": ch_id,
            "title": title,
            "start_line": start_line,
            "end_line": end_line,
            "source_file": f"{ch_id}.md",
            "repair_status": "pending",
            "translation_status": "pending",
        })

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(manifest['chapters'])} chapters to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
