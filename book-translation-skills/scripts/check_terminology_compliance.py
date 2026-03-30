"""Check translation compliance against master glossary with forbidden translations.

Usage:
    python check_terminology_compliance.py \
      --glossary reference_corpus/forest_law_master_glossary.json \
      --translated work/p5_translated/translated.json \
      --report work/p5_translated/terminology_compliance_report.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict


def load_glossary(path: pathlib.Path) -> dict[str, dict]:
    """Load master glossary and index by forbidden translations."""
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = data.get("terms", [])
    
    # Build lookup: source_term -> term_entry
    by_source = {}
    # Build lookup: forbidden_translation -> (source_term, correct_translation)
    forbidden_map = {}
    
    for term in terms:
        source = term.get("source", "").strip()
        if not source:
            continue
        by_source[source.lower()] = term
        
        for forbidden in term.get("forbidden_translations", []):
            forbidden_map[forbidden] = (source, term.get("target", ""))
    
    return by_source, forbidden_map


def check_translations(
    translated_path: pathlib.Path,
    forbidden_map: dict[str, tuple[str, str]],
) -> dict:
    """Check translated content for forbidden terminology usage."""
    data = json.loads(translated_path.read_text(encoding="utf-8"))
    
    violations = []
    warnings = []
    
    for entry in data:
        entry_id = entry.get("id", "unknown")
        text = entry.get("text", "")
        
        # Check for each forbidden translation
        for forbidden, (source, correct) in forbidden_map.items():
            # Simple substring match (can be improved with word boundaries)
            if forbidden in text:
                violations.append({
                    "entry_id": entry_id,
                    "forbidden_translation": forbidden,
                    "source_term": source,
                    "correct_translation": correct,
                    "context": text[max(0, text.find(forbidden)-20):text.find(forbidden)+len(forbidden)+20],
                })
    
    return {
        "total_entries_checked": len(data),
        "violations_found": len(violations),
        "violations": violations,
    }


def check_glossary_consistency(
    glossary_path: pathlib.Path,
    translated_path: pathlib.Path,
) -> dict:
    """Check if translated content uses glossary terms consistently."""
    glossary_data = json.loads(glossary_path.read_text(encoding="utf-8"))
    translated_data = json.loads(translated_path.read_text(encoding="utf-8"))
    
    terms = glossary_data.get("terms", [])
    
    # Build expected translations map
    expected = {}  # source_lower -> approved_target
    for term in terms:
        source = term.get("source", "").strip()
        target = term.get("target", "").strip()
        if source and target:
            expected[source.lower()] = target
    
    # Check translations
    issues = []
    for entry in translated_data:
        text = entry.get("text", "")
        entry_id = entry.get("id", "unknown")
        
        # For each glossary term, check if its variations appear but not the approved form
        # This is a simplified check - in production you'd want more sophisticated matching
        for source_lower, approved in expected.items():
            # Skip short terms to avoid false positives
            if len(approved) < 3:
                continue
            
            # If approved translation is NOT in text, but source term might be there
            # (This is a heuristic - better approach would be alignment)
            pass  # Placeholder for more sophisticated check
    
    return {
        "consistency_issues": issues,
        "issue_count": len(issues),
    }


def main():
    parser = argparse.ArgumentParser(description="Check terminology compliance in translations")
    parser.add_argument("--glossary", required=True, help="Path to master glossary JSON")
    parser.add_argument("--translated", required=True, help="Path to translated.json")
    parser.add_argument("--report", default="terminology_compliance_report.json", help="Output report path")
    args = parser.parse_args()
    
    glossary_path = pathlib.Path(args.glossary)
    translated_path = pathlib.Path(args.translated)
    report_path = pathlib.Path(args.report)
    
    if not glossary_path.is_file():
        print(f"Error: glossary not found: {glossary_path}", file=sys.stderr)
        sys.exit(1)
    
    if not translated_path.is_file():
        print(f"Error: translated file not found: {translated_path}", file=sys.stderr)
        sys.exit(1)
    
    print("Loading glossary...", file=sys.stderr)
    by_source, forbidden_map = load_glossary(glossary_path)
    print(f"Loaded {len(by_source)} terms, {len(forbidden_map)} forbidden translations", file=sys.stderr)
    
    print("Checking for forbidden translations...", file=sys.stderr)
    compliance_report = check_translations(translated_path, forbidden_map)
    
    # Write report
    report_path.write_text(json.dumps(compliance_report, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Summary
    print(f"\n=== Compliance Check Summary ===", file=sys.stderr)
    print(f"Total entries checked: {compliance_report['total_entries_checked']}", file=sys.stderr)
    print(f"Violations found: {compliance_report['violations_found']}", file=sys.stderr)
    
    if compliance_report['violations_found'] > 0:
        print("\n⚠️  Violations detected:", file=sys.stderr)
        for v in compliance_report['violations'][:10]:  # Show first 10
            print(f"  Entry {v['entry_id']}: '{v['forbidden_translation']}' used, should be '{v['correct_translation']}'", file=sys.stderr)
        if len(compliance_report['violations']) > 10:
            print(f"  ... and {len(compliance_report['violations']) - 10} more", file=sys.stderr)
        print(f"\nFull report saved to: {report_path}", file=sys.stderr)
        sys.exit(1)  # Exit with error if violations found
    else:
        print("✅ No terminology violations found!", file=sys.stderr)
        print(f"Report saved to: {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
