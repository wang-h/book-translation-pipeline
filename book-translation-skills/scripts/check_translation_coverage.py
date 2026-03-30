"""Check translation coverage at entry level.

Usage:
    python check_translation_coverage.py \
      --entries work/p4_translate_chunks/entries.json \
      --translated work/p5_translated/translated.json

Checks every source entry has a corresponding translated entry that is:
  - Present (not missing)
  - Non-empty
  - Not marked [TRANSLATION_FAILED]
  - Has reasonable length relative to source
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


KANA_RE = re.compile(r"[ぁ-んァ-ヶー]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check entry-level translation coverage")
    parser.add_argument("--entries", required=True, help="Source entries.json")
    parser.add_argument("--translated", required=True, help="Translated translated.json")
    parser.add_argument("--report", default=None, help="Output report JSON path")
    args = parser.parse_args()

    src_entries = json.loads(pathlib.Path(args.entries).read_text(encoding="utf-8"))
    tr_path = pathlib.Path(args.translated)
    if not tr_path.is_file():
        print(f"Error: {tr_path} not found", file=sys.stderr)
        sys.exit(1)

    tr_entries = json.loads(tr_path.read_text(encoding="utf-8"))
    tr_map = {e["id"]: e for e in tr_entries}

    missing: list[int] = []
    empty: list[int] = []
    failed: list[int] = []
    too_short: list[dict] = []
    high_kana: list[dict] = []

    for src in src_entries:
        eid = src["id"]
        src_text = src["text"]

        if eid not in tr_map:
            missing.append(eid)
            continue

        zh_text = tr_map[eid].get("text", "")

        if not zh_text.strip():
            empty.append(eid)
            continue

        if zh_text.startswith("[TRANSLATION_FAILED]"):
            failed.append(eid)
            continue

        ratio = len(zh_text) / max(1, len(src_text))
        if ratio < 0.15 and len(src_text) > 50:
            too_short.append({"id": eid, "src_len": len(src_text), "zh_len": len(zh_text), "ratio": round(ratio, 3)})

        kana_count = len(KANA_RE.findall(zh_text))
        kana_ratio = kana_count / max(1, len(zh_text))
        if kana_ratio > 0.08 and len(zh_text) > 30:
            high_kana.append({"id": eid, "kana_ratio": round(kana_ratio, 3)})

    total = len(src_entries)
    ok = total - len(missing) - len(empty) - len(failed)
    has_issues = bool(missing or empty or failed or too_short or high_kana)

    report = {
        "summary": {
            "total_entries": total,
            "translated_ok": ok,
            "missing": len(missing),
            "empty": len(empty),
            "failed": len(failed),
            "too_short": len(too_short),
            "high_kana": len(high_kana),
            "pass": not has_issues,
        },
        "missing_ids": missing,
        "empty_ids": empty,
        "failed_ids": failed,
        "too_short": too_short,
        "high_kana": high_kana,
    }

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))

    if args.report:
        rp = pathlib.Path(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Report: {rp}")

    if has_issues:
        if missing:
            print(f"Missing IDs: {missing[:20]}{'...' if len(missing) > 20 else ''}")
        if empty:
            print(f"Empty IDs: {empty[:20]}")
        if failed:
            print(f"Failed IDs: {failed[:20]}")
        sys.exit(2)
    else:
        print("All entries covered.")


if __name__ == "__main__":
    main()
