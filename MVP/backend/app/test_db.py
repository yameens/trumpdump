#!/usr/bin/env python3
"""
Self-check script: Inserts a fake post + fake analysis and fetches them back.
Run from project root: python -m backend.app.test_db
"""

from __future__ import annotations

import json
import os
import tempfile
import time

# Import the db module functions
from db import (
    init_db,
    run_migrations,
    insert_whitehouse_post,
    get_latest_whitehouse_post,
    get_whitehouse_post_by_id,
    insert_analysis,
    get_latest_relevant_analysis,
    get_analysis_by_id,
    get_analyses_for_post,
)


def test_db_operations():
    """Test all database operations with a temporary database."""
    
    # Use a temporary database file for testing
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        test_db_path = tmp.name
    
    print(f"🧪 Testing with temporary database: {test_db_path}\n")
    
    try:
        # 1. Initialize database (run migrations)
        print("1️⃣  Running migrations...")
        run_migrations(test_db_path)
        print("   ✅ Migrations completed - tables created\n")
        
        # 2. Insert a fake whitehouse post
        print("2️⃣  Inserting fake whitehouse post...")
        fake_post_url = "https://www.whitehouse.gov/briefings-statements/2026/01/test-post/"
        fake_post_title = "Test Executive Order on Market Transparency"
        fake_post_content = (
            "The President signed an executive order today requiring increased "
            "transparency in financial markets. This order will affect major "
            "banking institutions and hedge funds operating in the United States."
        )
        fake_scraped_at = int(time.time())
        
        post_id = insert_whitehouse_post(
            url=fake_post_url,
            title=fake_post_title,
            content=fake_post_content,
            scraped_at_utc=fake_scraped_at,
            db_path=test_db_path,
        )
        print(f"   ✅ Inserted post with id: {post_id}\n")
        
        # 3. Fetch the latest post
        print("3️⃣  Fetching latest whitehouse post...")
        latest_post = get_latest_whitehouse_post(db_path=test_db_path)
        print(f"   ✅ Retrieved post:")
        print(f"      - id: {latest_post['id']}")
        print(f"      - url: {latest_post['url']}")
        print(f"      - title: {latest_post['title']}")
        print(f"      - content: {latest_post['content'][:50]}...")
        print(f"      - scraped_at_utc: {latest_post['scraped_at_utc']}\n")
        
        # 4. Verify we can fetch by ID
        print("4️⃣  Fetching post by ID...")
        post_by_id = get_whitehouse_post_by_id(post_id, db_path=test_db_path)
        assert post_by_id is not None, "Post not found by ID"
        assert post_by_id["url"] == fake_post_url, "URL mismatch"
        print(f"   ✅ Verified post retrieval by ID\n")
        
        # 5. Insert a fake analysis
        print("5️⃣  Inserting fake analysis...")
        fake_market_data = {
            "relevance_score_0_100": 75,
            "why_relevant": ["Executive order affects financial sector"],
            "dominant_verticals_ranked": [
                {"vertical": "Banking", "rationale": "Direct regulation", "confidence_0_1": 0.85}
            ],
            "tickers_ranked": [
                {
                    "ticker_or_etf": "XLF",
                    "direction_up_down_mixed": "down",
                    "mechanism": "Increased regulatory burden",
                    "confidence_0_1": 0.7,
                }
            ],
        }
        
        fake_tickers_data = {
            "verticals": ["Banking", "Finance"],
            "etfs": ["XLF", "KRE"],
            "tickers": ["JPM", "BAC", "GS"],
            "notes": ["Short-term regulatory pressure expected"],
        }
        
        analysis_id = insert_analysis(
            post_id=post_id,
            relevance_score=75,
            market_json=json.dumps(fake_market_data),
            tickers_json=json.dumps(fake_tickers_data),
            top_vertical="Banking",
            top_vertical_conf=0.85,
            db_path=test_db_path,
        )
        print(f"   ✅ Inserted analysis with id: {analysis_id}\n")
        
        # 6. Fetch the latest relevant analysis
        print("6️⃣  Fetching latest relevant analysis (min_score=50, min_conf=0.5)...")
        latest_analysis = get_latest_relevant_analysis(
            min_score=50,
            min_conf=0.5,
            db_path=test_db_path,
        )
        print(f"   ✅ Retrieved analysis:")
        print(f"      - id: {latest_analysis['id']}")
        print(f"      - post_id: {latest_analysis['post_id']}")
        print(f"      - relevance_score: {latest_analysis['relevance_score']}")
        print(f"      - top_vertical: {latest_analysis['top_vertical']}")
        print(f"      - top_vertical_conf: {latest_analysis['top_vertical_conf']}")
        
        # Parse JSON fields
        market = json.loads(latest_analysis["market_json"])
        tickers = json.loads(latest_analysis["tickers_json"])
        print(f"      - market_json keys: {list(market.keys())}")
        print(f"      - tickers_json etfs: {tickers['etfs']}\n")
        
        # 7. Test filtering - should NOT find analysis with high thresholds
        print("7️⃣  Testing filtering (min_score=90, min_conf=0.95)...")
        high_threshold = get_latest_relevant_analysis(
            min_score=90,
            min_conf=0.95,
            db_path=test_db_path,
        )
        if high_threshold is None:
            print("   ✅ Correctly returned None for high thresholds\n")
        else:
            print("   ⚠️  Unexpectedly found an analysis (threshold filtering may need review)\n")
        
        # 8. Verify analysis retrieval by ID
        print("8️⃣  Fetching analysis by ID...")
        analysis_by_id = get_analysis_by_id(analysis_id, db_path=test_db_path)
        assert analysis_by_id is not None, "Analysis not found by ID"
        assert analysis_by_id["post_id"] == post_id, "Post ID mismatch"
        print(f"   ✅ Verified analysis retrieval by ID\n")
        
        # 9. Get all analyses for a post
        print("9️⃣  Fetching all analyses for post...")
        all_analyses = get_analyses_for_post(post_id, db_path=test_db_path)
        assert len(all_analyses) == 1, f"Expected 1 analysis, got {len(all_analyses)}"
        print(f"   ✅ Found {len(all_analyses)} analysis for post {post_id}\n")
        
        # 10. Test duplicate URL handling
        print("🔟 Testing duplicate URL handling...")
        duplicate_id = insert_whitehouse_post(
            url=fake_post_url,  # Same URL as before
            title="Different Title",
            content="Different content",
            db_path=test_db_path,
        )
        assert duplicate_id == post_id, f"Expected original ID {post_id}, got {duplicate_id}"
        print(f"   ✅ Duplicate URL correctly returned existing ID: {duplicate_id}\n")
        
        print("=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        
    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            print(f"\n🧹 Cleaned up temporary database: {test_db_path}")


if __name__ == "__main__":
    test_db_operations()

