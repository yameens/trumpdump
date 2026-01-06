#!/usr/bin/env python3
"""
Test script for SSE endpoint.

Run this while `curl -N localhost:8000/stream` is running in another terminal
to see real-time events.

Usage:
    # Terminal 1: Start SSE listener
    curl -N http://localhost:8000/stream
    
    # Terminal 2: Run this script to publish a test event
    python backend/app/services/test_sse.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


async def publish_test_event():
    """Publish a test analysis event to all SSE subscribers."""
    from backend.app.services.events import publish_analysis, get_subscriber_count
    
    print("=" * 60)
    print("SSE Test Event Publisher")
    print("=" * 60)
    
    # Check subscribers
    count = get_subscriber_count()
    print(f"\n📡 Current SSE subscribers: {count}")
    
    if count == 0:
        print("\n⚠️  No subscribers connected!")
        print("   Run this in another terminal first:")
        print("   curl -N http://localhost:8000/stream")
        print("\n   Then run this script again.")
        return
    
    # Publish test event
    print("\n📤 Publishing test analysis event...")
    
    test_analysis = {
        "id": 999,
        "post_id": 1,
        "relevance_score": 85,
        "top_vertical": "Technology",
        "top_vertical_conf": 0.92,
        "post": {
            "id": 1,
            "url": "https://www.whitehouse.gov/test/sse-test/",
            "title": "Test: New Technology Policy",
        },
        "verticals": [
            {
                "vertical": "Technology",
                "rationale": "Direct tech sector impact",
                "confidence_0_1": 0.92,
            }
        ],
        "tickers": [
            {
                "ticker_or_etf": "QQQ",
                "direction_up_down_mixed": "up",
                "mechanism": "Tech sector boost",
                "confidence_0_1": 0.78,
            }
        ],
        "base_case_summary": "This is a test analysis for SSE demonstration.",
    }
    
    await publish_analysis(test_analysis)
    
    print("\n✅ Event published!")
    print(f"   Check the curl output - you should see the event.")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(publish_test_event())

