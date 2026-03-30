"""Extract terminology from repaired Markdown using LLM.

Usage:
    python extract_terms.py <chapters_dir> [--output work/p4_terminology/glossary.json]

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
from collections import Counter, defaultdict

from llm_client import create_client_from_secrets

from book_translation_paths import resolve_workspace

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


def build_extract_prompt(
    source_lang: str, 
    target_lang: str, 
    master_glossary: list[dict] | None = None
) -> str:
    src = _lang_label(source_lang)
    tgt = _lang_label(target_lang)
    
    # 构建主术语库参考部分
    master_ref = ""
    if master_glossary:
        master_ref = "\n\n## 权威术语库参考（必须优先使用以下已审定的译法）\n"
        for term in master_glossary[:30]:  # 限制数量避免prompt太长
            src_term = term.get("source", "")
            tgt_term = term.get("target", "")
            definition = term.get("definition", "")
            forbidden = term.get("forbidden_translations", [])
            master_ref += f"\n- {src_term} → {tgt_term}"
            if definition:
                master_ref += f"（定义：{definition}）"
            if forbidden:
                master_ref += f"【禁用译法：{', '.join(forbidden)}】"
        master_ref += "\n\n## 术语翻译质量示例\n"
        master_ref += """
优质术语翻译示例：
- ❌ "domaine national" → "国有地带" （太泛，非法律用语）
- ✅ "domaine national" → "国有土地" （符合中国土地管理法用语）
- ❌ "classement" → "划入保护林区" （描述性，非术语）
- ✅ "classement" → "定级" （符合林业行政术语）
- ❌ "redevance" → "规费" （口语化）
- ✅ "redevance" → "行政事业性收费" （行政法正式用语）

"""
    
    return f"""\
You are a professional terminologist preparing a {src}→{tgt} translation glossary for a LEGAL/FORESTRY LAW book.

IMPORTANT: This is for translation into Chinese legal/forestry terminology. You must find the CLOSEST EQUIVALENT CONCEPT in Chinese law, NOT literal translation.{master_ref}

Given a chunk of {src} text, extract terms that genuinely need a GLOSSARY ENTRY to ensure translation consistency.

Focus on:
1. Law names & abbreviations.
2. Institutions & organizations.
3. Roles & titles.
4. Domain-specific concepts (especially forestry and administrative law).
5. Person names and fixed references.

DO NOT extract:
- Article/chapter/section numbers.
- Document serial/date references.
- Single characters or structural markers.
- Generic common words that do not need a glossary.

For each term provide:
- "source": source-language term (normalized, canonical form)
- "target": recommended target-language translation (MUST match Chinese legal/forestry usage)
- "type": one of "law_name", "institution", "role", "abbreviation", "person_name", "concept", "other"
- "notes": brief note if there is a translation trap or concept mismatch between legal systems

Return a JSON array only. No text outside the JSON.
Quality over quantity: keep only terms with real consistency value.
When in doubt between a literal translation and an established Chinese legal term, ALWAYS choose the established Chinese legal term."""


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
    client,
    model: str,
    system: str,
    user_content: str,
    max_tokens: int = 8192,
    max_retries: int = 3,
) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    
    response = client.call_with_retry(
        messages=messages,
        model=model,
        temperature=0.1,
        max_tokens=max_tokens,
        max_retries=max_retries,
    )
    
    content = response.content.strip()
    # Strip markdown code fences if present
    content = re.sub(r"^```json\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    return content


def extract_from_chunk(
    client,
    model: str,
    chunk_text: str,
    source_lang: str,
    target_lang: str,
    master_glossary: list[dict] | None = None,
) -> list[dict]:
    try:
        raw = call_llm(client, model, build_extract_prompt(source_lang, target_lang, master_glossary), chunk_text)
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
    client,
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
                client,
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


def load_master_glossary(path: pathlib.Path | None) -> list[dict] | None:
    """Load master glossary as reference for extraction."""
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        terms = data.get("terms", [])
        print(f"Loaded {len(terms)} terms from master glossary: {path}", file=sys.stderr)
        return terms
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: failed to load master glossary: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Extract terminology via LLM (2-pass)")
    parser.add_argument("chapters_dir", help="Directory with repaired .md files")
    parser.add_argument("--output", default="work/p4_terminology/glossary.json")
    parser.add_argument("--limit", type=int, default=0, help="Max chunks to process (0=all)")
    parser.add_argument("--provider", help="LLM provider (openai, kimi, gemini, anthropic). Uses default_provider from secrets if not specified.")
    parser.add_argument("--model", help="Override model from secrets")
    parser.add_argument("--skip-prune", action="store_true", help="Skip pass-2 pruning")
    parser.add_argument("--source-lang", default="ja", help="Source language code")
    parser.add_argument("--target-lang", default="zh-CN", help="Target language code")
    parser.add_argument("--master-glossary", help="Path to master glossary JSON for reference (e.g., reference_corpus/forest_law_master_glossary.json)")
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

    limit = args.limit if args.limit > 0 else len(chunks)
    all_raw: list[dict] = []

    # Load master glossary if provided
    master_glossary = None
    if args.master_glossary:
        master_glossary = load_master_glossary(pathlib.Path(args.master_glossary))
    
    print(f"\n=== Pass 1: Extract from {limit} chunks ===", file=sys.stderr)
    for i, chunk in enumerate(chunks[:limit]):
        print(f"[{i+1}/{limit}] extracting ({len(chunk)} chars) …", file=sys.stderr, flush=True)
        terms = extract_from_chunk(
            client,
            model,
            chunk,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            master_glossary=master_glossary,
        )
        print(f"  -> {len(terms)} terms", file=sys.stderr)
        all_raw.extend(terms)

    print(f"\nRaw terms: {len(all_raw)}", file=sys.stderr)
    merged = merge_terms(all_raw, source_lang=args.source_lang, target_lang=args.target_lang)
    print(f"After dedup: {len(merged)} unique terms", file=sys.stderr)

    if not args.skip_prune and len(merged) > 100:
        print(f"\n=== Pass 2: LLM quality pruning ===", file=sys.stderr)
        merged = prune_glossary(
            client,
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
