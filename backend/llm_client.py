"""Shared LLM HTTP client for hermes-wiki.

Handles .env loading, provider resolution, and HTTP transport
(OpenAI Chat Completions + Anthropic Messages API format detection).

NO prompt logic, NO JSON schema parsing — both wiki_builder.py (session
workflow) and topic/topic_builder.py (topic workflow) reuse this client
but supply their own system prompt and JSON parser.

Usage:
    client = LLMClient(config={"provider": "openrouter", "model": "..."})
    raw_text = client.send_request(system_prompt=..., user_prompt=..., max_tokens=2000)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("hermes-wiki")


class LLMClient:
    """Stateless LLM HTTP client. Construct per process, reuse across calls."""

    def __init__(self, config: Optional[dict] = None):
        self._config = config or {}

    def send_request(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> Optional[str]:
        """Send system+user prompt to LLM. Returns raw text content or None on failure.

        Caller is responsible for parsing the returned text into structured data.
        """
        import httpx

        # Ensure .env is loaded for API key resolution
        try:
            from hermes_cli.env_loader import load_hermes_dotenv
            from hermes_constants import get_hermes_home
            load_hermes_dotenv(hermes_home=get_hermes_home())
        except Exception:
            pass

        provider, model, api_key, base_url = self._resolve_credentials()
        if not model:
            logger.warning("No model configured, skipping LLM call")
            return None
        if not base_url:
            logger.warning("Cannot resolve base_url for %s", provider)
            return None
        if not api_key:
            api_key = "no-key"

        try:
            with httpx.Client(timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0)) as client:
                if "/anthropic" in base_url:
                    return self._call_anthropic(client, base_url, model, api_key, system_prompt, user_prompt, max_tokens)
                return self._call_openai(client, base_url, model, api_key, system_prompt, user_prompt, max_tokens, temperature)
        except Exception as e:
            logger.error("hermes-wiki: LLM call failed: %s", e)
            return None

    # -- Credential resolution (shared between session + topic) --------------

    def _resolve_credentials(self) -> tuple[str, str, str, str]:
        """Return (provider, model, api_key, base_url). Falls back to config.yaml."""
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
                    api_key = api_key or mc.get("api_key", "")
            except Exception:
                pass

        if not base_url:
            base_url = self._resolve_url(provider) or ""
        if not api_key:
            api_key = self._resolve_key(provider) or ""

        return provider, model, api_key, base_url

    @staticmethod
    def _resolve_url(provider: str) -> Optional[str]:
        """Resolve base URL via Hermes provider system."""
        try:
            from hermes_cli.providers import resolve_provider_full
            pdef = resolve_provider_full(provider)
            if pdef:
                if pdef.base_url_env_var and os.environ.get(pdef.base_url_env_var):
                    return os.environ[pdef.base_url_env_var].rstrip("/")
                if pdef.base_url:
                    return pdef.base_url.rstrip("/")
        except Exception:
            pass
        return None

    @staticmethod
    def _resolve_key(provider: str) -> Optional[str]:
        """Resolve API key via Hermes provider system."""
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
        # Fallback: try provider-specific env var pattern
        fallback_var = f"{provider.upper().replace('-', '_')}_API_KEY"
        val = os.environ.get(fallback_var, "")
        if val:
            return val
        return None

    # -- HTTP transport ------------------------------------------------------

    @staticmethod
    def _call_anthropic(client, base_url, model, api_key, system_prompt, user_prompt, max_tokens):
        resp = client.post(
            f"{base_url.rstrip('/')}/v1/messages",
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error("hermes-wiki: unexpected Anthropic response: %s", e)
            return None

    @staticmethod
    def _call_openai(client, base_url, model, api_key, system_prompt, user_prompt, max_tokens, temperature):
        msgs = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": msgs, "max_tokens": max_tokens, "temperature": temperature},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]