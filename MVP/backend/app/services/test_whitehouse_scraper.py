#!/usr/bin/env python3
"""
Self-check test for whitehouse_scraper.

Verifies: Running poll_whitehouse_once() twice yields "new post" then "None".

Uses mocked HTTP responses to avoid actual network calls.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.app.db import run_migrations, get_latest_whitehouse_post
from backend.app.services.whitehouse_scraper import (
    poll_whitehouse_once,
    WhiteHousePost,
    _extract_latest_listing_link,
    _extract_article_content,
)


# Mock HTML responses
MOCK_LISTING_HTML = """
<!DOCTYPE html>
<html>
<head><title>Briefings & Statements</title></head>
<body>
<main>
    <a href="/briefings-statements/2026/01/test-executive-order-on-ai/">
        Test Executive Order on AI Regulation
    </a>
    <a href="/briefings-statements/2026/01/old-post/">Old Post Title</a>
</main>
</body>
</html>
"""

MOCK_ARTICLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Executive Order on AI Regulation</title></head>
<body>
<main>
    <h1>Test Executive Order on AI Regulation</h1>
    <p>The President today signed an executive order establishing new guidelines for artificial intelligence development.</p>
    <p>This order will require all federal agencies to review their AI usage policies within 90 days.</p>
    <p>Industry leaders have expressed mixed reactions to the new requirements.</p>
</main>
</body>
</html>
"""


def mock_fetch_html(url: str) -> str:
    """Mock HTTP fetch - returns appropriate HTML based on URL."""
    if "briefings-statements/2026/01/test-executive-order" in url:
        return MOCK_ARTICLE_HTML
    return MOCK_LISTING_HTML


def test_scraper_new_then_none():
    """
    Test that:
    1. First call returns a new WhiteHousePost
    2. Second call returns None (already seen)
    """
    # Use a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        test_db_path = tmp.name

    print(f"🧪 Testing whitehouse_scraper with temp DB: {test_db_path}\n")

    try:
        # Initialize the database
        print("1️⃣  Initializing database...")
        run_migrations(test_db_path)
        print("   ✅ Database initialized\n")

        # Patch the _fetch_html function to use our mock
        with patch(
            "backend.app.services.whitehouse_scraper._fetch_html",
            side_effect=mock_fetch_html
        ):
            # First poll - should return new post
            print("2️⃣  First poll_whitehouse_once() call...")
            result1 = poll_whitehouse_once(db_path=test_db_path)

            assert result1 is not None, "First call should return a WhiteHousePost"
            assert isinstance(result1, WhiteHousePost), "Result should be WhiteHousePost dataclass"
            assert "test-executive-order" in result1.url, f"URL mismatch: {result1.url}"
            assert result1.title == "Test Executive Order on AI Regulation"
            assert "artificial intelligence" in result1.content
            assert result1.scraped_at_utc > 0

            print(f"   ✅ Got new post:")
            print(f"      - url: {result1.url}")
            print(f"      - title: {result1.title}")
            print(f"      - content preview: {result1.content[:60]}...")
            print(f"      - scraped_at_utc: {result1.scraped_at_utc}\n")

            # Verify it was stored in DB
            print("3️⃣  Verifying post was stored in DB...")
            stored = get_latest_whitehouse_post(db_path=test_db_path)
            assert stored is not None, "Post should be in database"
            assert stored["url"] == result1.url, "Stored URL should match"
            print(f"   ✅ Post found in DB with id: {stored['id']}\n")

            # Second poll - should return None (already seen)
            print("4️⃣  Second poll_whitehouse_once() call...")
            result2 = poll_whitehouse_once(db_path=test_db_path)

            assert result2 is None, "Second call should return None (post already seen)"
            print("   ✅ Correctly returned None (no new post)\n")

        print("=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSelf-check verified:")
        print("  ✓ First poll_whitehouse_once() → WhiteHousePost (new)")
        print("  ✓ Second poll_whitehouse_once() → None (already seen)")

    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            print(f"\n🧹 Cleaned up: {test_db_path}")


def test_html_parsing():
    """Test the internal HTML parsing functions."""
    print("\n" + "=" * 60)
    print("Testing HTML parsing functions...")
    print("=" * 60 + "\n")

    # Test listing extraction
    print("1️⃣  Testing _extract_latest_listing_link...")
    result = _extract_latest_listing_link(MOCK_LISTING_HTML)
    assert result is not None, "Should extract a link"
    url, title = result
    assert "test-executive-order" in url
    assert "AI" in title
    print(f"   ✅ Extracted: {title} -> {url}\n")

    # Test content extraction
    print("2️⃣  Testing _extract_article_content...")
    content = _extract_article_content(MOCK_ARTICLE_HTML)
    assert "executive order" in content.lower()
    assert "artificial intelligence" in content.lower()
    print(f"   ✅ Extracted {len(content)} chars of content")
    print(f"      Preview: {content[:80]}...\n")

    print("✅ HTML parsing tests passed!\n")


if __name__ == "__main__":
    test_html_parsing()
    test_scraper_new_then_none()

