"""Topic store — manages hermes_wiki_topics table.

Independent from WikiStore (which only manages hermes_wiki_pages for sessions).
Both stores share the same SQLite file (memory_store.db) but operate on
different tables.

Topic schema:
    hermes_wiki_topics(
        topic_id, slug, title, language, full_content,
        entities, session_count, sessions_json, created_at, updated_at
    )
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes-wiki")


# Topic table schema — independent from hermes_wiki_pages
TOPIC_SCHEMA = """
CREATE TABLE IF NOT EXISTS hermes_wiki_topics (
    topic_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    language        TEXT DEFAULT 'en',
    full_content    TEXT,
    entities        TEXT,
    session_count   INTEGER DEFAULT 0,
    sessions_json   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hermes_wiki_topics_slug ON hermes_wiki_topics(slug);
CREATE INDEX IF NOT EXISTS idx_hermes_wiki_topics_updated ON hermes_wiki_topics(updated_at);

CREATE TABLE IF NOT EXISTS hermes_wiki_topic_dirty (
    topic_slug      TEXT PRIMARY KEY,
    changed_pages   TEXT,        -- JSON: ["2026-07-23_slug1", "2026-07-20_slug2"]
    dirty_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class TopicStore:
    """Manages hermes_wiki_topics table.

    Also reads hermes_wiki_pages for session pages (read-only) since topic
    integration needs session full_content.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            try:
                from hermes_constants import get_hermes_home
                db_path = str(get_hermes_home() / "memory_store.db")
            except Exception:
                db_path = str(Path.home() / ".hermes" / "memory_store.db")
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        conn.executescript(TOPIC_SCHEMA)
        conn.commit()

    # -- Topic CRUD ---------------------------------------------------------

    def upsert_topic(
        self,
        slug: str,
        title: str,
        full_content: str,
        entities: list,
        session_count: int,
        sessions: list[str],
        language: str = "en",
    ) -> None:
        """Create or update a topic page.

        `sessions` is a list of session slugs (strings), stored as JSON.
        """
        conn = self._connect()
        entities_json = json.dumps(entities, ensure_ascii=False)
        sessions_json = json.dumps(sessions, ensure_ascii=False)
        existing = conn.execute(
            "SELECT topic_id FROM hermes_wiki_topics WHERE slug = ?", (slug,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE hermes_wiki_topics
                   SET title = ?, full_content = ?, entities = ?,
                       session_count = ?, sessions_json = ?, language = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE slug = ?""",
                (title, full_content, entities_json, session_count,
                 sessions_json, language, slug),
            )
        else:
            conn.execute(
                """INSERT INTO hermes_wiki_topics
                   (slug, title, language, full_content, entities,
                    session_count, sessions_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (slug, title, language, full_content, entities_json,
                 session_count, sessions_json),
            )
        conn.commit()
        logger.debug("hermes-wiki: upsert topic %s (%d sessions)", slug, session_count)

    def get_topic(self, slug: str) -> Optional[dict]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM hermes_wiki_topics WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["entities"] = json.loads(d.get("entities") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["entities"] = []
        try:
            d["sessions"] = json.loads(d.get("sessions_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["sessions"] = []
        # Enrich sessions with title/date for GUI consumption
        d["sessions"] = self._enrich_sessions(d["sessions"])
        return d

    def list_topics(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            """SELECT slug, title, language, entities, session_count,
                      sessions_json, updated_at
               FROM hermes_wiki_topics
               ORDER BY updated_at DESC"""
        ).fetchall()
        # First pass: collect all session slugs to batch-enrich
        all_slugs: set[str] = set()
        parsed: list[dict] = []
        for row in rows:
            d = dict(row)
            try:
                d["entities"] = json.loads(d.get("entities") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["entities"] = []
            try:
                d["sessions"] = json.loads(d.get("sessions_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["sessions"] = []
            all_slugs.update(d["sessions"])
            parsed.append(d)
        # Batch-enrich all session slugs in one query
        enrich_map = self._enrich_slugs(list(all_slugs))
        for d in parsed:
            d["sessions"] = [enrich_map.get(s, s) for s in d["sessions"]]
        return parsed

    def _enrich_sessions(self, slugs: list[str]) -> list[dict]:
        """Convert slug list to [{slug, title, date}, ...] via single batch query."""
        enrich_map = self._enrich_slugs(slugs)
        return [enrich_map.get(s, {"slug": s, "title": s, "date": ""}) for s in slugs]

    def _enrich_slugs(self, slugs: list[str]) -> dict[str, dict]:
        """Batch-fetch session metadata: {slug: {slug, title, date}}."""
        if not slugs:
            return {}
        conn = self._connect()
        placeholders = ",".join("?" * len(slugs))
        rows = conn.execute(
            f"""SELECT slug, title, date FROM hermes_wiki_pages
                WHERE slug IN ({placeholders}) AND page_type = 'session'""",
            slugs,
        ).fetchall()
        return {row["slug"]: dict(row) for row in rows}

    # -- Session reading (read-only access to hermes_wiki_pages) ------------

    def list_session_full_content(self) -> list[dict]:
        """Read all session pages with full_content for LLM integration.

        Quality filter is NOT applied here because:
        - session workflow already filters quality < 4 before INSERT
        - low-quality cleanup runs hourly in wiki_store
        The hermes_wiki_pages table for page_type='session' is effectively
        quality >= 4 in normal operation.
        """
        conn = self._connect()
        rows = conn.execute(
            """SELECT slug, title, date, language, topics, entities,
                      full_content, source_session_id, updated_at
               FROM hermes_wiki_pages
               WHERE page_type = 'session'"""
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            try:
                d["topics"] = json.loads(d.get("topics") or "[]")
            except (ValueError, TypeError):
                d["topics"] = []
            try:
                d["entities"] = json.loads(d.get("entities") or "[]")
            except (ValueError, TypeError):
                d["entities"] = []
            result.append(d)
        return result

    # -- Migration: copy existing page_type='topic' rows to new table ------

    def migrate_from_wiki_pages(self) -> int:
        """One-time migration: copy page_type='topic' rows to hermes_wiki_topics.

        Idempotent (INSERT OR IGNORE via slug UNIQUE constraint).
        Does NOT delete old rows — they stay in hermes_wiki_pages as a
        fallback until the new topic table is confirmed stable.
        """
        conn = self._connect()
        rows = conn.execute(
            """SELECT slug, title, language, full_content, entities
               FROM hermes_wiki_pages
               WHERE page_type = 'topic'"""
        ).fetchall()

        migrated = 0
        for row in rows:
            d = dict(row)
            try:
                entities = json.loads(d.get("entities") or "[]")
            except (ValueError, TypeError):
                entities = []
            try:
                existing = conn.execute(
                    "SELECT topic_id FROM hermes_wiki_topics WHERE slug = ?",
                    (d["slug"],)
                ).fetchone()
                if existing:
                    continue
                conn.execute(
                    """INSERT INTO hermes_wiki_topics
                       (slug, title, language, full_content, entities,
                        session_count, sessions_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (d["slug"], d["title"], d.get("language", "en"),
                     d.get("full_content", ""), json.dumps(entities, ensure_ascii=False),
                     0, "[]"),
                )
                migrated += 1
            except Exception as e:
                logger.debug("hermes-wiki: topic migration failed for %s: %s", d.get("slug"), e)
        if migrated:
            conn.commit()
            logger.info("hermes-wiki: migrated %d topic pages from hermes_wiki_pages", migrated)
        return migrated

    # -- Dirty marker CRUD (incremental topic aggregation) ------------------

    def mark_dirty(self, topic_slug: str, changed_session_slug: str) -> None:
        """Mark a topic as dirty after a wiki page changes.

        Called by WikiBuilder._process_session after writing a wiki page.
        Uses INSERT OR UPDATE to accumulate changed pages.
        """
        conn = self._connect()
        existing = conn.execute(
            "SELECT changed_pages FROM hermes_wiki_topic_dirty WHERE topic_slug = ?",
            (topic_slug,)
        ).fetchone()

        if existing:
            # Append to existing dirty list
            try:
                pages = json.loads(existing["changed_pages"] or "[]")
            except (json.JSONDecodeError, TypeError):
                pages = []
            if changed_session_slug not in pages:
                pages.append(changed_session_slug)
            conn.execute(
                """UPDATE hermes_wiki_topic_dirty
                   SET changed_pages = ?, dirty_at = CURRENT_TIMESTAMP
                   WHERE topic_slug = ?""",
                (json.dumps(pages, ensure_ascii=False), topic_slug),
            )
        else:
            conn.execute(
                """INSERT INTO hermes_wiki_topic_dirty
                   (topic_slug, changed_pages)
                   VALUES (?, ?)""",
                (topic_slug, json.dumps([changed_session_slug], ensure_ascii=False)),
            )
        conn.commit()

    def get_dirty_topics(self) -> list[dict]:
        """Return all dirty topic slugs and their changed page slugs."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT topic_slug, changed_pages, dirty_at FROM hermes_wiki_topic_dirty"
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            try:
                d["changed_pages"] = json.loads(d.get("changed_pages") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["changed_pages"] = []
            result.append(d)
        return result

    def clear_dirty(self, topic_slug: str) -> None:
        """Clear dirty marker after topic aggregation succeeds."""
        conn = self._connect()
        conn.execute(
            "DELETE FROM hermes_wiki_topic_dirty WHERE topic_slug = ?",
            (topic_slug,)
        )
        conn.commit()

    def reconcile_topics(self, active_slugs: set[str], min_sessions: int = 2) -> int:
        """Delete derived topics that are stale or below the session threshold."""
        conn = self._connect()
        rows = conn.execute("SELECT slug, session_count FROM hermes_wiki_topics").fetchall()
        removed = 0
        for row in rows:
            if row["slug"] not in active_slugs or int(row["session_count"] or 0) < min_sessions:
                conn.execute("DELETE FROM hermes_wiki_topics WHERE slug = ?", (row["slug"],))
                conn.execute("DELETE FROM hermes_wiki_topic_dirty WHERE topic_slug = ?", (row["slug"],))
                removed += 1
        conn.commit()
        if removed:
            logger.info("hermes-wiki: removed %d stale topic(s)", removed)
        return removed