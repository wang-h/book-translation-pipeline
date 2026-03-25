#!/usr/bin/env python3
"""
fix_heading_levels.py – Rebuild Markdown heading hierarchy from MinerU bbox data.

MinerU OCR marks every title as `# ` (level 1). This script reads the
content_list_v2.json layout data, clusters title bbox heights into natural
levels using Jenks natural breaks, and rewrites the Markdown with correct
`#`/`##`/`###`/… headings.

Usage:
    python fix_heading_levels.py \
        --json  workspace/work/p1_ocr/content_list_v2.json \
        --md    workspace/work/p1_ocr/full.md \
        --output workspace/work/p1_ocr/full_leveled.md
"""

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. Extract title blocks from MinerU JSON
# ---------------------------------------------------------------------------

def _title_text(block: dict) -> str:
    tc = block.get("content", {}).get("title_content", [])
    return "".join(
        t.get("content", "") if isinstance(t, dict) else str(t) for t in tc
    ).strip()


def _title_height(block: dict) -> int | None:
    bbox = block.get("bbox", [])
    return bbox[3] - bbox[1] if len(bbox) == 4 else None


def extract_titles(json_path: str) -> tuple[list[dict], int]:
    """Return (body_titles, toc_end_page).

    Auto-detects TOC / front-matter pages (high title density, small fonts)
    and excludes them so they don't pollute the height clustering.
    """
    with open(json_path) as f:
        pages = json.load(f)

    toc_end = 0
    for pi, page in enumerate(pages):
        if pi > 20:
            break
        titles = [b for b in page if b.get("type") == "title"]
        paras = [b for b in page if b.get("type") == "paragraph"]
        total = len(titles) + len(paras)
        if total == 0:
            continue
        title_ratio = len(titles) / total
        avg_h = 0
        if titles:
            hs = [_title_height(b) for b in titles]
            hs = [h for h in hs if h is not None]
            avg_h = sum(hs) / len(hs) if hs else 0
        if title_ratio > 0.4 and avg_h < 28 and len(titles) >= 5:
            toc_end = pi + 1

    body = []
    for pi, page in enumerate(pages):
        for block in page:
            if block.get("type") != "title":
                continue
            h = _title_height(block)
            text = _title_text(block)
            if h is None or not text:
                continue
            body.append({
                "page": pi + 1,
                "height": h,
                "text": text,
                "is_toc": pi < toc_end,
            })
    return body, toc_end


# ---------------------------------------------------------------------------
# 2. Jenks Natural Breaks (Fisher) for 1D classification
# ---------------------------------------------------------------------------

def jenks_breaks(data: list[float], k: int) -> list[float]:
    """Return k-1 break values that partition sorted *data* into k classes
    minimising within-class sum of squared deviations (SDCM).
    """
    data = sorted(data)
    n = len(data)
    if n <= k:
        return sorted(set(data))

    # lower_class_limits[i][j] = optimal start index for class j ending at i
    lcl = [[0] * (k + 1) for _ in range(n + 1)]
    var = [[float("inf")] * (k + 1) for _ in range(n + 1)]

    for j in range(1, k + 1):
        lcl[1][j] = 1
        var[1][j] = 0.0

    for i in range(2, n + 1):
        s1 = 0.0
        s2 = 0.0
        for m in range(1, i + 1):
            idx = i - m  # 0-based index into data
            val = data[idx]
            s1 += val
            s2 += val * val
            v = s2 - s1 * s1 / m
            if idx > 0:
                for j in range(2, k + 1):
                    candidate = v + var[idx][j - 1]
                    if candidate < var[i][j]:
                        lcl[i][j] = idx + 1
                        var[i][j] = candidate
            else:
                for j in range(1, k + 1):
                    if v < var[i][j]:
                        lcl[i][j] = 1
                        var[i][j] = v

    # Back-trace to find break points
    breaks = [data[-1]]
    kk = n
    for j in range(k, 1, -1):
        idx = lcl[kk][j] - 1
        breaks.append(data[idx])
        kk = lcl[kk][j] - 1
    breaks.sort()
    return breaks[:-1]  # k-1 upper bounds for the lower k-1 classes


# ---------------------------------------------------------------------------
# 3. Cluster heights → heading levels
# ---------------------------------------------------------------------------

def cluster_heights(titles: list[dict], max_levels: int = 5) -> dict[int, int]:
    """Map each unique body-page bbox height to a heading level (1 = biggest)."""
    body_titles = [t for t in titles if not t["is_toc"]]
    if not body_titles:
        body_titles = titles

    all_h = [t["height"] for t in body_titles]
    unique = sorted(set(all_h), reverse=True)
    if len(unique) <= max_levels:
        return {h: i + 1 for i, h in enumerate(unique)}

    breaks = sorted(jenks_breaks(all_h, max_levels), reverse=True)

    height_to_level: dict[int, int] = {}
    for h in unique:
        level = 1  # biggest height → top level
        for i, b in enumerate(breaks):
            if h <= b:
                level = i + 2
        height_to_level[h] = level

    # TOC-page titles that also appear in body get their body level;
    # TOC-only titles get max_levels (lowest importance).
    for t in titles:
        if t["is_toc"] and t["height"] not in height_to_level:
            height_to_level[t["height"]] = max_levels

    return height_to_level


# ---------------------------------------------------------------------------
# 4. Normalise text & fuzzy match for rewriting Markdown
# ---------------------------------------------------------------------------

def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[\u2500-\u257f·…·.、。，,]+$", "", s)
    return s.lower()


def build_title_level_map(
    titles: list[dict], height_to_level: dict[int, int]
) -> dict[str, int]:
    tlmap: dict[str, int] = {}
    for t in titles:
        key = normalize(t["text"])
        level = height_to_level.get(t["height"], 5)
        if key not in tlmap or level < tlmap[key]:
            tlmap[key] = level
    return tlmap


def _fuzzy_match(key: str, title_level_map: dict[str, int]) -> int | None:
    if len(key) < 4:
        return None
    best: int | None = None
    best_score = 0.0
    for map_key, level in title_level_map.items():
        if len(map_key) < 4:
            continue
        shorter, longer = (key, map_key) if len(key) <= len(map_key) else (map_key, key)
        if shorter in longer:
            score = len(shorter) / len(longer)
            if score > best_score:
                best_score = score
                best = level
            continue
        sa, sb = set(key), set(map_key)
        jaccard = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
        if jaccard > 0.75 and jaccard > best_score:
            best_score = jaccard
            best = level
    return best


_STRUCTURAL_PATTERNS = [
    # [第X章] / 第X章 → chapter level
    (re.compile(r"^\[?第\s*\d+\s*章\]?"), "chapter"),
    # <第X節> / 第X節 → section level
    (re.compile(r"^[<＜]?第\s*\d+\s*[節节]\s*[>＞]?"), "section"),
    # 第X条 → article level
    (re.compile(r"^第\s*\d+\s*条"), "article"),
    # [第X部] → part level
    (re.compile(r"^\[?第\s*\d+\s*部\]?"), "part"),
]

# Structural role → target level; these normalise bbox-noise inconsistencies.
_ROLE_LEVEL = {"part": 3, "chapter": 3, "section": 4, "article": 5}


def _detect_structural_role(text: str) -> str | None:
    clean = re.sub(r"^[\[【「]", "", text.strip())
    for pat, role in _STRUCTURAL_PATTERNS:
        if pat.match(clean):
            return role
    return None


def rewrite_markdown(md_path: str, title_level_map: dict[str, int]) -> list[str]:
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
    lines = Path(md_path).read_text(encoding="utf-8").splitlines()
    out: list[str] = []

    for line in lines:
        m = heading_re.match(line)
        if m:
            text = m.group(2).strip()
            key = normalize(text)

            # 1) bbox-based level
            level = title_level_map.get(key) or _fuzzy_match(key, title_level_map)

            # 2) structural pattern override: fix bbox noise for known markers
            role = _detect_structural_role(text)
            if role:
                level = _ROLE_LEVEL[role]

            if level:
                out.append(f"{'#' * level} {text}")
                continue
        out.append(line)

    return out


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fix Markdown heading levels from MinerU bbox data"
    )
    parser.add_argument("--json", required=True, help="content_list_v2.json")
    parser.add_argument("--md", required=True, help="Input Markdown")
    parser.add_argument("--output", required=True, help="Output Markdown")
    parser.add_argument("--max-levels", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    all_titles, toc_end = extract_titles(args.json)
    body_titles = [t for t in all_titles if not t["is_toc"]]
    print(f"Titles: {len(all_titles)} total, {len(body_titles)} body (TOC pages: 1-{toc_end})")

    height_to_level = cluster_heights(all_titles, max_levels=args.max_levels)

    print("\nHeight → Level mapping (body pages):")
    hcounts = Counter(t["height"] for t in body_titles)
    for h in sorted(height_to_level.keys(), reverse=True):
        cnt = hcounts.get(h, 0)
        if cnt == 0:
            continue
        sample = next((t["text"][:50] for t in body_titles if t["height"] == h), "")
        print(f"  {h:3d}px → {'#' * height_to_level[h]:6s} (×{cnt:4d})  e.g. {sample}")

    title_level_map = build_title_level_map(all_titles, height_to_level)

    if args.dry_run:
        print(f"\nWould rewrite {args.md} with {len(title_level_map)} title mappings")
        return

    result = rewrite_markdown(args.md, title_level_map)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(result) + "\n", encoding="utf-8")

    new_counts: dict[int, int] = {}
    for ln in result:
        m = re.match(r"^(#{1,6}) ", ln)
        if m:
            lv = len(m.group(1))
            new_counts[lv] = new_counts.get(lv, 0) + 1

    orig_h1 = sum(1 for ln in Path(args.md).read_text().splitlines() if re.match(r"^# ", ln))
    print(f"\nDone → {args.output}")
    print(f"  Before: {orig_h1} headings (all #)")
    print(f"  After:  {dict(sorted(new_counts.items()))}")


if __name__ == "__main__":
    main()
