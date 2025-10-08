#!/usr/bin/env python3
"""
Clean noisy Google Docs HTML exports.

- Strips inline styles and gdoc classes/spans
- Normalizes <b>/<i> to <strong>/<em>
- Drops empty elements and comments
- Preserves a small attribute whitelist (href, src, alt, title, id (anchors))

Usage:
  python clean_gdoc_html.py in.html -o out.html
  python clean_gdoc_html.py in.html --to markdown -o out.md
"""
import argparse, re, sys
from bs4 import BeautifulSoup, Comment

# Tags we allow to remain (others are unwrapped, not removed, to preserve text)
ALLOWED_TAGS = {
    "html","head","meta","title","body",
    "article","section","nav","aside","header","footer","main",
    "p","br","hr",
    "h1","h2","h3","h4","h5","h6",
    "ul","ol","li",
    "strong","em","blockquote","code","pre","kbd","samp","sub","sup","mark","del","ins",
    "a","img","figure","figcaption","table","thead","tbody","tfoot","tr","th","td"
}

# Attributes we keep by tag
ATTR_WHITELIST = {
    "*": {"id","title"},
    "a": {"href","title"},
    "img": {"src","alt","title","width","height","loading"},
    "th": {"colspan","rowspan","scope"},
    "td": {"colspan","rowspan"}
}

# Heuristics for "Google-y" classes/ids/styles
GOOGLEY_CLASS_RE = re.compile(r"(^| )(c\d+|s\d+|doc-|kix-|-gdoc|-google-)", re.I)
GOOGLEY_ID_RE    = re.compile(r"^docs-internal-.*", re.I)

def is_googley_class(cls: str) -> bool:
    return bool(GOOGLEY_CLASS_RE.search(cls)) if cls else False

def clean_attributes(tag):
    # Remove style & data-* always
    if tag.has_attr("style"):
        del tag["style"]
    for attr in list(tag.attrs):
        if attr.startswith("data-") or attr.startswith("aria-"):
            del tag[attr]

    # Drop gdocy classes/ids
    if tag.has_attr("class"):
        classes = [c for c in tag.get("class", []) if not is_googley_class(c)]
        if classes:
            tag["class"] = classes
        else:
            del tag["class"]
    if tag.has_attr("id") and GOOGLEY_ID_RE.match(tag["id"]):
        del tag["id"]

    # Enforce attribute whitelist
    allowed = ATTR_WHITELIST.get(tag.name, set()) | ATTR_WHITELIST.get("*", set())
    for attr in list(tag.attrs):
        if attr not in allowed:
            del tag[attr]

def normalize_inline_tags(soup):
    # <b>/<i>/<u> → semantic
    for b in soup.find_all("b"):
        b.name = "strong"
    for i in soup.find_all("i"):
        i.name = "em"
    # <u> has no semantic meaning; unwrap
    for u in soup.find_all("u"):
        u.unwrap()

def unwrap_noise(soup):
    # Remove comments
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()

    # Unwrap spans & fonts (Google loves them)
    for span in soup.find_all(["span","font"]):
        span.unwrap()

    # Unwrap divs that only contain phrasing content
    for div in soup.find_all("div"):
        # If a div contains block content, keep it; else convert to <p>
        if all(child.name in (None, "br", "strong", "em", "code", "a", "img", "mark", "sub", "sup") 
               for child in div.children if hasattr(child, "name")):
            # If it has only text-ish content, make it a paragraph
            div.name = "p"

def drop_empty_blocks(soup):
    def is_empty(tag):
        text = (tag.get_text(strip=True) or "")
        # consider <img> or <br> as content
        has_media_or_break = tag.find(["img","br"]) is not None
        return (text == "") and (not has_media_or_break)

    # Remove empty <p>, <li>, <div> (if any remain), <section>, etc.
    for tname in ["p","li","div","section","article","aside","header","footer","figure","figcaption"]:
        for t in list(soup.find_all(tname)):
            if is_empty(t):
                t.decompose()

def collapse_breaks(soup):
    # Replace <p><br></p> with nothing, collapse multiple <br>
    for p in soup.find_all("p"):
        # strip pure &nbsp; paragraphs to empty
        if p.get_text().replace("\xa0","").strip() == "" and not p.find("img"):
            p.decompose()
            continue

    # Collapse runs of <br>
    for br in soup.find_all("br"):
        nxt = br.find_next_sibling()
        if nxt and nxt.name == "br":
            # remove consecutive duplicates, keep one
            while nxt and nxt.name == "br":
                keep = nxt
                nxt = nxt.find_next_sibling()
                keep.decompose()

def sanitize(soup):
    # Remove unwanted tags (unwrap rather than delete text)
    for tag in list(soup.find_all(True)):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
            continue
        clean_attributes(tag)

def to_markdown_if_requested(html: str, to: str) -> str:
    if to.lower() not in ("md","markdown"):
        return html
    # Very small dependency-less HTML→MD pass (lightweight).
    # For best results, use `pandoc` instead.
    try:
        # Fallback: use html2text if available
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.body_width = 0
        return h.handle(html)
    except Exception:
        # If html2text is not available, just return the HTML with a note
        return html

def clean_html_string(html: str, to: str = "html") -> str:
    soup = BeautifulSoup(html, "lxml")  # lxml is robust with messy HTML

    # Work on <body> if present, else whole doc
    root = soup.body or soup

    normalize_inline_tags(root)
    unwrap_noise(root)
    sanitize(root)
    drop_empty_blocks(root)
    collapse_breaks(root)

    # Normalize whitespace in text nodes: replace non-breaking with normal spaces
    for text in root.find_all(string=True):
        text.replace_with(text.replace("\xa0", " "))

    output = str(soup if soup.body else root)
    return to_markdown_if_requested(output, to)

def main():
    ap = argparse.ArgumentParser(description="Clean Google Docs HTML.")
    ap.add_argument("input", help="Input HTML file")
    ap.add_argument("-o","--output", help="Output file (default: stdout)")
    ap.add_argument("--to", choices=["html","markdown","md"], default="html", help="Output format")
    args = ap.parse_args()

    data = open(args.input, "r", encoding="utf-8", errors="ignore").read()
    cleaned = clean_html_string(data, to=args.to)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(cleaned)
    else:
        sys.stdout.write(cleaned)

if __name__ == "__main__":
    main()
