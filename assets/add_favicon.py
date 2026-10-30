"""
fic-archive/assets/add_favicon.py
=================================
One-time backfill: injects the favicon <link> tags (assets/favicon/) into the
<head> of every existing fic page, plus the root pages. New files get them
automatically from phase4_process.py.

Usage (from project root):
    python assets/add_favicon.py

Covers archive/, assets/hiddenFics/, and index.html / kudos.html / rank.html.
originals/ is skipped — those are untouched backups. Safe to re-run: files that
already have it are left alone.
"""

import re
from pathlib import Path

from phase4_process import BASE_DIR, favicon_links

MARKER = "assets/favicon/favicon.ico"
HEAD_CLOSE = re.compile(r"</head\s*>", re.IGNORECASE)


def target_files():
    for name in ("index.html", "kudos.html", "rank.html"):
        yield BASE_DIR / name, ""
    for path in sorted((BASE_DIR / "archive").glob("*.html")):
        yield path, "../"
    for path in sorted((BASE_DIR / "assets" / "hiddenFics").glob("*.html")):
        yield path, "../../"


def main():
    added = skipped = no_head = 0
    for path, prefix in target_files():
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        if MARKER in html:
            skipped += 1
            continue
        match = HEAD_CLOSE.search(html)
        if not match:
            print(f"  no </head>, skipped: {path.relative_to(BASE_DIR)}")
            no_head += 1
            continue
        html = html[:match.start()] + favicon_links(prefix) + "\n" + html[match.start():]
        path.write_text(html, encoding="utf-8")
        added += 1
    print(f"Favicon added: {added}  already present: {skipped}  no <head>: {no_head}")


if __name__ == "__main__":
    main()
