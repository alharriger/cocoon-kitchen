"""Provider-profile registry for the Phase 6 bake-off (Task 4).

Claude owns the harness/bake-off (human/Claude split, Phase 6 kickoff). The
client seam (``clean_recipe.client``) reads ONE active credential set from the
environment — ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL`` /
``LLM_EXTRA_BODY`` — so ``evaluate.py --model X`` alone can only swap the model
*name*, not the endpoint or key. This registry closes that gap: each profile
carries a provider's full connection config, and ``activate()`` writes those four
env vars in-process so a run can target a different OpenAI-compatible endpoint
**without hand-swapping the dev-default GLM block in ``.env``**.

Design decisions this honours:
- Provider is config, not code (architecture 2026-07-11). These are connection
  details (base URLs, public model ids), NOT the human-owned rubric — Claude owns
  them per the Phase-6 split.
- Model/provider is eval-selected, never by brand (architecture 2026-07-11). The
  registry only makes the comparison runnable; the numbers pick the default.
- Thinking stays DISABLED on any reasoning model (2026-07-11 pitfall) — GLM via
  ``thinking:disabled``, Qwen via ``enable_thinking:false``; the rest are
  non-thinking models so their ``extra_body`` is blank.

Model ids DRIFT and free tiers change. These were verified **2026-07-19** (see
working_sprint Task 4): notably ``gemini-2.0-flash`` was shut down 2026-06-01, so
Gemini now points at ``gemini-2.5-flash-lite`` (cheapest 2.5 model, thinking off
by default). Re-verify before a future run.

Security: API keys are read from the environment only (``key_env`` names the var)
and are NEVER logged, printed, or written to results — only provider/model names
are surfaced.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    """One OpenAI-compatible endpoint profile for the bake-off.

    ``key_env`` is the NAME of the env var holding the API key (e.g.
    ``GEMINI_API_KEY``) — never the key itself. ``extra_body`` is the JSON string
    to put in ``LLM_EXTRA_BODY`` (``""`` → blank, for non-thinking models).
    ``min_interval`` paces calls to respect a free-tier RPM ceiling (seconds
    between the *start* of consecutive calls; 0 → no pacing).
    """

    name: str
    key_env: str
    base_url: str
    model: str
    extra_body: str = ""
    min_interval: float = 0.0
    note: str = ""


# The registry. GLM is included so the bake-off can re-run the incumbent under
# IDENTICAL conditions in the same pass — removing cross-run eval noise (~2pp /
# ~1 MAE) from the comparison against the tuned rubric's current numbers.
PROVIDERS: dict[str, Provider] = {
    # Dev default — Zhipu GLM-4.5-Flash on z.ai (always free, no card).
    "glm": Provider(
        name="glm",
        key_env="LLM_API_KEY",
        base_url="https://api.z.ai/api/paas/v4",
        model="glm-4.5-flash",
        extra_body='{"thinking": {"type": "disabled"}}',
        note="incumbent dev default",
    ),
    # Google Gemini — free tier, no card. A *flash-lite* model has thinking OFF by
    # default (no extra_body needed) — the cheapest non-thinking parity choice.
    # NOTE: gemini-2.0/2.5-flash-lite are gated for NEW accounts (2.0 shut down
    # 2026-06-01; 2.5-flash-lite returns 404 "no longer available to new users"
    # on generateContent even though it lists) — verified 2026-07-19. The current
    # available lite is gemini-3.1-flash-lite. Free tier is **15 RPM** (measured
    # 2026-07-19). Pace at 10s (6 req/min): 5s (12/min) still cascaded because
    # once the sliding window brushes 15, the OpenAI SDK's own 429-retries pile
    # back onto the same saturated minute (their ~8s backoff < the "retry in 26s"
    # the API asks for) and keep it pinned — 16/52 rows dropped. 6/min never
    # saturates, so no 429 and no retry-storm; slow (~9min/run) but completes.
    "gemini": Provider(
        name="gemini",
        key_env="GEMINI_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-3.1-flash-lite",
        extra_body="",
        min_interval=10.0,
        note="thinking off by default; free 1500 req/day, 15 RPM",
    ),
    # Groq — free tier, no card, JSON mode. Llama 3.3 70B is non-thinking.
    "groq": Provider(
        name="groq",
        key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile",
        extra_body="",
        note="non-thinking; generous free RPM/RPD",
    ),
    # Qwen (Alibaba Model Studio / DashScope international). qwen-plus THINKS by
    # default — disable it (2026-07-11 pitfall) or it rambles like GLM did.
    "qwen": Provider(
        name="qwen",
        key_env="QWEN_API_KEY",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        extra_body='{"enable_thinking": false}',
        note="thinking disabled; 1M in/1M out free for 90 days (intl)",
    ),
    # DeepSeek — deepseek-chat (V4 Flash) is non-thinking (deepseek-reasoner
    # thinks; avoid it here). One-time 5M-token grant, 30 days, no card.
    "deepseek": Provider(
        name="deepseek",
        key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        extra_body="",
        note="non-thinking; 5M-token signup grant, then paid",
    ),
}

# --- OpenRouter: one funded key + base_url proxies MANY models --------------
# Amber funded an OpenRouter account (2026-07-19) to sidestep the free-tier caps
# that truncated the direct bake-off (Gemini 15 RPM, Groq 100k tokens/day) and
# the new-account gating (Gemini flash-lite 404, DeepSeek needs balance). Every
# model here shares ONE key (OPEN_ROUTER_API_KEY) and ONE base_url — the model
# NAME is the only thing that changes — so we build a Provider per slug.
#
# Reasoning is disabled on models that think by default (GLM/Qwen/gpt-oss) via
# OpenRouter's unified `reasoning` param (2026-07-11 pitfall — a thinking model
# rambles past the token budget and returns empty). The est-cost figures are a
# snapshot of the OpenRouter catalog (2026-07-19), used only for a pre-run budget
# heads-up (~5.5k prompt + ~300 completion tokens/call × 52 rows).
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_KEY_ENV = "OPEN_ROUTER_API_KEY"
_REASONING_OFF = '{"reasoning": {"enabled": false}}'
# gpt-oss MANDATES reasoning (OpenRouter 400s on enabled:false, verified
# 2026-07-19) — the model class the 2026-07-11 pitfall warns about. Give it the
# minimum effort so it still emits JSON; reasoning tokens bill as output, so its
# real cost runs above the $0.013 estimate. If it skips rows in the full run,
# exclude + document rather than chase it.
_REASONING_MIN = '{"reasoning": {"effort": "low"}}'

# (slug, extra_body, est_usd_per_52row_run) — Amber's "Broader 8" set.
OPENROUTER_MODELS: list[tuple[str, str, float]] = [
    ("google/gemini-2.5-flash-lite", "", 0.035),
    ("z-ai/glm-4.7-flash", _REASONING_OFF, 0.024),
    ("meta-llama/llama-3.3-70b-instruct", "", 0.043),
    ("openai/gpt-4o-mini", "", 0.052),
    ("deepseek/deepseek-chat", "", 0.070),
    ("qwen/qwen-plus", _REASONING_OFF, 0.087),
    ("mistralai/mistral-small-3.2-24b-instruct", "", 0.033),
    ("openai/gpt-oss-120b", _REASONING_MIN, 0.013),
]


def openrouter_providers() -> list["Provider"]:
    """Build one Provider per OpenRouter model — all sharing the single key/URL.

    ``name`` is the short (post-slash) label for the comparison table; ``model``
    is the full ``vendor/slug`` OpenRouter needs.
    """
    return [
        Provider(
            name=slug.split("/")[-1],
            key_env=OPENROUTER_KEY_ENV,
            base_url=OPENROUTER_BASE_URL,
            model=slug,
            extra_body=extra_body,
            note=f"OpenRouter; est ${usd:.3f}/52-row run",
        )
        for slug, extra_body, usd in OPENROUTER_MODELS
    ]


def openrouter_est_cost() -> float:
    """Estimated total USD for one full 52-row pass over all OpenRouter models."""
    return sum(usd for _, _, usd in OPENROUTER_MODELS)


# The client-seam env vars a profile owns. activate() sets exactly these; nothing
# else in the environment is touched.
_CLIENT_ENV_VARS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_EXTRA_BODY")


def capture_active_credentials() -> dict[str, str]:
    """Snapshot the current client-seam env vars — the .env active / dev-default set.

    A bake-off LOOP mutates ``LLM_API_KEY`` each time it activates a provider. The
    ``glm`` (incumbent) profile sources its key from ``LLM_API_KEY`` — the SAME var
    activate() overwrites — so once any other provider activates, glm's original
    key is gone. Capture the incumbent BEFORE the loop, then restore it for the
    glm entry (see ``restore_credentials``). Returns a dict for later restore.
    """
    return {v: os.environ[v] for v in _CLIENT_ENV_VARS if v in os.environ}


def restore_credentials(snapshot: dict[str, str]) -> None:
    """Restore a snapshot from ``capture_active_credentials`` verbatim.

    Clears the four client-seam vars first so a key/flag left by another provider
    in a bake-off loop can't linger (e.g. a stray non-thinking extra_body).
    """
    for v in _CLIENT_ENV_VARS:
        os.environ.pop(v, None)
    os.environ.update(snapshot)


def select_provider(name: str) -> Provider:
    """Look up a profile by name; raise ``ValueError`` (fail loud) if unknown."""
    try:
        return PROVIDERS[name]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown provider {name!r}; known providers: {known}") from None


class MissingKeyError(RuntimeError):
    """Raised when a provider's API key env var is unset/empty.

    Distinct type so the bake-off can *skip* a keyless provider (report it) rather
    than aborting the whole run — an unfunded/absent provider is expected here.
    """


def activate(provider: Provider) -> None:
    """Point the client seam at ``provider`` by setting its four env vars.

    Reads the API key from ``provider.key_env`` (already loaded from ``.env`` by
    the entrypoint). Raises ``MissingKeyError`` if that var is unset/empty so the
    caller can skip the provider with a clear message. The key value itself is
    never included in the error or logged.
    """
    key = os.environ.get(provider.key_env)
    if not key or not key.strip():
        raise MissingKeyError(
            f"{provider.name}: env var {provider.key_env} is not set — "
            "add it to .env to include this provider in the bake-off."
        )
    os.environ["LLM_API_KEY"] = key
    os.environ["LLM_BASE_URL"] = provider.base_url
    os.environ["LLM_MODEL"] = provider.model
    # Blank extra_body must clear any prior value (e.g. GLM's thinking flag left
    # over from a previous provider in an --all-providers loop), else a
    # non-thinking model would get a stray, possibly-rejected param.
    if provider.extra_body:
        os.environ["LLM_EXTRA_BODY"] = provider.extra_body
    else:
        os.environ.pop("LLM_EXTRA_BODY", None)
