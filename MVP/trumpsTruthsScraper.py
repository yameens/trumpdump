import sqlite3
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LISTING_URL = "https://trumpstruth.org/"
USER_AGENT = "TrumpDumpBot/0.1 (contact: you@example.com)"


@dataclass
class LastListing:
    url: str
    source: str

@dataclass
class ReturnListing:
    url: str
    source: str
    content: str
    status: bool

def initialize_db(db_path: str = "trumpdump.db") -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tt_checkpoints (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tt_posts (
            unique_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            retruth INTEGER NOT NULL
        );
        """
    )

    conn.commit()
    conn.close()


def get_checkpoint(name: str, db_path: str = "trumpdump.db") -> Optional[str]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT value FROM tt_checkpoints WHERE name = ?", (name,))
    row = cur.fetchone()

    conn.close()
    return row[0] if row else None


def set_checkpoint(name: str, value: str, db_path: str = "trumpdump.db") -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO tt_checkpoints(name, value)
        VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET value = excluded.value
        """,
        (name, value),
    )

    conn.commit()
    conn.close()


def set_post(
    item: LastListing,
    content: str,
    unique_id: str,
    retruth: bool,
    db_path: str = "trumpdump.db",
) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR IGNORE INTO tt_posts(unique_id, url, content, source, retruth)
        VALUES (?, ?, ?, ?, ?)
        """,
        (unique_id, item.url, content, item.source, int(retruth)),
    )

    conn.commit()
    conn.close()


def fetch_html(url: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_latest_status(html: str) -> Optional[Tuple[LastListing, bool]]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("main") or soup

    status = root.find("div", class_="status")
    if not status:
        return None

    raw_url = status.get("data-status-url")
    if not raw_url:
        return None

    full_url = urljoin(LISTING_URL, raw_url)

    prev_tag = status.find_previous_sibling(lambda t: getattr(t, "name", None) is not None)

    is_retruth = False
    if prev_tag:
        prev_classes = prev_tag.get("class") or []
        if "status__reblog-indicator" in prev_classes:
            is_retruth = True
        elif prev_tag.find(class_="status__reblog-indicator"):
            is_retruth = True

    return LastListing(url=full_url, source="trumpstruth.org"), is_retruth


def get_status_content(url: str) -> str:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("main") or soup

    parts = []
    for p in root.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt:
            parts.append(txt)

    return "\n\n".join(parts)


def tt_poll_once(db_path: str = "trumpdump.db") -> Optional[ReturnListing]:
    html = fetch_html(LISTING_URL)
    latest_pair = extract_latest_status(html)

    if latest_pair is None:
        print("no status found in listing HTML.")
        return

    latest, is_retruth = latest_pair

    last_url = get_checkpoint("latest_status_url", db_path=db_path)
    if last_url == latest.url:
        print("no new status.")
        return

    content = get_status_content(latest.url)
    unique_id = latest.url.rstrip("/").split("/")[-1]

    set_post(latest, content, unique_id, is_retruth, db_path=db_path)
    set_checkpoint("latest_status_url", latest.url, db_path=db_path)

    print("Saved:", latest.url, "retruth=", is_retruth)
    print("Content", content)

    return ReturnListing(url=latest.url, source="Trump's Truths", content=content, status=is_retruth)


if __name__ == "__main__":
    initialize_db()
    tt_poll_once()
