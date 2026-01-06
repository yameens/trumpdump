import re
import time
import sqlite3
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

LISTING_URL = "https://www.whitehouse.gov/briefings-statements/"
USER_AGENT = "TrumpDumpBot/0.1 (contact: you@example.com)"

@dataclass
class LastListingItem:
    url: str
    title: str

@dataclass
class ReturnListing:
    url: str
    title: str
    source: str
    content: str

ARTICLE_URL_RE = re.compile(
    r"^/briefings-statements/\d{4}/\d{2}/[^\"'\s]+/?$"
)

def initialize_database(db_path: str = "trumpdump.db") -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wh_checkpoints (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            unique_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            scraped_at_utc INTEGER NOT NULL
        );
    """)

    conn.commit()
    conn.close()

def get_checkpoint(name: str, db_path: str = "trumpdump.db") -> Optional[str]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT value FROM wh_checkpoints WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()

    return row[0] if row else None

def set_checkpoint(name: str, value: str, db_path: str = "trumpdump.db") -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO wh_checkpoints(name, value)
        VALUES(?, ?)
        ON CONFLICT(name) DO UPDATE SET value = excluded.value
    """, (name, value))

    conn.commit()
    conn.close()

def store_latest_post(item: LastListingItem, unique_id: str, content: str, db_path: str = "trumpdump.db") -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO posts(unique_id, url, title, content, scraped_at_utc)
        VALUES(?, ?, ?, ?, ?)
    """, (unique_id, item.url, item.title, content, int(time.time())))

    conn.commit()
    conn.close()

def fetch_listing_html(url: str = LISTING_URL) -> str:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text

def get_latest_listing_link(list_html: str) -> Optional[LastListingItem]:
    soup = BeautifulSoup(list_html, "html.parser")
    main = soup.find("main") or soup

    for a in main.find_all("a", href=True):
        href = a["href"].strip()

        if href.startswith("https://www.whitehouse.gov"):
            href_for_match = href.replace("https://www.whitehouse.gov", "")
            full_url = href
        elif href.startswith("/"):
            href_for_match = href
            full_url = "https://www.whitehouse.gov" + href
        else:
            continue

        if ARTICLE_URL_RE.match(href_for_match):
            title = a.get_text(strip=True)
            if title:
                return LastListingItem(url=full_url, title=title)

    return None

def get_unique_content(article_html: str) -> str:
    soup = BeautifulSoup(article_html, "html.parser")
    main = soup.find("main") or soup

    paragraphs = []
    for p in main.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt:
            paragraphs.append(txt)

    return "\n\n".join(paragraphs)

def wh_poll_once(db_path: str = "trumpdump.db") -> Optional[ReturnListing]:
    checkpoint_name = "whitehouse_latest_url"

    html = fetch_listing_html()
    latest = get_latest_listing_link(html)

    if latest is None:
        print("Could not find a latest post link.")
        return None

    last_seen_url = get_checkpoint(checkpoint_name, db_path=db_path)
    if last_seen_url == latest.url:
        print("No new White House post.")
        return None

    article_html = fetch_listing_html(latest.url)
    content = get_unique_content(article_html)

    unique_id = latest.url  # simplest unique ID: use the URL itself
    store_latest_post(latest, unique_id, content, db_path=db_path)
    set_checkpoint(checkpoint_name, latest.url, db_path=db_path)

    print("NEW post saved:")
    print("Title:", latest.title)
    print("URL:", latest.url)

    return ReturnListing(url=unique_id, title=latest.title, source="White House", content=content)

def show_recent(db_path="trumpdump.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT title, url, scraped_at_utc FROM posts ORDER BY scraped_at_utc DESC LIMIT 5")
    for row in cur.fetchall():
        print(row)
    conn.close()

if __name__ == "__main__":
    initialize_database()
    wh_poll_once()
    show_recent()
