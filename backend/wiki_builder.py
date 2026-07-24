"""
Wiki Builder — LLM-based session analysis and wiki page generation.

Processes pending sessions from WikiStore's queue into structured wiki pages.
Supports 7 languages via automatic detection.

Topic aggregation has been moved to `topic/topic_builder.py` — this module
only handles single-session distillation.
"""

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from topic.topic_builder import normalize_topic_slug

logger = logging.getLogger(__name__)

_MAX_MSG_LEN = 3000
_MAX_MSGS = 80

_I18N = {
    "en": {"bg": "Background", "dec": "Key Decisions", "prob": "Problems & Solutions", "res": "Result", "tl": "Session Timeline", "ov": "Overview"},
    "zh": {"bg": "背景", "dec": "关键决策", "prob": "问题与解决", "res": "结果", "tl": "Session 时间线", "ov": "概述"},
    "ja": {"bg": "背景", "dec": "重要な決定", "prob": "問題と解決", "res": "結果", "tl": "セッションタイムライン", "ov": "概要"},
    "ko": {"bg": "배경", "dec": "주요 결정", "prob": "문제와 해결", "res": "결과", "tl": "세션 타임라인", "ov": "개요"},
    "de": {"bg": "Hintergrund", "dec": "Wichtige Entscheidungen", "prob": "Probleme & Lösungen", "res": "Ergebnis", "tl": "Sitzungsverlauf", "ov": "Übersicht"},
    "fr": {"bg": "Contexte", "dec": "Décisions clés", "prob": "Problèmes et solutions", "res": "Résultat", "tl": "Chronologie", "ov": "Aperçu"},
    "es": {"bg": "Contexto", "dec": "Decisiones clave", "prob": "Problemas y soluciones", "res": "Resultado", "tl": "Cronología", "ov": "Resumen"},
}


# ── WikiStore import (with path fix for plugin context) ─────────────────────

def _import_wiki_store():
    """Import WikiStore with path fix for plugin runtime context."""
    try:
        from wiki_store import WikiStore
        return WikiStore
    except ImportError:
        import sys
        from pathlib import Path
        backend_dir = str(Path(__file__).resolve().parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from wiki_store import WikiStore
        return WikiStore


class WikiBuilder:
    """Distills a single conversation session into a structured wiki page.

    Topic aggregation (cross-session integration) lives in
    topic/topic_builder.py and uses an independent prompt + LLMClient
    sharing only the underlying HTTP transport.
    """

    def __init__(self, config: Optional[dict] = None,
                 store=None, fact_store=None,
                 llm_client=None):
        self._config = config or {}
        self._fact_store = fact_store
        WikiStoreCls = _import_wiki_store()
        self._store = store or WikiStoreCls()
        # Lazy LLMClient initialization
        self._llm = llm_client
        # Lazy TopicStore for dirty marker writes
        self._topic_store = None

    # -- Hook entry point ---------------------------------------------------

    def enqueue_session(self, session_id: str, messages: list, title: str = "",
                        source: str = "hook") -> None:
        """Called by hooks (on_session_end / on_session_reset).

        Persists messages to the SQLite queue and kicks off the worker.
        """
        try:
            messages_json = json.dumps(messages, ensure_ascii=False, default=str)
            self._store.enqueue(session_id, title, source,
                                len(messages), messages_json)
            logger.debug("hermes-wiki: queued session %s (%d messages)", session_id, len(messages))
        except Exception as e:
            logger.error("hermes-wiki: enqueue failed for %s: %s", session_id, e)

    def process_pending(self) -> int:
        """Worker loop: drain the SQLite queue and process each session."""
        processed = 0
        try:
            while True:
                item = self._store.dequeue_pending()
                if not item:
                    break
                # sqlite Row with id field (queue row id)
                queue_id = item["id"]
                session_id = item["session_id"]
                try:
                    messages = json.loads(item["messages_json"])
                    self._process_session(
                        session_id=session_id,
                        title=item.get("title", ""),
                        source=item.get("source", "queue"),
                        messages=messages,
                        source_message_count=item.get("message_count", len(messages)),
                        original_sid=session_id,
                    )
                    self._store.mark_done(queue_id)
                    processed += 1
                except Exception as e:
                    logger.error("hermes-wiki: session %s failed: %s", session_id, e)
                    # Requeue for retry (topic-style infinite retry, no permanent fail).
                    # Exponential backoff capped at 5 min; next batch_scan picks it up
                    # once next_retry_at expires.
                    self._store.retry_or_fail(queue_id, str(e))
        except Exception as e:
            logger.error("hermes-wiki: queue processing error: %s", e)
        if processed:
            logger.info("hermes-wiki: processed %d sessions from queue", processed)
        return processed

    # -- Session processing -------------------------------------------------

    def _process_session(self, session_id: str, title: str, source: str,
                         messages: list, source_message_count: int,
                         original_sid: str) -> None:
        date = self._date_from_id(session_id)

        # Filter and truncate messages for LLM input
        filtered: List[Dict[str, str]] = []
        for msg in messages:
            content = msg.get("content") or msg.get("text") or ""
            if not content.strip():
                continue
            if len(content) > _MAX_MSG_LEN:
                content = content[: _MAX_MSG_LEN // 2] + "\n...[truncated]...\n" + content[-_MAX_MSG_LEN // 2:]
            filtered.append({"role": msg["role"], "content": content})

        if len(filtered) < 2:
            return
        if len(filtered) > _MAX_MSGS:
            filtered = filtered[:_MAX_MSGS]

        analysis = self._call_llm(filtered, title, source)
        if analysis is None:
            raise RuntimeError("LLM returned no usable wiki analysis")
        quality = max(1, min(5, analysis.get("quality", 2)))
        slug = self._slug(date, analysis.get("title", title))
        lang = analysis.get("language", "en")
        topics = analysis.get("topics", [])
        entities = analysis.get("entities", [])
        keywords = analysis.get("keywords", [])

        # Use LLM's full_content if available, otherwise fallback to _build_page
        llm_content = analysis.get("full_content", "")
        if llm_content and len(llm_content) > 50:
            # Fix LLM-hallucinated dates in YAML frontmatter and title
            llm_content = re.sub(
                r'^(date:\s*)\d{4}(-\d{2}(?:-\d{2})?)',
                rf'\g<1>{date}',
                llm_content, count=1, flags=re.MULTILINE,
            )
            llm_content = re.sub(
                r'^(#\s*.*?)\(\d{4}-\d{2}-\d{2}\)',
                rf'\1({date})',
                llm_content, count=1, flags=re.MULTILINE,
            )
            full_content = llm_content
        else:
            full_content = self._build_page(
                session_id=original_sid, date=date, title=analysis.get("title", title),
                language=lang, quality=quality, content_type=analysis.get("content_type", "discussion"),
                topics=topics, entities=entities, keywords=keywords,
                result=analysis.get("result", ""), background=analysis.get("background", ""),
                decisions=analysis.get("decisions", []), problems=analysis.get("problems", []),
            )

        self._store.insert_page(
            page_type="session", slug=slug, title=analysis.get("title", title),
            date=date, language=lang, quality=quality,
            content_type=analysis.get("content_type", "discussion"),
            topics=topics, entities=entities, keywords=keywords,
            summary=(analysis.get("result", "") or analysis.get("background", ""))[:200],
            full_content=full_content, source_session_id=original_sid,
            message_count=source_message_count,
        )

        if quality < 4:
            self._store.delete_low_quality_session_page(original_sid)
            self._store.record_session_state(session_id, source_message_count, quality)
            logger.info("hermes-wiki: discarded low-quality page for %s (q=%d)", session_id, quality)
            return

        # Extract facts to holographic memory (extension mode only)
        facts = analysis.get("facts", [])
        if facts and self._fact_store:
            self._extract_facts(facts, original_sid)

        self._store.record_session_state(session_id, source_message_count, quality)

        # Mark dirty topics for incremental topic aggregation
        self._mark_topics_dirty(topics, slug)

        logger.info("hermes-wiki: %s (q=%d, topics=%s, facts=%d)", slug, quality, topics, len(facts))

    # -- Topic dirty marker ------------------------------------------------

    def _mark_topics_dirty(self, topics: list, wiki_page_slug: str) -> None:
        """Mark topics as dirty after a wiki page is written.

        Lazy-initializes TopicStore on first call. Failures are non-fatal
        (dirty marker is a soft signal, not a correctness requirement).
        """
        if not topics:
            return
        if self._topic_store is None:
            try:
                from topic.topic_store import TopicStore
                self._topic_store = TopicStore()
            except Exception as e:
                logger.debug("hermes-wiki: TopicStore init failed, skipping dirty marker: %s", e)
                return
        for topic_slug in topics:
            if not topic_slug or not isinstance(topic_slug, str):
                continue
            topic_slug = normalize_topic_slug(topic_slug)
            if len(topic_slug) < 2:
                continue
            try:
                self._topic_store.mark_dirty(topic_slug, wiki_page_slug)
                logger.debug("hermes-wiki: marked %s dirty (page %s)", topic_slug, wiki_page_slug)
            except Exception as e:
                logger.debug("hermes-wiki: mark_dirty failed for %s: %s", topic_slug, e)

    # -- Fact extraction to holographic memory ----------------------------

    def _extract_facts(self, facts: list, session_id: str) -> None:
        """Write LLM-extracted facts to holographic fact_store."""
        if not self._fact_store:
            return
        for f in facts:
            content = (f.get("content") or "").strip()
            if not content or len(content) < 10:
                continue
            category = f.get("category", "general")
            if category not in ("tool", "project", "user_pref", "general"):
                category = "general"
            tags = f.get("tags", "")
            try:
                fact_id = self._fact_store.add_fact(
                    content=content,
                    category=category,
                    tags=tags,
                )
                logger.debug("hermes-wiki: fact #%d: %s...", fact_id, content[:50])
            except Exception as e:
                logger.debug("hermes-wiki: fact extraction failed: %s", e)

    # -- LLM call -----------------------------------------------------------

    def _call_llm(self, messages: list, title: str, source: str) -> Optional[dict]:
        """Send session chat to LLM via shared LLMClient, parse session-schema JSON."""
        from llm_client import LLMClient
        if self._llm is None:
            self._llm = LLMClient(config=self._config)
        user_prompt = self._format_msgs(messages, title, source)
        raw = self._llm.send_request(
            system_prompt=self._prompt(),
            user_prompt=user_prompt,
            max_tokens=3000,  # wiki pages can be ~1.5K tokens, leave headroom for JSON fields
            temperature=0.3,
        )
        if raw is None:
            return None
        return self._extract_json(raw)

    def _prompt(self) -> str:
        """Load the session wiki prompt from prompts/wiki.md.

        This is the session → wiki workflow prompt. The topic aggregation
        workflow uses a different prompt (prompts/topic.md) loaded by
        topic/topic_builder._topic_prompt().
        """
        try:
            prompt_path = Path(__file__).parent / "prompts" / "wiki.md"
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8")
        except Exception:
            pass
        # Built-in fallback
        return (
            "Analyze the following session and return strict JSON only:\n"
            '{"title":"Session title (<=30 chars)","language":"en","quality":3,'
            '"content_type":"discussion","topics":["topic-slug"],"entities":["Entity Name"],'
            '"keywords":["keyword"],"result":"One-sentence outcome",'
            '"background":"Brief user goal (<=100 chars)",'
            '"decisions":["Decision and reason"],"problems":["Problem -> Solution"],'
            '"full_content":"Complete Obsidian wiki page with YAML frontmatter, ## sections, [[wiki-links]], #tags"}\n\n'
            "CRITICAL: Respond in the SAME LANGUAGE as the session content.\n"
            'language field: ISO 639-1 ("en","zh","ja","ko","de","fr","es").\n'
            "All text fields in that language. topic slugs, entity names, content_type in English.\n"
            "Quality: 5=deep+important, 4=substantial, 3=moderate, 2=simple Q&A, 1=no value.\n"
            "full_content must be substantial (5+ paragraphs for quality >= 3)."
        )

    def _format_msgs(self, messages: list, title: str, source: str) -> str:
        lines = []
        if title:
            lines.append(f"Title: {title}")
        if source:
            lines.append(f"Source: {source}")
        lines.append(f"Messages: {len(messages)}")
        lines.append("---")
        for msg in messages:
            p = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"[{p}]: {msg['content'][:1500]}")
        return "\n".join(lines)

    def _extract_json(self, text: str) -> Optional[dict]:
        text = text.strip()
        for pattern in [
            lambda t: json.loads(t),
            lambda t: json.loads(re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", t, re.DOTALL).group(1).strip()),
            lambda t: json.loads(re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", t, re.DOTALL).group(0)),
        ]:
            try:
                return pattern(text)
            except (json.JSONDecodeError, AttributeError):
                continue
        return None

    # -- Defaults & helpers -------------------------------------------------

    def _default(self, title: str) -> dict:
        return {"title": title or "Untitled", "language": "en", "quality": 2,
                "content_type": "discussion", "topics": [], "entities": [], "keywords": [],
                "result": "", "background": "", "decisions": [], "problems": []}

    def _build_page(self, **kw) -> str:
        lang = kw.get("language", "en")
        h = _I18N.get(lang, _I18N["en"])
        lines = [
            "---",
            f'session_id: "{kw["session_id"]}"',
            f'date: {kw["date"]}',
            f'language: {lang}',
            f'quality: {kw["quality"]}',
            f'content_type: {kw["content_type"]}',
            f'topics: {json.dumps(kw["topics"], ensure_ascii=False)}',
            f'entities: {json.dumps(kw["entities"], ensure_ascii=False)}',
            f'keywords: {json.dumps(kw["keywords"], ensure_ascii=False)}',
            f'result: "{kw["result"]}"',
            "---", "",
            f"# {kw['title']} ({kw['date']})", "",
        ]
        for field, key in [("background", "bg"), ("decisions", "dec"), ("problems", "prob"), ("result", "res")]:
            val = kw.get(field)
            if not val:
                continue
            lines.append(f"## {h[key]}")
            if isinstance(val, list):
                for v in val:
                    lines.append(f"- {v}")
            else:
                lines.append(val)
            lines.append("")
        return "\n".join(lines)

    def _date_from_id(self, sid: str) -> str:
        m = re.match(r"(\d{4})(\d{2})(\d{2})", sid)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else datetime.date.today().isoformat()

    def _slug(self, date: str, title: str) -> str:
        s = re.sub(r"[^\w\s-]", "", title.lower())
        s = re.sub(r"[\s_]+", "-", s).strip("-")[:40]
        return f"{date}_{s}" if s else f"{date}_untitled"

    # -- HTTP/auth helpers (forwarded to LLMClient) -------------------------

    @staticmethod
    def _resolve_url(provider: str) -> Optional[str]:
        from llm_client import LLMClient
        return LLMClient._resolve_url(provider)

    @staticmethod
    def _resolve_key(provider: str) -> Optional[str]:
        from llm_client import LLMClient
        return LLMClient._resolve_key(provider)