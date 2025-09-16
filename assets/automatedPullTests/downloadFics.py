import os
import re
import sys
import time
import html
import getpass
import pathlib
import urllib.parse
from typing import Iterable, Tuple, Optional

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE = "https://archiveofourown.org"

# -------- Helpers --------

def sanitize_filename(name: str, max_len: int = 140) -> str:
    # Remove/disarm pathy or odd chars; keep spaces, dashes, underscores, periods.
    name = html.unescape(name)
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name or "work"

def get_csrf_token(session: requests.Session, url: str) -> str:
    r = session.get(url, timeout=90)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    tok = soup.find("input", {"name": "authenticity_token"})
    if not tok or not tok.get("value"):
        raise RuntimeError("Could not find AO3 authenticity_token on login page.")
    return tok["value"]

def login(session: requests.Session, username: str, password: str) -> None:
    token = get_csrf_token(session, f"{BASE}/users/login")
    payload = {
        "authenticity_token": token,
        "user[login]": username,
        "user[password]": password,
        "commit": "Log in",
        "utf8": "✓",
        "remember_me": "1",
    }
    # Important: include headers with a friendly UA
    headers = {
        "Referer": f"{BASE}/users/login",
        "User-Agent": "AO3-Bookmarks-Downloader (respectful; 1 req/2s)",
    }
    resp = session.post(f"{BASE}/users/login", data=payload, headers=headers, timeout=90)
    resp.raise_for_status()

    # Check login by looking for "Log out" in the returned page or a session cookie
    if "Log out" not in resp.text and "_otwarchive_session" not in session.cookies.get_dict():
        # Sometimes the login POST redirects; follow with a GET to root to double-check
        home = session.get(BASE, headers=headers, timeout=90)
        if "Log out" not in home.text:
            raise RuntimeError("Login appears to have failed. Double-check username/password (and 2FA if applicable).")

    # Let AO3 know we can view adult content
    session.cookies.set("view_adult", "true", domain="archiveofourown.org")

def iter_bookmark_pages(session: requests.Session, username: str) -> Iterable[str]:
    """
    Yields HTML of each bookmarks page for the given user.
    """
    page = 1
    headers = {"User-Agent": "AO3-Bookmarks-Downloader (respectful; 1 req/2s)"}
    while True:
        url = f"{BASE}/users/{urllib.parse.quote(username)}/bookmarks?page={page}"
        r = session.get(url, headers=headers, timeout=90)
        if r.status_code == 404 and page == 1:
            raise RuntimeError("Bookmarks page not found. Is the username correct, and are bookmarks visible to your account?")
        r.raise_for_status()
        text = r.text
        yield text

        soup = BeautifulSoup(text, "html.parser")
        next_link = soup.select_one("ol.pagination a[rel='next'], .pagination a[rel='next']")
        if not next_link:
            break
        page += 1
        time.sleep(2)  # be nice

def parse_work_links_from_bookmarks(page_html: str) -> Iterable[Tuple[str, Optional[str]]]:
    """
    Parse AO3 bookmarks page HTML and yield tuples of (work_url, title).
    Filters only AO3 works (not external works/series pages).
    """
    soup = BeautifulSoup(page_html, "html.parser")
    # Each bookmark for a work typically has a heading with a link to /works/<id>
    # Works may appear in articles with class 'bookmark blurb group'
    for a in soup.select("li.bookmark a[href*='/works/'], article.bookmark a[href*='/works/']"):
        href = a.get("href") or ""
        # Only match /works/<id> (not /works/<id>/chapters/<id> or anchors)
        m = re.match(r"^/works/(\d+)(?:\b|$)", urllib.parse.urlparse(href).path)
        if not m:
            continue
        title = a.get_text(strip=True) or None
        # Normalize to absolute URL
        work_url = urllib.parse.urljoin(BASE, f"/works/{m.group(1)}?view_full_work=true")
        yield work_url, title

def find_html_download_link(session: requests.Session, work_url: str) -> Optional[str]:
    """
    Load a work page and return the absolute 'HTML' download link if present.
    Falls back to returning the work page itself if no HTML download is found.
    """
    headers = {"User-Agent": "AO3-Bookmarks-Downloader (respectful; 1 req/2s)", "Referer": BASE}
    r = session.get(work_url, headers=headers, timeout=90)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # The "Download" menu includes multiple formats; we want the 'HTML' link specifically.
    # Typically it's an <a> whose text contains 'HTML' under a .download or .actions menu.
    for a in soup.select("a"):
        text = a.get_text(strip=True).lower()
        if "html" == text or text == "download html" or ("html" in text and "download" in text):
            href = a.get("href") or ""
            if href:
                return urllib.parse.urljoin(work_url, href)

    # Fallback: some templates label via title attribute or data-download attribute
    for a in soup.select("a[title*='HTML' i], a[data-download*='html' i]"):
        href = a.get("href") or ""
        if href:
            return urllib.parse.urljoin(work_url, href)

    # As a last resort, just return the work page (entire work view) so we still save something.
    return work_url

def extract_work_metadata_from_page(html_text: str) -> Tuple[str, Optional[str]]:
    """
    Try to get a user-friendly title and work ID from a work page HTML.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    # Title: usually <h2 class="title heading"> or <h2 class="title">
    title_el = soup.select_one("h2.title, h2.title.heading")
    title = title_el.get_text(strip=True) if title_el else "work"

    # Work ID: in canonical URL or meta tags; fallback to numeric pattern in links
    work_id = None
    canon = soup.find("link", rel="canonical")
    if canon and canon.get("href"):
        m = re.search(r"/works/(\d+)", canon["href"])
        if m:
            work_id = m.group(1)
    if not work_id:
        m = re.search(r"/works/(\d+)", html_text)
        if m:
            work_id = m.group(1)
    return title, work_id

def polite_get(session: requests.Session, url: str, sleep: float = 2.0, **kw) -> requests.Response:
    headers = kw.pop("headers", {})
    hdrs = {"User-Agent": "AO3-Bookmarks-Downloader (respectful; 1 req/2s)", **headers}
    r = session.get(url, headers=hdrs, timeout=90, **kw)
    r.raise_for_status()
    time.sleep(sleep)
    return r

# -------- Main flow --------

def download_html(session: requests.Session, url: str, out_dir: pathlib.Path) -> Optional[pathlib.Path]:
    """
    Download a single work's HTML (via the explicit HTML download link if possible).
    Returns the saved Path or None if skipped/failed.
    """
    # Get the download link (or fall back to full-work page)
    download_url = find_html_download_link(session, url)

    # Fetch the content
    resp = polite_get(session, download_url)

    # If we fetched the work page (not a true HTML download), we still try to name it nicely.
    title, work_id = extract_work_metadata_from_page(resp.text)

    # Filename: "<id> - <title>.html" if ID known; otherwise just title
    prefix = f"{work_id} - " if work_id else ""
    filename = sanitize_filename(f"{prefix}{title}.html")

    out_path = out_dir / filename
    if out_path.exists():
        return None  # skip, already downloaded

    out_path.write_bytes(resp.content)
    return out_path

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Download all AO3 bookmarked works (HTML) for a user.")
    parser.add_argument("--username", "-u", default="willowphile", help="Your AO3 username (account name).")
    parser.add_argument("--password", "-p", default="willow410",help="AO3 password. If omitted, you will be prompted securely.")
    parser.add_argument("--out", "-o", default="C:/Users/willo/OneDrive/Documents/GitHub/fics/ficArchive/staging", help="Output directory")
    parser.add_argument("--min-sleep", type=float, default=2.0, help="Seconds to sleep between requests (default: 2.0). Please be polite.")
    parser.add_argument("--limit", type=int, default=0, help="Max works to download (0 = no limit).")
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    password = args.password or getpass.getpass("AO3 password: ")

    with requests.Session() as session:
        # Friendly UA everywhere
        session.headers.update({"User-Agent": "AO3-Bookmarks-Downloader (respectful; 1 req/2s)"})
        # Login
        print("Logging in to AO3…")
        login(session, args.username, password)

        # Iterate all bookmarks pages and collect unique work URLs
        print("Fetching bookmark pages…")
        seen = set()
        work_urls = []
        total_pages = 0
        for page_html in iter_bookmark_pages(session, args.username):
            total_pages += 1
            for work_url, _title in parse_work_links_from_bookmarks(page_html):
                if work_url not in seen:
                    seen.add(work_url)
                    work_urls.append(work_url)

        if not work_urls:
            print("No works found in bookmarks (or they may all be external/series).")
            return

        # Download with progress bar
        print(f"Found {len(work_urls)} bookmarked works. Downloading HTML…")
        count = 0
        errors = 0
        for work_url in tqdm(work_urls, unit="work"):
            try:
                saved = download_html(session, work_url, out_dir)
                # Respect the user's chosen rate limit in polite_get, but also pause between items
                time.sleep(max(0.0, args.min_sleep))
                if saved:
                    count += 1
            except requests.HTTPError as e:
                errors += 1
                tqdm.write(f"[HTTP error] {work_url} -> {e}")
            except Exception as e:
                errors += 1
                tqdm.write(f"[Error] {work_url} -> {e}")

            if args.limit and (count >= args.limit):
                break

        print(f"\nDone. Saved {count} file(s) to: {out_dir}")
        if errors:
            print(f"Encountered {errors} error(s); see log above.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)