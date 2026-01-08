"""
FastAPI server for TrumpDump MVP.

Endpoints:
- GET /                    - Basic status
- GET /health              - Detailed health check with DB and scheduler status
- GET /latest              - Returns the latest relevant analysis
- GET /latest-with-tickers - Returns most recent analysis with ticker impacts
- GET /history             - Returns recent analyses (relevant first)
- GET /stream              - Server-Sent Events for real-time updates

Run from the MVP/ directory:
    cd MVP
    pip install -r backend/requirements.txt
    uvicorn backend.app.main:app --reload --port 8000

The server will start at http://localhost:8000
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .db import (
    get_latest_relevant_analysis,
    get_latest_analysis,
    get_latest_analysis_with_tickers,
    get_whitehouse_post_by_id,
    init_db,
    get_connection,
    check_db_connection,
    DEFAULT_MIN_RELEVANCE_SCORE,
    DEFAULT_MIN_TOP_VERTICAL_CONF,
    USE_POSTGRES,
)

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from Environment
# ---------------------------------------------------------------------------

# CORS origins (comma-separated list)
DEFAULT_ORIGINS = "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://127.0.0.1:3000"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",")

# Admin API key for protected endpoints
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

# App version
APP_VERSION = "0.2.0"

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TrumpDump API",
    description="Market impact analysis of White House announcements",
    version=APP_VERSION,
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Handle rate limit exceeded errors
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return HTTPException(
        status_code=429,
        detail={
            "message": "Rate limit exceeded",
            "retry_after": str(exc.detail),
        }
    )

# CORS middleware with configurable origins
logger.info(f"Configuring CORS for origins: {ALLOWED_ORIGINS}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize database and scheduler on startup
@app.on_event("startup")
async def startup_event():
    """Run database migrations and start scheduler on startup."""
    logger.info("Starting TrumpDump API...")
    logger.info(f"Database mode: {'PostgreSQL' if USE_POSTGRES else 'SQLite'}")
    
    init_db()
    logger.info("Database initialized")
    
    # Start scheduler unless disabled
    if os.getenv("DISABLE_SCHEDULER", "false").lower() != "true":
        from .services.scheduler import start_scheduler
        start_scheduler(app)
    else:
        logger.info("Scheduler disabled via DISABLE_SCHEDULER env var")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler on shutdown."""
    logger.info("Shutting down TrumpDump API...")
    from .services.scheduler import stop_scheduler
    stop_scheduler()


# ---------------------------------------------------------------------------
# Admin Authentication
# ---------------------------------------------------------------------------

async def verify_admin_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """
    Verify admin API key for protected endpoints.
    
    If ADMIN_API_KEY is not set, admin endpoints are open (for local dev).
    If set, requests must include X-API-Key header with matching value.
    """
    if ADMIN_API_KEY and x_api_key != ADMIN_API_KEY:
        raise HTTPException(
            status_code=403,
            detail={"message": "Invalid or missing API key"}
        )


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
    content_preview: Optional[str] = None  # First 500 chars for preview
    content: Optional[str] = None          # Full original post content


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
    """Detailed health check response."""
    status: str
    version: str
    database: str
    database_connected: bool
    scheduler_running: bool


class BasicStatus(BaseModel):
    """Basic status response."""
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
    
    # Get linked post info with content
    post_info = None
    post = get_whitehouse_post_by_id(row["post_id"])
    if post:
        content = post.get("content", "")
        content_preview = content[:500] + "..." if len(content) > 500 else content
        post_info = PostInfo(
            id=post["id"],
            url=post["url"],
            title=post.get("title"),
            content_preview=content_preview if content else None,
            content=content if content else None,
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
    from .db import _get_placeholder, USE_POSTGRES
    
    conn = get_connection()
    cur = conn.cursor()
    ph = _get_placeholder()
    
    if relevant_first:
        # Sort by relevance (relevant first), then by recency
        cur.execute(
            f"""
            SELECT id, post_id, created_at_utc, relevance_score,
                   top_vertical, top_vertical_conf
            FROM analyses
            ORDER BY 
                CASE 
                    WHEN relevance_score >= {ph} AND top_vertical_conf >= {ph} THEN 0 
                    ELSE 1 
                END,
                created_at_utc DESC,
                id DESC
            LIMIT {ph}
            """,
            (DEFAULT_MIN_RELEVANCE_SCORE, DEFAULT_MIN_TOP_VERTICAL_CONF, limit),
        )
    else:
        cur.execute(
            f"""
            SELECT id, post_id, created_at_utc, relevance_score,
                   top_vertical, top_vertical_conf
            FROM analyses
            ORDER BY created_at_utc DESC, id DESC
            LIMIT {ph}
            """,
            (limit,),
        )
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return [dict(row) for row in rows]


def count_analyses() -> int:
    """Get total count of analyses."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM analyses")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["count"] if row else 0


# ---------------------------------------------------------------------------
# Health & Status Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_model=BasicStatus)
async def root():
    """Basic status endpoint - always returns OK if server is running."""
    return BasicStatus(status="ok", version=APP_VERSION)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Detailed health check endpoint.
    
    Returns database connection status and scheduler status.
    Use this for monitoring and load balancer health checks.
    """
    from .services.scheduler import is_scheduler_running
    
    db_connected = check_db_connection()
    scheduler_running = is_scheduler_running()
    
    # Determine overall status
    status = "ok" if db_connected else "degraded"
    
    return HealthResponse(
        status=status,
        version=APP_VERSION,
        database="postgresql" if USE_POSTGRES else "sqlite",
        database_connected=db_connected,
        scheduler_running=scheduler_running,
    )


# ---------------------------------------------------------------------------
# Public API Endpoints (with rate limiting)
# ---------------------------------------------------------------------------

@app.get("/latest", response_model=LatestAnalysis)
@limiter.limit("60/minute")
async def get_latest(
    request: Request,
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


@app.get("/latest-with-tickers", response_model=LatestAnalysis)
@limiter.limit("60/minute")
async def get_latest_with_tickers(request: Request):
    """
    Get the most recent analysis that has ticker impacts.
    
    Use this to show "last impactful" analysis when the current
    latest analysis has no specific ticker recommendations.
    """
    row = get_latest_analysis_with_tickers()
    
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No analysis with ticker impacts found",
                "hint": "No analyses have been recorded with specific ticker recommendations yet",
            }
        )
    
    return parse_analysis_row(row)


@app.get("/history", response_model=HistoryResponse)
@limiter.limit("30/minute")
async def get_history(
    request: Request,
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
@limiter.limit("60/minute")
async def get_analysis_detail(request: Request, analysis_id: int):
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


# ---------------------------------------------------------------------------
# Admin/Scheduler endpoints (protected)
# ---------------------------------------------------------------------------

class SchedulerStatus(BaseModel):
    """Scheduler status response."""
    running: bool
    poll_interval_seconds: int
    skip_analysis: bool


@app.get("/admin/scheduler/status", response_model=SchedulerStatus, dependencies=[Depends(verify_admin_key)])
async def get_scheduler_status():
    """Get the current scheduler status. Requires admin API key if configured."""
    from .services.scheduler import is_scheduler_running, POLL_INTERVAL, SKIP_ANALYSIS
    
    return SchedulerStatus(
        running=is_scheduler_running(),
        poll_interval_seconds=POLL_INTERVAL,
        skip_analysis=SKIP_ANALYSIS,
    )


@app.post("/admin/scheduler/poll", dependencies=[Depends(verify_admin_key)])
async def trigger_poll():
    """Manually trigger a poll. Requires admin API key if configured."""
    from .services.scheduler import trigger_poll_now
    
    await trigger_poll_now()
    return {"message": "Poll triggered", "status": "ok"}


@app.get("/admin/sse/status", dependencies=[Depends(verify_admin_key)])
async def get_sse_status():
    """Get the current SSE subscriber count. Requires admin API key if configured."""
    from .services.events import get_subscriber_count
    
    return {
        "subscribers": get_subscriber_count(),
    }


@app.post("/admin/sse/test", dependencies=[Depends(verify_admin_key)])
async def publish_test_event():
    """Publish a test event to all SSE subscribers. Requires admin API key if configured."""
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
