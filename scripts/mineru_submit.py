"""Submit a PDF to MinerU v4 cloud AI standard API for OCR parsing.

Usage:
    python mineru_submit.py <pdf_path> [--url <public_url>] [--ocr] [--output-dir <dir>]

Outputs task_id to stdout and saves it to <output-dir>/task_id.txt.
"""

import argparse
import json
import pathlib
import sys

import requests

PIPELINE_ROOT = pathlib.Path(__file__).resolve().parent.parent
SECRETS_PATH = PIPELINE_ROOT / "local.secrets.json"


def load_secrets():
    if not SECRETS_PATH.exists():
        print(f"Error: secrets file not found at {SECRETS_PATH}", file=sys.stderr)
        print("Copy secrets.example.json to local.secrets.json and fill in your credentials.", file=sys.stderr)
        sys.exit(1)
    return json.loads(SECRETS_PATH.read_text())


def submit_by_file(base_url: str, token: str, pdf_path: str, ocr: bool, extra_formats: list[str]) -> str:
    filename = pathlib.Path(pdf_path).name
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    payload = {
        "files": [{"name": filename}],
        "model_version": "vlm",
        "enable_formula": True,
        "enable_table": True,
        "extra_formats": extra_formats,
    }
    if ocr:
        payload["files"][0]["is_ocr"] = True

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


def submit_by_url(base_url: str, token: str, url: str, ocr: bool, extra_formats: list[str]) -> str:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {
        "url": url,
        "model_version": "vlm",
        "enable_formula": True,
        "enable_table": True,
        "is_ocr": ocr,
        "extra_formats": extra_formats,
    }
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
    parser.add_argument("--output-dir", default="work/ocr", help="Directory to save task_id")
    parser.add_argument("--extra-formats", nargs="*", default=["latex"], help="Extra output formats")
    args = parser.parse_args()

    if not args.pdf_path and not args.url:
        parser.error("Provide either a local pdf_path or --url")

    secrets = load_secrets()
    base_url = secrets["mineru"]["base_url"]
    token = secrets["mineru"]["token"]

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.url:
        task_id = submit_by_url(base_url, token, args.url, args.ocr, args.extra_formats)
        id_type = "task_id"
    else:
        task_id = submit_by_file(base_url, token, args.pdf_path, args.ocr, args.extra_formats)
        id_type = "batch_id"

    id_file = output_dir / f"{id_type}.txt"
    id_file.write_text(task_id)
    print(task_id)


if __name__ == "__main__":
    main()
