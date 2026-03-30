"""Polish translated entry JSON with a stronger LLM while preserving 1:1 entry mapping.

Supports multiple providers: OpenAI, Kimi, Gemini, Anthropic/Claude.

Usage:
  python openai_polish_entries.py \
    --input-translated work/p5_translated_xxx/translated.json \
    --output-dir work/p4_polished_xxx \
    --target-lang zh-CN \
    --provider kimi \
    --model kimi-moonshot-v1-128k
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

from llm_client import create_client_from_secrets, get_thinking_level

from book_translation_paths import resolve_workspace


def build_system_prompt(target_lang: str) -> str:
    return f"""You are a senior legal-editor polishing translated book paragraphs.
Target language: {target_lang}.

Input is a JSON array: [{{"id": N, "text": "..."}}, ...]
Return a JSON array with EXACT same length, order, and ids.

Hard rules:
- Output ONLY valid JSON array.
- Keep one-to-one mapping, no missing ids, no reordering.
- Keep legal meaning strictly unchanged; do not add/delete facts.
- Improve only readability/formatting:
  1) fix awkward line breaks;
  2) normalize punctuation and spacing for target language;
  3) tidy heading/list/table markdown formatting when present.
- Output must remain only in target language for body text.
- Do not introduce source-language blocks or bilingual wrappers.
"""


def polish_batch(
    client,
    model: str,
    system: str,
    entries: list[dict],
    thinking_level: str | None,
) -> list[dict]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(entries, ensure_ascii=False)},
    ]
    
    expected_ids = [e["id"] for e in entries]
    
    extra_args = {}
    if thinking_level and client.provider in ("openai", "kimi"):
        extra_args["thinking_level"] = thinking_level
    
    response = client.call_with_retry(
        messages=messages,
        model=model,
        temperature=0.1,
        max_tokens=16384,
        max_retries=3,
        **extra_args
    )
    
    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content[: content.rfind("```")]
    content = content.strip()

    result = json.loads(content)
    if not isinstance(result, list):
        raise ValueError(f"LLM returned {type(result)}, expected list")

    result_ids = [e.get("id") for e in result]
    if result_ids != expected_ids:
        raise ValueError("ID mismatch")

    fixed = []
    for src, out in zip(entries, result):
        txt = out.get("text", "") if isinstance(out, dict) else ""
        if not isinstance(txt, str) or not txt.strip():
            txt = src["text"]
        # remove accidental bilingual wrapper if model introduces it
        txt = re.sub(r":::law-bilingual[\s\S]*?:::", "", txt).strip()
        fixed.append({"id": src["id"], "text": txt})
    return fixed


def assemble_markdown(entries: list[dict]) -> str:
    entries = sorted(entries, key=lambda x: x["id"])
    return "\n\n".join(e["text"] for e in entries) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Polish translated entries with 1:1 mapping")
    parser.add_argument("--input-translated", required=True, help="Path to translated.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-lang", default="zh-CN")
    parser.add_argument("--batch-size", type=int, default=6)
    parser.add_argument("--provider", help="LLM provider (openai, kimi, gemini, anthropic). Uses default_provider from secrets if not specified.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--thinking-level", choices=["LOW", "MEDIUM", "HIGH", "low", "medium", "high"], default=None)
    args = parser.parse_args()

    in_path = pathlib.Path(args.input_translated)
    if not in_path.is_file():
        print(f"Input not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = pathlib.Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        print("input translated.json must be a list", file=sys.stderr)
        sys.exit(1)

    # Create LLM client from secrets
    try:
        client, model = create_client_from_secrets(
            provider=args.provider,
            task="translate"
        )
    except Exception as e:
        print(f"Error initializing LLM client: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.model:
        model = args.model
    
    # Get thinking level from args, secrets, or default
    thinking_level = args.thinking_level
    if not thinking_level:
        thinking_level = get_thinking_level()
    if thinking_level:
        thinking_level = thinking_level.upper()

    system = build_system_prompt(args.target_lang)

    print(f"Provider: {client.provider}, Model: {model} (thinking={thinking_level})", file=sys.stderr)
    print(f"Entries: {len(entries)}, batch_size={args.batch_size}", file=sys.stderr)

    polished = []
    for i in range(0, len(entries), args.batch_size):
        batch = entries[i:i + args.batch_size]
        idx = i // args.batch_size + 1
        total = (len(entries) + args.batch_size - 1) // args.batch_size
        print(f"[{idx}/{total}] polishing {len(batch)} entries...", file=sys.stderr, flush=True)
        try:
            out = polish_batch(client, model, system, batch, thinking_level)
        except RuntimeError as e:
            print(f"  WARNING: batch failed, keep original: {e}", file=sys.stderr)
            out = batch
        polished.extend(out)

    polished = sorted(polished, key=lambda x: x["id"])
    (out_dir / "translated.json").write_text(json.dumps(polished, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "progress.json").write_text(json.dumps({
        "translated_count": len(polished),
        "total_entries": len(polished),
        "status": "polished",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "ch01.md").write_text(assemble_markdown(polished), encoding="utf-8")
    print(f"Done. Output: {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
