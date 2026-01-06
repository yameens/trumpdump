"""
Scheduler service for automated White House polling and analysis.

Uses APScheduler to run periodic tasks:
1. Poll White House for new posts
2. If new post found and passes heuristic, analyze it
3. Store analysis in database

Usage:
    from backend.app.services.scheduler import start_scheduler
    
    @app.on_event("startup")
    async def startup():
        start_scheduler(app)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from fastapi import FastAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Polling interval in seconds (can be overridden via environment)
DEFAULT_POLL_INTERVAL = 60  # 1 minute
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL))

# Whether to skip OpenAI analysis (for testing without API key)
SKIP_ANALYSIS = os.getenv("SKIP_ANALYSIS", "false").lower() == "true"

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


# ---------------------------------------------------------------------------
# Polling job
# ---------------------------------------------------------------------------

async def poll_and_analyze_job():
    """
    Main polling job that runs on schedule.
    
    1. Polls White House for new posts
    2. If new post found, checks heuristic
    3. If heuristic passes, runs analysis
    4. Stores analysis in database
    """
    logger.info("🔄 Polling White House for new posts...")
    
    try:
        # Import here to avoid circular imports
        from .whitehouse_scraper import poll_whitehouse_once
        from .relevance import passes_heuristic, is_relevant, get_heuristic_reason
        from ..db import (
            persist_analysis,
            get_whitehouse_post_by_url,
            insert_whitehouse_post,
        )
        
        # Step 1: Poll for new post
        new_post = poll_whitehouse_once()
        
        if new_post is None:
            logger.info("   No new post found.")
            return
        
        logger.info(f"📰 NEW POST: {new_post.title}")
        logger.info(f"   URL: {new_post.url}")
        
        # Get the post_id from database (poll_whitehouse_once already inserted it)
        db_post = get_whitehouse_post_by_url(new_post.url)
        if db_post is None:
            logger.error("   ❌ Post not found in database after insertion")
            return
        
        post_id = db_post["id"]
        logger.info(f"   Post ID: {post_id}")
        
        # Step 2: Check heuristic
        content = new_post.content
        if new_post.title:
            content = f"{new_post.title}\n\n{content}"
        
        if not passes_heuristic(content):
            reason = get_heuristic_reason(content)
            logger.info(f"   ⏭️  Skipping analysis: {reason}")
            return
        
        logger.info("   ✅ Heuristic passed - proceeding with analysis")
        
        # Step 3: Run analysis (if not skipped)
        if SKIP_ANALYSIS:
            logger.info("   ⏭️  SKIP_ANALYSIS=true, skipping OpenAI analysis")
            return
        
        try:
            from .analyzer import analyze_whitehouse_post
            
            logger.info("   🧠 Running OpenAI analysis...")
            market_json = analyze_whitehouse_post(new_post)
            
            # Step 4: Store analysis
            analysis_id = persist_analysis(post_id, market_json)
            logger.info(f"   💾 Analysis stored with ID: {analysis_id}")
            
            # Log relevance info
            relevance_score = market_json.get("relevance_score_0_100", 0)
            verticals = market_json.get("dominant_verticals_ranked", [])
            top_vertical = verticals[0] if verticals else {}
            top_vertical_name = top_vertical.get('vertical', 'N/A')
            top_vertical_conf = top_vertical.get('confidence_0_1', 0)
            
            logger.info(f"   📊 Relevance: {relevance_score}/100")
            logger.info(f"   📈 Top vertical: {top_vertical_name} (conf: {top_vertical_conf:.2f})")
            
            # Check if it meets relevance threshold
            if is_relevant(market_json):
                logger.info("   🎯 Analysis is RELEVANT and will be served")
                
                # Notify SSE subscribers of new relevant analysis
                try:
                    from .events import notify_new_analysis
                    
                    await notify_new_analysis(
                        analysis_id=analysis_id,
                        post_id=post_id,
                        relevance_score=relevance_score,
                        top_vertical=top_vertical_name,
                        top_vertical_conf=top_vertical_conf,
                        market_json=market_json,
                        post_info={
                            "id": post_id,
                            "url": new_post.url,
                            "title": new_post.title,
                        },
                    )
                    logger.info("   📡 SSE subscribers notified")
                except Exception as e:
                    logger.error(f"   ⚠️ Failed to notify SSE subscribers: {e}")
            else:
                logger.info("   📦 Analysis stored but below relevance threshold")
                
        except Exception as e:
            logger.error(f"   ❌ Analysis failed: {type(e).__name__}: {e}")
            # Don't re-raise - we want the scheduler to continue
            
    except Exception as e:
        logger.error(f"❌ Polling job error: {type(e).__name__}: {e}")
        # Don't re-raise - we want the scheduler to continue


def _sync_poll_and_analyze():
    """Synchronous wrapper for the async job."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # If we're already in an async context, create a task
        asyncio.create_task(poll_and_analyze_job())
    else:
        loop.run_until_complete(poll_and_analyze_job())


# ---------------------------------------------------------------------------
# Scheduler management
# ---------------------------------------------------------------------------

def start_scheduler(app: Optional["FastAPI"] = None) -> AsyncIOScheduler:
    """
    Start the background scheduler.
    
    Args:
        app: Optional FastAPI app instance (for lifecycle management)
    
    Returns:
        The scheduler instance
    """
    global _scheduler
    
    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running")
        return _scheduler
    
    logger.info("=" * 60)
    logger.info("🚀 Starting TrumpDump Scheduler")
    logger.info(f"   Poll interval: {POLL_INTERVAL} seconds")
    logger.info(f"   Skip analysis: {SKIP_ANALYSIS}")
    logger.info("=" * 60)
    
    _scheduler = AsyncIOScheduler()
    
    # Add the polling job
    _scheduler.add_job(
        poll_and_analyze_job,
        trigger=IntervalTrigger(seconds=POLL_INTERVAL),
        id="whitehouse_poll",
        name="White House Polling Job",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
    )
    
    # Start the scheduler
    _scheduler.start()
    
    # Run immediately on startup (don't wait for first interval)
    asyncio.create_task(poll_and_analyze_job())
    
    logger.info("✅ Scheduler started successfully")
    
    return _scheduler


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler
    
    if _scheduler is not None:
        logger.info("🛑 Stopping scheduler...")
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("✅ Scheduler stopped")


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Get the current scheduler instance."""
    return _scheduler


def is_scheduler_running() -> bool:
    """Check if the scheduler is running."""
    return _scheduler is not None and _scheduler.running


# ---------------------------------------------------------------------------
# Manual trigger (for testing)
# ---------------------------------------------------------------------------

async def trigger_poll_now():
    """Manually trigger a poll (for testing/admin purposes)."""
    logger.info("🔧 Manual poll triggered")
    await poll_and_analyze_job()


# ---------------------------------------------------------------------------
# Standalone mode (for testing without FastAPI)
# ---------------------------------------------------------------------------

async def _run_standalone():
    """Run scheduler in standalone mode for testing."""
    logger.info("Running scheduler in standalone mode...")
    
    # Initialize database
    from ..db import init_db
    init_db()
    
    # Start scheduler
    start_scheduler()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        stop_scheduler()


if __name__ == "__main__":
    # Run in standalone mode
    asyncio.run(_run_standalone())

