"""
FastAPI server for TrumpDump MVP.

Endpoints:
- GET /latest - Returns the latest relevant analysis
- GET /history - Returns recent analyses (relevant first)

Run with: uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .db import (
    get_latest_relevant_analysis,
    get_latest_analysis,
    get_whitehouse_post_by_id,
    init_db,
    get_connection,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_MIN_TOP_VERTICAL_CONF,
)

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TrumpDump API",
    description="Market impact analysis of White House announcements",
    version="0.1.0",
)

# CORS for localhost frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize database and scheduler on startup
@app.on_event("startup")
async def startup_event():
    """Run database migrations and start scheduler on startup."""
    import os
    
    init_db()
    
    # Start scheduler unless disabled
    if os.getenv("DISABLE_SCHEDULER", "false").lower() != "true":
        from .services.scheduler import start_scheduler
        start_scheduler(app)


@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler on shutdown."""
    from .services.scheduler import stop_scheduler
    stop_scheduler()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class TickerImpact(BaseModel):
    """Individual ticker/ETF impact prediction."""
    ticker_or_etf: str
    direction: str = Field(..., alias="direction_up_down_mixed")
    mechanism: str
    confidence: float = Field(..., alias="confidence_0_1")
    conservative_move: Optional[Dict[str, str]] = None
    aggressive_move: Optional[Dict[str, str]] = None
    
    class Config:
        populate_by_name = True


class VerticalImpact(BaseModel):
    """Dominant vertical/sector impact."""
    vertical: str
    rationale: str
    confidence: float = Field(..., alias="confidence_0_1")
    
    class Config:
        populate_by_name = True


class PostInfo(BaseModel):
    """Linked whitehouse post information."""
    id: int
    url: str
    title: Optional[str] = None


class LatestAnalysis(BaseModel):
    """Schema for the latest relevant analysis response."""
    id: int
    post_id: int
    post: Optional[PostInfo] = None
    created_at_utc: int
    relevance_score: int
    top_vertical: Optional[str] = None
    top_vertical_conf: Optional[float] = None
    
    # Parsed JSON fields
    verticals: List[VerticalImpact] = []
    tickers: List[TickerImpact] = []
    
    # Summary fields
    base_case_summary: Optional[str] = None
    conservative_case_summary: Optional[str] = None
    aggressive_case_summary: Optional[str] = None
    
    class Config:
        populate_by_name = True


class AnalysisSummary(BaseModel):
    """Shorter schema for history listing."""
    id: int
    post_id: int
    post_title: Optional[str] = None
    post_url: Optional[str] = None
    created_at_utc: int
    relevance_score: Optional[int] = None
    top_vertical: Optional[str] = None
    top_vertical_conf: Optional[float] = None
    is_relevant: bool = False


class HistoryResponse(BaseModel):
    """Response schema for history endpoint."""
    analyses: List[AnalysisSummary]
    total: int
    limit: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def parse_analysis_row(row: Dict[str, Any]) -> LatestAnalysis:
    """Parse a database row into LatestAnalysis schema."""
    # Parse market_json if present
    verticals = []
    tickers = []
    base_case = None
    conservative_case = None
    aggressive_case = None
    
    if row.get("market_json"):
        try:
            market = json.loads(row["market_json"])
            
            # Parse verticals
            for v in market.get("dominant_verticals_ranked", []):
                verticals.append(VerticalImpact(
                    vertical=v.get("vertical", ""),
                    rationale=v.get("rationale", ""),
                    confidence_0_1=v.get("confidence_0_1", 0),
                ))
            
            # Parse tickers
            for t in market.get("tickers_ranked", []):
                tickers.append(TickerImpact(
                    ticker_or_etf=t.get("ticker_or_etf", ""),
                    direction_up_down_mixed=t.get("direction_up_down_mixed", "unknown"),
                    mechanism=t.get("mechanism", ""),
                    confidence_0_1=t.get("confidence_0_1", 0),
                    conservative_move=t.get("conservative_move"),
                    aggressive_move=t.get("aggressive_move"),
                ))
            
            base_case = market.get("base_case_summary")
            conservative_case = market.get("conservative_case_summary")
            aggressive_case = market.get("aggressive_case_summary")
            
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Alternatively, parse tickers from tickers_json if market_json parsing failed
    if not tickers and row.get("tickers_json"):
        try:
            tickers_data = json.loads(row["tickers_json"])
            for t in tickers_data:
                tickers.append(TickerImpact(
                    ticker_or_etf=t.get("ticker_or_etf", ""),
                    direction_up_down_mixed=t.get("direction_up_down_mixed", "unknown"),
                    mechanism=t.get("mechanism", ""),
                    confidence_0_1=t.get("confidence_0_1", 0),
                    conservative_move=t.get("conservative_move"),
                    aggressive_move=t.get("aggressive_move"),
                ))
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Get linked post info
    post_info = None
    post = get_whitehouse_post_by_id(row["post_id"])
    if post:
        post_info = PostInfo(
            id=post["id"],
            url=post["url"],
            title=post.get("title"),
        )
    
    return LatestAnalysis(
        id=row["id"],
        post_id=row["post_id"],
        post=post_info,
        created_at_utc=row["created_at_utc"],
        relevance_score=row["relevance_score"] or 0,
        top_vertical=row.get("top_vertical"),
        top_vertical_conf=row.get("top_vertical_conf"),
        verticals=verticals,
        tickers=tickers,
        base_case_summary=base_case,
        conservative_case_summary=conservative_case,
        aggressive_case_summary=aggressive_case,
    )


def get_recent_analyses(
    limit: int = 20,
    relevant_first: bool = True,
) -> List[Dict[str, Any]]:
    """Get recent analyses, optionally sorted with relevant first."""
    conn = get_connection()
    cur = conn.cursor()
    
    if relevant_first:
        # Sort by relevance (relevant first), then by recency
        cur.execute(
            """
            SELECT id, post_id, created_at_utc, relevance_score,
                   top_vertical, top_vertical_conf
            FROM analyses
            ORDER BY 
                CASE 
                    WHEN relevance_score >= ? AND top_vertical_conf >= ? THEN 0 
                    ELSE 1 
                END,
                created_at_utc DESC,
                id DESC
            LIMIT ?
            """,
            (DEFAULT_MIN_RELEVANCE_SCORE, DEFAULT_MIN_TOP_VERTICAL_CONF, limit),
        )
    else:
        cur.execute(
            """
            SELECT id, post_id, created_at_utc, relevance_score,
                   top_vertical, top_vertical_conf
            FROM analyses
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def count_analyses() -> int:
    """Get total count of analyses."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM analyses")
    row = cur.fetchone()
    conn.close()
    return row["count"] if row else 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok", version="0.1.0")


@app.get("/latest", response_model=LatestAnalysis)
async def get_latest(
    min_score: Optional[int] = Query(
        None,
        ge=0,
        le=100,
        description=f"Minimum relevance score (default: {DEFAULT_MIN_RELEVANCE_SCORE})"
    ),
    min_conf: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
        description=f"Minimum top vertical confidence (default: {DEFAULT_MIN_TOP_VERTICAL_CONF})"
    ),
):
    """
    Get the latest relevant market analysis.
    
    Returns the most recent analysis that meets the relevance thresholds.
    Default thresholds: score >= 50, confidence >= 0.65
    """
    row = get_latest_relevant_analysis(
        min_score=min_score,
        min_conf=min_conf,
    )
    
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No relevant analysis found",
                "hint": "Either no analyses exist or none meet the relevance thresholds",
                "thresholds": {
                    "min_score": min_score or DEFAULT_MIN_RELEVANCE_SCORE,
                    "min_conf": min_conf or DEFAULT_MIN_TOP_VERTICAL_CONF,
                }
            }
        )
    
    return parse_analysis_row(row)


@app.get("/history", response_model=HistoryResponse)
async def get_history(
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum number of analyses to return"
    ),
    relevant_first: bool = Query(
        True,
        description="Sort relevant analyses first"
    ),
):
    """
    Get recent analyses.
    
    By default, relevant analyses are sorted first, then by recency.
    """
    rows = get_recent_analyses(limit=limit, relevant_first=relevant_first)
    total = count_analyses()
    
    # Build summary list with post info
    analyses = []
    for row in rows:
        # Check if this analysis is relevant
        is_relevant = (
            row.get("relevance_score") is not None
            and row["relevance_score"] >= DEFAULT_MIN_RELEVANCE_SCORE
            and row.get("top_vertical_conf") is not None
            and row["top_vertical_conf"] >= DEFAULT_MIN_TOP_VERTICAL_CONF
        )
        
        # Get post info
        post = get_whitehouse_post_by_id(row["post_id"])
        
        analyses.append(AnalysisSummary(
            id=row["id"],
            post_id=row["post_id"],
            post_title=post.get("title") if post else None,
            post_url=post.get("url") if post else None,
            created_at_utc=row["created_at_utc"],
            relevance_score=row.get("relevance_score"),
            top_vertical=row.get("top_vertical"),
            top_vertical_conf=row.get("top_vertical_conf"),
            is_relevant=is_relevant,
        ))
    
    return HistoryResponse(
        analyses=analyses,
        total=total,
        limit=limit,
    )


@app.get("/analysis/{analysis_id}", response_model=LatestAnalysis)
async def get_analysis_detail(analysis_id: int):
    """Get a specific analysis by ID."""
    from .db import get_analysis_by_id
    
    row = get_analysis_by_id(analysis_id)
    
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Analysis with id {analysis_id} not found"}
        )
    
    return parse_analysis_row(row)


# ---------------------------------------------------------------------------
# Admin/Scheduler endpoints
# ---------------------------------------------------------------------------

class SchedulerStatus(BaseModel):
    """Scheduler status response."""
    running: bool
    poll_interval_seconds: int
    skip_analysis: bool


@app.get("/admin/scheduler/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """Get the current scheduler status."""
    from .services.scheduler import is_scheduler_running, POLL_INTERVAL, SKIP_ANALYSIS
    
    return SchedulerStatus(
        running=is_scheduler_running(),
        poll_interval_seconds=POLL_INTERVAL,
        skip_analysis=SKIP_ANALYSIS,
    )


@app.post("/admin/scheduler/poll")
async def trigger_poll():
    """Manually trigger a poll (for testing/admin)."""
    from .services.scheduler import trigger_poll_now
    
    await trigger_poll_now()
    return {"message": "Poll triggered", "status": "ok"}


# ---------------------------------------------------------------------------
# Server-Sent Events (SSE) endpoint
# ---------------------------------------------------------------------------

@app.get("/stream")
async def stream_analyses():
    """
    Server-Sent Events endpoint for real-time analysis updates.
    
    Streams new relevant analyses as they are processed.
    
    Events:
    - `connected`: Sent on initial connection
    - `analysis`: Sent when a new relevant analysis is available
    - Keepalive comments sent every 30 seconds
    
    Usage:
        curl -N http://localhost:8000/stream
        
    Or in JavaScript:
        const evtSource = new EventSource('/stream');
        evtSource.addEventListener('analysis', (e) => {
            const analysis = JSON.parse(e.data);
            console.log('New analysis:', analysis);
        });
    """
    from .services.events import event_generator
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.get("/admin/sse/status")
async def get_sse_status():
    """Get the current SSE subscriber count."""
    from .services.events import get_subscriber_count
    
    return {
        "subscribers": get_subscriber_count(),
    }


@app.post("/admin/sse/test")
async def publish_test_event():
    """Publish a test event to all SSE subscribers (for testing)."""
    from .services.events import publish_analysis, get_subscriber_count
    
    subscriber_count = get_subscriber_count()
    
    if subscriber_count == 0:
        return {
            "status": "no_subscribers",
            "message": "No SSE subscribers connected. Open /stream first.",
        }
    
    # Publish test event
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
            {"vertical": "Technology", "rationale": "Test impact", "confidence_0_1": 0.92}
        ],
        "tickers": [
            {"ticker_or_etf": "QQQ", "direction_up_down_mixed": "up", "mechanism": "Test"}
        ],
        "base_case_summary": "This is a test analysis for SSE demonstration.",
    }
    
    await publish_analysis(test_analysis)
    
    return {
        "status": "published",
        "message": f"Test event sent to {subscriber_count} subscriber(s)",
    }

