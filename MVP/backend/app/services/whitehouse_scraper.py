"""
White House scraper service.

Scrapes the White House briefings & statements page for new posts.
Uses the centralized DB layer for storage - no direct DB logic here.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

# Import DB helpers from the centralized db module (relative import)
from ..db import (
    get_whitehouse_post_by_url,
    insert_whitehouse_post,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LISTING_URL = "https://www.whitehouse.gov/briefings-statements/"
USER_AGENT = "TrumpDumpBot/0.1 (contact: you@example.com)"

ARTICLE_URL_RE = re.compile(
    r"^/briefings-statements/\d{4}/\d{2}/[^\"'\s]+/?$"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WhiteHousePost:
    """Represents a scraped White House post."""
    url: str
    title: str
    content: str
    scraped_at_utc: int


# ---------------------------------------------------------------------------
# Internal scraping functions (pure scraping, no DB)
# ---------------------------------------------------------------------------

def _fetch_html(url: str) -> str:
    """Fetch HTML content from a URL."""
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def _extract_latest_listing_link(html: str) -> Optional[tuple[str, str]]:
    """
    Parse the listing page HTML and extract the latest article URL and title.
    Returns (url, title) tuple or None if not found.
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup

    for a in main.find_all("a", href=True):
        href = a["href"].strip()

        if href.startswith("https://www.whitehouse.gov"):
            href_for_match = href.replace("https://www.whitehouse.gov", "")
            full_url = href
        elif href.startswith("/"):
            href_for_match = href
            full_url = "https://www.whitehouse.gov" + href
        else:
            continue

        if ARTICLE_URL_RE.match(href_for_match):
            title = a.get_text(strip=True)
            if title:
                return (full_url, title)

    return None


def _extract_article_content(html: str) -> str:
    """Extract the main text content from an article page."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup

    paragraphs = []
    for p in main.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt:
            paragraphs.append(txt)

    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def poll_whitehouse_once(db_path: Optional[str] = None) -> Optional[WhiteHousePost]:
    """
    Poll the White House briefings page for a new post.
    
    Returns:
        WhiteHousePost if a new post is found and stored.
        None if no new post (already seen or couldn't find any).
    
    The post is automatically stored in the whitehouse_posts table
    via the db helpers.
    """
    # Step 1: Fetch the listing page
    try:
        listing_html = _fetch_html(LISTING_URL)
    except requests.RequestException as e:
        print(f"Error fetching listing page: {e}")
        return None

    # Step 2: Extract the latest article link
    latest = _extract_latest_listing_link(listing_html)
    if latest is None:
        print("Could not find a latest post link.")
        return None

    url, title = latest

    # Step 3: Check if we've already seen this post (using DB helpers)
    existing = get_whitehouse_post_by_url(url, db_path=db_path)
    if existing is not None:
        print("No new White House post.")
        return None

    # Step 4: Fetch and extract the article content
    try:
        article_html = _fetch_html(url)
    except requests.RequestException as e:
        print(f"Error fetching article: {e}")
        return None

    content = _extract_article_content(article_html)
    scraped_at_utc = int(time.time())

    # Step 5: Store in DB using the centralized db helpers
    insert_whitehouse_post(
        url=url,
        title=title,
        content=content,
        scraped_at_utc=scraped_at_utc,
        db_path=db_path,
    )

    print("NEW post saved:")
    print(f"  Title: {title}")
    print(f"  URL: {url}")

    # Step 6: Return the dataclass
    return WhiteHousePost(
        url=url,
        title=title,
        content=content,
        scraped_at_utc=scraped_at_utc,
    )


def scrape_whitehouse_post(url: str) -> Optional[WhiteHousePost]:
    """
    Scrape a specific White House post by URL.
    Does NOT check or store in DB - pure scraping only.
    
    Useful for re-scraping or testing.
    """
    try:
        article_html = _fetch_html(url)
    except requests.RequestException as e:
        print(f"Error fetching article: {e}")
        return None

    content = _extract_article_content(article_html)
    
    # Extract title from the page
    soup = BeautifulSoup(article_html, "html.parser")
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"

    return WhiteHousePost(
        url=url,
        title=title,
        content=content,
        scraped_at_utc=int(time.time()),
    )


# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick test - run poll_whitehouse_once
    from ..db import init_db
    
    init_db()
    result = poll_whitehouse_once()
    
    if result:
        print("\n--- Result ---")
        print(f"URL: {result.url}")
        print(f"Title: {result.title}")
        print(f"Content preview: {result.content[:200]}...")
        print(f"Scraped at: {result.scraped_at_utc}")
    else:
        print("\nNo new post found.")

