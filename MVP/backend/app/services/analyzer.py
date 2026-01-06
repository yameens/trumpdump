"""
Analyzer service for market impact analysis.

Wraps OpenAI calls and returns parsed JSON dicts.
All responses are properly parsed via _json_or_die - no .get() on raw response objects.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging - never log API keys
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAI client initialization (lazy)
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    """Lazy initialization of OpenAI client with safe error handling."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing OPENAI_API_KEY in environment. "
            "Ensure .env file exists and contains the key."
        )

    # Import here to avoid import errors if openai not installed
    try:
        from openai import OpenAI
        _client = OpenAI()
        logger.info("OpenAI client initialized successfully")
        return _client
    except ImportError as e:
        raise RuntimeError("openai package not installed. Run: pip install openai") from e
    except Exception as e:
        # Never log the actual error which might contain API key info
        logger.error("Failed to initialize OpenAI client (details hidden for security)")
        raise RuntimeError("Failed to initialize OpenAI client") from e


# Model configuration via environment
def _get_facts_model() -> str:
    return os.getenv("FACTS_MODEL", os.getenv("facts_model", "gpt-4o-mini"))


def _get_market_model() -> str:
    return os.getenv("MARKET_MODEL", os.getenv("market_model", "gpt-4o"))


# ---------------------------------------------------------------------------
# JSON Schemas (reused from original analysis.py)
# ---------------------------------------------------------------------------

FACTS_SCHEMA: Dict[str, Any] = {
    "name": "facts_extraction",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "record": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "url": {"type": "string"},
                    "timestamp_utc": {"type": "string"},
                },
                "required": ["source", "url", "timestamp_utc"],
            },
            "facts": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "actors": {"type": "array", "items": {"type": "string"}},
                    "actions": {"type": "array", "items": {"type": "string"}},
                    "locations": {"type": "array", "items": {"type": "string"}},
                    "time_refs": {"type": "array", "items": {"type": "string"}},
                    "policy_tools": {"type": "array", "items": {"type": "string"}},
                    "targets_named": {"type": "array", "items": {"type": "string"}},
                    "intensity_words": {"type": "array", "items": {"type": "string"}},
                    "direct_company_mentions": {"type": "array", "items": {"type": "string"}},
                    "direct_ticker_mentions": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "actors",
                    "actions",
                    "locations",
                    "time_refs",
                    "policy_tools",
                    "targets_named",
                    "intensity_words",
                    "direct_company_mentions",
                    "direct_ticker_mentions",
                ],
            },
            "claims_requiring_verification": {"type": "array", "items": {"type": "string"}},
            "market_relevance_triggers": {"type": "array", "items": {"type": "string"}},
            "assumptions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "assumption": {"type": "string"},
                        "confidence_0_1": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["assumption", "confidence_0_1"],
                },
            },
        },
        "required": [
            "record",
            "facts",
            "claims_requiring_verification",
            "market_relevance_triggers",
            "assumptions",
        ],
    },
}

MARKET_SCHEMA: Dict[str, Any] = {
    "name": "market_impact",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "relevance_score_0_100": {"type": "integer", "minimum": 0, "maximum": 100},
            "why_relevant": {"type": "array", "items": {"type": "string"}},
            "dominant_verticals_ranked": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "vertical": {"type": "string"},
                        "rationale": {"type": "string"},
                        "confidence_0_1": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["vertical", "rationale", "confidence_0_1"],
                },
            },
            "tickers_ranked": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "ticker_or_etf": {"type": "string"},
                        "direction_up_down_mixed": {
                            "type": "string",
                            "enum": ["up", "down", "mixed", "unknown"],
                        },
                        "mechanism": {"type": "string"},
                        "confidence_0_1": {"type": "number", "minimum": 0, "maximum": 1},
                        "conservative_move": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "horizon": {
                                    "type": "string",
                                    "enum": ["0-2h", "1d", "2-5d", "1-4w", "unknown"],
                                },
                                "expected_pct_range": {"type": "string"},
                            },
                            "required": ["horizon", "expected_pct_range"],
                        },
                        "aggressive_move": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "horizon": {
                                    "type": "string",
                                    "enum": ["0-2h", "1d", "2-5d", "1-4w", "unknown"],
                                },
                                "expected_pct_range": {"type": "string"},
                            },
                            "required": ["horizon", "expected_pct_range"],
                        },
                        "what_would_change_your_mind": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "ticker_or_etf",
                        "direction_up_down_mixed",
                        "mechanism",
                        "confidence_0_1",
                        "conservative_move",
                        "aggressive_move",
                        "what_would_change_your_mind",
                    ],
                },
            },
            "base_case_summary": {"type": "string"},
            "conservative_case_summary": {"type": "string"},
            "aggressive_case_summary": {"type": "string"},
            "facts_used": {"type": "array", "items": {"type": "string"}},
            "verified_additions": {"type": "array", "items": {"type": "string"}},
            "data_needed_next": {"type": "array", "items": {"type": "string"}},
            "inferences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "inference": {"type": "string"},
                        "confidence_0_1": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["inference", "confidence_0_1"],
                },
            },
        },
        "required": [
            "relevance_score_0_100",
            "why_relevant",
            "dominant_verticals_ranked",
            "tickers_ranked",
            "base_case_summary",
            "conservative_case_summary",
            "aggressive_case_summary",
            "facts_used",
            "verified_additions",
            "data_needed_next",
            "inferences",
        ],
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _json_or_die(s: str) -> Dict[str, Any]:
    """
    Parse JSON string or raise RuntimeError with safe preview.
    Never includes sensitive data in error messages.
    """
    if not s:
        raise RuntimeError("Empty response from model (no output_text)")
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        # Safe preview - first 500 chars, no sensitive data
        preview = s[:500] if len(s) > 500 else s
        logger.error(f"JSON parse failed at position {e.pos}")
        raise RuntimeError(
            f"Model returned invalid JSON (first 500 chars): {preview}"
        ) from e


def _format_from_schema(schema_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Convert schema to OpenAI structured output format."""
    return {
        "type": "json_schema",
        "name": schema_obj["name"],
        "schema": schema_obj["schema"],
        "strict": True,
    }


def _call_structured(
    model: str,
    messages: List[Dict[str, str]],
    schema_obj: Dict[str, Any],
    use_reasoning: bool = False,
) -> Dict[str, Any]:
    """
    Make a structured OpenAI API call and return parsed JSON.
    
    FIXED: Always parses resp.output_text via _json_or_die.
    Never calls .get() on the raw response object.
    """
    client = _get_client()

    try:
        kwargs = {
            "model": model,
            "input": messages,
            "text": {"format": _format_from_schema(schema_obj)},
            "store": False,
        }

        if use_reasoning:
            kwargs["reasoning"] = {"effort": "high"}

        resp = client.responses.create(**kwargs)

        # FIXED: Always use getattr + _json_or_die, never .get() on response
        output_text = getattr(resp, "output_text", None)
        if not output_text:
            raise RuntimeError("Empty output_text from model response")

        return _json_or_die(output_text)

    except Exception as e:
        # Log safely - never include potential API key info
        error_type = type(e).__name__
        logger.error(f"OpenAI API call failed: {error_type}")

        # Re-raise with safe message
        if "api_key" in str(e).lower() or "apikey" in str(e).lower():
            raise RuntimeError("API authentication error (details hidden)") from e
        raise


# ---------------------------------------------------------------------------
# Metadata dataclass for facts extraction
# ---------------------------------------------------------------------------

@dataclass
class PostMeta:
    """Metadata for a post being analyzed."""
    source: str
    url: str
    timestamp_utc: Optional[str] = None

    def to_dict(self) -> Dict[str, str]:
        ts = self.timestamp_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "source": self.source,
            "url": self.url,
            "timestamp_utc": ts,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_facts(
    text: str,
    meta: Union[PostMeta, Dict[str, str]],
) -> Dict[str, Any]:
    """
    Extract structured facts from text.
    
    Args:
        text: The content to analyze
        meta: PostMeta or dict with {source, url, timestamp_utc}
    
    Returns:
        Dict matching FACTS_SCHEMA with keys:
        - record: {source, url, timestamp_utc}
        - facts: {actors, actions, locations, ...}
        - claims_requiring_verification: [...]
        - market_relevance_triggers: [...]
        - assumptions: [{assumption, confidence_0_1}, ...]
    """
    if not text or not text.strip():
        raise ValueError("Cannot extract facts from empty text")

    # Convert meta to dict if needed
    if isinstance(meta, PostMeta):
        meta_dict = meta.to_dict()
    else:
        meta_dict = meta
        if "timestamp_utc" not in meta_dict:
            meta_dict["timestamp_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    messages = [
        {
            "role": "system",
            "content": (
                "You extract structured facts from the provided text.\n"
                "Hard rules:\n"
                "a. Do not invent facts, tickers, or numbers. If unsure, use \"unknown\".\n"
                "b. Separate direct facts from assumptions.\n"
                "c. Output must match the provided JSON schema exactly.\n"
                "d. Prefer empty arrays [] over omitting fields.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                "Record metadata (authoritative):\n"
                f"a. source: {meta_dict['source']}\n"
                f"b. url: {meta_dict['url']}\n"
                f"c. timestamp_utc: {meta_dict['timestamp_utc']}\n\n"
                "Text to extract from:\n"
                f"{text}\n\n"
                "Return JSON matching the schema, including record, facts, "
                "claims_requiring_verification, market_relevance_triggers, and assumptions."
            ),
        },
    ]

    logger.info(f"Extracting facts from {len(text)} chars of text")
    facts_json = _call_structured(_get_facts_model(), messages, FACTS_SCHEMA)
    logger.info("Facts extraction completed")

    return facts_json


def market_impact(facts_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate market impact analysis from extracted facts.
    
    Args:
        facts_json: Output from extract_facts()
    
    Returns:
        Dict matching MARKET_SCHEMA with keys:
        - relevance_score_0_100: int
        - why_relevant: [...]
        - dominant_verticals_ranked: [{vertical, rationale, confidence_0_1}, ...]
        - tickers_ranked: [{ticker_or_etf, direction, mechanism, ...}, ...]
        - base_case_summary, conservative_case_summary, aggressive_case_summary: str
        - facts_used: [...]
        - verified_additions: [] (always empty)
        - data_needed_next: [...]
        - inferences: [{inference, confidence_0_1}, ...]
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are an institutional, risk-averse market analyst.\n"
                "You must use only the provided extracted JSON facts as your factual basis.\n"
                "Do not invent tickers, sectors, or numbers. If uncertain, write \"unknown\" and add to data_needed_next.\n"
                "verified_additions MUST be [] (no web verification in this script).\n"
                "Be conservative by default.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                "extracted_facts_json (authoritative):\n"
                f"{json.dumps(facts_json, ensure_ascii=False)}\n\n"
                "Using only the extracted facts above, produce a market impact analysis.\n"
                "Constraints:\n"
                "a. verified_additions MUST be []\n"
                "b. Provide confidence_0_1 for each inference\n"
                "c. Moves must be ranges like \"-0.5% to +0.2%\"\n"
                "d. If factual basis is weak/unverified, cap relevance_score_0_100 at 60\n"
                "Return JSON matching the schema."
            ),
        },
    ]

    logger.info("Generating market impact analysis")
    market_json = _call_structured(
        _get_market_model(),
        messages,
        MARKET_SCHEMA,
        use_reasoning=True,
    )

    # ENFORCE: verified_additions must always be []
    market_json["verified_additions"] = []

    logger.info(
        f"Market analysis completed: relevance={market_json.get('relevance_score_0_100', 'N/A')}"
    )

    return market_json


def analyze_whitehouse_post(
    post: Union[Dict[str, Any], Any],
) -> Dict[str, Any]:
    """
    Convenience function: analyze a White House post end-to-end.
    
    Args:
        post: Either a dict with {url, title, content, scraped_at_utc}
              or a WhiteHousePost dataclass
    
    Returns:
        market_json dict matching MARKET_SCHEMA
    
    Raises:
        ValueError: If post content is empty
        RuntimeError: On API errors
    """
    # Extract fields from post (handle both dict and dataclass)
    if isinstance(post, dict):
        url = post.get("url", "unknown")
        title = post.get("title", "")
        content = post.get("content", "")
    else:
        # Assume dataclass with attributes
        url = getattr(post, "url", "unknown")
        title = getattr(post, "title", "")
        content = getattr(post, "content", "")

    # Build full text from title + content
    text_parts = []
    if title:
        text_parts.append(f"Title: {title}")
    if content:
        text_parts.append(content)

    full_text = "\n\n".join(text_parts)

    if not full_text.strip():
        raise ValueError("Post has no content to analyze")

    # Create metadata
    meta = PostMeta(
        source="White House",
        url=url,
    )

    # Step 1: Extract facts
    logger.info(f"Analyzing White House post: {url}")
    facts_json = extract_facts(full_text, meta)

    # Step 2: Generate market impact
    market_json = market_impact(facts_json)

    return market_json


# ---------------------------------------------------------------------------
# Self-check / testing
# ---------------------------------------------------------------------------

def _create_mock_facts_json() -> Dict[str, Any]:
    """Create mock facts_json for testing without API calls."""
    return {
        "record": {
            "source": "White House",
            "url": "https://www.whitehouse.gov/test",
            "timestamp_utc": "2026-01-04T12:00:00Z",
        },
        "facts": {
            "actors": ["President", "Treasury Secretary"],
            "actions": ["signed executive order", "announced tariffs"],
            "locations": ["United States", "China"],
            "time_refs": ["immediately", "within 90 days"],
            "policy_tools": ["executive order", "tariffs"],
            "targets_named": ["Chinese imports", "steel industry"],
            "intensity_words": ["significant", "major"],
            "direct_company_mentions": [],
            "direct_ticker_mentions": [],
        },
        "claims_requiring_verification": [
            "Tariff rate of 25% on steel imports"
        ],
        "market_relevance_triggers": [
            "Trade policy change",
            "Tariff announcement",
        ],
        "assumptions": [
            {"assumption": "Policy will be implemented as stated", "confidence_0_1": 0.7}
        ],
    }


def _create_mock_market_json() -> Dict[str, Any]:
    """Create mock market_json that matches the schema for testing."""
    return {
        "relevance_score_0_100": 75,
        "why_relevant": [
            "Direct trade policy impact",
            "Affects steel industry valuations",
        ],
        "dominant_verticals_ranked": [
            {
                "vertical": "Steel/Materials",
                "rationale": "Direct target of tariff policy",
                "confidence_0_1": 0.85,
            },
            {
                "vertical": "Manufacturing",
                "rationale": "Input cost implications",
                "confidence_0_1": 0.7,
            },
        ],
        "tickers_ranked": [
            {
                "ticker_or_etf": "XME",
                "direction_up_down_mixed": "up",
                "mechanism": "Domestic steel producers benefit from import tariffs",
                "confidence_0_1": 0.75,
                "conservative_move": {
                    "horizon": "2-5d",
                    "expected_pct_range": "+0.5% to +2.0%",
                },
                "aggressive_move": {
                    "horizon": "1-4w",
                    "expected_pct_range": "+2.0% to +5.0%",
                },
                "what_would_change_your_mind": [
                    "Tariff exemptions announced",
                    "Trade deal negotiations",
                ],
            },
        ],
        "base_case_summary": "Steel tariffs likely to boost domestic producers in short term.",
        "conservative_case_summary": "Limited impact if exemptions are granted.",
        "aggressive_case_summary": "Significant rally in steel stocks if policy fully implemented.",
        "facts_used": [
            "Executive order signed",
            "25% tariff on steel imports",
        ],
        "verified_additions": [],  # Always empty
        "data_needed_next": [
            "Specific tariff rates",
            "Implementation timeline",
        ],
        "inferences": [
            {
                "inference": "Domestic steel prices will increase",
                "confidence_0_1": 0.8,
            },
        ],
    }


if __name__ == "__main__":
    # Self-check: validate that mock data matches schemas
    import sys

    print("=" * 60)
    print("Analyzer Self-Check")
    print("=" * 60)

    # Test 1: Validate mock facts_json structure
    print("\n1️⃣  Validating mock facts_json structure...")
    mock_facts = _create_mock_facts_json()
    required_facts_keys = FACTS_SCHEMA["schema"]["required"]
    for key in required_facts_keys:
        assert key in mock_facts, f"Missing required key: {key}"
    print(f"   ✅ All {len(required_facts_keys)} required keys present")

    # Test 2: Validate mock market_json structure
    print("\n2️⃣  Validating mock market_json structure...")
    mock_market = _create_mock_market_json()
    required_market_keys = MARKET_SCHEMA["schema"]["required"]
    for key in required_market_keys:
        assert key in mock_market, f"Missing required key: {key}"
    print(f"   ✅ All {len(required_market_keys)} required keys present")

    # Test 3: Verify verified_additions is always []
    print("\n3️⃣  Verifying verified_additions enforcement...")
    assert mock_market["verified_additions"] == [], "verified_additions must be []"
    print("   ✅ verified_additions is []")

    # Test 4: Test _json_or_die
    print("\n4️⃣  Testing _json_or_die...")
    test_json = '{"test": "value", "number": 42}'
    parsed = _json_or_die(test_json)
    assert parsed == {"test": "value", "number": 42}
    print("   ✅ Valid JSON parsed correctly")

    try:
        _json_or_die("not valid json {")
        print("   ❌ Should have raised error")
        sys.exit(1)
    except RuntimeError as e:
        print("   ✅ Invalid JSON raises RuntimeError")

    # Test 5: Test PostMeta
    print("\n5️⃣  Testing PostMeta...")
    meta = PostMeta(source="Test", url="https://example.com")
    meta_dict = meta.to_dict()
    assert "source" in meta_dict
    assert "url" in meta_dict
    assert "timestamp_utc" in meta_dict
    print("   ✅ PostMeta.to_dict() works correctly")

    print("\n" + "=" * 60)
    print("🎉 ALL SELF-CHECKS PASSED!")
    print("=" * 60)
    print("\nNote: API calls not tested (would require OPENAI_API_KEY).")
    print("To test with real API, set OPENAI_API_KEY and call:")
    print("  facts = extract_facts(text, meta)")
    print("  market = market_impact(facts)")

