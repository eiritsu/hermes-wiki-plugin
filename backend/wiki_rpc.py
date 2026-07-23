"""
Gateway JSON-RPC handlers for hermes-wiki.

Each handler has signature: handler(rid, params) -> dict
These are registered via ctx.register_rpc() in __init__.py.
"""

import json
import sqlite3
import logging
from typing import Any

logger = logging.getLogger(__name__)

_wiki_db = None


def _get_wiki_db():
    global _wiki_db
    if _wiki_db is None:
        from hermes_constants import get_hermes_home
        db_path = str(get_hermes_home() / "memory_store.db")
        _wiki_db = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
        _wiki_db.row_factory = sqlite3.Row
        _wiki_db.execute("PRAGMA journal_mode=WAL")
    return _wiki_db


def _err(rid, code, msg):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def _row_to_dict(row):
    d = dict(row)
    for key in ("topics", "keywords", "entities"):
        if d.get(key) and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                d[key] = []
    return d


def wiki_list(rid, params):
    try:
        db = _get_wiki_db()
        page_type = params.get("page_type")
        query = params.get("query", "").strip()
        limit = params.get("limit", 100)
        cols = ("slug, page_type, title, date, quality, content_type, "
                "topics, keywords, entities, summary, language, "
                "source_session_id, created_at, updated_at")
        if query:
            q = f"%{query}%"
            rows = db.execute(
                f"SELECT {cols} FROM hermes_wiki_pages "
                "WHERE title LIKE ? OR summary LIKE ? OR topics LIKE ? OR keywords LIKE ? "
                "ORDER BY date DESC LIMIT ?",
                (q, q, q, q, limit),
            ).fetchall()
        elif page_type:
            rows = db.execute(
                f"SELECT {cols} FROM hermes_wiki_pages WHERE page_type = ? "
                "ORDER BY date DESC LIMIT ?",
                (page_type, limit),
            ).fetchall()
        else:
            rows = db.execute(
                f"SELECT {cols} FROM hermes_wiki_pages ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        pages = [_row_to_dict(r) for r in rows]
        return {"jsonrpc": "2.0", "id": rid, "result": {"pages": pages, "count": len(pages)}}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.list failed: {exc}")


def wiki_get(rid, params):
    try:
        db = _get_wiki_db()
        slug = params.get("slug", "")
        if not slug:
            return _err(rid, -32602, "slug is required")
        row = db.execute(
            "SELECT slug, page_type, title, date, quality, content_type, "
            "topics, keywords, entities, summary, full_content, language, "
            "source_session_id, created_at, updated_at "
            "FROM hermes_wiki_pages WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not row:
            return _err(rid, -32001, f"wiki page not found: {slug}")
        return {"jsonrpc": "2.0", "id": rid, "result": _row_to_dict(row)}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.get failed: {exc}")


def wiki_create(rid, params):
    try:
        db = _get_wiki_db()
        slug = params.get("slug", "")
        title = params.get("title", "")
        if not slug or not title:
            return _err(rid, -32602, "slug and title are required")
        if db.execute("SELECT 1 FROM hermes_wiki_pages WHERE slug = ?", (slug,)).fetchone():
            return _err(rid, -32002, f"slug already exists: {slug}")
        db.execute(
            "INSERT INTO hermes_wiki_pages "
            "(page_type, slug, title, date, language, quality, content_type, "
            "topics, keywords, entities, summary, full_content, source_session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (params.get("page_type", "manual"), slug, title,
             params.get("date", ""), params.get("language", "en"),
             params.get("quality", 3), params.get("content_type", "manual"),
             json.dumps(params.get("topics", []), ensure_ascii=False),
             json.dumps(params.get("keywords", []), ensure_ascii=False),
             json.dumps(params.get("entities", []), ensure_ascii=False),
             params.get("summary", ""), params.get("full_content", ""),
             params.get("source_session_id")),
        )
        db.commit()
        return {"jsonrpc": "2.0", "id": rid, "result": {"slug": slug, "created": True}}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.create failed: {exc}")


def wiki_update(rid, params):
    try:
        db = _get_wiki_db()
        slug = params.get("slug", "")
        if not slug:
            return _err(rid, -32602, "slug is required")
        if not db.execute("SELECT 1 FROM hermes_wiki_pages WHERE slug = ?", (slug,)).fetchone():
            return _err(rid, -32001, f"wiki page not found: {slug}")
        updates, values = [], []
        for f in ("title", "date", "language", "quality", "content_type", "summary", "full_content"):
            if f in params:
                updates.append(f"{f} = ?"); values.append(params[f])
        for f in ("topics", "keywords", "entities"):
            if f in params:
                updates.append(f"{f} = ?"); values.append(json.dumps(params[f], ensure_ascii=False))
        if not updates:
            return _err(rid, -32602, "no fields to update")
        updates.append("updated_at = CURRENT_TIMESTAMP"); values.append(slug)
        db.execute(f"UPDATE hermes_wiki_pages SET {', '.join(updates)} WHERE slug = ?", values)
        db.commit()
        return {"jsonrpc": "2.0", "id": rid, "result": {"slug": slug, "updated": True}}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.update failed: {exc}")


def wiki_delete(rid, params):
    try:
        db = _get_wiki_db()
        slug = params.get("slug", "")
        if not slug:
            return _err(rid, -32602, "slug is required")
        result = db.execute("DELETE FROM hermes_wiki_pages WHERE slug = ?", (slug,))
        db.commit()
        if result.rowcount == 0:
            return _err(rid, -32001, f"wiki page not found: {slug}")
        return {"jsonrpc": "2.0", "id": rid, "result": {"slug": slug, "deleted": True}}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.delete failed: {exc}")


def wiki_stats(rid, params):
    try:
        db = _get_wiki_db()
        total = db.execute("SELECT COUNT(*) FROM hermes_wiki_pages").fetchone()[0]
        by_type = {}
        for row in db.execute(
            "SELECT page_type, COUNT(*) as cnt FROM hermes_wiki_pages GROUP BY page_type"
        ).fetchall():
            by_type[row[0]] = row[1]
        avg_q = db.execute(
            "SELECT AVG(quality) FROM hermes_wiki_pages WHERE quality IS NOT NULL"
        ).fetchone()[0]
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"total": total, "by_type": by_type, "avg_quality": round(avg_q or 0, 1)}}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.stats failed: {exc}")


def wiki_batch_process(rid, params):
    try:
        import sys as _sys
        from hermes_constants import get_hermes_home

        db = _get_wiki_db()
        state_db_path = str(get_hermes_home() / "state.db")
        limit = params.get("limit", 20)

        processed = {}
        for row in db.execute(
            "SELECT session_id, message_count FROM hermes_wiki_session_state"
        ).fetchall():
            processed[row[0]] = int(row[1] or 0)

        plugins_dir = str(get_hermes_home() / "plugins")
        if plugins_dir not in _sys.path:
            _sys.path.insert(0, plugins_dir)
        from hermes_wiki.wiki_store import WikiStore

        ws = WikiStore(conn=db)
        ws.recover_stale_processing(max_age_seconds=900)

        state_db = sqlite3.connect(state_db_path, check_same_thread=False, timeout=5.0)
        state_db.row_factory = sqlite3.Row
        sessions = state_db.execute(
            "SELECT id, title, source, message_count FROM sessions "
            "WHERE source NOT IN ('cron', 'subagent') AND message_count >= 2 "
            "ORDER BY started_at DESC LIMIT ?",
            (limit * 2,),
        ).fetchall()

        enqueued = 0
        for sess in sessions:
            sid = sess["id"]
            current_count = int(sess["message_count"] or 0)
            if sid in processed and current_count <= processed[sid]:
                continue
            if enqueued >= limit:
                break
            msg_rows = state_db.execute(
                "SELECT role, content, timestamp FROM messages "
                "WHERE session_id = ? AND role IN ('user', 'assistant') "
                "ORDER BY timestamp ASC",
                (sid,),
            ).fetchall()
            if len(msg_rows) < 2:
                continue

            # Group messages by date
            import datetime
            from collections import OrderedDict
            date_msgs = OrderedDict()
            for r in msg_rows:
                d = datetime.datetime.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d")
                date_msgs.setdefault(d, []).append(r)

            today = datetime.date.today().isoformat()

            for date_str, msgs in date_msgs.items():
                queue_key = f"{sid}:{date_str}"
                messages = [{"role": r["role"], "content": r["content"] or ""} for r in msgs]
                msg_count = len(messages)
                if msg_count < 2:
                    continue
                if ws.is_date_processed(queue_key) and msg_count <= ws.date_message_count(queue_key):
                    continue
                latest_ts = max(r["timestamp"] for r in msgs)
                queue_id = ws.enqueue(
                    queue_key, messages, sess["title"] or "", sess["source"] or "",
                    message_count=msg_count, latest_message_at=latest_ts,
                    original_session_id=sid,
                )
                if queue_id:
                    enqueued += 1
        state_db.close()

        from hermes_wiki.wiki_builder import WikiBuilder
        wb = WikiBuilder(ws)
        processed_count = wb.process_pending()

        return {"jsonrpc": "2.0", "id": rid,
                "result": {"enqueued": enqueued, "processed": processed_count,
                           "total_sessions": len(sessions), "already_processed": len(processed)}}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.batch_process failed: {exc}")


def wiki_list_topics(rid, params):
    """Return all topic pages with their associated session pages."""
    try:
        import sys as _sys
        from pathlib import Path as _Path
        plugins_dir = str(_Path(__file__).resolve().parent.parent)
        if plugins_dir not in _sys.path:
            _sys.path.insert(0, plugins_dir)
        from hermes_constants import get_hermes_home
        from hermes_wiki.wiki_store import WikiStore

        ws = WikiStore()
        topics = ws.list_topics()
        ws.close()

        # Simplify session data for frontend
        for t in topics:
            for s in t.get("sessions", []):
                s.pop("source_session_id", None)

        return {"jsonrpc": "2.0", "id": rid,
                "result": {"topics": topics, "count": len(topics)}}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.list_topics failed: {exc}")


def wiki_get_topic(rid, params):
    """Return a topic page with its full content and associated sessions."""
    try:
        slug = params.get("slug", "")
        if not slug:
            return _err(rid, -32602, "Missing 'slug' parameter")

        from hermes_constants import get_hermes_home
        import sys as _sys
        from pathlib import Path as _Path
        plugins_dir = str(_Path(__file__).resolve().parent.parent)
        if plugins_dir not in _sys.path:
            _sys.path.insert(0, plugins_dir)
        from hermes_wiki.wiki_store import WikiStore

        ws = WikiStore()
        topic = ws.get_topic_page(slug)
        if not topic:
            ws.close()
            return _err(rid, -32001, f"Topic '{slug}' not found")

        # Get associated sessions
        topics_list = ws.list_topics()
        sessions = []
        for t in topics_list:
            if t["slug"] == slug:
                sessions = t.get("sessions", [])
                break
        ws.close()

        return {"jsonrpc": "2.0", "id": rid,
                "result": {"topic": dict(topic), "sessions": sessions}}
    except Exception as exc:
        return _err(rid, -32000, f"wiki.get_topic failed: {exc}")
