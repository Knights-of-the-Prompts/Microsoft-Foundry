"""Thin LLM wrapper for the KPI Challenge Agent.

Uses azure-ai-projects AIProjectClient to obtain an OpenAI-compatible client
backed by the Azure AI Foundry project endpoint.

Design rules:
- Never raises: every public method catches all exceptions and returns None
  on failure so the caller can decide to fall back to deterministic behaviour.
- ``is_available()`` is cheap and safe to call at request time.
- JSON mode is requested via response_format when a json_schema is passed.
- Model is configurable via CONTROL_PLANE_KPI_LLM_MODEL (default: gpt-4o-mini).
- Live mode is opt-in via CONTROL_PLANE_KPI_LLM_ENABLED=true.

Activation (add to .env):
    CONTROL_PLANE_KPI_LLM_ENABLED=true
    FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com/
    CONTROL_PLANE_KPI_LLM_MODEL=gpt-4o-mini   # optional
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.environ.get("CONTROL_PLANE_KPI_LLM_ENABLED", "").lower() in (
        "true", "1", "yes"
    )


def _endpoint() -> Optional[str]:
    return os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or None


def _model() -> str:
    return os.environ.get("CONTROL_PLANE_KPI_LLM_MODEL", "gpt-4o-mini")


class LlmClient:
    """Lightweight wrapper around the AI Foundry OpenAI-compatible endpoint.

    Usage::

        client = LlmClient()
        if client.is_available():
            result = client.chat_complete(messages=[...], json_schema={...})
            if result is not None:
                # use result
    """

    def is_available(self) -> bool:
        """Return True when live LLM calls are configured and enabled."""
        return _enabled() and bool(_endpoint())

    def chat_complete(
        self,
        messages: List[Dict[str, str]],
        json_schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> Optional[Dict[str, Any]]:
        """Send a chat completion request and return parsed JSON, or None.

        When ``json_schema`` is provided the model is instructed to respond in
        JSON mode and the response is parsed as a dict.  If the response cannot
        be parsed as JSON, or if any error occurs, None is returned so the
        caller can fall back to deterministic behaviour.

        Args:
            messages: OpenAI-format message list, e.g.
                ``[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]``
            json_schema: Optional dict describing the expected JSON structure,
                used only to instruct the model (not validated server-side).
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            Parsed dict on success, None on any failure.
        """
        if not self.is_available():
            return None

        try:
            openai_client = self._build_openai_client()
            if openai_client is None:
                return None

            # Build the request kwargs
            kwargs: Dict[str, Any] = {
                "model": _model(),
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            if json_schema is not None:
                # Instruct the model to respond in JSON and inject the schema
                # into the system message so it understands the expected shape.
                kwargs["response_format"] = {"type": "json_object"}

            response = openai_client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""

            if json_schema is not None:
                return json.loads(content)

            return {"text": content}

        except Exception as exc:  # noqa: BLE001
            logger.warning("LlmClient.chat_complete failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_openai_client(self):
        """Build and return an OpenAI client via AIProjectClient, or None."""
        endpoint = _endpoint()
        if not endpoint:
            return None
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential

            project_client = AIProjectClient(
                endpoint=endpoint,
                credential=DefaultAzureCredential(),
            )
            return project_client.get_openai_client()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LlmClient: failed to build OpenAI client: %s", exc)
            return None
