"""Translate book Markdown between configurable language pairs via LLM API.

Supports multiple providers: OpenAI, Kimi, Gemini, Anthropic/Claude.
Structured JSON I/O: each source entry maps 1:1 to a translated entry.

Usage:
    python openai_translate_md.py \
      --entries-dir work/p4_translate_chunks \
      --output-dir work/p5_translated \
      --glossary work/p4_terminology/glossary.json \
      --provider kimi

Inputs:
    entries-dir/batch_XXXX.json   – batched source entries [{"id": N, "text": "..."}, ...]
    entries-dir/entries.json      – full entry list (for validation)

Outputs:
    output-dir/translated.json    – [{"id": N, "text": "translated..."}, ...]
    output-dir/progress.json      – {"completed_batches": [...], "translated_ids": [...]}
    output-dir/ch01.md            – assembled Markdown (for downstream LaTeX)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

from llm_client import create_client_from_secrets, get_thinking_level

from book_translation_paths import resolve_workspace


def _lang_col_zh(lang: str) -> str:
    low = lang.lower()
    if low.startswith("ja"):
        return "日文"
    if low.startswith("zh"):
        return "中文"
    if low.startswith("en"):
        return "英文"
    if low.startswith("ko"):
        return "韩文"
    if low.startswith("fr"):
        return "法文"
    if low.startswith("de"):
        return "德文"
    if low.startswith("es"):
        return "西文"
    return "原文"


def load_glossary_segment(
    glossary_path: pathlib.Path | None,
    source_lang: str,
    target_lang: str,
) -> str:
    if glossary_path is None or not glossary_path.is_file():
        return ""
    try:
        data = json.loads(glossary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    terms = data.get("terms") or data.get("entries") or []
    if not terms:
        return ""
    src_col = _lang_col_zh(source_lang)
    tgt_col = _lang_col_zh(target_lang)
    
    # 检查是否为新格式（包含 definition, forbidden_translations 等）
    lines = ["## 强制术语约束（必须一字不差地遵循）", ""]
    lines.append("以下术语的译法已由中国法律专家审定。翻译时必须使用'批准译法'，绝对禁止使用'禁止译法'：")
    lines.append("")
    
    for t in terms[:200]:
        if isinstance(t, dict):
            src = t.get("source") or t.get("ja") or t.get("term") or ""
            zh = (
                t.get("preferred_translation")
                or t.get("target")
                or t.get("zh")
                or t.get("translation")
                or ""
            )
            if not src or not zh:
                continue
            
            # 新格式：包含 forbidden_translations
            forbidden = t.get("forbidden_translations", [])
            definition = t.get("definition", "")
            note = t.get("notes", "")
            
            lines.append(f"- **{src}** → **{zh}**")
            if definition:
                lines.append(f"  - 定义：{definition}")
            if forbidden:
                lines.append(f"  - 🚫 禁止译为：{', '.join(forbidden)}")
            if note:
                lines.append(f"  - 备注：{note}")
            lines.append("")
        elif isinstance(t, (list, tuple)) and len(t) >= 2:
            lines.append(f"- **{t[0]}** → **{t[1]}**")
            lines.append("")
    
    if len(lines) <= 5:
        return ""
    
    lines.append("⚠️ 警告：如果译文使用了'禁止译法'中的任何一个，该翻译将被视为不合格。")
    lines.append("")
    return "\n".join(lines) + "\n"


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


KANJI_DIGITS = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}


def _int_to_kanji(num: int) -> str:
    if num == 0:
        return "零"
    units = ["", "十", "百", "千", "万"]
    s = str(num)
    out = []
    length = len(s)
    for i, ch in enumerate(s):
        d = int(ch)
        pos = length - i - 1
        if d == 0:
            continue
        if d == 1 and pos > 0 and not out:
            out.append(units[pos])
        else:
            out.append(KANJI_DIGITS[ch] + units[pos])
    return "".join(out)


def normalize_legal_ordinals(text: str, target_lang: str) -> str:
    """Normalize legal ordinals based on target language conventions."""
    low = target_lang.lower()
    if not (low.startswith("ja") or low.startswith("zh")):
        return text

    def repl(m):
        raw = m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        unit = m.group(2)
        try:
            n = int(raw)
        except ValueError:
            return m.group(0)
        return f"第{_int_to_kanji(n)}{unit}"

    # "第5章" => "第五章", "第12条" => "第十二条"
    return re.sub(r"第\s*([0-9０-９]+)\s*([章节条])", repl, text)


def build_system_prompt(
    glossary_segment: str,
    source_lang: str,
    target_lang: str,
    domain: str,
    law_bilingual: bool,
) -> str:
    src_label = _lang_label(source_lang)
    tgt_label = _lang_label(target_lang)
    domain_desc = "a legal/professional reference book" if domain == "legal" else "a professional non-fiction book"
    base = f"""\
You are a professional translator for {domain_desc}.
Translate {src_label} ({source_lang}) to {tgt_label} ({target_lang}).

You will receive a JSON array: [{{"id": N, "text": "<source markdown paragraph>"}}, ...]
You MUST return a JSON array of the SAME length, SAME order, SAME ids:
[{{"id": N, "text": "<translated paragraph>"}} , ...]

Hard rules:
- Output ONLY valid JSON. No explanations outside the JSON array.
- Each output entry MUST correspond 1:1 to the input entry with the same id.
- NEVER skip, merge, or reorder entries. len(output) == len(input).
- Preserve Markdown structure: headings (#/##/###), lists, tables, footnotes [^n], images ![](...), math $...$.
- Do NOT merge or split paragraphs.
- Keep translation faithful, precise, and publication-ready."""
    if domain == "legal":
        base += """
- For legal terms and law names, use established literature conventions in the target language."""
    if law_bilingual:
        src_tag = source_lang.split("-")[0].upper()
        tgt_tag = target_lang.split("-")[0].upper()
        base += f"""
- For legal article content, keep source + translation together in this format:
  :::law-bilingual
  【法条原文（{src_tag}）】
  <exact source legal article text>

  【法条译文（{tgt_tag}）】
  <translated legal article text>
  :::"""
    if target_lang.lower().startswith("zh"):
        base += """
- Use full-width Chinese punctuation for body text."""
    if target_lang.lower().startswith("ja") or target_lang.lower().startswith("zh"):
        base += """
- For legal ordinals, use kanji numerals instead of arabic digits:
  write "第五章", "第十二条" (not "第5章", "第12条")."""
    if glossary_segment.strip():
        return base + "\n\n" + glossary_segment
    return base


def translate_batch(
    client,
    model: str,
    system: str,
    entries: list[dict],
    target_lang: str,
    thinking_level: str | None = None,
    max_retries: int = 3,
) -> list[dict]:
    """Send a batch of entries, get back translated entries with same IDs."""
    user_content = json.dumps(entries, ensure_ascii=False)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    expected_ids = [e["id"] for e in entries]

    try:
        extra_args = {}
        if thinking_level and client.provider in ("openai", "kimi"):
            extra_args["thinking_level"] = thinking_level
        
        response = client.call_with_retry(
            messages=messages,
            model=model,
            temperature=0.2,
            max_tokens=16384,
            max_retries=max_retries,
            **extra_args
        )
        
        content = response.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[: content.rfind("```")]
        content = content.strip()

        result = json.loads(content)
        if not isinstance(result, list):
            raise ValueError(f"LLM returned {type(result)}, expected list")

        result_ids = [e.get("id") for e in result]
        if result_ids == expected_ids and all(
            isinstance(e.get("text"), str) and e["text"].strip() for e in result
        ):
            for e in result:
                e["text"] = normalize_legal_ordinals(e["text"], target_lang)
            return result

        if len(result) == len(entries):
            fixed = []
            for src, out in zip(entries, result):
                fixed.append({
                    "id": src["id"],
                    "text": normalize_legal_ordinals(out.get("text", ""), target_lang),
                })
            if all(f["text"].strip() for f in fixed):
                return fixed

        raise ValueError(f"ID mismatch or empty entries: expected {len(entries)}, got {len(result)}")

    except Exception as e:
        raise RuntimeError(f"translate_batch failed: {e}")


def retry_singles(
    client,
    model: str,
    system: str,
    entries: list[dict],
    target_lang: str,
    thinking_level: str | None,
) -> list[dict]:
    """Fallback: translate entries one by one when batch fails."""
    results = []
    for e in entries:
        print(f"    retry single id={e['id']} …", file=sys.stderr, flush=True)
        try:
            out = translate_batch(
                client, model, system, [e], target_lang, thinking_level, max_retries=2
            )
            results.extend(out)
        except RuntimeError as err:
            print(f"    FAILED id={e['id']}: {err}", file=sys.stderr)
            results.append({"id": e["id"], "text": f"[TRANSLATION_FAILED] {e['text']}"})
    return results


def assemble_markdown(translated: list[dict]) -> str:
    """Join translated entries back into markdown."""
    translated.sort(key=lambda e: e["id"])
    return "\n\n".join(e["text"] for e in translated) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Translate entry batches with configurable source/target languages (structured JSON)"
    )
    parser.add_argument("--entries-dir", required=True, help="Directory with batch_*.json and entries.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for translated.json and .md")
    parser.add_argument("--glossary", help="Optional glossary JSON")
    parser.add_argument("--source-lang", default="ja", help="Source language code, e.g. ja, en, fr")
    parser.add_argument("--target-lang", default="zh-CN", help="Target language code, e.g. zh-CN, en, ja")
    parser.add_argument(
        "--domain",
        choices=["general", "legal"],
        default="legal",
        help="Translation domain constraints",
    )
    parser.add_argument(
        "--law-bilingual",
        action="store_true",
        help="Force :::law-bilingual blocks for legal article content",
    )
    parser.add_argument(
        "--no-law-bilingual",
        action="store_true",
        help="Disable :::law-bilingual output requirement",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from progress.json")
    parser.add_argument("--limit", type=int, default=0, help="Max batches to process (0=all)")
    parser.add_argument("--provider", help="LLM provider (openai, kimi, gemini, anthropic). Uses default_provider from secrets if not specified.")
    parser.add_argument("--model", help="Override model from secrets")
    parser.add_argument(
        "--thinking-level",
        choices=["LOW", "MEDIUM", "HIGH", "low", "medium", "high"],
        help="Reasoning level",
    )
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="Only re-translate entries marked [TRANSLATION_FAILED]",
    )
    args = parser.parse_args()

    entries_dir = pathlib.Path(args.entries_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    entries_path = entries_dir / "entries.json"
    if not entries_path.is_file():
        print(f"Error: {entries_path} not found", file=sys.stderr)
        sys.exit(1)

    all_entries = json.loads(entries_path.read_text(encoding="utf-8"))
    all_ids = {e["id"] for e in all_entries}

    # Match only real batch shards (batch_0000.json, ...), exclude batch_manifest.json
    batch_files = sorted(entries_dir.glob("batch_[0-9][0-9][0-9][0-9].json"))
    if not batch_files:
        print(f"No batch_*.json in {entries_dir}", file=sys.stderr)
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
    
    print(f"Provider: {client.provider}, Model: {model}", file=sys.stderr)
    
    glossary_path = pathlib.Path(args.glossary) if args.glossary else None
    glossary_seg = load_glossary_segment(
        glossary_path,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
    )
    law_bilingual = args.domain == "legal"
    if args.law_bilingual:
        law_bilingual = True
    if args.no_law_bilingual:
        law_bilingual = False
    system = build_system_prompt(
        glossary_seg,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        domain=args.domain,
        law_bilingual=law_bilingual,
    )

    translated_path = output_dir / "translated.json"
    progress_path = output_dir / "progress.json"

    translated_map: dict[int, dict] = {}
    done_batches: set[str] = set()

    if args.resume and translated_path.is_file():
        existing = json.loads(translated_path.read_text(encoding="utf-8"))
        for e in existing:
            translated_map[e["id"]] = e
    if args.resume and progress_path.is_file():
        prog = json.loads(progress_path.read_text(encoding="utf-8"))
        done_batches = set(prog.get("completed_batches", []))

    if args.retry_failed:
        failed = [
            e for e in translated_map.values()
            if isinstance(e.get("text"), str) and e["text"].startswith("[TRANSLATION_FAILED]")
        ]
        if not failed:
            print("No [TRANSLATION_FAILED] entries found.", file=sys.stderr)
            sys.exit(0)

        src_map = {e["id"]: e for e in all_entries}
        to_retry = [src_map[e["id"]] for e in failed if e["id"] in src_map]
        print(f"Retrying {len(to_retry)} failed entries …", file=sys.stderr)

        retried = retry_singles(client, model, system, to_retry, args.target_lang, thinking_level)
        for e in retried:
            translated_map[e["id"]] = e
        _save_state(translated_map, done_batches, translated_path, progress_path, all_ids, output_dir)
        return

    print(f"Model: {model} (thinking_level={thinking_level})", file=sys.stderr)
    print(f"Entries: {len(all_entries)}, Batches: {len(batch_files)}", file=sys.stderr)

    limit = args.limit if args.limit > 0 else len(batch_files)
    processed = 0

    for bf in batch_files:
        if bf.name in done_batches:
            continue
        if processed >= limit:
            break

        batch = json.loads(bf.read_text(encoding="utf-8"))
        entry_count = len(batch)
        char_count = sum(len(e["text"]) for e in batch)
        print(
            f"[{processed+1}/{limit}] {bf.name} ({entry_count} entries, {char_count} chars) …",
            file=sys.stderr,
            flush=True,
        )

        try:
            result = translate_batch(client, model, system, batch, args.target_lang, thinking_level)
        except RuntimeError as e:
            print(f"  Batch failed, falling back to single-entry retry: {e}", file=sys.stderr)
            result = retry_singles(client, model, system, batch, args.target_lang, thinking_level)

        for e in result:
            translated_map[e["id"]] = e
        done_batches.add(bf.name)

        _save_state(translated_map, done_batches, translated_path, progress_path, all_ids, output_dir)

        ok = sum(1 for e in result if not e["text"].startswith("[TRANSLATION_FAILED]"))
        print(f"  -> {ok}/{entry_count} OK", file=sys.stderr)
        processed += 1

    _save_state(translated_map, done_batches, translated_path, progress_path, all_ids, output_dir)

    total = len(all_ids)
    done = sum(1 for eid in all_ids if eid in translated_map)
    failed = sum(
        1 for eid in all_ids
        if eid in translated_map and translated_map[eid]["text"].startswith("[TRANSLATION_FAILED]")
    )
    missing = total - done
    print(f"\nDone. {done}/{total} entries translated, {failed} failed, {missing} missing.", file=sys.stderr)


def _save_state(
    translated_map: dict[int, dict],
    done_batches: set[str],
    translated_path: pathlib.Path,
    progress_path: pathlib.Path,
    all_ids: set[int],
    output_dir: pathlib.Path,
) -> None:
    ordered = sorted(translated_map.values(), key=lambda e: e["id"])
    translated_path.write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    progress_path.write_text(
        json.dumps(
            {
                "completed_batches": sorted(done_batches),
                "translated_count": len(translated_map),
                "total_entries": len(all_ids),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    md = assemble_markdown(list(translated_map.values()))
    (output_dir / "ch01.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
