"""Extract candidate terminology from repaired Markdown chapters.

Usage:
    python extract_terms.py <chapters_dir> [--output <path>] [--min-freq 2]

Scans all .md files for capitalized phrases, abbreviations, quoted terms,
and italicized terms. Outputs term_candidates.json with frequency and chapter
source information.
"""

import argparse
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict


def extract_capitalized_phrases(text: str) -> list[str]:
    """Extract multi-word capitalized phrases (likely proper nouns or terms)."""
    return re.findall(r"\b(?:[A-Z][a-z]+(?:\s+(?:of|the|and|for|in|on|to|a|an)\s+)?){2,}[A-Z][a-z]*\b", text)


def extract_abbreviations(text: str) -> list[str]:
    """Extract uppercase abbreviations (2+ letters)."""
    return re.findall(r"\b[A-Z]{2,}\b", text)


def extract_quoted_terms(text: str) -> list[str]:
    """Extract terms in quotes or italics."""
    double_quoted = re.findall(r'"([^"]{2,60})"', text)
    single_quoted = re.findall(r"'([^']{2,60})'", text)
    italicized = re.findall(r"\*([^*]{2,60})\*", text)
    return double_quoted + single_quoted + italicized


def normalize_term(term: str) -> str:
    """Normalize a term for deduplication."""
    return re.sub(r"\s+", " ", term.strip()).title()


def process_chapter(filepath: pathlib.Path) -> dict[str, list[str]]:
    """Extract all term candidates from a single chapter file."""
    text = filepath.read_text(encoding="utf-8")
    chapter_id = filepath.stem

    raw_terms = []
    raw_terms.extend(extract_capitalized_phrases(text))
    raw_terms.extend(extract_abbreviations(text))
    raw_terms.extend(extract_quoted_terms(text))

    term_contexts = {}
    for term in raw_terms:
        normalized = normalize_term(term)
        if normalized not in term_contexts:
            pattern = re.escape(term)
            match = re.search(rf".{{0,60}}{pattern}.{{0,60}}", text)
            context = match.group(0).strip() if match else ""
            term_contexts[normalized] = {
                "chapter": chapter_id,
                "context": context,
            }

    return term_contexts


def main():
    parser = argparse.ArgumentParser(description="Extract terminology candidates from Markdown chapters")
    parser.add_argument("chapters_dir", help="Directory containing repaired chapter .md files")
    parser.add_argument("--output", default="work/p3_terminology/term_candidates.json", help="Output path")
    parser.add_argument("--min-freq", type=int, default=2, help="Minimum frequency to include a term")
    args = parser.parse_args()

    chapters_dir = pathlib.Path(args.chapters_dir)
    if not chapters_dir.is_dir():
        print(f"Error: {chapters_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(chapters_dir.glob("*.md"))
    if not md_files:
        print(f"Error: no .md files found in {chapters_dir}", file=sys.stderr)
        sys.exit(1)

    global_freq = Counter()
    term_examples = defaultdict(list)

    for filepath in md_files:
        chapter_terms = process_chapter(filepath)
        for normalized, info in chapter_terms.items():
            global_freq[normalized] += 1
            if len(term_examples[normalized]) < 3:
                term_examples[normalized].append(info)

    candidates = []
    for term, freq in global_freq.most_common():
        if freq >= args.min_freq:
            candidates.append({
                "source_term": term,
                "frequency": freq,
                "chapter_examples": term_examples[term],
                "preferred_translation": "",
                "alternatives": [],
                "forbidden_translations": [],
                "part_of_speech_or_type": "",
                "retain_original": False,
                "notes": "",
                "status": "candidate",
            })

    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Extracted {len(candidates)} term candidates (min_freq={args.min_freq})", file=sys.stderr)
    print(f"Saved to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
