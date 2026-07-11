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

import os

from openai import OpenAI

# GLM-4.5-Flash (and other thinking-tier models) spend reasoning tokens *before*
# the answer, so the ceiling must be generous or ``content`` comes back empty
# (see ai_docs/pitfalls.md 2026-07-11). A full Verdict payload is small; this
# leaves ample room for hidden reasoning.
DEFAULT_MAX_TOKENS = 1500


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
    )
    return resp.choices[0].message.content or ""
