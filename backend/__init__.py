"""
hermes-wiki — Automatic session-to-wiki conversion plugin.

Two modes:
  - Extension mode: holographic active → shares connection, augments fact_store search
  - Standalone mode: no holographic → own connection, wiki_search tool

Trigger strategy:
  - on_session_end hook: immediate processing when session closes
  - Periodic scan (every 5 min): incremental batch of unprocessed sessions from state.db
  - First load: full batch of all historical sessions
"""

import datetime
import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_wiki_store = None
_wiki_builder = None
_wiki_thread = None
_wiki_thread_lock = threading.Lock()
_scan_timer = None
_SCAN_INTERVAL = 3600  # 1 hour

WIKI_SEARCH_SCHEMA = {
    "name": "wiki_search",
    "description": (
        "PRIORITY TOOL for historical queries. Search the wiki knowledge base "
        "FIRST before using session_search. Wiki pages are auto-generated from "
        "conversation sessions with quality scoring, topic classification, "
        "entity extraction, and 7-language i18n. Use this to find past "
        "session knowledge, decisions, and technical details. "
        "Covers dates, topics, entities, and keywords."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
        },
        "required": ["query"],
    },
}


# ── Session end hook ────────────────────────────────────────────────────

def _on_session_end(messages: List[Dict[str, Any]], **kwargs) -> None:
    """Hook: enqueue session for wiki processing (non-blocking), date-segmented."""
    global _wiki_store, _wiki_builder
    if not _wiki_store or not _wiki_builder or not messages or len(messages) < 2:
        return

    session_id = kwargs.get("session_id", "")
    if not session_id or "cron_" in session_id or "memory-wiki" in session_id:
        return

    try:
        # Group messages by date
        from collections import OrderedDict
        date_msgs: OrderedDict = OrderedDict()
        for msg in messages:
            ts = msg.get("timestamp", 0)
            if ts:
                d = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            else:
                d = datetime.date.today().isoformat()
            date_msgs.setdefault(d, []).append(msg)

        title = kwargs.get("title", "")
        source = kwargs.get("source", "")

        for date_str, msgs in date_msgs.items():
            if len(msgs) < 2:
                continue
            queue_key = f"{session_id}:{date_str}"
            latest_ts = max(m.get("timestamp", 0) for m in msgs if m.get("timestamp"))
            _wiki_store.enqueue(
                queue_key, msgs, title, source,
                latest_message_at=latest_ts if latest_ts else None,
                original_session_id=session_id,
            )
        _schedule_worker()
    except Exception as e:
        logger.debug("hermes-wiki: enqueue failed: %s", e)


# ── Periodic batch scan ────────────────────────────────────────────────

def _batch_scan() -> None:
    """Scan state.db for unprocessed sessions and enqueue them."""
    global _wiki_store, _wiki_builder
    if not _wiki_store or not _wiki_builder:
        return

    try:
        _wiki_store.recover_stale_processing(max_age_seconds=900)
        from hermes_constants import get_hermes_home
        state_db_path = str(get_hermes_home() / "state.db")

        state_db = sqlite3.connect(state_db_path, check_same_thread=False, timeout=5.0)
        state_db.row_factory = sqlite3.Row

        # Get all non-cron/subagent sessions with >= 2 messages
        sessions = state_db.execute(
            """SELECT id, title, source, message_count
               FROM sessions
               WHERE source NOT IN ('cron', 'subagent')
                 AND message_count >= 2
               ORDER BY started_at DESC
               LIMIT 50""",
        ).fetchall()

        # Read messages for each session, group by date, enqueue per-date segments.
        enqueued = 0
        for sess in sessions:
            sid = sess["id"]

            # Skip if any pending items exist for this session
            pending_rows = _wiki_store._conn.execute(
                "SELECT 1 FROM hermes_wiki_pending_queue WHERE session_id = ? AND status IN ('pending', 'processing')",
                (sid,),
            ).fetchone()
            if pending_rows:
                continue

            title = sess["title"] or ""
            source = sess["source"] or ""

            msg_rows = state_db.execute(
                """SELECT role, content, timestamp FROM messages
                   WHERE session_id = ? AND role IN ('user', 'assistant')
                   ORDER BY timestamp ASC""",
                (sid,),
            ).fetchall()

            if len(msg_rows) < 2:
                continue

            # Group messages by date
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

                # For historical dates, skip if already processed with same or more messages
                if date_str != today:
                    if _wiki_store.is_date_processed(queue_key) and msg_count <= _wiki_store.date_message_count(queue_key):
                        continue

                # For today, skip if message count hasn't grown
                if date_str == today:
                    if _wiki_store.is_date_processed(queue_key) and msg_count <= _wiki_store.date_message_count(queue_key):
                        continue

                latest_ts = max(r["timestamp"] for r in msgs)
                _wiki_store.enqueue(
                    queue_key, messages, title, source,
                    message_count=msg_count, latest_message_at=latest_ts,
                    original_session_id=sid,
                )
                enqueued += 1

        state_db.close()

        if enqueued:
            logger.info("hermes-wiki: batch scan enqueued %d sessions", enqueued)
            _schedule_worker()
        else:
            # No new sessions — check if there are retried items ready to process
            ready = _wiki_store._conn.execute(
                "SELECT 1 FROM hermes_wiki_pending_queue "
                "WHERE status = 'pending' "
                "AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP) "
                "LIMIT 1"
            ).fetchone()
            if ready:
                _schedule_worker()
            elif _wiki_builder:
                _wiki_builder.cleanup()

    except Exception as e:
        logger.debug("hermes-wiki: batch scan failed: %s", e)


def _start_scan_timer() -> None:
    """Start periodic scan timer (every 5 minutes)."""
    global _scan_timer
    try:
        _batch_scan()  # Run immediately on first load
    except Exception:
        pass

    def _tick():
        _batch_scan()
        _schedule_timer()

    def _schedule_timer():
        global _scan_timer
        _scan_timer = threading.Timer(_SCAN_INTERVAL, _tick)
        _scan_timer.daemon = True
        _scan_timer.start()

    _schedule_timer()


# ── Background worker ──────────────────────────────────────────────────

def _schedule_worker() -> None:
    global _wiki_thread
    with _wiki_thread_lock:
        if _wiki_thread and _wiki_thread.is_alive():
            return
        _wiki_thread = threading.Thread(target=_worker, daemon=True, name="hermes-wiki")
        _wiki_thread.start()


def _worker() -> None:
    global _wiki_builder
    try:
        count = _wiki_builder.process_pending()
        if count:
            logger.info("hermes-wiki: processed %d sessions", count)
    except Exception as e:
        logger.error("hermes-wiki: worker failed: %s", e)


# ── Tool handlers ──────────────────────────────────────────────────────

def _handle_wiki_search(args: dict, **kwargs) -> str:
    global _wiki_store
    if not _wiki_store:
        logger.warning("wiki_search: _wiki_store is None")
        return json.dumps({"error": "Wiki store not initialized"})
    query = args.get("query", "").strip()
    if not query:
        logger.warning("wiki_search: empty query, args=%s", args)
        return json.dumps({"error": "Empty query"})
    results = _wiki_store.search_pages(query, limit=args.get("limit", 5))
    logger.info("wiki_search: query=%r results=%d", query, len(results))
    return json.dumps({"results": results, "count": len(results)})


def _handle_wiki_command(raw_args: str) -> str:
    """Slash command handler for /wiki <query>."""
    global _wiki_store
    if not _wiki_store:
        return "Wiki store not initialized"
    query = raw_args.strip()
    if not query:
        # Show recent pages
        pages = _wiki_store.get_all_pages()
        if not pages:
            return "No wiki pages yet."
        lines = [f"Wiki pages ({len(pages)}):"]
        for p in pages[:15]:
            lines.append(f"  [{p.get('date','')}] {p.get('title','')} (q={p.get('quality','')})")
        if len(pages) > 15:
            lines.append(f"  ... and {len(pages)-15} more")
        return "\n".join(lines)
    results = _wiki_store.search_pages(query, limit=10)
    if not results:
        return f"No wiki pages matching '{query}'."
    lines = [f"Wiki search '{query}' ({len(results)} results):"]
    for r in results:
        lines.append(f"  [{r.get('date','')}] {r.get('title','')} (q={r.get('quality','')})")
        if r.get('summary'):
            lines.append(f"    {r['summary'][:100]}")
    return "\n".join(lines)


def _transform_fact_store_result(tool_name: str, result: str, **kwargs) -> str:
    """Hook: inject wiki results into fact_store search results."""
    if tool_name != "fact_store":
        return result
    try:
        args = kwargs.get("args", {})
        if args.get("action") != "search":
            return result
        query = args.get("query", "").strip()
        if not query or not _wiki_store:
            return result

        wiki_results = _wiki_store.search_pages(query, limit=3)
        if not wiki_results:
            return result

        parsed = json.loads(result)
        for r in wiki_results:
            parsed["results"].append({
                "content": r.get("summary", r.get("title", "")),
                "category": "wiki",
                "tags": f"wiki:{r.get('slug', '')}",
                "source": "wiki",
                "wiki_slug": r.get("slug", ""),
                "wiki_title": r.get("title", ""),
                "wiki_quality": r.get("quality"),
            })
        parsed["count"] = len(parsed["results"])
        return json.dumps(parsed)
    except Exception:
        return result


# ── Plugin entry point ─────────────────────────────────────────────────

def register(ctx) -> None:
    """Plugin entry point: detect holographic, register hooks and tools."""
    global _wiki_store, _wiki_builder

    from .wiki_store import WikiStore
    from .wiki_builder import WikiBuilder

    # Detect holographic provider
    holographic_conn = None
    holographic_lock = None
    try:
        from plugins.memory.holographic.store import MemoryStore as HoloStore
        if HoloStore._shared:
            for key, entry in HoloStore._shared.items():
                if "memory_store.db" in key:
                    holographic_conn = entry["conn"]
                    holographic_lock = entry["lock"]
                    break
    except (ImportError, AttributeError):
        pass

    if holographic_conn:
        logger.info("hermes-wiki: extension mode (holographic detected)")
        _wiki_store = WikiStore(conn=holographic_conn, lock=holographic_lock)
        ctx.register_hook("transform_tool_result", _transform_fact_store_result)
        # Create MemoryStore for fact extraction (reuses shared connection)
        try:
            _fact_store = HoloStore()
        except Exception:
            _fact_store = None
    else:
        logger.info("hermes-wiki: standalone mode")
        _wiki_store = WikiStore()
        _fact_store = None
        ctx.register_tool(
            name="wiki_search",
            toolset="memory",
            schema=WIKI_SEARCH_SCHEMA,
            handler=_handle_wiki_search,
        )

    _wiki_builder = WikiBuilder(_wiki_store, fact_store=_fact_store)

    # Register session end hook (immediate processing)
    ctx.register_hook("on_session_end", _on_session_end)

    # Register Gateway RPC methods for Desktop Plugin GUI when the host supports it.
    # Older/local Hermes builds without plugin RPC must still load the backend timer.
    if hasattr(ctx, "register_rpc"):
        from .wiki_rpc import (
            wiki_list, wiki_get, wiki_create,
            wiki_update, wiki_delete, wiki_stats, wiki_batch_process,
        )
        ctx.register_rpc("wiki.list", wiki_list)
        ctx.register_rpc("wiki.get", wiki_get)
        ctx.register_rpc("wiki.create", wiki_create)
        ctx.register_rpc("wiki.update", wiki_update)
        ctx.register_rpc("wiki.delete", wiki_delete)
        ctx.register_rpc("wiki.stats", wiki_stats)
        ctx.register_rpc("wiki.batch_process", wiki_batch_process)
    else:
        logger.warning("hermes-wiki: plugin RPC unavailable; Desktop GUI RPC disabled")

    # Start periodic scan timer (5 min interval + immediate first run)
    _start_scan_timer()
