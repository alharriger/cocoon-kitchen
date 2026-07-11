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

### 2026-07-11 — GLM-4.5-Flash is a thinking model; budget max_tokens for reasoning
**What happened:** First working call returned `finish_reason: stop` but **empty** `content`. The model had spent all 60 `max_tokens` on hidden reasoning.
**Root cause:** GLM-4.5-Flash emits reasoning tokens (in a separate `reasoning_content` field) *before* the answer. A low `max_tokens` gets consumed by reasoning, leaving no room for `content`.
**Prevention rule:** Budget `max_tokens` generously (≥512 for tiny outputs; more for a full `Verdict`). Read the answer from `message.content`; reasoning is in `message.reasoning_content`. This is exactly why Contract 3 mandates validate-and-retry-once. Watch for the same on other thinking-tier models in the bake-off.
**Status:** Active

### 2026-07-10 — Bare `python` is not on PATH
**What happened:** `python` and `python -m pytest` fail (`command not found`); system `python3` is EOL 3.9.6 without pytest.
**Root cause:** This machine has no `python` shim; the working interpreter is the project venv.
**Prevention rule:** Run Python via `.venv/bin/python` (e.g. `.venv/bin/python -m pytest`), or activate the venv first. Don't assume a bare `python`.
**Status:** Active
