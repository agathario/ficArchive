#!/usr/bin/env python3
"""Rename fic HTML files to {workId}_{title}.html format."""

from __future__ import annotations

import os
import re

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
TITLE_MAX_CHARS = 50


def slugify(title: str, max_chars: int) -> str:
    """Convert title to lowercase_underscore slug, truncated at word boundary."""
    # Lowercase, strip parens/brackets and their contents for brevity
    slug = title.lower()
    # Remove special chars except spaces and alphanumerics
    slug = re.sub(r"[^\w\s]", "", slug)
    # Replace whitespace runs with single underscore
    slug = re.sub(r"\s+", "_", slug).strip("_")

    if len(slug) <= max_chars:
        return slug

    # Truncate at word boundary (underscore)
    truncated = slug[:max_chars]
    last_underscore = truncated.rfind("_")
    if last_underscore > 0:
        truncated = truncated[:last_underscore]
    return truncated


def extract_ao3_id(content: str) -> str | None:
    match = re.search(r'archiveofourown\.org/works/(\d+)', content)
    return match.group(1) if match else None


def extract_title(content: str) -> str | None:
    match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
    return match.group(1).strip() if match else None


def main():
    html_files = sorted(
        f for f in os.listdir(ARCHIVE_DIR)
        if f.endswith(".html") and f != "index.html"
    )

    renamed = []
    skipped_no_ao3 = []
    skipped_conflict = []
    errors = []

    # Pre-collect target names to detect conflicts
    planned: dict[str, str] = {}  # new_name -> old_name

    for filename in html_files:
        filepath = os.path.join(ARCHIVE_DIR, filename)
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            errors.append((filename, str(e)))
            continue

        ao3_id = extract_ao3_id(content)
        title = extract_title(content)

        if not ao3_id:
            skipped_no_ao3.append((filename, title or "(no title found)"))
            continue

        if not title:
            errors.append((filename, "has AO3 ID but no <title> tag"))
            continue

        slug = slugify(title, TITLE_MAX_CHARS)
        new_name = f"{ao3_id}_{slug}.html"

        if new_name in planned:
            skipped_conflict.append((filename, new_name, planned[new_name]))
            continue

        planned[new_name] = filename

    # Execute renames
    for new_name, old_name in planned.items():
        old_path = os.path.join(ARCHIVE_DIR, old_name)
        new_path = os.path.join(ARCHIVE_DIR, new_name)
        if old_name == new_name:
            renamed.append((old_name, new_name, "already correct"))
            continue
        os.rename(old_path, new_path)
        renamed.append((old_name, new_name, "renamed"))

    # ── Report ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"RENAME COMPLETE  ({len(renamed)} files processed)")
    print("=" * 70)

    actual_renames = [(o, n) for o, n, status in renamed if status == "renamed"]
    already_ok = [(o, n) for o, n, status in renamed if status == "already correct"]

    if actual_renames:
        print(f"\n✓ RENAMED ({len(actual_renames)}):")
        for old, new in actual_renames:
            print(f"  {old}")
            print(f"    → {new}")

    if already_ok:
        print(f"\n~ ALREADY CORRECT ({len(already_ok)}):")
        for old, _ in already_ok:
            print(f"  {old}")

    if skipped_no_ao3:
        print(f"\n⚠ SKIPPED — no AO3 work ID ({len(skipped_no_ao3)}):")
        for filename, title in skipped_no_ao3:
            print(f"  {filename}  (title: {title})")

    if skipped_conflict:
        print(f"\n⚠ SKIPPED — name conflict ({len(skipped_conflict)}):")
        for filename, new_name, existing in skipped_conflict:
            print(f"  {filename}  →  {new_name}  (conflicts with {existing})")

    if errors:
        print(f"\n✗ ERRORS ({len(errors)}):")
        for filename, msg in errors:
            print(f"  {filename}: {msg}")

    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
