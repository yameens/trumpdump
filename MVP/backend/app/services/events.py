"""
Event bus for Server-Sent Events (SSE).

Maintains an in-memory asyncio queue of new relevant analyses.
Multiple SSE clients can subscribe and receive real-time updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Set
from weakref import WeakSet

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global event management
# ---------------------------------------------------------------------------

# Set of all active subscriber queues (using WeakSet for auto-cleanup)
_subscribers: Set[asyncio.Queue] = set()
_lock = asyncio.Lock()


async def subscribe() -> asyncio.Queue:
    """
    Subscribe to analysis events.
    Returns a queue that will receive new analysis events.
    """
    queue: asyncio.Queue = asyncio.Queue()
    async with _lock:
        _subscribers.add(queue)
        logger.info(f"📡 New SSE subscriber (total: {len(_subscribers)})")
    return queue


async def unsubscribe(queue: asyncio.Queue) -> None:
    """
    Unsubscribe from analysis events.
    """
    async with _lock:
        _subscribers.discard(queue)
        logger.info(f"📡 SSE subscriber disconnected (remaining: {len(_subscribers)})")


async def publish_analysis(analysis_data: Dict[str, Any]) -> None:
    """
    Publish a new analysis to all subscribers.
    
    Args:
        analysis_data: The analysis data to broadcast (will be JSON serialized)
    """
    async with _lock:
        subscriber_count = len(_subscribers)
        if subscriber_count == 0:
            logger.debug("No SSE subscribers to notify")
            return
        
        logger.info(f"📤 Broadcasting analysis to {subscriber_count} subscriber(s)")
        
        # Create copies to avoid modification during iteration
        dead_queues = []
        
        for queue in _subscribers:
            try:
                # Non-blocking put with a small timeout
                queue.put_nowait(analysis_data)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full, skipping")
            except Exception as e:
                logger.error(f"Error publishing to subscriber: {e}")
                dead_queues.append(queue)
        
        # Remove dead queues
        for queue in dead_queues:
            _subscribers.discard(queue)


def get_subscriber_count() -> int:
    """Get the current number of active subscribers."""
    return len(_subscribers)


# ---------------------------------------------------------------------------
# SSE event generator
# ---------------------------------------------------------------------------

async def event_generator() -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted events.
    
    Yields events in the format:
        data: {JSON}\n\n
    
    Also sends periodic keepalive comments to prevent connection timeout.
    """
    queue = await subscribe()
    
    try:
        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'subscribers': get_subscriber_count()})}\n\n"
        
        while True:
            try:
                # Wait for new analysis with timeout (for keepalive)
                analysis = await asyncio.wait_for(queue.get(), timeout=30.0)
                
                # Format as SSE event
                event_data = json.dumps(analysis)
                yield f"event: analysis\ndata: {event_data}\n\n"
                
            except asyncio.TimeoutError:
                # Send keepalive comment (SSE comment starts with :)
                yield ": keepalive\n\n"
                
    except asyncio.CancelledError:
        logger.info("SSE connection cancelled")
        raise
    except Exception as e:
        logger.error(f"SSE generator error: {e}")
        raise
    finally:
        await unsubscribe(queue)


# ---------------------------------------------------------------------------
# Helper for scheduler integration
# ---------------------------------------------------------------------------

async def notify_new_analysis(
    analysis_id: int,
    post_id: int,
    relevance_score: int,
    top_vertical: str,
    top_vertical_conf: float,
    market_json: Dict[str, Any],
    post_info: Dict[str, Any] = None,
) -> None:
    """
    Helper to notify subscribers of a new relevant analysis.
    Called from the scheduler when a relevant analysis is stored.
    """
    # Build the notification payload
    payload = {
        "id": analysis_id,
        "post_id": post_id,
        "relevance_score": relevance_score,
        "top_vertical": top_vertical,
        "top_vertical_conf": top_vertical_conf,
        "post": post_info,
        "verticals": market_json.get("dominant_verticals_ranked", []),
        "tickers": market_json.get("tickers_ranked", []),
        "base_case_summary": market_json.get("base_case_summary"),
    }
    
    await publish_analysis(payload)

