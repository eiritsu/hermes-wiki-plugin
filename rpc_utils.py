"""Shared JSON-RPC utilities for hermes-wiki.

Reused by:
- backend/wiki_rpc.py (session RPCs: wiki.list, wiki.get, ...)
- backend/topic/topic_rpc.py (topic RPCs: topic.list, topic.get)

Only the plumbing (error envelope, path setup, JSON column parsing)
is shared. The actual SQL/Store access stays in each module's RPC.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


def _err(rid, code: int, msg: str) -> dict:
    """Return a JSON-RPC 2.0 error envelope."""
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def setup_plugin_path() -> None:
    """Ensure the hermes-wiki plugin's backend dir is on sys.path.

    Idempotent — safe to call multiple times.
    """
    backend_dir = str(Path(__file__).resolve().parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def parse_json_columns(row: dict, columns: tuple[str, ...] = ("topics", "keywords", "entities")) -> dict:
    """Parse JSON-encoded columns in a sqlite Row dict.

    Returns a copy with parsed lists/objects. Missing or invalid JSON
    becomes an empty list.
    """
    out = dict(row)
    for key in columns:
        if key not in out:
            continue
        val = out[key]
        if isinstance(val, str) and val:
            try:
                out[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                out[key] = []
        elif not val:
            out[key] = []
    return out


# Standard JSON-RPC error codes used by hermes-wiki RPCs
class RpcError:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # Application-defined codes (plugin-specific)
    NOT_FOUND = -32004
    CONFLICT = -32002
    SERVER_ERROR = -32000