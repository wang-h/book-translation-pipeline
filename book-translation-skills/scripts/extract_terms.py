"""Extract terminology from repaired Markdown using LLM.

Usage:
    python extract_terms.py <chapters_dir> [--output work/p3_terminology/glossary.json]

Two-pass approach:
  Pass 1 – Chunk-level extraction with strict quality prompt
  Pass 2 – LLM-based dedup & pruning on the merged list
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from collections import Counter, defaultdict

import requests

from book_translation_paths import resolve_workspace

SECRETS_CANDIDATES = ("local.secrets.json", "secrets.json")

def _lang_label(lang: str) -> str:
    low = lang.lower()
    if low.startswith("ja"):
        return "Japanese"
    if low.startswith("zh"):
        return "Chinese"
    if low.startswith("en"):
        return "English"
    if low.startswith("ko"):
        return "Korean"
    if low.startswith("fr"):
        return "French"
    if low.startswith("de"):
        return "German"
    if low.startswith("es"):
        return "Spanish"
    return lang


def build_extract_prompt(source_lang: str, target_lang: str) -> str:
    src = _lang_label(source_lang)
    tgt = _lang_label(target_lang)
    return f"""\
You are a professional terminologist preparing a {src}→{tgt} translation glossary for a legal/professional book.

Given a chunk of {src} text, extract terms that genuinely need a GLOSSARY ENTRY to ensure translation consistency.

Focus on:
1. Law names & abbreviations.
2. Institutions & organizations.
3. Roles & titles.
4. Domain-specific concepts.
5. Person names and fixed references.

DO NOT extract:
- Article/chapter/section numbers.
- Document serial/date references.
- Single characters or structural markers.
- Generic common words that do not need a glossary.

For each term provide:
- "source": source-language term (normalized, canonical form)
- "target": recommended target-language translation
- "type": one of "law_name", "institution", "role", "abbreviation", "person_name", "concept", "other"
- "notes": brief note only if there is a translation trap

Return a JSON array only. No text outside the JSON.
Quality over quantity: keep only terms with real consistency value."""


def build_prune_prompt(source_lang: str, target_lang: str) -> str:
    src = _lang_label(source_lang)
    tgt = _lang_label(target_lang)
    return f"""\
You are a terminology quality reviewer for a {src}→{tgt} legal/professional book glossary.

You will receive a glossary JSON array. Return a CLEANED JSON array:

1. REMOVE entries that are:
   - Pure numbering/article references.
   - Serial/date reference strings.
   - Generic words with no glossary value.
   - Duplicates or near-duplicates where one can represent the concept.

2. MERGE entries where:
   - Surface forms vary but concept is identical.
   - Full form and abbreviation refer to the same concept.

3. KEEP entries where:
   - Translation could drift or is non-obvious.
   - Proper nouns or domain terms require consistency.

Output format per entry:
- "source", "target", "type", "notes"

Return only JSON array. No extra text."""


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


def load_openai_cfg():
    path = resolve_secrets_path()
    if path is None:
        print("No secrets.json / local.secrets.json", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    oa = data.get("openai") or {}
    base = (oa.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    key = oa.get("api_key")
    model = oa.get("extract_model") or "gpt-5.4-mini"
    if not key:
        print("openai.api_key missing in secrets", file=sys.stderr)
        sys.exit(1)
    return base, key, model


def split_into_chunks(text: str, max_chars: int = 12000) -> list[str]:
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for p in paragraphs:
        plen = len(p) + 2
        if current and size + plen > max_chars:
            chunks.append("\n\n".join(current))
            current = [p]
            size = plen
        else:
            current.append(p)
            size += plen
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def call_llm(
    base: str, key: str, model: str, system: str, user_content: str,
    max_tokens: int = 8192, max_retries: int = 3,
) -> str:
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0.1,
        "max_completion_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    }
    last_err = None
    for attempt in range(max_retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=300)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:300]}"
                time.sleep(5 * (attempt + 1))
                continue
            content = r.json()["choices"][0]["message"]["content"].strip()
            content = re.sub(r"^```json\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
            return content
        except Exception as e:
            last_err = str(e)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {max_retries} retries: {last_err}")


def extract_from_chunk(
    base: str,
    key: str,
    model: str,
    chunk_text: str,
    source_lang: str,
    target_lang: str,
) -> list[dict]:
    try:
        raw = call_llm(base, key, model, build_extract_prompt(source_lang, target_lang), chunk_text)
        terms = json.loads(raw)
        if isinstance(terms, list):
            return [t for t in terms if isinstance(t, dict)]
    except (json.JSONDecodeError, RuntimeError) as e:
        print(f"  WARNING: extraction failed: {e}", file=sys.stderr)
    return []


def merge_terms(all_raw: list[dict], source_lang: str, target_lang: str) -> list[dict]:
    """Deduplicate and merge terms, picking most common translation."""
    source_to_targets: dict[str, list[str]] = defaultdict(list)
    source_to_type: dict[str, list[str]] = defaultdict(list)
    source_to_notes: dict[str, str] = {}

    for entry in all_raw:
        if not isinstance(entry, dict):
            continue
        source = (entry.get("source") or entry.get("ja") or entry.get("term") or "").strip()
        target = (entry.get("target") or entry.get("zh") or entry.get("translation") or "").strip()
        if not source or not target:
            continue
        source_to_targets[source].append(target)
        source_to_type[source].append(entry.get("type") or "other")
        if entry.get("notes"):
            source_to_notes[source] = entry["notes"]

    merged = []
    for source, translations in sorted(source_to_targets.items(), key=lambda x: -len(x[1])):
        target_counts = Counter(translations)
        best_target = target_counts.most_common(1)[0][0]
        type_counts = Counter(source_to_type[source])
        best_type = type_counts.most_common(1)[0][0]
        notes = source_to_notes.get(source, "")
        if len(target_counts) > 1:
            alts = [z for z, _ in target_counts.most_common() if z != best_target]
            if alts:
                notes = f"其他译法: {', '.join(alts[:3])}" + (f"; {notes}" if notes else "")
        item = {"source": source, "target": best_target, "type": best_type, "notes": notes}
        if source_lang.lower().startswith("ja"):
            item["ja"] = source
        if target_lang.lower().startswith("zh"):
            item["zh"] = best_target
        merged.append(item)
    return merged


def prune_glossary(
    base: str,
    key: str,
    model: str,
    terms: list[dict],
    source_lang: str,
    target_lang: str,
    batch_size: int = 400,
) -> list[dict]:
    """Pass 2: LLM-based quality pruning in batches."""
    if len(terms) <= batch_size:
        batches = [terms]
    else:
        batches = [terms[i:i + batch_size] for i in range(0, len(terms), batch_size)]

    pruned: list[dict] = []
    for i, batch in enumerate(batches):
        print(f"  Pruning batch {i+1}/{len(batches)} ({len(batch)} terms) …", file=sys.stderr, flush=True)
        user_content = json.dumps(batch, ensure_ascii=False)
        try:
            raw = call_llm(
                base,
                key,
                model,
                build_prune_prompt(source_lang, target_lang),
                user_content,
                max_tokens=16384,
            )
            result = json.loads(raw)
            if isinstance(result, list):
                pruned.extend(t for t in result if isinstance(t, dict))
                print(f"    -> {len(result)} terms kept", file=sys.stderr)
            else:
                print(f"    WARNING: prune returned non-list, keeping original batch", file=sys.stderr)
                pruned.extend(batch)
        except (json.JSONDecodeError, RuntimeError) as e:
            print(f"    WARNING: prune failed ({e}), keeping original batch", file=sys.stderr)
            pruned.extend(batch)
    return pruned


def main():
    parser = argparse.ArgumentParser(description="Extract terminology via LLM (2-pass)")
    parser.add_argument("chapters_dir", help="Directory with repaired .md files")
    parser.add_argument("--output", default="work/p3_terminology/glossary.json")
    parser.add_argument("--limit", type=int, default=0, help="Max chunks to process (0=all)")
    parser.add_argument("--model", help="Override model from secrets")
    parser.add_argument("--skip-prune", action="store_true", help="Skip pass-2 pruning")
    parser.add_argument("--source-lang", default="ja", help="Source language code")
    parser.add_argument("--target-lang", default="zh-CN", help="Target language code")
    args = parser.parse_args()

    chapters_dir = pathlib.Path(args.chapters_dir)
    if not chapters_dir.is_dir():
        print(f"Error: {chapters_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(chapters_dir.glob("*.md"))
    if not md_files:
        print(f"Error: no .md files in {chapters_dir}", file=sys.stderr)
        sys.exit(1)

    combined = "\n\n".join(f.read_text(encoding="utf-8") for f in md_files)
    chunks = split_into_chunks(combined, max_chars=12000)
    print(f"Text: {len(combined)} chars -> {len(chunks)} chunks", file=sys.stderr)

    base, key, model = load_openai_cfg()
    if args.model:
        model = args.model
    print(f"Model: {model} @ {base}", file=sys.stderr)

    limit = args.limit if args.limit > 0 else len(chunks)
    all_raw: list[dict] = []

    print(f"\n=== Pass 1: Extract from {limit} chunks ===", file=sys.stderr)
    for i, chunk in enumerate(chunks[:limit]):
        print(f"[{i+1}/{limit}] extracting ({len(chunk)} chars) …", file=sys.stderr, flush=True)
        terms = extract_from_chunk(
            base,
            key,
            model,
            chunk,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
        )
        print(f"  -> {len(terms)} terms", file=sys.stderr)
        all_raw.extend(terms)

    print(f"\nRaw terms: {len(all_raw)}", file=sys.stderr)
    merged = merge_terms(all_raw, source_lang=args.source_lang, target_lang=args.target_lang)
    print(f"After dedup: {len(merged)} unique terms", file=sys.stderr)

    if not args.skip_prune and len(merged) > 100:
        print(f"\n=== Pass 2: LLM quality pruning ===", file=sys.stderr)
        merged = prune_glossary(
            base,
            key,
            model,
            merged,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
        )
        final_dedup: dict[str, dict] = {}
        for t in merged:
            source = (t.get("source") or t.get("ja") or t.get("term") or "").strip()
            if source and source not in final_dedup:
                final_dedup[source] = t
        merged = list(final_dedup.values())
        print(f"Final glossary: {len(merged)} terms", file=sys.stderr)

    glossary = {
        "meta": {
            "source_lang": args.source_lang,
            "target_lang": args.target_lang,
            "status": "frozen",
            "book": "",
        },
        "terms": merged,
    }

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(glossary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(merged)} terms to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
