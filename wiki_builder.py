"""
Wiki Builder — LLM-based session analysis and wiki page generation.

Processes pending sessions from WikiStore's queue into structured wiki pages.
Supports 7 languages via automatic detection.
"""

import datetime
import json
import logging
import re
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
                logger.error("hermes-wiki: failed for %s: %s", item.get("session_id"), e)
                self._store.mark_done(item["id"], "failed")
        return processed

    def _process_session(self, item: dict) -> None:
        session_id = item["session_id"]
        title = item.get("title", "") or ""
        source = item.get("source", "")
        messages = item.get("messages", [])

        if self._store.is_session_processed(session_id):
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

        analysis = self._call_llm(filtered, title, source) or self._default(title)
        quality = max(1, min(5, analysis.get("quality", 2)))
        date = self._date_from_id(session_id)
        slug = self._slug(date, analysis.get("title", title))
        lang = analysis.get("language", "en")
        topics = analysis.get("topics", [])
        entities = analysis.get("entities", [])
        keywords = analysis.get("keywords", [])

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
        )

        for topic in topics:
            self._update_topic(topic, date, analysis.get("title", title), quality)

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
                    base_url = base_url or mc.get("base_url", "")
            except Exception:
                pass

        if not model:
            return None
        if not base_url:
            base_url = self._resolve_url(provider)
        if not base_url:
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
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    json={"model": model, "messages": msgs, "max_tokens": 2000, "temperature": 0.3},
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
            return self._extract_json(resp.json()["choices"][0]["message"]["content"])
        except Exception as e:
            logger.error("hermes-wiki: LLM failed: %s", e)
            return None

    def _prompt(self) -> str:
        return (
            "Analyze the following session and return strict JSON only:\n"
            '{"title":"Session title (<=30 chars)","language":"en","quality":3,'
            '"content_type":"discussion","topics":["topic-slug"],"entities":["Entity Name"],'
            '"keywords":["keyword"],"result":"One-sentence outcome",'
            '"background":"Brief user goal (<=100 chars)",'
            '"decisions":["Decision and reason"],"problems":["Problem -> Solution"]}\n\n'
            "CRITICAL: Respond in the SAME LANGUAGE as the session content.\n"
            'language field: ISO 639-1 ("en","zh","ja","ko","de","fr","es").\n'
            "All text fields in that language. topic slugs, entity names, content_type in English.\n"
            "Quality: 5=deep+important, 4=substantial, 3=moderate, 2=simple Q&A, 1=no value.\n"
            "Types: troubleshooting/development/research/planning/review/setup/migration/quickfix/discussion.\n"
            "Max 3 topics. Reuse existing slugs when possible."
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

    # -- URL/key resolution -------------------------------------------------

    def _resolve_url(self, provider: str) -> Optional[str]:
        import os
        for k in ("OPENAI_BASE_URL", "CUSTOM_BASE_URL", "XIAOMI_BASE_URL"):
            if os.environ.get(k):
                return os.environ[k]
        try:
            from hermes_cli.auth import PROVIDER_REGISTRY
            cfg = PROVIDER_REGISTRY.get(provider)
            if cfg and cfg.inference_base_url:
                if cfg.base_url_env_var and os.environ.get(cfg.base_url_env_var):
                    return os.environ[cfg.base_url_env_var]
                return cfg.inference_base_url
        except ImportError:
            pass
        return None

    def _resolve_key(self, provider: str) -> Optional[str]:
        import os
        for k in ("CUSTOM_API_KEY", "OPENAI_API_KEY"):
            if os.environ.get(k):
                return os.environ[k]
        try:
            from hermes_cli.auth import PROVIDER_REGISTRY
            cfg = PROVIDER_REGISTRY.get(provider)
            if cfg and cfg.api_key_env_vars:
                for ev in cfg.api_key_env_vars:
                    if os.environ.get(ev):
                        return os.environ[ev]
        except ImportError:
            pass
        return None

    # -- Defaults & helpers -------------------------------------------------

    def _default(self, title: str) -> dict:
        return {"title": title or "Untitled", "language": "en", "quality": 2,
                "content_type": "discussion", "topics": [], "entities": [], "keywords": [],
                "result": "", "background": "", "decisions": [], "problems": []}

    def _update_topic(self, topic: str, date: str, title: str, quality: int) -> None:
        existing = self._store.get_topic_page(topic)
        h = _I18N["en"]
        if existing:
            content = existing.get("full_content") or ""
            entry = f"- [{date}] {title} - quality: {quality}"
            if entry not in content:
                self._store.update_page_content(
                    existing["page_id"],
                    content.replace(f"## {h['tl']}\n", f"## {h['tl']}\n{entry}\n"),
                )
        else:
            page = (
                f"---\ntopic: {topic}\npage_count: 1\nfirst_seen: {date}\nlast_updated: {date}\n---\n\n"
                f"# {topic}\n\n## {h['ov']}\n\n## {h['tl']}\n- [{date}] {title} - quality: {quality}\n"
            )
            self._store.insert_page(page_type="topic", slug=topic, title=topic, date=date,
                                    topics=[topic], summary=f"Topic: {topic}", full_content=page)

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
