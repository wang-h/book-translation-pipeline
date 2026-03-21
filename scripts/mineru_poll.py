"""Poll MinerU v4 cloud API for task completion and download results.

Usage:
    python mineru_poll.py <task_or_batch_id> [--batch] [--output-dir <dir>] [--timeout 1800]

Downloads the result ZIP and extracts it to <output-dir>/.
"""

import argparse
import io
import json
import pathlib
import sys
import time
import zipfile

import requests

PIPELINE_ROOT = pathlib.Path(__file__).resolve().parent.parent
SECRETS_PATH = PIPELINE_ROOT / "local.secrets.json"


def load_secrets():
    if not SECRETS_PATH.exists():
        print(f"Error: secrets file not found at {SECRETS_PATH}", file=sys.stderr)
        print("Copy secrets.example.json to local.secrets.json and fill in your credentials.", file=sys.stderr)
        sys.exit(1)
    return json.loads(SECRETS_PATH.read_text())


def poll_single_task(base_url: str, token: str, task_id: str, timeout: int) -> str | None:
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()

    while time.time() - start < timeout:
        resp = requests.get(f"{base_url}/extract/task/{task_id}", headers=headers)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        state = data.get("state", "unknown")
        elapsed = int(time.time() - start)

        if state == "done":
            url = data.get("full_zip_url")
            print(f"[{elapsed}s] Done. ZIP URL: {url}", file=sys.stderr)
            return url

        if state == "failed":
            err = data.get("err_msg", "unknown error")
            print(f"[{elapsed}s] Failed: {err}", file=sys.stderr)
            return None

        progress = data.get("extract_progress", {})
        extracted = progress.get("extracted_pages", "?")
        total = progress.get("total_pages", "?")
        print(f"[{elapsed}s] {state} ({extracted}/{total} pages)", file=sys.stderr)

        time.sleep(10)

    print(f"Timeout after {timeout}s", file=sys.stderr)
    return None


def poll_batch(base_url: str, token: str, batch_id: str, timeout: int) -> list[str]:
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    urls = []

    while time.time() - start < timeout:
        resp = requests.get(f"{base_url}/extract-results/batch/{batch_id}", headers=headers)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        results = data.get("extract_result", [])

        all_done = True
        for r in results:
            state = r.get("state", "unknown")
            if state == "done":
                url = r.get("full_zip_url")
                if url and url not in urls:
                    urls.append(url)
            elif state == "failed":
                print(f"File {r.get('file_name')} failed: {r.get('err_msg')}", file=sys.stderr)
            else:
                all_done = False

        elapsed = int(time.time() - start)
        if all_done:
            print(f"[{elapsed}s] All tasks done.", file=sys.stderr)
            return urls

        print(f"[{elapsed}s] Waiting... ({len(urls)}/{len(results)} done)", file=sys.stderr)
        time.sleep(10)

    print(f"Timeout after {timeout}s", file=sys.stderr)
    return urls


def download_and_extract(zip_url: str, output_dir: pathlib.Path):
    print(f"Downloading {zip_url}...", file=sys.stderr)
    resp = requests.get(zip_url)
    resp.raise_for_status()

    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(output_dir)

    print(f"Extracted to {output_dir}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Poll MinerU task and download results")
    parser.add_argument("task_id", help="task_id or batch_id to poll")
    parser.add_argument("--batch", action="store_true", help="Poll as batch task")
    parser.add_argument("--output-dir", default="work/ocr", help="Directory to extract results")
    parser.add_argument("--timeout", type=int, default=1800, help="Max wait time in seconds")
    args = parser.parse_args()

    secrets = load_secrets()
    base_url = secrets["mineru"]["base_url"]
    token = secrets["mineru"]["token"]
    output_dir = pathlib.Path(args.output_dir)

    if args.batch:
        urls = poll_batch(base_url, token, args.task_id, args.timeout)
        for url in urls:
            download_and_extract(url, output_dir)
    else:
        url = poll_single_task(base_url, token, args.task_id, args.timeout)
        if url:
            download_and_extract(url, output_dir)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
