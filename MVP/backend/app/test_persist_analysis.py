#!/usr/bin/env python3
"""
Self-check test for persist_analysis and get_latest_relevant_analysis.

Verifies:
1. persist_analysis() correctly extracts and stores fields from market_json
2. get_latest_relevant_analysis() returns exactly the latest relevant one
3. Non-relevant analyses are stored but not returned by default query
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.db import (
    run_migrations,
    insert_whitehouse_post,
    persist_analysis,
    get_latest_relevant_analysis,
    get_latest_analysis,
    get_analysis_by_id,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_MIN_TOP_VERTICAL_CONF,
)


def create_mock_market_json(
    relevance_score: int = 75,
    top_vertical: str = "Banking",
    top_confidence: float = 0.85,
    tickers: list = None,
) -> dict:
    """Create a mock market_json that matches the schema."""
    if tickers is None:
        tickers = [
            {
                "ticker_or_etf": "XLF",
                "direction_up_down_mixed": "up",
                "mechanism": "Direct regulatory impact",
                "confidence_0_1": 0.7,
                "conservative_move": {"horizon": "2-5d", "expected_pct_range": "+0.5% to +1.5%"},
                "aggressive_move": {"horizon": "1-4w", "expected_pct_range": "+1.5% to +3.0%"},
                "what_would_change_your_mind": ["Policy reversal"],
            }
        ]
    
    return {
        "relevance_score_0_100": relevance_score,
        "why_relevant": ["Test reason"],
        "dominant_verticals_ranked": [
            {
                "vertical": top_vertical,
                "rationale": "Test rationale",
                "confidence_0_1": top_confidence,
            }
        ],
        "tickers_ranked": tickers,
        "base_case_summary": "Test base case",
        "conservative_case_summary": "Test conservative case",
        "aggressive_case_summary": "Test aggressive case",
        "facts_used": ["Fact 1", "Fact 2"],
        "verified_additions": [],
        "data_needed_next": ["More data"],
        "inferences": [{"inference": "Test inference", "confidence_0_1": 0.6}],
    }


def test_persist_and_retrieve():
    """Test the full persist_analysis pipeline."""
    
    # Use a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        test_db_path = tmp.name

    print(f"🧪 Testing persist_analysis pipeline")
    print(f"   DB: {test_db_path}")
    print(f"   Thresholds: score >= {DEFAULT_MIN_RELEVANCE_SCORE}, conf >= {DEFAULT_MIN_TOP_VERTICAL_CONF}\n")

    try:
        # Initialize database
        print("1️⃣  Initializing database...")
        run_migrations(test_db_path)
        print("   ✅ Database initialized\n")

        # Insert a test post
        print("2️⃣  Inserting test whitehouse post...")
        post_id = insert_whitehouse_post(
            url="https://www.whitehouse.gov/test/analysis-test/",
            title="Test Post for Analysis",
            content="Test content about market policy.",
            db_path=test_db_path,
        )
        print(f"   ✅ Post inserted with id: {post_id}\n")

        # -----------------------------------------------------------------------
        # Test 1: Insert a NON-RELEVANT analysis (low score)
        # -----------------------------------------------------------------------
        print("3️⃣  Inserting NON-RELEVANT analysis (score=30, conf=0.4)...")
        non_relevant_market = create_mock_market_json(
            relevance_score=30,
            top_vertical="Unknown",
            top_confidence=0.4,
        )
        
        non_relevant_id = persist_analysis(
            post_id=post_id,
            market_json=non_relevant_market,
            db_path=test_db_path,
        )
        print(f"   ✅ Non-relevant analysis inserted with id: {non_relevant_id}")
        
        # Verify it was stored correctly
        stored = get_analysis_by_id(non_relevant_id, db_path=test_db_path)
        assert stored is not None, "Analysis should be stored"
        assert stored["relevance_score"] == 30
        assert stored["top_vertical"] == "Unknown"
        assert stored["top_vertical_conf"] == 0.4
        print("   ✅ Fields extracted correctly\n")

        # -----------------------------------------------------------------------
        # Test 2: get_latest_relevant_analysis should return None (no relevant yet)
        # -----------------------------------------------------------------------
        print("4️⃣  Querying get_latest_relevant_analysis()...")
        latest_relevant = get_latest_relevant_analysis(db_path=test_db_path)
        assert latest_relevant is None, "Should return None when no relevant analysis exists"
        print("   ✅ Correctly returned None (no relevant analysis yet)\n")

        # Small delay to ensure different timestamps
        time.sleep(0.1)

        # -----------------------------------------------------------------------
        # Test 3: Insert a RELEVANT analysis
        # -----------------------------------------------------------------------
        print("5️⃣  Inserting RELEVANT analysis (score=75, conf=0.85)...")
        relevant_market = create_mock_market_json(
            relevance_score=75,
            top_vertical="Banking",
            top_confidence=0.85,
            tickers=[
                {
                    "ticker_or_etf": "XLF",
                    "direction_up_down_mixed": "up",
                    "mechanism": "Financial regulation impact",
                    "confidence_0_1": 0.75,
                    "conservative_move": {"horizon": "2-5d", "expected_pct_range": "+0.5% to +1.5%"},
                    "aggressive_move": {"horizon": "1-4w", "expected_pct_range": "+1.5% to +3.0%"},
                    "what_would_change_your_mind": ["Policy change"],
                },
                {
                    "ticker_or_etf": "KRE",
                    "direction_up_down_mixed": "up",
                    "mechanism": "Regional bank benefit",
                    "confidence_0_1": 0.6,
                    "conservative_move": {"horizon": "2-5d", "expected_pct_range": "+0.3% to +1.0%"},
                    "aggressive_move": {"horizon": "1-4w", "expected_pct_range": "+1.0% to +2.0%"},
                    "what_would_change_your_mind": ["Market conditions"],
                },
            ],
        )
        
        relevant_id = persist_analysis(
            post_id=post_id,
            market_json=relevant_market,
            db_path=test_db_path,
        )
        print(f"   ✅ Relevant analysis inserted with id: {relevant_id}\n")

        # -----------------------------------------------------------------------
        # Test 4: get_latest_relevant_analysis should now return the relevant one
        # -----------------------------------------------------------------------
        print("6️⃣  Querying get_latest_relevant_analysis() again...")
        latest_relevant = get_latest_relevant_analysis(db_path=test_db_path)
        
        assert latest_relevant is not None, "Should return the relevant analysis"
        assert latest_relevant["id"] == relevant_id, f"Should be id {relevant_id}, got {latest_relevant['id']}"
        assert latest_relevant["relevance_score"] == 75
        assert latest_relevant["top_vertical"] == "Banking"
        assert latest_relevant["top_vertical_conf"] == 0.85
        
        print(f"   ✅ Returned analysis id: {latest_relevant['id']}")
        print(f"   ✅ relevance_score: {latest_relevant['relevance_score']}")
        print(f"   ✅ top_vertical: {latest_relevant['top_vertical']}")
        print(f"   ✅ top_vertical_conf: {latest_relevant['top_vertical_conf']}\n")

        # -----------------------------------------------------------------------
        # Test 5: Verify tickers_json was stored separately
        # -----------------------------------------------------------------------
        print("7️⃣  Verifying tickers_json stored separately...")
        tickers_json = latest_relevant["tickers_json"]
        assert tickers_json is not None, "tickers_json should be stored"
        
        tickers = json.loads(tickers_json)
        assert len(tickers) == 2, f"Should have 2 tickers, got {len(tickers)}"
        assert tickers[0]["ticker_or_etf"] == "XLF"
        assert tickers[1]["ticker_or_etf"] == "KRE"
        print(f"   ✅ tickers_json has {len(tickers)} tickers: {[t['ticker_or_etf'] for t in tickers]}\n")

        # -----------------------------------------------------------------------
        # Test 6: Verify full market_json was stored
        # -----------------------------------------------------------------------
        print("8️⃣  Verifying full market_json stored...")
        market_json_str = latest_relevant["market_json"]
        assert market_json_str is not None, "market_json should be stored"
        
        market = json.loads(market_json_str)
        assert market["relevance_score_0_100"] == 75
        assert market["base_case_summary"] == "Test base case"
        assert len(market["dominant_verticals_ranked"]) == 1
        print(f"   ✅ Full market_json stored ({len(market_json_str)} chars)\n")

        # -----------------------------------------------------------------------
        # Test 7: Insert another RELEVANT analysis (newer, should be returned)
        # -----------------------------------------------------------------------
        time.sleep(0.1)
        print("9️⃣  Inserting NEWER relevant analysis (score=85, conf=0.9)...")
        newer_market = create_mock_market_json(
            relevance_score=85,
            top_vertical="Technology",
            top_confidence=0.9,
        )
        
        newer_id = persist_analysis(
            post_id=post_id,
            market_json=newer_market,
            db_path=test_db_path,
        )
        print(f"   ✅ Newer analysis inserted with id: {newer_id}\n")

        # -----------------------------------------------------------------------
        # Test 8: get_latest_relevant_analysis should return the NEWER one
        # -----------------------------------------------------------------------
        print("🔟 Querying get_latest_relevant_analysis() for newest...")
        latest_relevant = get_latest_relevant_analysis(db_path=test_db_path)
        
        assert latest_relevant is not None
        assert latest_relevant["id"] == newer_id, f"Should be newest id {newer_id}, got {latest_relevant['id']}"
        assert latest_relevant["relevance_score"] == 85
        assert latest_relevant["top_vertical"] == "Technology"
        print(f"   ✅ Correctly returned newest relevant analysis (id={newer_id})")
        print(f"   ✅ score={latest_relevant['relevance_score']}, vertical={latest_relevant['top_vertical']}\n")

        # -----------------------------------------------------------------------
        # Test 9: get_latest_analysis returns ANY latest (regardless of relevance)
        # -----------------------------------------------------------------------
        print("1️⃣1️⃣  Verifying get_latest_analysis() returns any latest...")
        latest_any = get_latest_analysis(db_path=test_db_path)
        assert latest_any is not None, "get_latest_analysis() should return something"
        # The newest analysis is id=3, but we just need to verify the function works
        print(f"   ✅ get_latest_analysis() returned id={latest_any['id']}")
        print(f"      (score={latest_any['relevance_score']}, vertical={latest_any['top_vertical']})\n")

        # -----------------------------------------------------------------------
        # Summary
        # -----------------------------------------------------------------------
        print("=" * 70)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        print("\nSummary:")
        print(f"  - Inserted 3 analyses (1 non-relevant, 2 relevant)")
        print(f"  - get_latest_relevant_analysis() correctly filters by thresholds")
        print(f"  - get_latest_relevant_analysis() returns the NEWEST relevant one")
        print(f"  - Fields extracted: relevance_score, top_vertical, top_vertical_conf")
        print(f"  - tickers_json stored separately for fast reads")
        print(f"  - Full market_json preserved as TEXT")

    finally:
        # Cleanup
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            print(f"\n🧹 Cleaned up: {test_db_path}")


if __name__ == "__main__":
    test_persist_and_retrieve()

