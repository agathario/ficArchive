"""
assets/pdf_original_convert.py
==============================
Convert a PDF of a fic that was never posted on AO3 (Google Docs, Ellipsus,
etc.) into the AO3 download layout, so phase4_process.py can handle it.
There's no metadata page in these PDFs, so title/author/rating/status are
passed in; summary and tags can be added later via the override CSVs.

Needs pdfplumber (pip install pdfplumber).

    python assets/pdf_original_convert.py staging/z2_my_condolences.pdf \\
        --title "My Condolences" --author LovettBlack --rating Explicit --wip

Writes staging/<same name>.html. Chapter headings are found as centered
lines starting with Chapter/Prologue/Epilogue (with an optional title on
the next centered line); emoji/symbol-only lines become centered dividers.
Use --order 1,2,3,5,4,6 to reorder chapters by their position in the PDF.
"""

import argparse
import html
import re
import sys
from datetime import date
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).parent))
import pdf_convert as pc

HEADING = re.compile(r"^(prologue|epilogue|chapter\s*\d+)\b\s*[:—–-]?\s*(.*)$", re.I)


def has_letters(t):
    return re.search(r"[A-Za-z]{2}", t) is not None


def chapters_from(paras):
    chapters, expect_title, skip_divider = [], False, False
    for p in paras:
        t = p["text"].replace("(cid:0)", "").strip()
        h = p["html"].replace("(cid:0)", "").strip()
        if not t:
            continue
        m = HEADING.match(t)
        if m and (p["centered"] or p["heading"]) and len(t) < 90:
            label = m.group(1).strip()
            num = re.search(r"\d+", label)
            label = f"Chapter {int(num.group())}" if num else label.title()
            chapters.append({"heading": label, "title": m.group(2).strip(), "body": []})
            expect_title, skip_divider = not m.group(2).strip(), True
            continue
        if chapters and expect_title and (p["centered"] or p["heading"]) and has_letters(t):
            chapters[-1]["title"] = t
            expect_title = False
            continue
        expect_title = False
        if not has_letters(t) and skip_divider:
            skip_divider = False      # decorative rule under the chapter heading
            continue
        skip_divider = False
        if not chapters:
            chapters.append({"heading": "", "title": "", "body": []})
        center = p["centered"] or not has_letters(t)
        chapters[-1]["body"].append(('<p class="center">' if center else "<p>") + h + "</p>")
    for c in chapters:
        c["full"] = f'{c["heading"]}: {c["title"]}' if c["heading"] and c["title"] else c["heading"] or c["title"]
    return chapters


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--rating", default="Explicit")
    ap.add_argument("--ship", default="Agatha Harkness/Rio Vidal")
    ap.add_argument("--fandom", default="Agatha All Along (TV)")
    ap.add_argument("--characters", default="Agatha Harkness, Rio Vidal")
    ap.add_argument("--wip", action="store_true", help="mark as in progress (Chapters: N/?)")
    ap.add_argument("--date", default=date.today().isoformat(), help="published/updated date (YYYY-MM-DD)")
    ap.add_argument("--order", help="comma-separated chapter positions, e.g. 1,2,3,5,4,6")
    ap.add_argument("--out", help="output path (default: same name, .html)")
    a = ap.parse_args()

    src = Path(a.pdf).expanduser()
    with pdfplumber.open(src) as pdf:
        lines = pc.read_lines(pdf)
    chapters = chapters_from(pc.paragraphs(lines, *pc.layout_stats(lines)))
    if a.order:
        chapters = [chapters[int(i) - 1] for i in a.order.split(",")]

    words = sum(len(re.sub(r"<[^>]+>", " ", b).split()) for c in chapters for b in c["body"])
    n = len(chapters)
    e = html.escape
    chs = "".join(
        (f'<div class="meta group">\n<h2 class="heading">{e(c["full"])}</h2>\n</div>\n' if c["full"] else "")
        + '<div class="userstuff">\n' + "\n".join(c["body"]) + "\n</div>\n"
        for c in chapters
    )
    status_line = f"Updated: {a.date}" if a.wip else f"Completed: {a.date}"
    doc = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
<meta charset="utf-8" />
<title>{e(a.title)} - {e(a.author)} - {e(a.fandom)}</title>
</head>
<body>

<div id="preface">
<h2 class="toc-heading">Preface</h2>
<p class="message">
<b>{e(a.title)}</b><br />
Not posted on the Archive of Our Own.
</p>
<div class="meta">
<dl class="tags">
<dt>Rating:</dt>
<dd>{e(a.rating)}</dd>
<dt>Fandoms:</dt>
<dd>{e(a.fandom)}</dd>
<dt>Relationships:</dt>
<dd>{e(a.ship)}</dd>
<dt>Characters:</dt>
<dd>{e(a.characters)}</dd>
<dt>Language:</dt>
<dd>English</dd>
<dt>Stats:</dt>
<dd>
Published: {a.date}
{status_line}
Words: {words:,}
Chapters: {n}/{"?" if a.wip else n}
</dd>
</dl>
<h1>{e(a.title)}</h1>
<div class="byline">by <a rel="author" href="#">{e(a.author)}</a></div>
</div>
</div>

<div id="chapters" class="userstuff">
{chs}</div>

<div id="afterword">
<h2 class="toc-heading">Afterword</h2>
<p class="message">Converted from PDF (never posted on AO3) by pdf_original_convert.py.</p>
</div>

</body>
</html>
"""
    out = Path(a.out) if a.out else src.with_suffix(".html")
    out.write_text(doc, encoding="utf-8")
    print(f"{out}  ({n} chapters, {words:,} words)")
    for i, c in enumerate(chapters, 1):
        print(f"  {i}. {c['full'] or '(no heading)'}  — {len(c['body'])} paragraphs")


if __name__ == "__main__":
    main()
