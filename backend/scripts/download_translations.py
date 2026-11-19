#!/usr/bin/env python3
"""
Download all 66-book English Bible translations from bible.helloao.org
and save each as a .txt file in backend/app/assets/translations/

Format per line:
    {Book} {chapter}:{verse}  {text}
Example:
    Genesis 1:1  In the beginning God created the heavens and the earth.

Usage:
    cd backend
    python scripts/download_translations.py

    # Download only specific translations:
    python scripts/download_translations.py --only BSB eng_kjv eng_asv

    # Force re-download even if file exists:
    python scripts/download_translations.py --force
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    import urllib.request as _req

    httpx = None

BASE_URL = "https://bible.helloao.org/api"
OUTPUT_DIR = Path(__file__).parent.parent / "app" / "assets" / "translations"
DELAY_SECONDS = 1.0  # pause between translation requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_json(url: str) -> dict:
    if httpx:
        resp = httpx.get(url, timeout=120)
        resp.raise_for_status()
        return resp.json()
    with _req.urlopen(url, timeout=120) as r:
        return json.loads(r.read())


def extract_verse_text(content_items: list) -> str:
    """Flatten verse content array to plain text, skipping footnote refs."""
    parts = []
    for item in content_items:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            if "text" in item:
                parts.append(item["text"])
            # skip: {"noteId": N}, {"lineBreak": true}, etc.
    return " ".join(parts).strip()


def download_translation(
    translation_id: str, translation_name: str, force: bool = False
) -> int:
    """Download one translation to txt. Returns number of verses written (0 = skipped)."""
    out_path = OUTPUT_DIR / f"{translation_id}.txt"

    if out_path.exists() and not force:
        print(
            f"  [{translation_id}] Already exists — skipping. (use --force to re-download)"
        )
        return 0

    print(
        f"  [{translation_id}] Downloading {translation_name} ...", end="", flush=True
    )

    data = _get_json(f"{BASE_URL}/{translation_id}/complete.json")

    lines = []
    verse_count = 0

    for book in data["books"]:
        book_name = book["name"]
        for chapter_wrapper in book["chapters"]:
            chapter_obj = chapter_wrapper["chapter"]
            chapter_num = chapter_obj["number"]
            for item in chapter_obj["content"]:
                if item.get("type") != "verse":
                    continue
                verse_num = item["number"]
                text = extract_verse_text(item["content"])
                if text:
                    lines.append(f"{book_name} {chapter_num}:{verse_num}  {text}")
                    verse_count += 1

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f" {verse_count:,} verses saved → {out_path.name}")
    return verse_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Download Bible translations from bible.helloao.org"
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="ID",
        help="Download only these translation IDs (e.g. BSB eng_kjv)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the file already exists",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching translation list...")
    all_translations = _get_json(f"{BASE_URL}/available_translations.json")[
        "translations"
    ]

    # Filter: English + exactly 66 books
    targets = [
        t
        for t in all_translations
        if t["language"] == "eng" and t["numberOfBooks"] == 66
    ]
    print(f"Found {len(targets)} 66-book English translations.")

    if args.only:
        requested = set(args.only)
        targets = [t for t in targets if t["id"] in requested]
        missing = requested - {t["id"] for t in targets}
        if missing:
            print(
                f"WARNING: these IDs were not found (or don't have 66 books): {missing}",
                file=sys.stderr,
            )
        print(
            f"Filtered to {len(targets)} translation(s): {[t['id'] for t in targets]}"
        )

    print()
    total_verses = 0
    errors = []

    for i, t in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}]", end=" ")
        try:
            n = download_translation(t["id"], t["englishName"], force=args.force)
            total_verses += n
        except Exception as exc:
            print(f"  ERROR: {exc}")
            errors.append((t["id"], str(exc)))

        if i < len(targets):
            time.sleep(DELAY_SECONDS)

    print(f"\n{'='*50}")
    print(
        f"Done. {len(targets) - len(errors)} translations downloaded, {total_verses:,} verses total."
    )
    print(f"Files saved to: {OUTPUT_DIR}")
    if errors:
        print(f"\nFailed ({len(errors)}):")
        for tid, err in errors:
            print(f"  {tid}: {err}")
    print(
        "\nNext step: restart the backend — the default translation index will build on first startup."
    )


if __name__ == "__main__":
    main()
