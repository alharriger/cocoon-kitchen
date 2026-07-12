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

### 2026-07-11 — Schema validation must enforce value ranges, not just types
**What happened:** `SubScores` fields were bare `float` (type-checked but unbounded). Code review found that a flaky model returning e.g. `1000` would be weighted and then **silently clamped** by `compose_score` into a clean-looking composite — defeating the "malformed output fails loud" guarantee.
**Root cause:** The schema transcribed the "0–100" contract as a comment, not an enforced constraint. Type validity ≠ contract validity.
**Prevention rule:** When a contract specifies a numeric range/enum/length, encode it in the Pydantic field (`Field(ge=0, le=100)`, `Literal[...]`, etc.), not just a comment — so out-of-contract model output raises `ValidationError` and hits the fail-loud/retry path. Clamping is not validation.
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

### 2026-07-12 — A model-I/O contract change must ripple to every shape-dependent site
**What happened:** Adding the required `is_recipe` field to `ModelOutput` (Phase 3) left three dependent sites stale, all caught in code review: (1) the retry `_REPAIR_HINT` still told the model to return the *old* shape (no `is_recipe`), so a compliant retry would fail validation — silently defeating retry-once; (2) making `swaps`/`flagged_ingredients` optional to fit the non-recipe case narrowed validation for the recipe case (a recipe missing `swaps` no longer failed loud); (3) `evaluate.run_eval` didn't handle the new `NotARecipeError`, so one row could abort a whole bake-off.
**Root cause:** A change to the model-output contract (`schema`/prompt shape) has a blast radius: the retry/repair hint that restates the shape, every `except` that handles `score_recipe`'s raises, and any constraint relaxed "just for the new branch." Editing the model class in isolation looks complete but isn't.
**Prevention rule:** When you change the model-I/O contract, in the SAME change walk the whole blast radius: (a) update every prompt/hint that restates the shape (system prompt AND `_REPAIR_HINT`); (b) update every caller's exception handling for new raise types (`app.py`, `cli.py`, `evaluate.py`); (c) if you relax a constraint for one branch, add a branch-specific validator so the other branch keeps its original guarantee (don't let `Optional` silently weaken the happy path); (d) log the change in `llm_contracts.md`. A quick `grep` for the changed symbol + the function name across `src/`, `app.py`, `evals/` surfaces the sites.
**Status:** Active

### 2026-07-12 — Unpinned transitive deps can segfault: pin what Streamlit pulls in
**What happened:** The console's AppTest suite segfaulted (hard interpreter crash, not a test failure) on nearly every full run, inside `st.dataframe` → pyarrow's DataFrame→Arrow serialization in Streamlit's script thread. The project pins direct deps exactly, but `pandas`/`pyarrow` arrived transitively via streamlit, unpinned, and resolved to brand-new majors (pandas 3.0.3, pyarrow 25.0.0). First hypothesis (pandas 3's arrow-backed strings) was wrong — pinning `pandas==2.3.3` still crashed; the culprit was pyarrow 25.0.0 itself, and `pyarrow==21.0.0` fixed it (3× clean full-suite runs).
**Root cause:** "Exact-pinned deps" only covered *direct* dependencies; transitive ones float to whatever's newest at install time, including days-old majors with native-code bugs. And a segfault that passes in isolation but dies on full runs looks like test flakiness when it's really a native library bug.
**Prevention rule:** When a heavy framework (streamlit) pulls native-code deps (pyarrow, pandas, numpy), pin the load-bearing ones explicitly in pyproject once they're actually exercised (st.dataframe ⇒ pyarrow). On any interpreter-level crash (`Fatal Python error`), read the "Current thread" stack to find the native library, and test the fix by rerunning the FULL suite several times — single-test passes prove nothing about thread/state-dependent native crashes.
**Status:** Active

### 2026-07-10 — Bare `python` is not on PATH
**What happened:** `python` and `python -m pytest` fail (`command not found`); system `python3` is EOL 3.9.6 without pytest.
**Root cause:** This machine has no `python` shim; the working interpreter is the project venv.
**Prevention rule:** Run Python via `.venv/bin/python` (e.g. `.venv/bin/python -m pytest`), or activate the venv first. Don't assume a bare `python`.
**Status:** Active
