"""
Relevance filtering module.

Two-stage gate system:
1. passes_heuristic(content) - Pre-filter before OpenAI calls (saves cost)
2. is_relevant(market_json) - Post-analysis gate based on model output

All thresholds are centralized here for easy tuning.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

# ===========================================================================
# THRESHOLDS - All tunable parameters in one place
# ===========================================================================

# Heuristic gate thresholds
MIN_CONTENT_LENGTH = 50  # Minimum characters for meaningful content
MAX_BOILERPLATE_RATIO = 0.5  # If >50% matches boilerplate patterns, skip

# Model gate thresholds
MIN_RELEVANCE_SCORE = 50  # Minimum relevance_score_0_100
MIN_TOP_VERTICAL_CONFIDENCE = 0.65  # Minimum confidence for top vertical

# ===========================================================================
# Keyword triggers - content must contain at least one to pass heuristic
# ===========================================================================

MARKET_KEYWORDS: Set[str] = {
    # Economic policy
    "tariff", "tariffs", "trade", "import", "export", "sanction", "sanctions",
    "economy", "economic", "gdp", "inflation", "deflation", "recession",
    "stimulus", "spending", "budget", "deficit", "debt", "treasury",
    
    # Financial/market terms
    "market", "markets", "stock", "stocks", "bond", "bonds", "equity",
    "investor", "investors", "investment", "bank", "banks", "banking",
    "fed", "federal reserve", "interest rate", "rates", "monetary",
    "fiscal", "tax", "taxes", "taxation", "revenue",
    
    # Industry verticals
    "oil", "gas", "energy", "semiconductor", "semiconductors", "chip", "chips",
    "tech", "technology", "defense", "military", "healthcare", "pharma",
    "pharmaceutical", "manufacturing", "auto", "automotive", "steel",
    "aluminum", "agriculture", "farming",
    
    # Trade/geopolitics
    "china", "chinese", "russia", "russian", "european", "eu", "nato",
    "bilateral", "multilateral", "agreement", "deal", "treaty",
    "embargo", "restriction", "restrictions", "ban", "banned",
    
    # Policy actions
    "executive order", "regulation", "regulations", "deregulation",
    "policy", "legislation", "bill", "act", "law", "mandate",
    "subsidy", "subsidies", "incentive", "incentives",
    
    # Corporate/business
    "company", "companies", "corporation", "business", "businesses",
    "industry", "sector", "merger", "acquisition", "ipo",
    "earnings", "profit", "profits", "revenue", "revenues",
    
    # Specific impact words
    "impact", "affect", "effect", "consequence", "result",
    "increase", "decrease", "rise", "fall", "surge", "plunge",
    "boost", "cut", "slash", "hike", "reduce", "expand",
}

# ===========================================================================
# Boilerplate patterns - content matching these is likely not market-relevant
# ===========================================================================

BOILERPLATE_PATTERNS: List[re.Pattern] = [
    # Standard government document headers/footers
    re.compile(r"for immediate release", re.IGNORECASE),
    re.compile(r"###\s*$", re.MULTILINE),  # Press release end marker
    re.compile(r"contact:\s*\S+@\S+", re.IGNORECASE),  # Contact emails
    re.compile(r"press\s*secretary", re.IGNORECASE),
    
    # Ceremonial/procedural content
    re.compile(r"(birthday|anniversary|congratulat|celebrat)", re.IGNORECASE),
    re.compile(r"(medal|honor|award|ceremony|memorial)", re.IGNORECASE),
    re.compile(r"(holiday|christmas|thanksgiving|easter|independence day)", re.IGNORECASE),
    re.compile(r"(proclamation|observance|recognition)\s+(of|for)", re.IGNORECASE),
    
    # Personnel announcements (usually not market-moving)
    re.compile(r"(appoint|nominat)\w*\s+(to serve|as|for)", re.IGNORECASE),
    re.compile(r"(resign|retirement|stepping down)", re.IGNORECASE),
    
    # Scheduling/travel
    re.compile(r"(schedule|itinerary|travel|visit)\s+(for|to|of)", re.IGNORECASE),
    re.compile(r"(meeting|summit|conference)\s+with", re.IGNORECASE),
    
    # Boilerplate phrases
    re.compile(r"(god bless america|god bless the united states)", re.IGNORECASE),
    re.compile(r"(signing statement|remarks by|readout of)", re.IGNORECASE),
]

# Exceptions - if these appear, DON'T skip even if boilerplate detected
BOILERPLATE_EXCEPTIONS: Set[str] = {
    "tariff", "sanction", "executive order", "trade", "economic",
    "market", "billion", "trillion", "percent", "rate",
}


# ===========================================================================
# Heuristic Gate (Pre-OpenAI filter)
# ===========================================================================

def passes_heuristic(content: str) -> bool:
    """
    Quick heuristic check before sending to OpenAI.
    
    Returns True if content is worth analyzing:
    - Has minimum length
    - Contains market-relevant keywords
    - Is not mostly boilerplate
    
    This saves OpenAI API costs by filtering obvious non-relevant content.
    """
    if not content:
        return False
    
    content = content.strip()
    
    # Gate 1: Minimum length
    if len(content) < MIN_CONTENT_LENGTH:
        return False
    
    content_lower = content.lower()
    
    # Gate 2: Must contain at least one market keyword
    has_keyword = any(kw in content_lower for kw in MARKET_KEYWORDS)
    if not has_keyword:
        return False
    
    # Gate 3: Check boilerplate ratio
    boilerplate_matches = sum(
        1 for pattern in BOILERPLATE_PATTERNS
        if pattern.search(content)
    )
    
    if boilerplate_matches > 0:
        # Check for exceptions - strong market signals override boilerplate
        has_exception = any(exc in content_lower for exc in BOILERPLATE_EXCEPTIONS)
        if has_exception:
            # Has boilerplate BUT also has strong market signal - allow
            return True
        
        # High boilerplate ratio without exceptions - skip
        boilerplate_ratio = boilerplate_matches / len(BOILERPLATE_PATTERNS)
        if boilerplate_ratio > MAX_BOILERPLATE_RATIO:
            return False
    
    return True


def get_heuristic_reason(content: str) -> str:
    """
    Debug helper: explains why content passed or failed heuristic.
    Useful for tuning thresholds.
    """
    if not content:
        return "FAIL: Empty content"
    
    content = content.strip()
    
    if len(content) < MIN_CONTENT_LENGTH:
        return f"FAIL: Too short ({len(content)} < {MIN_CONTENT_LENGTH} chars)"
    
    content_lower = content.lower()
    
    # Find matching keywords
    matched_keywords = [kw for kw in MARKET_KEYWORDS if kw in content_lower]
    if not matched_keywords:
        return "FAIL: No market keywords found"
    
    # Find boilerplate matches
    boilerplate_matches = [
        p.pattern for p in BOILERPLATE_PATTERNS if p.search(content)
    ]
    
    if boilerplate_matches:
        exceptions_found = [exc for exc in BOILERPLATE_EXCEPTIONS if exc in content_lower]
        if exceptions_found:
            return (
                f"PASS: Boilerplate detected ({len(boilerplate_matches)} patterns) "
                f"but overridden by: {exceptions_found[:3]}"
            )
        
        ratio = len(boilerplate_matches) / len(BOILERPLATE_PATTERNS)
        if ratio > MAX_BOILERPLATE_RATIO:
            return f"FAIL: Too much boilerplate ({ratio:.0%} > {MAX_BOILERPLATE_RATIO:.0%})"
    
    return f"PASS: {len(matched_keywords)} keywords found: {matched_keywords[:5]}"


# ===========================================================================
# Model Gate (Post-analysis filter)
# ===========================================================================

def is_relevant(market_json: Dict[str, Any]) -> bool:
    """
    Check if the model's analysis indicates market relevance.
    
    Returns True if:
    - relevance_score_0_100 >= MIN_RELEVANCE_SCORE (50)
    - Top vertical confidence >= MIN_TOP_VERTICAL_CONFIDENCE (0.65)
    
    Both conditions must be met.
    """
    # Extract relevance score
    relevance_score = market_json.get("relevance_score_0_100")
    if relevance_score is None:
        return False
    
    if relevance_score < MIN_RELEVANCE_SCORE:
        return False
    
    # Extract top vertical confidence
    verticals = market_json.get("dominant_verticals_ranked")
    if not verticals or not isinstance(verticals, list) or len(verticals) == 0:
        return False
    
    top_vertical = verticals[0]
    if not isinstance(top_vertical, dict):
        return False
    
    top_confidence = top_vertical.get("confidence_0_1")
    if top_confidence is None:
        return False
    
    if top_confidence < MIN_TOP_VERTICAL_CONFIDENCE:
        return False
    
    return True


def get_relevance_reason(market_json: Dict[str, Any]) -> str:
    """
    Debug helper: explains why market_json passed or failed relevance gate.
    """
    relevance_score = market_json.get("relevance_score_0_100")
    if relevance_score is None:
        return "FAIL: No relevance_score_0_100 field"
    
    verticals = market_json.get("dominant_verticals_ranked")
    if not verticals or not isinstance(verticals, list) or len(verticals) == 0:
        return f"FAIL: No dominant_verticals_ranked (score={relevance_score})"
    
    top_vertical = verticals[0]
    if not isinstance(top_vertical, dict):
        return f"FAIL: Invalid vertical format (score={relevance_score})"
    
    top_confidence = top_vertical.get("confidence_0_1")
    vertical_name = top_vertical.get("vertical", "unknown")
    
    if top_confidence is None:
        return f"FAIL: No confidence_0_1 in top vertical (score={relevance_score})"
    
    score_pass = relevance_score >= MIN_RELEVANCE_SCORE
    conf_pass = top_confidence >= MIN_TOP_VERTICAL_CONFIDENCE
    
    if score_pass and conf_pass:
        return (
            f"PASS: score={relevance_score} >= {MIN_RELEVANCE_SCORE}, "
            f"conf={top_confidence:.2f} >= {MIN_TOP_VERTICAL_CONFIDENCE} "
            f"(vertical={vertical_name})"
        )
    
    failures = []
    if not score_pass:
        failures.append(f"score={relevance_score} < {MIN_RELEVANCE_SCORE}")
    if not conf_pass:
        failures.append(f"conf={top_confidence:.2f} < {MIN_TOP_VERTICAL_CONFIDENCE}")
    
    return f"FAIL: {', '.join(failures)} (vertical={vertical_name})"


# ===========================================================================
# Convenience: Combined check
# ===========================================================================

def should_analyze(content: str) -> bool:
    """
    Convenience function: should we send this content to OpenAI?
    Alias for passes_heuristic().
    """
    return passes_heuristic(content)


def should_serve(market_json: Dict[str, Any]) -> bool:
    """
    Convenience function: should we serve this analysis to users?
    Alias for is_relevant().
    """
    return is_relevant(market_json)


# ===========================================================================
# Self-check / Unit tests
# ===========================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Relevance Module Self-Check")
    print("=" * 70)
    print(f"\nThresholds:")
    print(f"  - MIN_CONTENT_LENGTH: {MIN_CONTENT_LENGTH}")
    print(f"  - MIN_RELEVANCE_SCORE: {MIN_RELEVANCE_SCORE}")
    print(f"  - MIN_TOP_VERTICAL_CONFIDENCE: {MIN_TOP_VERTICAL_CONFIDENCE}")
    print(f"  - MAX_BOILERPLATE_RATIO: {MAX_BOILERPLATE_RATIO}")
    print(f"  - MARKET_KEYWORDS count: {len(MARKET_KEYWORDS)}")
    print(f"  - BOILERPLATE_PATTERNS count: {len(BOILERPLATE_PATTERNS)}")
    
    # -----------------------------------------------------------------------
    # Test passes_heuristic()
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("Testing passes_heuristic()")
    print("-" * 70)
    
    heuristic_tests = [
        # (content, expected, description)
        ("", False, "Empty string"),
        ("Short", False, "Too short"),
        ("x" * 100, False, "Long but no keywords"),
        (
            "The President announced new tariffs on Chinese imports today.",
            True,
            "Market keywords (tariff, chinese, import)"
        ),
        (
            "The market reacted strongly to the economic policy announcement.",
            True,
            "Multiple keywords (market, economic, policy)"
        ),
        (
            "Happy birthday to our great nation! God bless America!",
            False,
            "Boilerplate (birthday, god bless)"
        ),
        (
            "For Immediate Release: Holiday schedule announcement.",
            False,
            "Press release boilerplate + holiday"
        ),
        (
            "For Immediate Release: New tariff policy on steel imports effective immediately.",
            True,
            "Boilerplate BUT has tariff exception"
        ),
        (
            "The President signed an executive order on semiconductor export restrictions to China.",
            True,
            "Strong market signals (executive order, semiconductor, export, china)"
        ),
        (
            "Medal of Honor ceremony for brave soldiers.",
            False,
            "Ceremonial boilerplate"
        ),
        (
            "Treasury Department announces $500 billion economic stimulus package for businesses.",
            True,
            "Market keywords (treasury, billion, stimulus, economic)"
        ),
    ]
    
    passed = 0
    for content, expected, desc in heuristic_tests:
        result = passes_heuristic(content)
        status = "✅" if result == expected else "❌"
        if result != expected:
            reason = get_heuristic_reason(content)
            print(f"{status} {desc}")
            print(f"   Expected: {expected}, Got: {result}")
            print(f"   Reason: {reason}")
        else:
            passed += 1
            print(f"{status} {desc}: {result}")
    
    print(f"\nHeuristic tests: {passed}/{len(heuristic_tests)} passed")
    assert passed == len(heuristic_tests), "Some heuristic tests failed!"
    
    # -----------------------------------------------------------------------
    # Test is_relevant()
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("Testing is_relevant()")
    print("-" * 70)
    
    relevance_tests = [
        # (market_json, expected, description)
        ({}, False, "Empty market_json"),
        ({"relevance_score_0_100": 75}, False, "Missing verticals"),
        (
            {
                "relevance_score_0_100": 75,
                "dominant_verticals_ranked": []
            },
            False,
            "Empty verticals list"
        ),
        (
            {
                "relevance_score_0_100": 40,
                "dominant_verticals_ranked": [
                    {"vertical": "Energy", "confidence_0_1": 0.8}
                ]
            },
            False,
            "Score too low (40 < 50)"
        ),
        (
            {
                "relevance_score_0_100": 75,
                "dominant_verticals_ranked": [
                    {"vertical": "Energy", "confidence_0_1": 0.5}
                ]
            },
            False,
            "Confidence too low (0.5 < 0.65)"
        ),
        (
            {
                "relevance_score_0_100": 50,
                "dominant_verticals_ranked": [
                    {"vertical": "Banking", "confidence_0_1": 0.65}
                ]
            },
            True,
            "Exactly at thresholds (50, 0.65)"
        ),
        (
            {
                "relevance_score_0_100": 85,
                "dominant_verticals_ranked": [
                    {"vertical": "Technology", "confidence_0_1": 0.9}
                ]
            },
            True,
            "Well above thresholds"
        ),
        (
            {
                "relevance_score_0_100": 60,
                "dominant_verticals_ranked": [
                    {"vertical": "Steel", "confidence_0_1": 0.7},
                    {"vertical": "Manufacturing", "confidence_0_1": 0.5}
                ]
            },
            True,
            "Multiple verticals, top one passes"
        ),
        (
            {
                "relevance_score_0_100": 100,
                "dominant_verticals_ranked": [
                    {"vertical": "unknown"}  # Missing confidence
                ]
            },
            False,
            "Missing confidence_0_1 field"
        ),
    ]
    
    passed = 0
    for market_json, expected, desc in relevance_tests:
        result = is_relevant(market_json)
        status = "✅" if result == expected else "❌"
        if result != expected:
            reason = get_relevance_reason(market_json)
            print(f"{status} {desc}")
            print(f"   Expected: {expected}, Got: {result}")
            print(f"   Reason: {reason}")
        else:
            passed += 1
            print(f"{status} {desc}: {result}")
    
    print(f"\nRelevance tests: {passed}/{len(relevance_tests)} passed")
    assert passed == len(relevance_tests), "Some relevance tests failed!"
    
    # -----------------------------------------------------------------------
    # Test debug helpers
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("Testing debug helpers")
    print("-" * 70)
    
    print("\n1️⃣  get_heuristic_reason():")
    test_content = "The Federal Reserve announced interest rate changes affecting markets."
    reason = get_heuristic_reason(test_content)
    print(f"   Input: {test_content[:50]}...")
    print(f"   Result: {reason}")
    assert "PASS" in reason
    print("   ✅ Works correctly")
    
    print("\n2️⃣  get_relevance_reason():")
    test_market = {
        "relevance_score_0_100": 72,
        "dominant_verticals_ranked": [
            {"vertical": "Banking", "confidence_0_1": 0.78}
        ]
    }
    reason = get_relevance_reason(test_market)
    print(f"   Input: score=72, vertical=Banking, conf=0.78")
    print(f"   Result: {reason}")
    assert "PASS" in reason
    print("   ✅ Works correctly")
    
    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("🎉 ALL SELF-CHECKS PASSED!")
    print("=" * 70)
    print("\nUsage:")
    print("  from backend.app.services.relevance import passes_heuristic, is_relevant")
    print("")
    print("  # Before OpenAI call:")
    print("  if passes_heuristic(content):")
    print("      facts = extract_facts(content, meta)")
    print("      market = market_impact(facts)")
    print("")
    print("  # After OpenAI call:")
    print("  if is_relevant(market_json):")
    print("      serve_to_user(market_json)")
    print("  else:")
    print("      store_as_non_relevant(market_json)")

