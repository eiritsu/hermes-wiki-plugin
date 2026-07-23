"""TopicBuilder — independent topic aggregation workflow.

Reads session wiki pages from hermes_wiki_pages (via TopicStore),
calls LLM (via LLMClient, prompts/topic.md) to integrate cross-session
content, and writes topic pages to hermes_wiki_topics.

This is a completely separate workflow from WikiBuilder (session
distillation). No shared prompt, no shared JSON schema — only the
underlying LLMClient HTTP transport is shared.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from llm_client import LLMClient
from topic.topic_store import TopicStore

logger = logging.getLogger("hermes-wiki")


_PROMPT_FILE = "topic.md"

# Per-session full_content truncation (chars). Keeps topic input bounded.
_MAX_SESSION_CONTENT_CHARS = 1500

# Max sessions per topic fed to LLM. Older sessions dropped if exceeded.
_MAX_SESSIONS_PER_TOPIC = 8

# If total input exceeds this, skip LLM and use template fallback.
_MAX_TOTAL_INPUT_CHARS = 10_000


class TopicBuilder:
    """Aggregates session wiki pages into topic pages via LLM integration."""

    def __init__(self, config: Optional[dict] = None,
                 store: Optional[TopicStore] = None,
                 llm: Optional[LLMClient] = None):
        self._config = config or {}
        self._store = store or TopicStore()
        self._llm = llm or LLMClient(config=self._config)

    # -- Prompt loading -----------------------------------------------------

    def _topic_prompt(self) -> str:
        """Load prompts/topic.md. Built-in fallback if file missing."""
        try:
            prompt_path = Path(__file__).parent / "prompts" / _PROMPT_FILE
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8")
        except Exception:
            pass
        # Minimal fallback (should never trigger in production)
        return (
            "Integrate the following wiki sessions into a single topic page. "
            "Return strict JSON with: title, language, overview, "
            "cross_session_decisions, patterns_insights, key_evolution, "
            "timeline, entities, full_content."
        )

    # -- Main aggregation entry point --------------------------------------

    def aggregate_topics(self) -> int:
        """Incremental topic aggregation — only process dirty topics.

        Reads hermes_wiki_topic_dirty for topics that need re-aggregation,
        fetches their wiki pages, calls LLM to integrate, then clears dirty.
        Returns number of topics updated.
        """
        dirty_topics = self._store.get_dirty_topics()
        if not dirty_topics:
            logger.debug("hermes-wiki: no dirty topics, skipping aggregation")
            return 0

        # Build a lookup: topic_slug -> list of changed page slugs
        dirty_map: dict[str, list[str]] = {}
        for d in dirty_topics:
            dirty_map[d["topic_slug"]] = d.get("changed_pages", [])

        # Read all wiki pages once (batch)
        all_sessions = self._store.list_session_full_content()
        if not all_sessions:
            return 0

        # Group all sessions by topic (for later lookup)
        topic_sessions: dict[str, list[dict]] = defaultdict(list)
        for s in all_sessions:
            for t in s.get("topics", []):
                if not t or not isinstance(t, str):
                    continue
                slug = t.strip().lower().replace(" ", "-")
                if len(slug) < 2:
                    continue
                topic_sessions[slug].append(s)

        # Process only dirty topics
        updated = 0
        for topic_slug in dirty_map:
            t_sessions = topic_sessions.get(topic_slug, [])
            if len(t_sessions) < 2:
                # Not enough sessions — clear dirty without aggregation
                self._store.clear_dirty(topic_slug)
                continue
            try:
                if self._aggregate_topic(topic_slug, t_sessions):
                    updated += 1
                    logger.info("hermes-wiki: topic %s aggregated", topic_slug)
                else:
                    # Cache hit — sessions unchanged since last LLM run
                    self._store.clear_dirty(topic_slug)
            except Exception as e:
                logger.debug("hermes-wiki: topic %s aggregation failed: %s", topic_slug, e)
                # Leave dirty — retry next cycle

        logger.info("hermes-wiki: aggregated %d/%d dirty topics", updated, len(dirty_map))
        return updated

    def _aggregate_topic(self, topic_slug: str, sessions: list[dict]) -> bool:
        """Aggregate a single topic.

        Returns:
            True  — LLM integration succeeded (topic page written with full content)
            False — cache hit (no work needed, sessions unchanged since last LLM run)

        On LLM failure: writes fallback topic page AND re-marks topic as dirty
        so the next cycle retries LLM. Caller should NOT clear dirty on False
        return from fallback.
        """
        # Sort by date ascending (oldest first → evolution trace)
        sessions = sorted(sessions, key=lambda s: s.get("date", ""))

        # Cache check: compute signature from session slugs + dates
        signature = self._compute_signature(topic_slug, sessions)
        existing = self._store.get_topic(topic_slug)
        if existing and existing.get("full_content"):
            cached_sig = self._extract_signature_from_content(existing["full_content"])
            if cached_sig == signature and "|fallback" not in (cached_sig or ""):
                logger.debug("hermes-wiki: topic %s cache hit, skipping LLM", topic_slug)
                return False

        # Truncate sessions to fit budget
        truncated = self._truncate_sessions(sessions)
        total_chars = sum(len(s.get("full_content", "")) for s in truncated)
        if total_chars > _MAX_TOTAL_INPUT_CHARS:
            logger.info("hermes-wiki: topic %s too large (%d chars), using fallback",
                        topic_slug, total_chars)
            self._fallback_topic(topic_slug, truncated)
            # Re-mark dirty so next cycle retries LLM
            try:
                self._store.mark_dirty(topic_slug, "__fallback_retry__")
            except Exception:
                pass
            return True  # topic page was written (fallback content)

        # Call LLM
        analysis = self._call_topic_llm(topic_slug, truncated)
        if analysis is None:
            logger.info("hermes-wiki: topic %s LLM failed, using fallback", topic_slug)
            self._fallback_topic(topic_slug, truncated)
            # Re-mark dirty so next cycle retries LLM
            try:
                self._store.mark_dirty(topic_slug, "__fallback_retry__")
            except Exception:
                pass
            return True  # topic page was written (fallback content)

        # Inject signature into full_content YAML frontmatter (cache key)
        full_content = analysis.get("full_content", "")
        full_content = self._inject_signature(full_content, signature)

        title = analysis.get("title") or topic_slug.replace("-", " ").title()
        entities = analysis.get("entities", [])
        language = analysis.get("language", "en")
        session_slugs = [s["slug"] for s in sessions]

        self._store.upsert_topic(
            slug=topic_slug,
            title=title,
            full_content=full_content,
            entities=entities,
            session_count=len(sessions),
            sessions=session_slugs,
            language=language,
        )
        # Clear dirty — LLM integration succeeded
        self._store.clear_dirty(topic_slug)
        return True

    # -- LLM call -----------------------------------------------------------

    def _call_topic_llm(self, topic_slug: str, sessions: list[dict]) -> Optional[dict]:
        """Call LLM with topic prompt + formatted session input."""
        user_prompt = self._format_topic_input(topic_slug, sessions)
        raw = self._llm.send_request(
            system_prompt=self._topic_prompt(),
            user_prompt=user_prompt,
            max_tokens=4000,  # topic integration needs more room than session
            temperature=0.3,
        )
        if raw is None:
            return None
        return self._extract_topic_json(raw)

    def _format_topic_input(self, topic_slug: str, sessions: list[dict]) -> str:
        """Format N session wiki pages into the input the topic prompt expects."""
        lines = [f"# Topic: {topic_slug}", "", f"Linked Sessions ({len(sessions)}):", ""]
        for i, s in enumerate(sessions, 1):
            lines.append(f"═══════════════════════════════════════")
            lines.append(f"[Session {i}] {s.get('date', '')} — {s.get('title', s.get('slug', ''))}")
            lines.append(f"[Slug: {s.get('slug', '')}]")
            lines.append(f"")
            lines.append(s.get("full_content", ""))
            lines.append("")
        return "\n".join(lines)

    def _extract_topic_json(self, raw: str) -> Optional[dict]:
        """Parse topic schema JSON from LLM response."""
        if not raw:
            return None
        # Strip markdown code fences
        text = raw.strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        else:
            # Find first { and last }
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("hermes-wiki: topic JSON parse failed: %s", e)
            return None

    # -- Cache signature (stored in YAML frontmatter) ----------------------

    @staticmethod
    def _compute_signature(topic_slug: str, sessions: list[dict]) -> str:
        """Compute deterministic signature for cache invalidation."""
        parts = [topic_slug, str(len(sessions))]
        for s in sessions:
            parts.append(f"{s.get('slug', '')}@{s.get('date', '')}")
        return "|".join(parts)

    @staticmethod
    def _inject_signature(full_content: str, signature: str) -> str:
        """Add aggregation signature to YAML frontmatter for cache check."""
        if not full_content.startswith("---"):
            # No frontmatter — wrap with one
            return f"---\naggregation_sig: {signature}\n---\n\n{full_content}"
        # Insert aggregation_sig after the opening ---
        lines = full_content.split("\n", 1)
        if len(lines) < 2:
            return f"---\naggregation_sig: {signature}\n---\n\n{full_content}"
        rest = lines[1]
        # rest starts with content; insert after first closing --- if present
        # Simple approach: just add a line right after the opening fence
        return f"---\naggregation_sig: {signature}\n{rest}"

    @staticmethod
    def _extract_signature_from_content(full_content: str) -> Optional[str]:
        """Extract aggregation_sig from YAML frontmatter."""
        if not full_content.startswith("---"):
            return None
        # Find aggregation_sig line in frontmatter (between first two ---)
        end = full_content.find("---", 3)
        if end < 0:
            return None
        frontmatter = full_content[3:end]
        m = re.search(r"^aggregation_sig:\s*(.+)$", frontmatter, re.MULTILINE)
        return m.group(1).strip() if m else None

    # -- Truncation ---------------------------------------------------------

    @staticmethod
    def _truncate_sessions(sessions: list[dict]) -> list[dict]:
        """Bound the LLM input size."""
        if len(sessions) > _MAX_SESSIONS_PER_TOPIC:
            # Drop oldest, keep most recent N
            sessions = sessions[-_MAX_SESSIONS_PER_TOPIC:]
        result = []
        for s in sessions:
            s = dict(s)
            content = s.get("full_content", "") or ""
            if len(content) > _MAX_SESSION_CONTENT_CHARS:
                s["full_content"] = (
                    content[: _MAX_SESSION_CONTENT_CHARS // 2]
                    + "\n...[truncated]...\n"
                    + content[-_MAX_SESSION_CONTENT_CHARS // 2:]
                )
            result.append(s)
        return result

    # -- Fallback (LLM failure / over-budget) ------------------------------

    def _fallback_topic(self, topic_slug: str, sessions: list[dict]) -> None:
        """Generate a minimal topic page without LLM."""
        title = topic_slug.replace("-", " ").title()
        count = len(sessions)

        # Merge entities
        all_entities = set()
        for s in sessions:
            for e in s.get("entities", []):
                if e:
                    all_entities.add(str(e))

        # Build timeline
        timeline_lines = []
        for s in sessions:
            summary = self._extract_summary(s.get("full_content", ""))
            timeline_lines.append(
                f"- [[{s.get('slug', '')}]] ({s.get('date', '')}) — {summary}"
            )

        full_content = f"""---
type: topic-aggregate
aggregation_sig: {self._compute_signature(topic_slug, sessions)}|fallback
sessions: {count}
updated: {sessions[-1].get('date', '') if sessions else ''}
---

# {title}

## Overview
{title} — 包含 {count} 个相关会话的讨论记录。

## Sessions
{chr(10).join(timeline_lines)}

## Related Entities
{chr(10).join(f'- [[{e}]]' for e in sorted(all_entities)) if all_entities else '- (none yet)'}
"""
        self._store.upsert_topic(
            slug=topic_slug,
            title=title,
            full_content=full_content,
            entities=sorted(all_entities),
            session_count=count,
            sessions=[s.get("slug", "") for s in sessions],
            language="en",
        )

    @staticmethod
    def _extract_summary(full_content: str) -> str:
        """Pull first paragraph after # title as a quick summary."""
        if not full_content:
            return ""
        lines = full_content.split("\n")
        in_body = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("# "):
                in_body = True
                continue
            if in_body and not stripped.startswith("#"):
                return stripped[:200]
        return ""