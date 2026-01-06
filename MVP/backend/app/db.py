"""
Database module for TrumpDump MVP.

Handles SQLite connections, migrations, and provides helper functions
for whitehouse_posts and analyses tables.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default database path (relative to project root)
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "trumpdump.db"


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Open a SQLite connection with row factory for dict-like access.
    """
    path = db_path or str(DEFAULT_DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # enables dict-like row access
    return conn


def run_migrations(db_path: Optional[str] = None) -> None:
    """
    Create tables if they don't exist. Idempotent - safe to call on every startup.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    # whitehouse_posts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS whitehouse_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT,
            content TEXT,
            scraped_at_utc INTEGER NOT NULL
        );
    """)

    # analyses table with foreign key to whitehouse_posts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            created_at_utc INTEGER NOT NULL,
            relevance_score INTEGER,
            market_json TEXT,
            tickers_json TEXT,
            top_vertical TEXT,
            top_vertical_conf REAL,
            FOREIGN KEY (post_id) REFERENCES whitehouse_posts(id)
        );
    """)

    # Create indexes for common queries
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_whitehouse_posts_scraped_at
        ON whitehouse_posts(scraped_at_utc DESC);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_analyses_created_at
        ON analyses(created_at_utc DESC);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_analyses_relevance
        ON analyses(relevance_score DESC, top_vertical_conf DESC);
    """)

    conn.commit()
    conn.close()


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Convert a sqlite3.Row to a plain dict, or None if row is None."""
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# whitehouse_posts helpers
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
    
    If a post with the same URL already exists, returns the existing row id.
    """
    if scraped_at_utc is None:
        scraped_at_utc = int(time.time())

    conn = get_connection(db_path)
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO whitehouse_posts (url, title, content, scraped_at_utc)
            VALUES (?, ?, ?, ?)
            """,
            (url, title, content, scraped_at_utc),
        )
        row_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        # URL already exists, fetch existing id
        cur.execute("SELECT id FROM whitehouse_posts WHERE url = ?", (url,))
        row = cur.fetchone()
        row_id = row["id"] if row else -1
    finally:
        conn.close()

    return row_id


def get_latest_whitehouse_post(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get the most recently scraped whitehouse post.
    Returns a dict with keys: id, url, title, content, scraped_at_utc
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, url, title, content, scraped_at_utc
        FROM whitehouse_posts
        ORDER BY scraped_at_utc DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()

    return _row_to_dict(row)


def get_whitehouse_post_by_id(
    post_id: int,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get a whitehouse post by its id.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, url, title, content, scraped_at_utc
        FROM whitehouse_posts
        WHERE id = ?
        """,
        (post_id,),
    )
    row = cur.fetchone()
    conn.close()

    return _row_to_dict(row)


def get_whitehouse_post_by_url(
    url: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get a whitehouse post by its URL.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, url, title, content, scraped_at_utc
        FROM whitehouse_posts
        WHERE url = ?
        """,
        (url,),
    )
    row = cur.fetchone()
    conn.close()

    return _row_to_dict(row)


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

    cur.execute(
        """
        INSERT INTO analyses (
            post_id, created_at_utc, relevance_score,
            market_json, tickers_json, top_vertical, top_vertical_conf
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
        post_id: ID of the whitehouse_post this analysis is for
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

    cur.execute(
        """
        SELECT id, post_id, created_at_utc, relevance_score,
               market_json, tickers_json, top_vertical, top_vertical_conf
        FROM analyses
        WHERE relevance_score IS NOT NULL 
          AND relevance_score >= ?
          AND top_vertical_conf IS NOT NULL
          AND top_vertical_conf >= ?
        ORDER BY created_at_utc DESC, id DESC
        LIMIT 1
        """,
        (min_score, min_conf),
    )
    row = cur.fetchone()
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

    cur.execute(
        """
        SELECT id, post_id, created_at_utc, relevance_score,
               market_json, tickers_json, top_vertical, top_vertical_conf
        FROM analyses
        WHERE id = ?
        """,
        (analysis_id,),
    )
    row = cur.fetchone()
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

    cur.execute(
        """
        SELECT id, post_id, created_at_utc, relevance_score,
               market_json, tickers_json, top_vertical, top_vertical_conf
        FROM analyses
        WHERE post_id = ?
        ORDER BY created_at_utc DESC
        """,
        (post_id,),
    )
    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize the database: run migrations to ensure tables exist.
    Call this on application startup.
    """
    run_migrations(db_path)


# Run migrations on module import for convenience
# (can be disabled by importing specific functions only)
if __name__ != "__main__":
    # Auto-migrate when imported as a module
    run_migrations()

