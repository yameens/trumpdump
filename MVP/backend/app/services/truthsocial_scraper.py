"""
Truth Social scraper service.

Scrapes Trump's Truth Social posts via trumpstruth.org aggregator.
Uses the centralized DB layer for storage - no direct DB logic here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Import DB helpers from the centralized db module (relative import)
from ..db import (
    get_truthsocial_post_by_url,
    insert_truthsocial_post,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LISTING_URL = "https://trumpstruth.org/"
USER_AGENT = "TrumpDumpBot/0.1 (contact: you@example.com)"

# Configure logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TruthSocialPost:
    """Represents a scraped Truth Social post."""
    url: str
    content: str
    is_retruth: bool
    scraped_at_utc: int
    title: Optional[str] = None  # Truth Social posts don't have titles, but we keep for consistency


# ---------------------------------------------------------------------------
# Internal scraping functions (pure scraping, no DB)
# ---------------------------------------------------------------------------

def _fetch_html(url: str) -> str:
    """Fetch HTML content from a URL."""
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def _extract_latest_status(html: str) -> Optional[Tuple[str, str, bool]]:
    """
    Parse the listing page HTML and extract the latest status URL.
    
    Returns (full_url, source, is_retruth) tuple or None if not found.
    """
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("main") or soup

    status = root.find("div", class_="status")
    if not status:
        logger.debug("No status div found in HTML")
        return None

    raw_url = status.get("data-status-url")
    if not raw_url:
        logger.debug("No data-status-url attribute found")
        return None

    full_url = urljoin(LISTING_URL, raw_url)

    # Check if this is a retruth (repost)
    prev_tag = status.find_previous_sibling(lambda t: getattr(t, "name", None) is not None)

    is_retruth = False
    if prev_tag:
        prev_classes = prev_tag.get("class") or []
        if "status__reblog-indicator" in prev_classes:
            is_retruth = True
        elif prev_tag.find(class_="status__reblog-indicator"):
            is_retruth = True

    return (full_url, "trumpstruth.org", is_retruth)


def _get_status_content(url: str) -> str:
    """
    Fetch and extract the text content from a status page.
    """
    html = _fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("main") or soup

    parts = []
    for p in root.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt:
            parts.append(txt)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def poll_truthsocial_once(db_path: Optional[str] = None) -> Optional[TruthSocialPost]:
    """
    Poll Trump's Truth Social for a new post.
    
    Returns:
        TruthSocialPost if a new post is found and stored.
        None if no new post (already seen or couldn't find any).
    
    The post is automatically stored in the posts table
    via the db helpers.
    """
    # Step 1: Fetch the listing page
    try:
        listing_html = _fetch_html(LISTING_URL)
    except requests.RequestException as e:
        logger.error(f"Error fetching Truth Social listing page: {e}")
        return None

    # Step 2: Extract the latest status
    latest = _extract_latest_status(listing_html)
    if latest is None:
        logger.debug("Could not find a latest Truth Social post.")
        return None

    url, source, is_retruth = latest

    # Step 3: Check if we've already seen this post (using DB helpers)
    existing = get_truthsocial_post_by_url(url, db_path=db_path)
    if existing is not None:
        logger.debug("No new Truth Social post.")
        return None

    # Step 4: Fetch and extract the status content
    try:
        content = _get_status_content(url)
    except requests.RequestException as e:
        logger.error(f"Error fetching Truth Social status content: {e}")
        return None

    scraped_at_utc = int(time.time())

    # Step 5: Store in DB using the centralized db helpers
    insert_truthsocial_post(
        url=url,
        content=content,
        is_retruth=is_retruth,
        title=None,  # Truth Social posts don't have titles
        scraped_at_utc=scraped_at_utc,
        db_path=db_path,
    )

    logger.info(f"NEW Truth Social post saved: {url}")
    logger.info(f"  Is ReTruth: {is_retruth}")
    logger.info(f"  Content preview: {content[:100]}..." if len(content) > 100 else f"  Content: {content}")

    # Step 6: Return the dataclass
    return TruthSocialPost(
        url=url,
        content=content,
        is_retruth=is_retruth,
        scraped_at_utc=scraped_at_utc,
        title=None,
    )


def scrape_truthsocial_post(url: str) -> Optional[TruthSocialPost]:
    """
    Scrape a specific Truth Social post by URL.
    Does NOT check or store in DB - pure scraping only.
    
    Useful for re-scraping or testing.
    """
    try:
        content = _get_status_content(url)
    except requests.RequestException as e:
        logger.error(f"Error fetching Truth Social post: {e}")
        return None

    return TruthSocialPost(
        url=url,
        content=content,
        is_retruth=False,  # Can't determine from direct URL
        scraped_at_utc=int(time.time()),
        title=None,
    )


# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick test - run poll_truthsocial_once
    import sys
    sys.path.insert(0, str(__file__.parent.parent.parent))
    
    from backend.app.db import init_db
    
    logging.basicConfig(level=logging.INFO)
    
    init_db()
    result = poll_truthsocial_once()
    
    if result:
        print("\n--- Result ---")
        print(f"URL: {result.url}")
        print(f"Is ReTruth: {result.is_retruth}")
        print(f"Content: {result.content[:200]}..." if len(result.content) > 200 else f"Content: {result.content}")
        print(f"Scraped at: {result.scraped_at_utc}")
    else:
        print("\nNo new Truth Social post found.")

