"""Translate Japanese book Markdown to simplified Chinese via OpenAI-compatible API.

Usage:
    python openai_translate_md.py --chunks-dir work/p4_translate_chunks --output work/p4_translated/ch01.md
    python openai_translate_md.py --chunks-dir ... --output ... --glossary work/p3_terminology/glossary.json
    python openai_translate_md.py --chunks-dir ... --output ... --resume
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import requests

from book_translation_paths import resolve_workspace

SECRETS_CANDIDATES = ("local.secrets.json", "secrets.json")


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
    model = oa.get("model") or "gpt-4o"
    if not key:
        print("openai.api_key missing in secrets", file=sys.stderr)
        sys.exit(1)
    return base, key, model


def load_glossary_segment(glossary_path: pathlib.Path | None) -> str:
    if glossary_path is None or not glossary_path.is_file():
        return ""
    try:
        data = json.loads(glossary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    terms = data.get("terms") or data.get("entries") or []
    if not terms:
        return ""
    lines = ["## 必须遵守的术语译法（glossary）", "| 原文/日文 | 中文 | 备注 |", "|---|---|---|"]
    for t in terms[:200]:
        if isinstance(t, dict):
            src = t.get("source") or t.get("ja") or t.get("term") or ""
            zh = t.get("preferred_translation") or t.get("zh") or t.get("translation") or ""
            note = t.get("notes") or ""
            if src and zh:
                lines.append(f"| {src} | {zh} | {note} |")
        elif isinstance(t, (list, tuple)) and len(t) >= 2:
            lines.append(f"| {t[0]} | {t[1]} | |")
    if len(lines) <= 3:
        return ""
    return "\n".join(lines) + "\n\n"


def build_system_prompt(glossary_segment: str) -> str:
    base = """You are a professional translator for a Japanese legal-education reference book (教育関係法, 日本評論社系).
Translate the following Markdown from Japanese into **simplified Chinese (简体中文)**.

Hard rules:
- Preserve ALL Markdown structure exactly: #/##/### headings, lists, blockquotes, tables, footnote markers [^n], image lines ![](...), math $...$ / $$...$$.
- Do NOT merge or split paragraphs/blocks unless the source clearly has one blank-line-separated block = one output block.
- Do NOT omit, summarize, or add commentary.
- Japanese law names: use common Chinese legal literature forms where established (e.g. 学校教育法、教育基本法); otherwise transliterate clearly and keep consistency.
- Use full-width Chinese punctuation where appropriate for body text; keep ASCII in URLs/ISBNs.
- Return ONLY the translated Markdown for this chunk. No explanations."""
    if glossary_segment.strip():
        return base + "\n\n" + glossary_segment
    return base


def translate_chunk(
    base: str,
    key: str,
    model: str,
    system: str,
    user_text: str,
    max_retries: int = 3,
) -> str:
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_completion_tokens": 16384,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    }
    last_err = None
    for attempt in range(max_retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=600)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:500]}"
                time.sleep(5 * (attempt + 1))
                continue
            data = r.json()
            choice = data["choices"][0]["message"]["content"]
            if not choice or not choice.strip():
                last_err = "empty completion"
                time.sleep(3)
                continue
            return choice.strip()
        except Exception as e:
            last_err = str(e)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(last_err or "translate_chunk failed")


def main():
    parser = argparse.ArgumentParser(description="Translate JP Markdown chunks to zh-CN")
    parser.add_argument("--chunks-dir", required=True, help="Directory with chunk_*.md")
    parser.add_argument("--output", required=True, help="Concatenated translated Markdown path")
    parser.add_argument(
        "--glossary",
        help="Optional glossary JSON (work/p3_terminology/glossary.json)",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N chunks (0=all)")
    parser.add_argument("--model", help="Override openai.model from secrets")
    args = parser.parse_args()

    chunks_dir = pathlib.Path(args.chunks_dir)
    chunk_files = sorted(chunks_dir.glob("chunk_*.md"))
    if not chunk_files:
        print(f"No chunk_*.md in {chunks_dir}", file=sys.stderr)
        sys.exit(1)

    glossary_path = pathlib.Path(args.glossary) if args.glossary else None
    glossary_seg = load_glossary_segment(glossary_path)
    system = build_system_prompt(glossary_seg)

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path = out_path.with_suffix(out_path.suffix + ".progress.json")

    if args.resume and progress_path.is_file():
        done = set(json.loads(progress_path.read_text(encoding="utf-8")).get("completed", []))
    else:
        done = set()
        out_path.unlink(missing_ok=True)
        progress_path.unlink(missing_ok=True)

    base, key, model = load_openai_cfg()
    if args.model:
        model = args.model
    print(f"Using model {model} at {base}", file=sys.stderr)

    limit = args.limit if args.limit > 0 else len(chunk_files)
    processed = 0
    file_mode = "a" if out_path.exists() else "w"

    with out_path.open(file_mode, encoding="utf-8") as out:
        for cf in chunk_files:
            if cf.name in done:
                continue
            if processed >= limit:
                break
            raw = cf.read_text(encoding="utf-8")
            print(f"[{processed + 1}/{limit}] {cf.name} ({len(raw)} chars) …", file=sys.stderr, flush=True)
            zh = translate_chunk(base, key, model, system, raw)
            out.write(zh)
            if not zh.endswith("\n"):
                out.write("\n")
            out.write("\n")
            out.flush()
            done.add(cf.name)
            progress_path.write_text(json.dumps({"completed": sorted(done)}, indent=2), encoding="utf-8")
            processed += 1

    print(f"Done. Wrote {out_path} ({processed} chunks)", file=sys.stderr)


if __name__ == "__main__":
    main()
