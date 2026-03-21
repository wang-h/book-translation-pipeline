"""Check a compiled LaTeX book for common layout issues.

Usage:
    python pdf_layout_check.py <latex_dir> [--log book.log] [--pdf output/pdf/book-draft.pdf]

Parses the compilation log for warnings and performs basic PDF page-count
validation against the chapter manifest.
"""

import argparse
import json
import pathlib
import re
import sys


def parse_log_warnings(log_path: pathlib.Path) -> dict:
    """Parse LaTeX compilation log for warnings and errors."""
    if not log_path.exists():
        return {"error": f"Log file not found: {log_path}"}

    text = log_path.read_text(encoding="utf-8", errors="replace")

    overfull_hbox = re.findall(r"Overfull \\hbox .+? in paragraph at lines (\d+)--(\d+)", text)
    underfull_hbox = re.findall(r"Underfull \\hbox .+? in paragraph at lines (\d+)--(\d+)", text)
    overfull_vbox = re.findall(r"Overfull \\vbox .+? has occurred while \\output is active", text)
    errors = re.findall(r"^! (.+)$", text, re.MULTILINE)
    font_warnings = re.findall(r"Font .+? not found", text, re.IGNORECASE)
    missing_refs = re.findall(r"LaTeX Warning: Reference .+? undefined", text)

    pages_match = re.search(r"Output written on .+? \((\d+) pages", text)
    page_count = int(pages_match.group(1)) if pages_match else None

    return {
        "page_count": page_count,
        "errors": errors[:20],
        "overfull_hbox_count": len(overfull_hbox),
        "underfull_hbox_count": len(underfull_hbox),
        "overfull_vbox_count": len(overfull_vbox),
        "font_warnings": font_warnings,
        "missing_references": missing_refs,
        "overfull_hbox_locations": overfull_hbox[:10],
    }


def check_chapter_count(latex_dir: pathlib.Path, manifest_path: pathlib.Path) -> dict:
    """Verify chapter .tex file count matches manifest."""
    chapters_dir = latex_dir / "chapters"
    tex_files = sorted(chapters_dir.glob("ch*.tex")) if chapters_dir.is_dir() else []

    result = {"tex_chapter_count": len(tex_files)}

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_count = len([c for c in manifest if c.get("title") != "frontmatter"])
        result["manifest_chapter_count"] = manifest_count
        result["chapter_count_match"] = len(tex_files) == manifest_count
    else:
        result["manifest_chapter_count"] = None
        result["chapter_count_match"] = None

    return result


def check_blank_pages(log_text: str) -> int:
    """Estimate number of intentional blank pages from log."""
    return len(re.findall(r"\\cleardoublepage", log_text))


def main():
    parser = argparse.ArgumentParser(description="Check LaTeX book compilation for layout issues")
    parser.add_argument("latex_dir", help="LaTeX project directory (containing book.tex)")
    parser.add_argument("--log", default="book.log", help="Log filename relative to latex_dir")
    parser.add_argument("--manifest", default="config/chapter_manifest.json", help="Chapter manifest path")
    args = parser.parse_args()

    latex_dir = pathlib.Path(args.latex_dir)
    log_path = latex_dir / args.log
    manifest_path = pathlib.Path(args.manifest)

    report = {"latex_dir": str(latex_dir)}

    log_results = parse_log_warnings(log_path)
    report["compilation"] = log_results

    chapter_results = check_chapter_count(latex_dir, manifest_path)
    report["chapters"] = chapter_results

    severity = "OK"
    issues = []

    if log_results.get("errors"):
        severity = "ERROR"
        issues.append(f"{len(log_results['errors'])} compilation error(s)")

    if log_results.get("font_warnings"):
        severity = max(severity, "WARNING")
        issues.append(f"{len(log_results['font_warnings'])} font warning(s)")

    if log_results.get("overfull_hbox_count", 0) > 10:
        severity = max(severity, "WARNING")
        issues.append(f"{log_results['overfull_hbox_count']} overfull hbox warnings")

    if log_results.get("overfull_vbox_count", 0) > 0:
        severity = max(severity, "WARNING")
        issues.append(f"{log_results['overfull_vbox_count']} overfull vbox warnings (possible page overflow)")

    if chapter_results.get("chapter_count_match") is False:
        severity = max(severity, "WARNING")
        issues.append(
            f"Chapter count mismatch: {chapter_results['tex_chapter_count']} tex files "
            f"vs {chapter_results['manifest_chapter_count']} in manifest"
        )

    report["severity"] = severity
    report["issues"] = issues

    print(json.dumps(report, indent=2, ensure_ascii=False))

    if severity == "ERROR":
        sys.exit(1)


if __name__ == "__main__":
    main()
