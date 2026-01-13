"""
Database module for TrumpDump MVP.

Supports both PostgreSQL (production) and SQLite (local development).
Uses DATABASE_URL environment variable to determine which to use.

If DATABASE_URL starts with "postgres://" or "postgresql://", uses PostgreSQL.
Otherwise, uses SQLite with the provided path or default location.

Tables:
- posts: Unified table for all scraped posts (whitehouse, truthsocial, etc.)
- analyses: Analysis results linked to posts
- whitehouse_posts: Legacy table (kept for backward compatibility)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Check if we should use PostgreSQL
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

# Default SQLite path for local development
DEFAULT_SQLITE_PATH = Path(__file__).parent.parent.parent / "trumpdump.db"

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    logger.info("Using PostgreSQL database")
else:
    import sqlite3
    logger.info(f"Using SQLite database at {DEFAULT_SQLITE_PATH}")


# ---------------------------------------------------------------------------
# Constants for sources
# ---------------------------------------------------------------------------

SOURCE_WHITEHOUSE = "whitehouse"
SOURCE_TRUTHSOCIAL = "truthsocial"


# ---------------------------------------------------------------------------
# Connection Management
# ---------------------------------------------------------------------------

def get_connection(db_path: Optional[str] = None) -> Any:
    """
    Get a database connection.
    
    For PostgreSQL: Uses DATABASE_URL environment variable.
    For SQLite: Uses db_path or DEFAULT_SQLITE_PATH.
    
    Returns a connection object with dict-like row access.
    """
    if USE_POSTGRES:
        # PostgreSQL connection
        # Handle Railway's postgres:// vs postgresql://
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        return conn
    else:
        # SQLite connection
        path = db_path or str(DEFAULT_SQLITE_PATH)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row  # enables dict-like row access
        return conn


def _row_to_dict(row: Any) -> Optional[Dict[str, Any]]:
    """Convert a database row to a plain dict, or None if row is None."""
    if row is None:
        return None
    if USE_POSTGRES:
        # RealDictRow is already dict-like
        return dict(row)
    else:
        # sqlite3.Row needs conversion
        return dict(row)


def _get_placeholder() -> str:
    """Get the parameter placeholder for the current database."""
    return "%s" if USE_POSTGRES else "?"


def _get_returning_id() -> str:
    """Get the RETURNING clause for the current database."""
    return " RETURNING id" if USE_POSTGRES else ""


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

def run_migrations(db_path: Optional[str] = None) -> None:
    """
    Create tables if they don't exist. Idempotent - safe to call on every startup.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    if USE_POSTGRES:
        # PostgreSQL schema
        
        # Legacy whitehouse_posts table (for backward compatibility)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS whitehouse_posts (
                id SERIAL PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                content TEXT,
                scraped_at_utc BIGINT NOT NULL
            );
        """)
        
        # NEW: Unified posts table for all sources
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                source TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                content TEXT,
                scraped_at_utc BIGINT NOT NULL,
                is_retruth BOOLEAN DEFAULT FALSE
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                created_at_utc BIGINT NOT NULL,
                relevance_score INTEGER,
                market_json TEXT,
                tickers_json TEXT,
                top_vertical TEXT,
                top_vertical_conf REAL
            );
        """)
        
        # FIX: Drop old foreign key constraint that references whitehouse_posts
        # and add new constraint that references unified posts table
        cur.execute("""
            DO $$
            BEGIN
                -- Drop old constraint if it exists (references whitehouse_posts)
                IF EXISTS (
                    SELECT 1 FROM information_schema.table_constraints 
                    WHERE constraint_name = 'analyses_post_id_fkey' 
                    AND table_name = 'analyses'
                ) THEN
                    ALTER TABLE analyses DROP CONSTRAINT analyses_post_id_fkey;
                END IF;
                
                -- Add new constraint referencing posts table (if not exists)
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints 
                    WHERE constraint_name = 'analyses_post_id_posts_fkey' 
                    AND table_name = 'analyses'
                ) THEN
                    ALTER TABLE analyses 
                    ADD CONSTRAINT analyses_post_id_posts_fkey 
                    FOREIGN KEY (post_id) REFERENCES posts(id);
                END IF;
            END $$;
        """)

        # Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_whitehouse_posts_scraped_at
            ON whitehouse_posts(scraped_at_utc DESC);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_scraped_at
            ON posts(scraped_at_utc DESC);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_source
            ON posts(source);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyses_created_at
            ON analyses(created_at_utc DESC);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyses_relevance
            ON analyses(relevance_score DESC, top_vertical_conf DESC);
        """)
        
        # Migrate data from whitehouse_posts to posts if not already done
        cur.execute("""
            INSERT INTO posts (source, url, title, content, scraped_at_utc, is_retruth)
            SELECT 'whitehouse', url, title, content, scraped_at_utc, FALSE
            FROM whitehouse_posts
            WHERE NOT EXISTS (
                SELECT 1 FROM posts WHERE posts.url = whitehouse_posts.url
            )
            ON CONFLICT (url) DO NOTHING;
        """)
        
    else:
        # SQLite schema
        
        # Legacy whitehouse_posts table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS whitehouse_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                content TEXT,
                scraped_at_utc INTEGER NOT NULL
            );
        """)
        
        # NEW: Unified posts table for all sources
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                content TEXT,
                scraped_at_utc INTEGER NOT NULL,
                is_retruth INTEGER DEFAULT 0
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                created_at_utc INTEGER NOT NULL,
                relevance_score INTEGER,
                market_json TEXT,
                tickers_json TEXT,
                top_vertical TEXT,
                top_vertical_conf REAL
            );
        """)

        # Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_whitehouse_posts_scraped_at
            ON whitehouse_posts(scraped_at_utc DESC);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_scraped_at
            ON posts(scraped_at_utc DESC);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_source
            ON posts(source);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyses_created_at
            ON analyses(created_at_utc DESC);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyses_relevance
            ON analyses(relevance_score DESC, top_vertical_conf DESC);
        """)
        
        # Migrate data from whitehouse_posts to posts if not already done
        cur.execute("""
            INSERT OR IGNORE INTO posts (source, url, title, content, scraped_at_utc, is_retruth)
            SELECT 'whitehouse', url, title, content, scraped_at_utc, 0
            FROM whitehouse_posts
            WHERE url NOT IN (SELECT url FROM posts);
        """)

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Database migrations completed successfully")


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

def check_db_connection() -> bool:
    """
    Check if the database connection is working.
    Returns True if connected, False otherwise.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


# ---------------------------------------------------------------------------
# UNIFIED posts table helpers (NEW)
# ---------------------------------------------------------------------------

def insert_post(
    source: str,
    url: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    scraped_at_utc: Optional[int] = None,
    is_retruth: bool = False,
    db_path: Optional[str] = None,
) -> int:
    """
    Insert a new post into the unified posts table. Returns the inserted row id.
    
    Args:
        source: Source of the post (e.g., 'whitehouse', 'truthsocial')
        url: Unique URL of the post
        title: Optional title
        content: Optional content text
        scraped_at_utc: Unix timestamp (defaults to now)
        is_retruth: Whether this is a retruth/repost (for Truth Social)
        db_path: Optional database path (SQLite only)
    
    If a post with the same URL already exists, returns the existing row id.
    """
    if scraped_at_utc is None:
        scraped_at_utc = int(time.time())

    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()
    
    # Convert bool to int for SQLite
    is_retruth_val = is_retruth if USE_POSTGRES else int(is_retruth)

    try:
        if USE_POSTGRES:
            cur.execute(
                f"""
                INSERT INTO posts (source, url, title, content, scraped_at_utc, is_retruth)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (url) DO NOTHING
                RETURNING id
                """,
                (source, url, title, content, scraped_at_utc, is_retruth_val),
            )
            result = cur.fetchone()
            if result:
                row_id = result["id"]
            else:
                # URL already exists, fetch existing id
                cur.execute(f"SELECT id FROM posts WHERE url = {ph}", (url,))
                row = cur.fetchone()
                row_id = row["id"] if row else -1
        else:
            # SQLite
            try:
                cur.execute(
                    f"""
                    INSERT INTO posts (source, url, title, content, scraped_at_utc, is_retruth)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (source, url, title, content, scraped_at_utc, is_retruth_val),
                )
                row_id = cur.lastrowid
            except sqlite3.IntegrityError:
                # URL already exists, fetch existing id
                cur.execute(f"SELECT id FROM posts WHERE url = {ph}", (url,))
                row = cur.fetchone()
                row_id = row["id"] if row else -1
        
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return row_id


def get_post_by_url(
    url: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get a post by its URL from the unified posts table.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()

    cur.execute(
        f"""
        SELECT id, source, url, title, content, scraped_at_utc, is_retruth
        FROM posts
        WHERE url = {ph}
        """,
        (url,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return _row_to_dict(row)


def get_post_by_id(
    post_id: int,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get a post by its ID from the unified posts table.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()

    cur.execute(
        f"""
        SELECT id, source, url, title, content, scraped_at_utc, is_retruth
        FROM posts
        WHERE id = {ph}
        """,
        (post_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return _row_to_dict(row)


def get_latest_post(
    source: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get the most recently scraped post.
    
    Args:
        source: Optional filter by source (e.g., 'whitehouse', 'truthsocial')
        db_path: Optional database path (SQLite only)
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()

    if source:
        cur.execute(
            f"""
            SELECT id, source, url, title, content, scraped_at_utc, is_retruth
            FROM posts
            WHERE source = {ph}
            ORDER BY scraped_at_utc DESC
            LIMIT 1
            """,
            (source,),
        )
    else:
        cur.execute("""
            SELECT id, source, url, title, content, scraped_at_utc, is_retruth
            FROM posts
            ORDER BY scraped_at_utc DESC
            LIMIT 1
        """)
    
    row = cur.fetchone()
    cur.close()
    conn.close()

    return _row_to_dict(row)


def get_posts_by_source(
    source: str,
    limit: int = 20,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get posts filtered by source, ordered by most recent first.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()

    cur.execute(
        f"""
        SELECT id, source, url, title, content, scraped_at_utc, is_retruth
        FROM posts
        WHERE source = {ph}
        ORDER BY scraped_at_utc DESC
        LIMIT {ph}
        """,
        (source, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Legacy whitehouse_posts helpers (kept for backward compatibility)
# ---------------------------------------------------------------------------

def insert_whitehouse_post(
    url: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    scraped_at_utc: Optional[int] = None,
    db_path: Optional[str] = None,
) -> int:
    """
    Insert a new whitehouse post. Returns the inserted row id.
    
    NOTE: This now inserts into the unified 'posts' table with source='whitehouse'.
    The legacy whitehouse_posts table is kept for backward compatibility.
    """
    # Insert into unified posts table
    return insert_post(
        source=SOURCE_WHITEHOUSE,
        url=url,
        title=title,
        content=content,
        scraped_at_utc=scraped_at_utc,
        is_retruth=False,
        db_path=db_path,
    )


def get_latest_whitehouse_post(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get the most recently scraped whitehouse post.
    """
    return get_latest_post(source=SOURCE_WHITEHOUSE, db_path=db_path)


def get_whitehouse_post_by_id(
    post_id: int,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get a whitehouse post by its id.
    """
    post = get_post_by_id(post_id, db_path)
    if post and post.get("source") == SOURCE_WHITEHOUSE:
        return post
    return None


def get_whitehouse_post_by_url(
    url: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get a whitehouse post by its URL.
    """
    post = get_post_by_url(url, db_path)
    if post and post.get("source") == SOURCE_WHITEHOUSE:
        return post
    return None


# ---------------------------------------------------------------------------
# Truth Social posts helpers (NEW)
# ---------------------------------------------------------------------------

def insert_truthsocial_post(
    url: str,
    content: str,
    is_retruth: bool = False,
    title: Optional[str] = None,
    scraped_at_utc: Optional[int] = None,
    db_path: Optional[str] = None,
) -> int:
    """
    Insert a new Truth Social post. Returns the inserted row id.
    """
    return insert_post(
        source=SOURCE_TRUTHSOCIAL,
        url=url,
        title=title,
        content=content,
        scraped_at_utc=scraped_at_utc,
        is_retruth=is_retruth,
        db_path=db_path,
    )


def get_latest_truthsocial_post(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get the most recently scraped Truth Social post.
    """
    return get_latest_post(source=SOURCE_TRUTHSOCIAL, db_path=db_path)


def get_truthsocial_post_by_url(
    url: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get a Truth Social post by its URL.
    """
    post = get_post_by_url(url, db_path)
    if post and post.get("source") == SOURCE_TRUTHSOCIAL:
        return post
    return None


# ---------------------------------------------------------------------------
# analyses helpers
# ---------------------------------------------------------------------------

def insert_analysis(
    post_id: int,
    relevance_score: Optional[int] = None,
    market_json: Optional[str] = None,
    tickers_json: Optional[str] = None,
    top_vertical: Optional[str] = None,
    top_vertical_conf: Optional[float] = None,
    created_at_utc: Optional[int] = None,
    db_path: Optional[str] = None,
) -> int:
    """
    Insert a new analysis for a post. Returns the inserted row id.
    
    market_json and tickers_json should be JSON strings (use json.dumps()).
    
    Note: Prefer using persist_analysis() which automatically extracts fields
    from a market_json dict.
    """
    if created_at_utc is None:
        created_at_utc = int(time.time())

    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()

    if USE_POSTGRES:
        cur.execute(
            f"""
            INSERT INTO analyses (
                post_id, created_at_utc, relevance_score,
                market_json, tickers_json, top_vertical, top_vertical_conf
            )
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            RETURNING id
            """,
            (
                post_id,
                created_at_utc,
                relevance_score,
                market_json,
                tickers_json,
                top_vertical,
                top_vertical_conf,
            ),
        )
        row_id = cur.fetchone()["id"]
    else:
        cur.execute(
            f"""
            INSERT INTO analyses (
                post_id, created_at_utc, relevance_score,
                market_json, tickers_json, top_vertical, top_vertical_conf
            )
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
            (
                post_id,
                created_at_utc,
                relevance_score,
                market_json,
                tickers_json,
                top_vertical,
                top_vertical_conf,
            ),
        )
        row_id = cur.lastrowid

    conn.commit()
    cur.close()
    conn.close()

    return row_id


def persist_analysis(
    post_id: int,
    market_json: Dict[str, Any],
    db_path: Optional[str] = None,
) -> int:
    """
    Persist a market analysis to the database, extracting key fields automatically.
    
    This is the preferred way to store analysis results from the analyzer pipeline.
    
    Extracts from market_json:
    - relevance_score from "relevance_score_0_100"
    - top_vertical and top_vertical_conf from "dominant_verticals_ranked[0]"
    - tickers_json from "tickers_ranked" (stored separately for fast reads)
    - Full market_json stored as TEXT
    
    Args:
        post_id: ID of the post this analysis is for
        market_json: The market impact analysis dict from analyzer
        db_path: Optional path to database
    
    Returns:
        The inserted analysis row id
    """
    # Extract relevance score
    relevance_score = market_json.get("relevance_score_0_100")
    
    # Extract top vertical info
    top_vertical = None
    top_vertical_conf = None
    verticals = market_json.get("dominant_verticals_ranked")
    if verticals and isinstance(verticals, list) and len(verticals) > 0:
        top = verticals[0]
        if isinstance(top, dict):
            top_vertical = top.get("vertical")
            top_vertical_conf = top.get("confidence_0_1")
    
    # Extract tickers_ranked separately for faster reads
    tickers_ranked = market_json.get("tickers_ranked")
    tickers_json_str = json.dumps(tickers_ranked) if tickers_ranked else None
    
    # Store full market_json as TEXT
    market_json_str = json.dumps(market_json)
    
    # Insert using the base function
    return insert_analysis(
        post_id=post_id,
        relevance_score=relevance_score,
        market_json=market_json_str,
        tickers_json=tickers_json_str,
        top_vertical=top_vertical,
        top_vertical_conf=top_vertical_conf,
        db_path=db_path,
    )


# Default relevance thresholds (matching relevance.py)
DEFAULT_MIN_RELEVANCE_SCORE = 50
DEFAULT_MIN_TOP_VERTICAL_CONF = 0.65


def get_latest_relevant_analysis(
    min_score: Optional[int] = None,
    min_conf: Optional[float] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get the most recent analysis that meets the minimum relevance score
    and top vertical confidence thresholds.
    
    Args:
        min_score: Minimum relevance_score_0_100 (default: 50)
        min_conf: Minimum top_vertical_conf (default: 0.65)
        db_path: Optional path to database
    
    Returns a dict with keys: id, post_id, created_at_utc, relevance_score,
    market_json, tickers_json, top_vertical, top_vertical_conf
    
    Note: Default thresholds match backend.app.services.relevance module.
    """
    # Use defaults if not specified
    if min_score is None:
        min_score = DEFAULT_MIN_RELEVANCE_SCORE
    if min_conf is None:
        min_conf = DEFAULT_MIN_TOP_VERTICAL_CONF
    
    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()

    cur.execute(
        f"""
        SELECT id, post_id, created_at_utc, relevance_score,
               market_json, tickers_json, top_vertical, top_vertical_conf
        FROM analyses
        WHERE relevance_score IS NOT NULL 
          AND relevance_score >= {ph}
          AND top_vertical_conf IS NOT NULL
          AND top_vertical_conf >= {ph}
        ORDER BY created_at_utc DESC, id DESC
        LIMIT 1
        """,
        (min_score, min_conf),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return _row_to_dict(row)


def get_latest_analysis(
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get the most recent analysis regardless of relevance.
    
    Use this when you want any analysis, not just relevant ones.
    For relevant-only, use get_latest_relevant_analysis().
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, post_id, created_at_utc, relevance_score,
               market_json, tickers_json, top_vertical, top_vertical_conf
        FROM analyses
        ORDER BY created_at_utc DESC, id DESC
        LIMIT 1
        """,
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return _row_to_dict(row)


def get_latest_analysis_with_tickers(
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get the most recent analysis that has ticker impacts.
    
    Returns the latest analysis where tickers_json is not null/empty.
    Useful for showing "last impactful" analysis when current has no tickers.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, post_id, created_at_utc, relevance_score,
               market_json, tickers_json, top_vertical, top_vertical_conf
        FROM analyses
        WHERE tickers_json IS NOT NULL 
          AND tickers_json != '[]'
          AND tickers_json != 'null'
          AND length(tickers_json) > 2
        ORDER BY created_at_utc DESC, id DESC
        LIMIT 1
        """,
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return _row_to_dict(row)


def get_analysis_by_id(
    analysis_id: int,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get an analysis by its id.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()

    cur.execute(
        f"""
        SELECT id, post_id, created_at_utc, relevance_score,
               market_json, tickers_json, top_vertical, top_vertical_conf
        FROM analyses
        WHERE id = {ph}
        """,
        (analysis_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    return _row_to_dict(row)


def get_analyses_for_post(
    post_id: int,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get all analyses for a given post, ordered by creation time (newest first).
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    ph = _get_placeholder()

    cur.execute(
        f"""
        SELECT id, post_id, created_at_utc, relevance_score,
               market_json, tickers_json, top_vertical, top_vertical_conf
        FROM analyses
        WHERE post_id = {ph}
        ORDER BY created_at_utc DESC
        """,
        (post_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

_initialized = False

def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize the database: run migrations to ensure tables exist.
    Call this on application startup.
    """
    global _initialized
    if not _initialized:
        run_migrations(db_path)
        _initialized = True


# Don't auto-run migrations on import in production
# Let the app explicitly call init_db()
