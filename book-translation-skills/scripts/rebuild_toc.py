"""Rebuild a normalized TOC tree from markdown headings.

Usage:
    python rebuild_toc.py \
      --md work/p2_repaired/full_repaired.md \
      --output-json work/p3_toc/chapter_structure.json \
      --output-md work/p3_toc/toc.md

Optional:
    --toc-json work/p3_toc/chapter_structure_raw.json
If provided, page numbers from toc-json are matched by title and merged into
the rebuilt structure.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def normalize_title(title: str) -> str:
    s = title.strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[·•\.\-—–…]+$", "", s)
    return s.lower()


def parse_headings(md_text: str, max_depth: int = 3) -> list[dict[str, Any]]:
    root: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []

    for line in md_text.splitlines():
        m = HEADING_RE.match(line)
        if not m:
            continue
        level = min(len(m.group(1)), max_depth)
        title = m.group(2).strip()
        node = {"title": title, "level": level, "children": []}

        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            stack[-1][1]["children"].append(node)
        else:
            root.append(node)
        stack.append((level, node))

    return root


def flatten_toc_pages(toc_obj: dict[str, Any]) -> dict[str, int]:
    title_to_page: dict[str, int] = {}

    def walk(node: dict[str, Any]) -> None:
        title = str(node.get("title", "")).strip()
        page = node.get("page")
        if title and isinstance(page, int):
            title_to_page[normalize_title(title)] = page
        for k in ("sections", "subsections", "children"):
            arr = node.get(k)
            if isinstance(arr, list):
                for child in arr:
                    if isinstance(child, dict):
                        walk(child)

    chapters = toc_obj.get("chapters")
    if isinstance(chapters, list):
        for ch in chapters:
            if isinstance(ch, dict):
                walk(ch)
    return title_to_page


def to_chapter_structure(nodes: list[dict[str, Any]], title_to_page: dict[str, int]) -> dict[str, Any]:
    chapters = []
    for ch in nodes:
        chapter = {
            "title": ch["title"],
            "page": title_to_page.get(normalize_title(ch["title"])),
            "type": "chapter",
            "sections": [],
        }
        for sec in ch.get("children", []):
            section = {
                "title": sec["title"],
                "page": title_to_page.get(normalize_title(sec["title"])),
                "type": "section",
                "subsections": [],
            }
            for sub in sec.get("children", []):
                section["subsections"].append({
                    "title": sub["title"],
                    "page": title_to_page.get(normalize_title(sub["title"])),
                    "type": "subsection",
                })
            chapter["sections"].append(section)
        chapters.append(chapter)
    return {"chapters": chapters}


def render_toc_md(structure: dict[str, Any]) -> str:
    lines = ["# 目录重构结果", ""]
    for ch in structure.get("chapters", []):
        title = ch.get("title", "")
        page = ch.get("page")
        suffix = f" (p.{page})" if isinstance(page, int) else ""
        lines.append(f"- {title}{suffix}")
        for sec in ch.get("sections", []):
            st = sec.get("title", "")
            sp = sec.get("page")
            ss = f" (p.{sp})" if isinstance(sp, int) else ""
            lines.append(f"  - {st}{ss}")
            for sub in sec.get("subsections", []):
                subt = sub.get("title", "")
                subp = sub.get("page")
                subs = f" (p.{subp})" if isinstance(subp, int) else ""
                lines.append(f"    - {subt}{subs}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild normalized TOC from markdown headings")
    parser.add_argument("--md", required=True, help="Input markdown file (usually repaired full.md)")
    parser.add_argument("--output-json", default="work/p3_toc/chapter_structure.json", help="Output TOC JSON")
    parser.add_argument("--output-md", default="work/p3_toc/toc.md", help="Output human-readable TOC markdown")
    parser.add_argument("--toc-json", help="Optional TOC JSON with page numbers (from extract_toc.py)")
    parser.add_argument("--max-depth", type=int, default=3, help="Heading depth to keep (default: 3)")
    args = parser.parse_args()

    md_path = pathlib.Path(args.md)
    text = md_path.read_text(encoding="utf-8")
    nodes = parse_headings(text, max_depth=max(1, args.max_depth))

    title_to_page: dict[str, int] = {}
    if args.toc_json:
        toc_path = pathlib.Path(args.toc_json)
        if toc_path.is_file():
            toc_obj = json.loads(toc_path.read_text(encoding="utf-8"))
            title_to_page = flatten_toc_pages(toc_obj)

    structure = to_chapter_structure(nodes, title_to_page)

    out_json = pathlib.Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    out_md = pathlib.Path(args.output_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_toc_md(structure), encoding="utf-8")

    chapter_count = len(structure.get("chapters", []))
    print(f"Rebuilt TOC: {chapter_count} chapters")
    print(f"JSON: {out_json}")
    print(f"MD: {out_md}")


if __name__ == "__main__":
    main()
