# Services package
from .whitehouse_scraper import poll_whitehouse_once, WhiteHousePost
from .analyzer import (
    extract_facts,
    market_impact,
    analyze_whitehouse_post,
    PostMeta,
    FACTS_SCHEMA,
    MARKET_SCHEMA,
)
from .relevance import (
    passes_heuristic,
    is_relevant,
    should_analyze,
    should_serve,
    get_heuristic_reason,
    get_relevance_reason,
    # Thresholds (for reference/override)
    MIN_CONTENT_LENGTH,
    MIN_RELEVANCE_SCORE,
    MIN_TOP_VERTICAL_CONFIDENCE,
)
from .scheduler import (
    start_scheduler,
    stop_scheduler,
    is_scheduler_running,
    trigger_poll_now,
    POLL_INTERVAL,
)
from .events import (
    subscribe,
    unsubscribe,
    publish_analysis,
    event_generator,
    notify_new_analysis,
    get_subscriber_count,
)

__all__ = [
    # Scraper
    "poll_whitehouse_once",
    "WhiteHousePost",
    # Analyzer
    "extract_facts",
    "market_impact",
    "analyze_whitehouse_post",
    "PostMeta",
    "FACTS_SCHEMA",
    "MARKET_SCHEMA",
    # Relevance gates
    "passes_heuristic",
    "is_relevant",
    "should_analyze",
    "should_serve",
    "get_heuristic_reason",
    "get_relevance_reason",
    "MIN_CONTENT_LENGTH",
    "MIN_RELEVANCE_SCORE",
    "MIN_TOP_VERTICAL_CONFIDENCE",
    # Scheduler
    "start_scheduler",
    "stop_scheduler",
    "is_scheduler_running",
    "trigger_poll_now",
    "POLL_INTERVAL",
    # Events (SSE)
    "subscribe",
    "unsubscribe",
    "publish_analysis",
    "event_generator",
    "notify_new_analysis",
    "get_subscriber_count",
]

