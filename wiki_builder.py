"""
Wiki Builder — LLM-based session analysis and wiki page generation.

Processes pending sessions from WikiStore's queue into structured wiki pages.
Supports 7 languages via automatic detection.
"""

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

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


class WikiBuilder:
    """Process pending sessions into wiki pages via LLM analysis."""

    def __init__(self, store, config: dict = None):
        self._store = store
        self._config = config or {}

    def process_pending(self) -> int:
        processed = 0
        while True:
            items = self._store.dequeue(limit=1)
            if not items:
                break
            item = items[0]
            try:
                self._process_session(item)
                self._store.mark_done(item["id"], "done")
                processed += 1
            except Exception as e:
                status = self._store.retry_or_fail(item["id"], str(e))
                logger.warning(
                    "hermes-wiki: %s for %s after error: %s",
                    status, item.get("session_id"), e,
                )
        self._cleanup()
        return processed

    def cleanup(self) -> None:
        """Public cleanup — can be called independently."""
        self._cleanup()

    def _cleanup(self) -> None:
        """Remove low-quality pages, topic pages, and stale queue entries."""
        try:
            with self._store._lock:
                # 1. Delete quality < 4 session pages
                self._store._conn.execute(
                    "DELETE FROM hermes_wiki_pages WHERE quality < 4 AND page_type = 'session'"
                )
                # 2. Delete all topic pages (not needed)
                self._store._conn.execute(
                    "DELETE FROM hermes_wiki_pages WHERE page_type = 'topic'"
                )
                # 3. Clean up done/failed queue entries
                self._store._conn.execute(
                    "DELETE FROM hermes_wiki_pending_queue WHERE status IN ('done', 'failed')"
                )
                self._store._conn.commit()
            logger.debug("hermes-wiki: cleanup done")
        except Exception as e:
            logger.debug("hermes-wiki: cleanup failed: %s", e)

    def _process_session(self, item: dict) -> None:
        session_id = item["session_id"]
        title = item.get("title", "") or ""
        source = item.get("source", "")
        messages = item.get("messages", [])
        source_message_count = int(item.get("message_count") or len(messages))

        if self._store.is_session_processed(session_id) and source_message_count <= self._store.session_message_count(session_id):
            return

        filtered = []
        for msg in messages:
            if msg.get("role") not in ("user", "assistant"):
                continue
            content = msg.get("content", "")
            if not content or not isinstance(content, str):
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
        date = self._date_from_id(session_id)
        slug = self._slug(date, analysis.get("title", title))
        lang = analysis.get("language", "en")
        topics = analysis.get("topics", [])
        entities = analysis.get("entities", [])
        keywords = analysis.get("keywords", [])

        # Use LLM's full_content if available, otherwise fallback to _build_page
        llm_content = analysis.get("full_content", "")
        if llm_content and len(llm_content) > 50:
            full_content = llm_content
        else:
            full_content = self._build_page(
                session_id=session_id, date=date, title=analysis.get("title", title),
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
            full_content=full_content, source_session_id=session_id,
            message_count=source_message_count,
        )

        if quality < 4:
            # Record the attempted revision so periodic scans do not endlessly requeue it.
            self._store.delete_low_quality_session_page(session_id)
            self._store.record_session_state(session_id, source_message_count, quality)
            logger.info("hermes-wiki: discarded low-quality page for %s (q=%d)", session_id, quality)
            return

        self._store.record_session_state(session_id, source_message_count, quality)
        logger.info("hermes-wiki: %s (q=%d, topics=%s)", slug, quality, topics)

    # -- LLM call -----------------------------------------------------------

    def _call_llm(self, messages: list, title: str, source: str) -> Optional[dict]:
        import httpx

        provider = self._config.get("provider", "")
        model = self._config.get("model", "")
        api_key = self._config.get("api_key", "")
        base_url = self._config.get("base_url", "")

        if not model or not provider:
            try:
                import yaml
                from hermes_constants import get_hermes_home
                cfg_path = get_hermes_home() / "config.yaml"
                if cfg_path.exists():
                    with open(cfg_path) as f:
                        cfg = yaml.safe_load(f) or {}
                    mc = cfg.get("model", {})
                    model = model or mc.get("default", "") or mc.get("model", "")
                    provider = provider or mc.get("provider", "")
            except Exception:
                pass

        if not model:
            logger.warning("No model configured, skipping LLM call")
            return None

        if not base_url:
            base_url = self._resolve_url(provider)
        if not base_url:
            logger.warning("Cannot resolve base_url for %s", provider)
            return None

        if not api_key:
            api_key = self._resolve_key(provider)
        if not api_key:
            api_key = "no-key"

        msgs = [
            {"role": "system", "content": self._prompt()},
            {"role": "user", "content": self._format_msgs(messages, title, source)},
        ]

        try:
            with httpx.Client(timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0)) as client:
                # Detect API format from URL
                if "/anthropic" in base_url:
                    # Anthropic Messages API
                    anthropic_msgs = [{"role": "user", "content": msgs[1]["content"]}]
                    resp = client.post(
                        f"{base_url.rstrip('/')}/v1/messages",
                        json={"model": model, "max_tokens": 4096,
                              "system": msgs[0]["content"],
                              "messages": anthropic_msgs},
                        headers={"Content-Type": "application/json",
                                 "x-api-key": api_key,
                                 "anthropic-version": "2023-06-01"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    try:
                        content = data["content"][0]["text"]
                    except (KeyError, IndexError, TypeError) as e:
                        logger.error("hermes-wiki: unexpected Anthropic response: %s", e)
                        return None
                else:
                    # OpenAI Chat Completions API
                    resp = client.post(
                        f"{base_url.rstrip('/')}/chat/completions",
                        json={"model": model, "messages": msgs,
                              "max_tokens": 2000, "temperature": 0.3},
                        headers={"Content-Type": "application/json",
                                 "Authorization": f"Bearer {api_key}"},
                    )
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"]
            return self._extract_json(content)
        except Exception as e:
            logger.error("hermes-wiki: LLM failed: %s", e)
            return None

    def _prompt(self) -> str:
        """Load prompt from prompts/default.md, fallback to built-in."""
        try:
            prompt_path = Path(__file__).parent / "prompts" / "default.md"
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

    # -- URL/key resolution (uses Hermes provider system) -----------------

    @staticmethod
    def _resolve_url(provider: str) -> Optional[str]:
        """Resolve base URL — same logic as Hermes agent."""
        import os
        try:
            from hermes_cli.providers import resolve_provider_full
            pdef = resolve_provider_full(provider)
            if pdef:
                # Env var override takes precedence (same as agent)
                if pdef.base_url_env_var and os.environ.get(pdef.base_url_env_var):
                    return os.environ[pdef.base_url_env_var].rstrip("/")
                if pdef.base_url:
                    return pdef.base_url.rstrip("/")
        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_key(provider: str) -> Optional[str]:
        """Resolve API key via Hermes's provider system."""
        import os
        try:
            from hermes_cli.providers import resolve_provider_full
            pdef = resolve_provider_full(provider)
            if pdef and pdef.api_key_env_vars:
                for env_var in pdef.api_key_env_vars:
                    val = os.environ.get(env_var, "")
                    if val:
                        return val
        except Exception:
            pass
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
        return f"{date}_{s or 'session'}"
