"""Provider-neutral LLM client — the OpenAI-compatible seam.

Provider is config, not code (see ai_docs/architecture.md 2026-07-11 decision):
this reads ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL`` from the environment
and talks to any OpenAI-compatible endpoint. The development default is Zhipu
GLM-4.5-Flash on z.ai; swapping to a bake-off model (Gemini, Groq, DeepSeek, …)
is an env change, never a code change.

The pure core reads ``os.environ`` directly — entrypoints (CLI, eval harness)
are responsible for loading ``.env`` first. Nothing here imports python-dotenv.

Security: the API key comes only from the environment and is never logged.
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

# The JSON payload is small (~250 tokens). With thinking disabled (see
# LLM_EXTRA_BODY below) this is plenty; it also leaves headroom for providers
# without a thinking toggle. Do NOT rely on a big ceiling to tame a thinking
# model — GLM's reasoning is unbounded and will eat any budget (pitfalls.md).
DEFAULT_MAX_TOKENS = 2048


def _extra_body() -> dict:
    """Optional provider-specific request params, as a JSON object in the
    ``LLM_EXTRA_BODY`` env var. Keeps the seam provider-neutral while letting the
    config pass things like GLM's ``{"thinking": {"type": "disabled"}}`` (which
    this scoring task needs — GLM's reasoning otherwise consumes the whole token
    budget before it emits JSON). Empty/unset → no extra params.
    """
    raw = os.environ.get("LLM_EXTRA_BODY")
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM_EXTRA_BODY is not valid JSON: {e}") from e
    if not isinstance(value, dict):
        raise RuntimeError("LLM_EXTRA_BODY must be a JSON object")
    return value


def _client() -> OpenAI:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    base_url = os.environ.get("LLM_BASE_URL") or None
    return OpenAI(api_key=api_key, base_url=base_url)


def complete_json(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.0,
) -> str:
    """Send an OpenAI-style chat request in JSON mode; return the raw content.

    ``model`` defaults to ``LLM_MODEL`` from the environment. JSON mode
    (``response_format=json_object``) is portable across every bake-off provider.
    Returns the assistant message content as a string (may be empty if the model
    exhausted its token budget on reasoning — the caller validates and retries).
    """
    model = model or os.environ.get("LLM_MODEL")
    if not model:
        raise RuntimeError("LLM_MODEL is not set (add it to your .env).")

    resp = _client().chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body=_extra_body() or None,
    )
    return resp.choices[0].message.content or ""
