"""
hermes-wiki — Automatic session-to-wiki conversion plugin.

Two modes:
  - Extension mode: holographic active → shares connection, augments fact_store search
  - Standalone mode: no holographic → own connection, wiki_search tool
"""

import json
import logging
import threading
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_wiki_store = None
_wiki_builder = None
_wiki_thread = None
_wiki_thread_lock = threading.Lock()

WIKI_SEARCH_SCHEMA = {
    "name": "wiki_search",
    "description": (
        "Search the wiki knowledge base. Wiki pages are auto-generated from "
        "conversation sessions with quality scoring, topic classification, "
        "entity extraction, and 7-language i18n. Use this to find past "
        "session knowledge, decisions, and technical details."
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


def _on_session_end(messages: List[Dict[str, Any]], **kwargs) -> None:
    """Hook: enqueue session for wiki processing (non-blocking)."""
    global _wiki_store, _wiki_builder
    if not _wiki_store or not _wiki_builder or not messages or len(messages) < 2:
        return

    session_id = kwargs.get("session_id", "")
    if not session_id or "cron_" in session_id or "memory-wiki" in session_id:
        return

    try:
        _wiki_store.enqueue(
            session_id=session_id, messages=messages,
            title=kwargs.get("title", ""), source=kwargs.get("source", ""),
        )
        _schedule_worker()
    except Exception as e:
        logger.debug("hermes-wiki: enqueue failed: %s", e)


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


def _handle_wiki_search(args: dict) -> str:
    global _wiki_store
    if not _wiki_store:
        return json.dumps({"error": "Wiki store not initialized"})
    query = args.get("query", "").strip()
    if not query:
        return json.dumps({"error": "Empty query"})
    results = _wiki_store.search_pages(query, limit=args.get("limit", 5))
    return json.dumps({"results": results, "count": len(results)})


def _transform_fact_store_result(tool_name: str, result: str, **kwargs) -> str:
    """Hook: inject wiki results into fact_store search results.

    When holographic is active and user calls fact_store(action='search'),
    this hook appends wiki page results to the response.
    """
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
        # Access the shared connection registry
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
        # Augment fact_store search with wiki results
        ctx.register_hook("transform_tool_result", _transform_fact_store_result)
    else:
        logger.info("hermes-wiki: standalone mode")
        _wiki_store = WikiStore()
        # Register wiki_search tool
        ctx.register_tool(
            name="wiki_search",
            toolset="hermes-wiki",
            schema=WIKI_SEARCH_SCHEMA,
            handler=_handle_wiki_search,
        )

    _wiki_builder = WikiBuilder(_wiki_store)

    # Register session end hook
    ctx.register_hook("on_session_end", _on_session_end)

    # Process leftover queue from previous runs
    _schedule_worker()
