from __future__ import annotations

from dotenv import load_dotenv
import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from trumpsTruthsScraper import tt_poll_once
from openai import OpenAI


load_dotenv()

# hard-fail early if missing key (prevents confusing runtime errors later)
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("missing openai_api_key in environment (.env not loaded or key not set).")

client = OpenAI()

# optional: allow overriding models via env
facts_model = os.getenv("facts_model", "gpt-5-nano")
market_model = os.getenv("market_model", "gpt-5.2-pro")


facts_schema: Dict[str, Any] = {
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

market_schema: Dict[str, Any] = {
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


def _json_or_die(s: str) -> Dict[str, Any]:
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        preview = s[:800]
        raise RuntimeError(f"model returned non-json (first 800 chars):\n{preview}") from e


def _format_from_schema(schema_obj: Dict[str, Any]) -> Dict[str, Any]:
    # responses api structured outputs: text.format = {type:"json_schema", name:"...", schema:{...}, strict:true}
    return {
        "type": "json_schema",
        "name": schema_obj["name"],
        "schema": schema_obj["schema"],
        "strict": True,
    }


def _call_structured(model: str, messages: List[Dict[str, str]], schema_obj: Dict[str, Any]) -> Dict[str, Any]:
    resp = client.responses.create(
        model=model,
        input=messages,
        text={"format": _format_from_schema(schema_obj)},
        store=False,
    )
    if not getattr(resp, "output_text", None):
        raise RuntimeError("empty output_text from model response")
    return _json_or_die(resp.output_text)


def analysis() -> None:
    result = tt_poll_once()
    if result is None:
        print("no new trump social post. skipping analysis.")
        return

    content = (getattr(result, "content", "") or "").strip()
    if not content:
        print("post content was empty. skipping analysis.")
        return

    source = getattr(result, "source", "unknown")
    url = getattr(result, "url", "unknown")
    timestamp_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # step 1: facts extraction
    facts_messages = [
        {
            "role": "system",
            "content": (\
                "you extract structured facts from the provided text.\n"
                "hard rules:\n"
                "a. do not invent facts, tickers, or numbers. if unsure, use \"unknown\".\n"
                "b. separate direct facts from assumptions.\n"
                "c. output must match the provided json schema exactly.\n"
                "d. prefer empty arrays [] over omitting fields.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                "record metadata (authoritative):\n"
                f"a. source: {source}\n"
                f"b. url: {url}\n"
                f"c. timestamp_utc: {timestamp_utc}\n\n"
                "text to extract from:\n"
                f"{content}\n\n"
                "return json matching the schema, including record, facts, "
                "claims_requiring_verification, market_relevance_triggers, and assumptions."
            ),
        },
    ]

    facts_json = _call_structured(facts_model, facts_messages, facts_schema)
    print("part one completed. facts extracted. moving to part two.")

    # step 2: market analysis (must use only extracted facts)
    market_messages = [
        {
            "role": "system",
            "content": (
                "you are an institutional, risk-averse market analyst.\n"
                "you must use only the provided extracted json facts as your factual basis.\n"
                "do not invent tickers, sectors, or numbers. if uncertain, write \"unknown\" and add to data_needed_next.\n"
                "verified_additions must be [] (no web verification in this script).\n"
                "be conservative by default.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                "extracted_facts_json (authoritative):\n"
                f"{json.dumps(facts_json, ensure_ascii=False)}\n\n"
                "using only the extracted facts above, produce a market impact analysis.\n"
                "constraints:\n"
                "a. verified_additions must be []\n"
                "b. provide confidence_0_1 for each inference\n"
                "c. moves must be ranges like \"-0.5% to +0.2%\"\n"
                "d. if factual basis is weak/unverified, cap relevance_score_0_100 at 60\n"
                "return json matching the schema."
            ),
        },
    ]

    ticker_messages = [
    {
        "role": "system",
        "content": (
            "you are an institutional, risk-averse market analyst whose task is to identify "
            "which investable etfs or stocks are most likely to be impacted by the provided analysis.\n\n"

            "rules:\n"
            "a. do not invent tickers or companies.\n"
            "b. only assign tickers if market relevance is sufficiently high and a clear economic "
            "transmission mechanism exists.\n"
            "c. prefer etfs over single-name stocks when the signal is driven by a broad vertical "
            "(e.g., war, energy, banking, semiconductors, regulation).\n"
            "d. only assign single-name stocks if there is direct entity exposure or a highly specific, "
            "defensible linkage.\n"
            "e. if mapping is inferred (not explicit), you must explain the mechanism and reduce confidence.\n"
            "f. if there is insufficient evidence to assign any etf or ticker, return an empty list.\n\n"

            "vertical to etf guidance (non-exhaustive, use only when justified):\n"
            "a. defense, war, military escalation -> ita, xar\n"
            "b. energy supply, sanctions, geopolitics -> xle, oih\n"
            "c. banking, financial regulation -> xlf, kre\n"
            "d. semiconductors, export controls -> soxx, smh\n"
            "e. broad geopolitical risk, risk-off sentiment -> spy (mixed), dia (mixed)\n\n"

            "confidence and magnitude:\n"
            "a. assign confidence_0_1 conservatively.\n"
            "b. conservative move ranges should reflect short-term sentiment impact, not long-term fundamentals.\n"
            "c. if confidence is below 0.5, expected price impact should be very small or the horizon marked as unknown.\n\n"

            "output requirements:\n"
            "a. rank tickers or etfs by expected impact, most impacted first.\n"
            "b. clearly state the transmission mechanism for each assignment.\n"
            "c. if no ticker assignment is justified, output an empty tickers list.\n"
            "d. never force a ticker assignment.\n\n"

            "goal:\n"
            "identify plausible, defensible market exposure rather than maximizing coverage."
        )
    }
]

    market_resp = client.responses.create(
        model=market_model,
        input=market_messages,
        reasoning={"effort": "high"},
        text={"format": _format_from_schema(market_schema)},
        store=False,
    )
    
    print(market_resp.output_text)
    print("part two completed. analysis complete.")

    relevance = int(market_resp.get("relevance_score_0_100", 0), 0)
    verticals = market_resp.get("dominant_verticals_ranked") or []
    if not isinstance(verticals, list):
        verticals = []

    top_vertical_confidence = 0.0
    if verticals and isinstance(verticals[0], dict):
        top_vertical_confidence = float(verticals[0].get("confidence_0_1") or 0.0)


    if relevance >= 50 and top_vertical_confidence >= 0.65:
        ticker_schema = {
            "name": "ticker_candidates",
            "schema": {
                    "type": "object",
                    "additionalProperties": False,
            "properties": {
                "verticals": {"type": "array", "items": {"type": "string"}},
                "etfs": {"type": "array", "items": {"type": "string"}},
                "tickers": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["verticals", "etfs", "tickers", "notes"],
    },
}

    else:
        ticker_schema = None
    
    if ticker_schema: 
        ticker_resp = client.responses.create(
            model=market_model,
            input=ticker_messages,
            reasoning={"effort": "high"},
            text={"format": _format_from_schema(ticker_schema)},
            store=False,
        )
    else:
        print("no relevant tickers or etfs. ")
        ticker_resp = None
    
    if ticker_resp:
        print(ticker_resp.output_text)


    


if __name__ == "__main__":
    analysis()
