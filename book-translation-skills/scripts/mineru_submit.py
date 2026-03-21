"""Submit a PDF to MinerU v4 cloud AI standard API for OCR parsing.

Usage:
    python mineru_submit.py <pdf_path> [--url <public_url>] [--ocr] [--output-dir <dir>]
    python mineru_submit.py book.pdf --ocr --first-pages 10   # 只解析前 10 页（测试）
    python mineru_submit.py book.pdf --ocr --page-ranges "1-10"

Outputs task_id to stdout and saves it to <output-dir>/task_id.txt.
"""

import argparse
import json
import pathlib
import sys

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


def load_secrets():
    path = resolve_secrets_path()
    if path is None:
        print(
            "Error: no secrets file found. Create one of:",
            file=sys.stderr,
        )
        for name in SECRETS_CANDIDATES:
            print(f"  {resolve_workspace() / name}", file=sys.stderr)
        print("Copy secrets.example.json and fill in MinerU token and API keys.", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def submit_by_file(
    base_url: str,
    token: str,
    pdf_path: str,
    ocr: bool,
    extra_formats: list[str],
    page_ranges: str | None,
) -> str:
    filename = pathlib.Path(pdf_path).name
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    file_entry: dict = {"name": filename}
    if ocr:
        file_entry["is_ocr"] = True
    if page_ranges:
        file_entry["page_ranges"] = page_ranges

    payload = {
        "files": [file_entry],
        "model_version": "vlm",
        "enable_formula": True,
        "enable_table": True,
        "extra_formats": extra_formats,
    }

    resp = requests.post(f"{base_url}/file-urls/batch", headers=headers, json=payload)
    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0:
        print(f"API error: {result.get('msg')}", file=sys.stderr)
        sys.exit(1)

    batch_id = result["data"]["batch_id"]
    file_url = result["data"]["file_urls"][0]

    with open(pdf_path, "rb") as f:
        put_resp = requests.put(file_url, data=f)
        if put_resp.status_code not in (200, 201):
            print(f"File upload failed: HTTP {put_resp.status_code}", file=sys.stderr)
            sys.exit(1)

    print(f"Uploaded {filename}, batch_id: {batch_id}", file=sys.stderr)
    return batch_id


def submit_by_url(
    base_url: str,
    token: str,
    url: str,
    ocr: bool,
    extra_formats: list[str],
    page_ranges: str | None,
) -> str:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {
        "url": url,
        "model_version": "vlm",
        "enable_formula": True,
        "enable_table": True,
        "is_ocr": ocr,
        "extra_formats": extra_formats,
    }
    if page_ranges:
        payload["page_ranges"] = page_ranges
    resp = requests.post(f"{base_url}/extract/task", headers=headers, json=payload)
    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0:
        print(f"API error: {result.get('msg')}", file=sys.stderr)
        sys.exit(1)

    task_id = result["data"]["task_id"]
    print(f"Submitted URL task, task_id: {task_id}", file=sys.stderr)
    return task_id


def main():
    parser = argparse.ArgumentParser(description="Submit PDF to MinerU v4 cloud API")
    parser.add_argument("pdf_path", nargs="?", help="Local PDF file path")
    parser.add_argument("--url", help="Public URL of the PDF (use instead of local file)")
    parser.add_argument("--ocr", action="store_true", help="Force OCR mode for scanned documents")
    parser.add_argument("--output-dir", default="work/p1_ocr", help="Directory to save task_id")
    parser.add_argument("--extra-formats", nargs="*", default=["latex"], help="Extra output formats")
    parser.add_argument(
        "--page-ranges",
        metavar="SPEC",
        help='MinerU page_ranges (e.g. "1-10", "2,4-6"). See MinerU API docs.',
    )
    parser.add_argument(
        "--first-pages",
        type=int,
        metavar="N",
        help='Shortcut: same as --page-ranges "1-N" (e.g. --first-pages 10)',
    )
    args = parser.parse_args()

    if not args.pdf_path and not args.url:
        parser.error("Provide either a local pdf_path or --url")

    page_ranges = args.page_ranges
    if args.first_pages is not None:
        if args.first_pages < 1:
            parser.error("--first-pages must be >= 1")
        if page_ranges:
            parser.error("Use only one of --page-ranges or --first-pages")
        page_ranges = f"1-{args.first_pages}"

    secrets = load_secrets()
    base_url = secrets["mineru"]["base_url"]
    token = secrets["mineru"]["token"]

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if page_ranges:
        print(f"page_ranges: {page_ranges}", file=sys.stderr)

    if args.url:
        task_id = submit_by_url(base_url, token, args.url, args.ocr, args.extra_formats, page_ranges)
        id_type = "task_id"
    else:
        task_id = submit_by_file(base_url, token, args.pdf_path, args.ocr, args.extra_formats, page_ranges)
        id_type = "batch_id"

    id_file = output_dir / f"{id_type}.txt"
    id_file.write_text(task_id)
    print(task_id)


if __name__ == "__main__":
    main()
