"""
Wiki Store — SQLite table and queue management for hermes-wiki plugin.

Two connection modes:
  - Extension (holographic present): shares holographic's SQLite connection
  - Standalone (no holographic): owns its own connection to memory_store.db

Tables are prefixed with 'wiki_' to avoid collision with holographic tables.
Uses memory_store.db so wiki data co-exists with fact_store.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_WIKI_SCHEMA = """
CREATE TABLE IF NOT EXISTS hermes_wiki_pages (
    page_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    page_type      TEXT NOT NULL,
    slug           TEXT UNIQUE NOT NULL,
    title          TEXT NOT NULL,
    date           TEXT,
    language       TEXT DEFAULT 'en',
    quality        INTEGER,
    content_type   TEXT,
    topics         TEXT,
    keywords       TEXT,
    entities       TEXT,
    summary        TEXT,
    full_content   TEXT,
    source_session_id TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hermes_wiki_pending_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    title          TEXT,
    source         TEXT,
    message_count  INTEGER,
    messages_json  TEXT NOT NULL,
    enqueued_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status         TEXT DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_hermes_wiki_queue_status ON hermes_wiki_pending_queue(status);
CREATE INDEX IF NOT EXISTS idx_hermes_hermes_wiki_pages_type ON hermes_wiki_pages(page_type);
CREATE INDEX IF NOT EXISTS idx_hermes_hermes_wiki_pages_date ON hermes_wiki_pages(date);
"""


class WikiStore:
    """Manages wiki SQLite tables and pending queue.

    Args:
        conn: Optional shared sqlite3.Connection (extension mode).
              If None, creates own connection to memory_store.db (standalone mode).
        lock: Optional shared threading.RLock (extension mode).
              If None, creates own lock.
    """

    # Shared connection registry for standalone mode (same pattern as holographic)
    _shared: dict = {}
    _shared_guard = threading.Lock()

    def __init__(self, conn: Optional[sqlite3.Connection] = None, lock: Optional[threading.RLock] = None):
        if conn is not None:
            # Extension mode: use holographic's shared connection
            self._conn = conn
            self._lock = lock or threading.RLock()
            self._owns_connection = False
            self._init_schema()
        else:
            # Standalone mode: create own connection
            self._owns_connection = True
            self._init_own_connection()

    def _init_own_connection(self) -> None:
        """Create own connection to memory_store.db."""
        from hermes_constants import get_hermes_home
        db_path = str(get_hermes_home() / "memory_store.db")

        try:
            self._key = str(Path(db_path).resolve())
        except OSError:
            self._key = db_path

        with WikiStore._shared_guard:
            entry = WikiStore._shared.get(self._key)
            if entry is None:
                conn = sqlite3.connect(
                    self._key,
                    check_same_thread=False,
                    timeout=10.0,
                    isolation_level=None,
                )
                conn.row_factory = sqlite3.Row
                entry = {"conn": conn, "lock": threading.RLock(), "refs": 0, "ready": False}
                WikiStore._shared[self._key] = entry
            entry["refs"] += 1
            self._entry = entry
            self._conn = entry["conn"]
            self._lock = entry["lock"]

        with self._lock:
            if not self._entry["ready"]:
                try:
                    from hermes_state import apply_wal_with_fallback
                    apply_wal_with_fallback(self._conn, db_label="memory_store.db (hermes-wiki)")
                except ImportError:
                    pass
                self._init_schema()
                self._entry["ready"] = True

    def _init_schema(self) -> None:
        """Create wiki tables if they don't exist."""
        self._conn.executescript(_WIKI_SCHEMA)
        self._conn.commit()

    # -- Queue operations ---------------------------------------------------

    def enqueue(self, session_id: str, messages: list, title: str = "", source: str = "") -> int:
        messages_json = json.dumps(messages, ensure_ascii=False)
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO hermes_wiki_pending_queue
                   (session_id, title, source, message_count, messages_json, status)
                   VALUES (?, ?, ?, ?, ?, 'pending')""",
                (session_id, title, source, len(messages), messages_json),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def dequeue(self, limit: int = 1) -> list:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, session_id, title, source, message_count, messages_json
                   FROM hermes_wiki_pending_queue WHERE status = 'pending'
                   ORDER BY enqueued_at ASC LIMIT ?""",
                (limit,),
            ).fetchall()
            if not rows:
                return []
            ids = [dict(r)["id"] for r in rows]
            placeholders = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE hermes_wiki_pending_queue SET status = 'processing' WHERE id IN ({placeholders})",
                ids,
            )
            self._conn.commit()
        results = []
        for row in rows:
            d = dict(row)
            d["messages"] = json.loads(d.pop("messages_json"))
            results.append(d)
        return results

    def mark_done(self, queue_id: int, status: str = "done") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE hermes_wiki_pending_queue SET status = ? WHERE id = ?", (status, queue_id)
            )
            self._conn.commit()

    def pending_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM hermes_wiki_pending_queue WHERE status = 'pending'"
        ).fetchone()
        return row[0] if row else 0

    def is_session_processed(self, session_id: str) -> bool:
        if not session_id:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM hermes_wiki_pages WHERE source_session_id = ?", (session_id,)
        ).fetchone()
        return row is not None

    # -- Wiki page CRUD -----------------------------------------------------

    def insert_page(self, **kwargs) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT OR REPLACE INTO hermes_wiki_pages
                   (page_type, slug, title, date, language, quality, content_type,
                    topics, keywords, entities, summary, full_content, source_session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    kwargs.get("page_type", "session"),
                    kwargs["slug"],
                    kwargs["title"],
                    kwargs.get("date"),
                    kwargs.get("language", "en"),
                    kwargs.get("quality"),
                    kwargs.get("content_type"),
                    json.dumps(kwargs.get("topics", []), ensure_ascii=False),
                    json.dumps(kwargs.get("keywords", []), ensure_ascii=False),
                    json.dumps(kwargs.get("entities", []), ensure_ascii=False),
                    kwargs.get("summary"),
                    kwargs.get("full_content"),
                    kwargs.get("source_session_id"),
                ),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def get_topic_page(self, slug: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM hermes_wiki_pages WHERE slug = ? AND page_type = 'topic'", (slug,)
            ).fetchone()
            return dict(row) if row else None

    def update_page_content(self, page_id: int, content: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE hermes_wiki_pages SET full_content = ?, updated_at = CURRENT_TIMESTAMP WHERE page_id = ?",
                (content, page_id),
            )
            self._conn.commit()

    def search_pages(self, query: str, limit: int = 10) -> list:
        """Search wiki pages by keyword (LIKE-based, CJK compatible)."""
        if not query or not query.strip():
            return []
        q = f"%{query.strip()}%"
        with self._lock:
            rows = self._conn.execute(
                """SELECT slug, page_type, title, date, quality, summary, topics
                   FROM hermes_wiki_pages
                   WHERE title LIKE ? OR summary LIKE ? OR topics LIKE ? OR keywords LIKE ?
                   LIMIT ?""",
                (q, q, q, q, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_pages(self) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT slug, page_type, title, date, quality, topics, summary, full_content, source_session_id FROM hermes_wiki_pages"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_session_ids(self) -> set:
        with self._lock:
            rows = self._conn.execute(
                "SELECT source_session_id FROM hermes_wiki_pages WHERE source_session_id IS NOT NULL"
            ).fetchall()
            return {r[0] for r in rows}

    # -- Cleanup ------------------------------------------------------------

    def close(self) -> None:
        """Release connection (standalone mode only)."""
        if not self._owns_connection:
            return
        if getattr(self, "_entry", None) is None:
            return
        with WikiStore._shared_guard:
            entry = self._entry
            if entry is None:
                return
            entry["refs"] -= 1
            if entry["refs"] <= 0:
                try:
                    entry["conn"].close()
                except Exception:
                    pass
                WikiStore._shared.pop(self._key, None)
            self._entry = None
