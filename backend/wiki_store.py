"""
Wiki Store — SQLite table and queue management for hermes-wiki plugin.

Two connection modes:
  - Extension (holographic present): shares holographic's SQLite connection
  - Standalone (no holographic): owns its own connection to memory_store.db

Tables are prefixed with 'wiki_' to avoid collision with holographic tables.
Uses memory_store.db so wiki data co-exists with fact_store.
"""

import datetime
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
    message_count  INTEGER DEFAULT 0,
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
    processing_started_at TIMESTAMP,
    attempts       INTEGER DEFAULT 0,
    next_retry_at  TIMESTAMP,
    last_error     TEXT,
    status         TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS hermes_wiki_session_state (
    session_id      TEXT PRIMARY KEY,
    message_count   INTEGER NOT NULL DEFAULT 0,
    quality         INTEGER,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(hermes_wiki_pages)").fetchall()}
        if "message_count" not in columns:
            self._conn.execute("ALTER TABLE hermes_wiki_pages ADD COLUMN message_count INTEGER DEFAULT 0")
        queue_columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(hermes_wiki_pending_queue)").fetchall()
        }
        for name, definition in (
            ("processing_started_at", "TIMESTAMP"),
            ("attempts", "INTEGER DEFAULT 0"),
            ("next_retry_at", "TIMESTAMP"),
            ("last_error", "TEXT"),
            ("latest_date", "TEXT"),
            ("original_session_id", "TEXT"),
        ):
            if name not in queue_columns:
                self._conn.execute(f"ALTER TABLE hermes_wiki_pending_queue ADD COLUMN {name} {definition}")
        self._conn.commit()

    # -- Queue operations ---------------------------------------------------

    def enqueue(
        self,
        session_id: str,
        messages: list,
        title: str = "",
        source: str = "",
        message_count: Optional[int] = None,
        latest_message_at: Optional[float] = None,
        original_session_id: str = "",
    ) -> int:
        messages_json = json.dumps(messages, ensure_ascii=False)
        source_count = len(messages) if message_count is None else int(message_count)
        latest_date = None
        if latest_message_at is not None:
            latest_date = datetime.datetime.fromtimestamp(latest_message_at).strftime("%Y-%m-%d")
        with self._lock:
            active = self._conn.execute(
                """SELECT id FROM hermes_wiki_pending_queue
                   WHERE session_id = ? AND status IN ('pending', 'processing')
                   ORDER BY id DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
            if active:
                return int(active[0])
            cur = self._conn.execute(
                """INSERT INTO hermes_wiki_pending_queue
                   (session_id, title, source, message_count, messages_json, latest_date, original_session_id, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (session_id, title, source, source_count, messages_json, latest_date, original_session_id),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def dequeue(self, limit: int = 1) -> list:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, session_id, title, source, message_count, messages_json, latest_date, original_session_id
                   FROM hermes_wiki_pending_queue
                   WHERE status = 'pending'
                     AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                   ORDER BY enqueued_at ASC LIMIT ?""",
                (limit,),
            ).fetchall()
            if not rows:
                return []
            ids = [dict(r)["id"] for r in rows]
            placeholders = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE hermes_wiki_pending_queue "
                f"SET status = 'processing', processing_started_at = CURRENT_TIMESTAMP "
                f"WHERE id IN ({placeholders})",
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
                "UPDATE hermes_wiki_pending_queue SET status = ?, processing_started_at = NULL WHERE id = ?",
                (status, queue_id),
            )
            self._conn.commit()

    def retry_or_fail(self, queue_id: int, error: str, max_attempts: int = 3) -> str:
        """Retry transient failures with exponential backoff, then mark failed."""
        with self._lock:
            row = self._conn.execute(
                "SELECT attempts FROM hermes_wiki_pending_queue WHERE id = ?", (queue_id,)
            ).fetchone()
            attempts = int(row[0] or 0) + 1 if row else max_attempts
            status = "failed" if attempts >= max_attempts else "pending"
            delay_seconds = min(300, 15 * (2 ** (attempts - 1)))
            retry_at = None if status == "failed" else f"+{delay_seconds} seconds"
            self._conn.execute(
                """UPDATE hermes_wiki_pending_queue
                   SET status = ?, attempts = ?, last_error = ?, processing_started_at = NULL,
                       next_retry_at = CASE WHEN ? IS NULL THEN NULL ELSE datetime('now', ?) END
                   WHERE id = ?""",
                (status, attempts, error[:1000], retry_at, retry_at, queue_id),
            )
            self._conn.commit()
            return status

    def recover_stale_processing(self, max_age_seconds: int = 900) -> int:
        """Requeue work left in processing by an interrupted worker."""
        with self._lock:
            cur = self._conn.execute(
                """UPDATE hermes_wiki_pending_queue
                   SET status = 'pending', processing_started_at = NULL,
                       last_error = COALESCE(last_error, 'worker interrupted')
                   WHERE status = 'processing'
                     AND processing_started_at < datetime('now', ?)""",
                (f"-{max_age_seconds} seconds",),
            )
            self._conn.commit()
            return cur.rowcount

    def delete_low_quality_session_page(self, session_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM hermes_wiki_pages "
                "WHERE source_session_id = ? AND page_type = 'session' AND quality < 4",
                (session_id,),
            )
            self._conn.commit()
            return cur.rowcount

    def pending_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM hermes_wiki_pending_queue WHERE status = 'pending'"
        ).fetchone()
        return row[0] if row else 0

    def is_session_processed(self, session_id: str) -> bool:
        if not session_id:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM hermes_wiki_session_state WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row is not None

    def session_message_count(self, session_id: str) -> int:
        if not session_id:
            return 0
        row = self._conn.execute(
            "SELECT message_count FROM hermes_wiki_session_state WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def is_date_processed(self, queue_key: str) -> bool:
        """Check if a session:date segment has been processed (queue_key = sid:date)."""
        if not queue_key:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM hermes_wiki_session_state WHERE session_id = ?", (queue_key,)
        ).fetchone()
        return row is not None

    def date_message_count(self, queue_key: str) -> int:
        """Get message count for a session:date segment (queue_key = sid:date)."""
        if not queue_key:
            return 0
        row = self._conn.execute(
            "SELECT message_count FROM hermes_wiki_session_state WHERE session_id = ?",
            (queue_key,),
        ).fetchone()
        return int(row[0]) if row else 0

    def record_session_state(self, session_id: str, message_count: int, quality: int) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO hermes_wiki_session_state (session_id, message_count, quality, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(session_id) DO UPDATE SET
                       message_count = excluded.message_count,
                       quality = excluded.quality,
                       updated_at = CURRENT_TIMESTAMP""",
                (session_id, message_count, quality),
            )
            self._conn.commit()

    # -- Wiki page CRUD -----------------------------------------------------

    def insert_page(self, **kwargs) -> int:
        with self._lock:
            source_session_id = kwargs.get("source_session_id")
            if source_session_id:
                self._conn.execute(
                    "DELETE FROM hermes_wiki_pages WHERE source_session_id = ? AND slug != ?",
                    (source_session_id, kwargs["slug"]),
                )
            cur = self._conn.execute(
                """INSERT OR REPLACE INTO hermes_wiki_pages
                   (page_type, slug, title, date, language, quality, content_type,
                    topics, keywords, entities, summary, full_content, source_session_id, message_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    source_session_id,
                    kwargs.get("message_count", 0),
                ),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    def get_topic_page(self, slug: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM hermes_wiki_pages WHERE slug = ? AND page_type = 'topic'", (slug,),
            ).fetchone()
            return dict(row) if row else None

    def upsert_topic_page(self, slug: str, title: str, full_content: str,
                          session_count: int = 0, topics: list = None,
                          entities: list = None, keywords: list = None) -> int:
        """Create or update a topic aggregation page."""
        with self._lock:
            existing = self._conn.execute(
                "SELECT page_id FROM hermes_wiki_pages WHERE slug = ? AND page_type = 'topic'",
                (slug,),
            ).fetchone()
            if existing:
                self._conn.execute(
                    """UPDATE hermes_wiki_pages
                       SET title=?, full_content=?, message_count=?,
                           topics=?, entities=?, keywords=?, updated_at=CURRENT_TIMESTAMP
                       WHERE page_id=?""",
                    (title, full_content, session_count,
                     json.dumps(topics or [], ensure_ascii=False),
                     json.dumps(entities or [], ensure_ascii=False),
                     json.dumps(keywords or [], ensure_ascii=False),
                     existing["page_id"]),
                )
                self._conn.commit()
                return existing["page_id"]
            else:
                cur = self._conn.execute(
                    """INSERT INTO hermes_wiki_pages
                       (page_type, slug, title, date, language, quality, content_type,
                        topics, keywords, entities, summary, full_content, message_count)
                       VALUES ('topic', ?, ?, DATE('now'), 'en', 5, 'topic-aggregate',
                               ?, ?, ?, '', ?, ?)""",
                    (slug, title,
                     json.dumps(topics or [], ensure_ascii=False),
                     json.dumps(keywords or [], ensure_ascii=False),
                     json.dumps(entities or [], ensure_ascii=False),
                     full_content, session_count),
                )
                self._conn.commit()
                return cur.lastrowid  # type: ignore[return-value]

    def list_topics(self) -> list:
        """Return all topic pages with their associated session pages."""
        with self._lock:
            topic_rows = self._conn.execute(
                """SELECT slug, title, quality, date, message_count, summary,
                          topics, entities, keywords, updated_at
                   FROM hermes_wiki_pages WHERE page_type = 'topic'
                   ORDER BY updated_at DESC"""
            ).fetchall()
            results = []
            for t in topic_rows:
                topic = dict(t)
                # Find session pages that reference this topic in their topics JSON array
                topic_slug = topic["slug"]
                session_rows = self._conn.execute(
                    """SELECT slug, title, date, quality, summary, source_session_id
                       FROM hermes_wiki_pages
                       WHERE page_type = 'session'
                       AND (
                           topics LIKE ? OR topics LIKE ? OR topics LIKE ?
                       )
                       ORDER BY date DESC""",
                    (f'%"{topic_slug}"%', f'%"{topic_slug.replace("-", " ")}"%',
                     f'%"{topic_slug.replace("-", "_")}"%'),
                ).fetchall()
                topic["sessions"] = [dict(s) for s in session_rows]
                results.append(topic)
            return results

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
        terms = query.strip().split()
        if not terms:
            return []
        # Build OR conditions for each term
        conditions = []
        params = []
        for term in terms:
            q = f"%{term}%"
            conditions.append("(title LIKE ? OR summary LIKE ? OR topics LIKE ? OR keywords LIKE ? OR date LIKE ?)")
            params.extend([q, q, q, q, q])
        where = " OR ".join(conditions)
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT slug, page_type, title, date, quality, summary, topics
                   FROM hermes_wiki_pages
                   WHERE {where}
                   LIMIT ?""",
                params,
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
