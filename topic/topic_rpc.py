"""Topic RPC methods — registered as topic.list / topic.get.

Replaces the old wiki.list_topics / wiki.get_topic RPCs (which were
implemented in wiki_rpc.py and coupled the topic workflow to the wiki
workflow). These are independent methods backed by TopicStore.
"""

from __future__ import annotations

import logging
from typing import Optional

from rpc_utils import _err, RpcError

logger = logging.getLogger("hermes-wiki")

_store: Optional["TopicStore"] = None


def _get_store() -> "TopicStore":
    global _store
    if _store is None:
        from topic.topic_store import TopicStore
        _store = TopicStore()
    return _store


def topic_list(rid, params):
    """Return all topic pages."""
    try:
        store = _get_store()
        topics = store.list_topics()
        return {"jsonrpc": "2.0", "id": rid, "result": {"topics": topics}}
    except Exception as e:
        logger.error("hermes-wiki: topic.list failed: %s", e)
        return _err(rid, RpcError.INTERNAL_ERROR, f"Internal error: {e}")


def topic_get(rid, params):
    """Return a single topic page by slug."""
    slug = (params or {}).get("slug", "")
    if not slug:
        return _err(rid, RpcError.INVALID_PARAMS, "Missing 'slug' parameter")
    try:
        store = _get_store()
        topic = store.get_topic(slug)
        if not topic:
            return _err(rid, RpcError.NOT_FOUND, f"Topic not found: {slug}")
        return {"jsonrpc": "2.0", "id": rid, "result": topic}
    except Exception as e:
        logger.error("hermes-wiki: topic.get failed: %s", e)
        return _err(rid, RpcError.INTERNAL_ERROR, f"Internal error: {e}")