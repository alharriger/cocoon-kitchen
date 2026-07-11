# Pitfalls — Working Relationship Log

Every mistake gets logged here during the retrospective (or immediately, if it bit us mid-phase). The point is iteration: a pitfall entry isn't blame, it's a prevention rule. **Check this file before starting work; don't repeat an entry.**

## Entry format
```
### YYYY-MM-DD — short title
**What happened:** one or two sentences.
**Root cause:** the actual why, not the symptom.
**Prevention rule:** the concrete behavior change (checklist item, doc update, process step).
**Status:** Active | Retired (rule absorbed into process/memory)
```

---

### 2026-07-10 — Package name ≠ import name
**What happened:** The project/distribution is named `cocoonkitchen` (`pyproject.toml`, `pip install -e .`) but the source package — and therefore the import name — is `clean_recipe` (`src/clean_recipe/`). Writing `from cocoonkitchen import ...` fails.
**Root cause:** The `cleanplate → cocoonkitchen` rename updated docs and the distribution name but intentionally left the code package as `clean_recipe` (architecture.md target layout).
**Prevention rule:** Imports use `clean_recipe` (e.g. `from clean_recipe.schema import Verdict`). The name `cocoonkitchen` is only the pip/distribution name. Don't "fix" this mismatch — it's by design.
**Status:** Active

### 2026-07-11 — z.ai base URL is `/api/paas/v4`, not `/api/openai/v1`
**What happened:** The `.env.example` template shipped `LLM_BASE_URL=https://api.z.ai/api/openai/v1`; the first smoke test got HTTP 200 with body `{"code":500,"msg":"404 NOT_FOUND"}`. Switching to `https://api.z.ai/api/paas/v4` worked immediately.
**Root cause:** z.ai's OpenAI-shaped endpoint is the native `/api/paas/v4/chat/completions` path; the `/api/openai/v1` route a web search suggested does not resolve. The 404 was wrapped in a 200 envelope, so it didn't raise.
**Prevention rule:** For z.ai GLM, use `base_url=https://api.z.ai/api/paas/v4`. When a provider returns 200, inspect the body for an embedded error code before trusting it.
**Status:** Active

### 2026-07-11 — GLM-4.5-Flash thinking is UNBOUNDED; disable it, don't raise max_tokens
**What happened:** `score_recipe` on a real recipe (French onion soup) raised `ScoringError: model did not return JSON` — the model returned **empty** `content` (`finish_reason: length`), and the retry hit the same wall. My first instinct (and the earlier version of this pitfall) was "raise `max_tokens`." That is WRONG.
**Root cause:** GLM-4.5-Flash emits reasoning tokens (`reasoning_content`) *before* the answer, and the reasoning length is **unbounded and highly variable**. Diagnostic on the same input: max_tokens=1500 → truncated (empty); 3000 → happened to finish; **4096 → rambled 16K chars of reasoning and truncated again.** More budget just buys more rambling — it does not reliably leave room for the JSON.
**Prevention rule:** For deterministic scoring/classification, **disable thinking**, don't chase it with tokens. GLM: `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}` (thinking-off → `finish=stop`, ~208 completion tokens, valid JSON, reliable even at max_tokens=800). The seam passes `LLM_EXTRA_BODY` (provider-specific JSON) via `extra_body`. Bake-off models with their own reasoning modes need the same treatment; leave `LLM_EXTRA_BODY` blank for models without a toggle and rely on generous max_tokens + validate-retry-once there.
**Status:** Active

### 2026-07-10 — Bare `python` is not on PATH
**What happened:** `python` and `python -m pytest` fail (`command not found`); system `python3` is EOL 3.9.6 without pytest.
**Root cause:** This machine has no `python` shim; the working interpreter is the project venv.
**Prevention rule:** Run Python via `.venv/bin/python` (e.g. `.venv/bin/python -m pytest`), or activate the venv first. Don't assume a bare `python`.
**Status:** Active
