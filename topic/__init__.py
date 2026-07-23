"""Topic backend — independent module.

Registered by the main plugin's __init__.py via register().
Owns:
- TopicBuilder (LLM-driven topic aggregation)
- TopicStore (hermes_wiki_topics table)
- topic.* RPC methods

The main wiki backend (__init__.py + wiki_builder.py + wiki_rpc.py) is
unaware of this module's internals — they only share the underlying
LLMClient HTTP transport and the memory_store.db file.
"""

import sys
import threading
import logging
from pathlib import Path

# Ensure backend dir is on path
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

logger = logging.getLogger("hermes-wiki")

_TOPIC_AGG_INTERVAL = 7200  # 2 hours
_topic_agg_timer: "threading.Timer | None" = None
_topic_builder_instance = None


def _start_topic_timer(ctx) -> None:
    """Start topic aggregation timer (every 2 hours, independent of session scan)."""
    global _topic_agg_timer, _topic_builder_instance

    from topic.topic_builder import TopicBuilder

    def _tick():
        global _topic_builder_instance
        try:
            if _topic_builder_instance is None:
                _topic_builder_instance = TopicBuilder()
            _topic_builder_instance.aggregate_topics()
        except Exception as e:
            logger.debug("hermes-wiki: topic aggregation failed: %s", e)
        _schedule_topic_timer(ctx)

    def _schedule_topic_timer(ctx):
        global _topic_agg_timer
        _topic_agg_timer = threading.Timer(_TOPIC_AGG_INTERVAL, _tick)
        _topic_agg_timer.daemon = True
        _topic_agg_timer.start()

    # Run first aggregation after a short delay (let session processing settle)
    _topic_agg_timer = threading.Timer(60, _tick)
    _topic_agg_timer.daemon = True
    _topic_agg_timer.start()


def register(ctx) -> None:
    """Register topic RPCs and start topic timer. Called by main __init__.py."""
    from topic.topic_rpc import topic_list, topic_get
    from topic.topic_store import TopicStore

    # One-time migration: copy page_type='topic' rows from hermes_wiki_pages
    try:
        TopicStore().migrate_from_wiki_pages()
    except Exception as e:
        logger.debug("hermes-wiki: topic migration failed: %s", e)

    # Register topic.* RPC
    try:
        ctx.register_rpc("topic.list", topic_list)
        ctx.register_rpc("topic.get", topic_get)
    except Exception:
        logger.warning("hermes-wiki: topic RPC registration unavailable")

    # Start topic aggregation timer
    _start_topic_timer(ctx)