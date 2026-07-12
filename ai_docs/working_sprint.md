# Working Sprint — LIVE DOCUMENT

> This file tracks the **current phase only**. It is the handoff artifact between Claude sessions:
> update task status as work happens, log decisions and blockers immediately, and when the phase
> completes (retro done, merged to main), **refresh this file** for the next phase.

---

## Current phase: Phase 3 — UI & End-to-End

**Goal:** A local Streamlit app where you paste a recipe (or a link) and get a Verdict card — score, band, flagged ingredients, 3 swaps — rendered in the product's non-shaming tone. `app.py` is a **thin consumer** of the already-built core (`parse_recipe` → `score_recipe`); no scoring logic lives in the UI.

**Branch:** create `phase-3/ui` off `main` (Phase 2 is merged to main).

**⚠️ First task is to PLAN, not code.** Per our working loop, write the detailed Phase 3 plan (files, UI states, error handling, security notes) and get Amber's approval BEFORE writing any code. Read `CLAUDE.md`, this file, `ai_docs/pitfalls.md`, and **`ai_docs/design_system.md`** (UI/tone source of truth).

### Tasks
| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Write detailed Phase 3 plan + security audit; get Amber's approval | ⬜ Not started | **← start here.** Cover: input handling, error/empty states, no secrets in UI, untrusted paste/URL already handled by parse.py |
| 2 | Add `streamlit` (pinned) to `pyproject.toml`; `app.py` scaffold | ⬜ Not started | streamlit entrypoint loads `.env` (dotenv), like cli.py |
| 3 | `app.py`: paste/link toggle → `parse_recipe` → `score_recipe` → render Verdict card | ⬜ Not started | card = score, band, six sub-scores, flagged list, 3 swaps |
| 4 | Error/empty states: parse failure → paste-fallback message; ScoringError → friendly message; loading spinner | ⬜ Not started | never dump a traceback at the user |
| 5 | Design/tone pass per `design_system.md` (awareness not shaming; band styling) | ⬜ Not started | |
| 6 | Pause for Amber's manual test (`streamlit run app.py`; paste + link) | ⬜ Not started | full local flow |
| 7 | Merge gates: `/verify` + code-review sub-agent + `/security-review`; merge to main | ⬜ Not started | |
| 8 | Phase 3 retrospective → log pitfalls → refresh this doc for Phase 4 | ⬜ Not started | |

### Definition of done (Phase 3)
`streamlit run app.py` locally: pasting a recipe (or a supported link) returns a sane Verdict card in the right tone; parse/scoring failures show friendly messages, not tracebacks; every scored recipe is logged (already handled by `score_recipe`); unit tests still green; docs in sync; merged to main.

### Decisions carried in
- **`app.py` is a thin consumer** — it imports `parse_recipe`/`score_recipe` and renders; it never re-implements scoring or logging (architecture load-bearing rule). Logging is already wired inside `score_recipe` (`log=True` default).
- Provider is config via `.env` (dev default GLM-4.5-Flash, thinking off via `LLM_EXTRA_BODY`). The Streamlit entrypoint loads dotenv; the pure core reads `os.environ`.
- Untrusted input (paste text, recipe URLs) is already defended in `parse.py` (SSRF-guarded fetch) and `prompt.py` (injection defense) — the UI adds no new trust boundary beyond not leaking the key.
- New dep: `streamlit` (pinned exact; anti-bloat — first UI dep). Deploy (Streamlit Cloud) is Phase 4, not now.
- `ai_docs/design_system.md` is the UI/tone source of truth.

### Environment reminders (from pitfalls)
- Import name is `clean_recipe`, NOT `cocoonkitchen`.
- Run Python via `.venv/bin/python`; bare `python` isn't on PATH.
- Model calls need `.env` (already set up: z.ai GLM key + `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}`).

### Blockers
- None. Core engines are built, tested (77 tests), and verified end-to-end on GLM; the `.env` key is in place. Real golden labels remain a Phase 5 item.

### Handoff notes for next session
- Phase 2 (parse + score + eval harness) is merged to main and manually verified by Amber. `score_recipe(title, ingredients) -> Verdict` and `parse_recipe(source) -> ParsedRecipe` are the two functions `app.py` wires together.
- The CLI (`python -m clean_recipe.cli`) is a working reference for the parse→score flow; `app.py` is its Streamlit equivalent.
- Deferred (noted for Phase 5): Contract 4's `raw_ingredients` "path to a text file" option isn't implemented in `evaluate.py` (only inline `"; "`-separated); confirm with the human whether it's still wanted when real labels land. Per-component MAE + swap-quality metrics also await golden columns.
- Start by drafting the Phase 3 plan and presenting it for approval.

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory; roadmap + practices approved. Merged to main.
- **Phase 1 — Scaffold, Schemas & Logging** ✅ (2026-07-10): repo layout; pinned deps; `schema.py` (Verdict/SubScores/Swap); placeholder `rubric.yaml`; `log.py`; 15 tests. Merged to main.
- **Phase 2 — Core Engines** ✅ (2026-07-11): `parse.py` (paste/URL, pinned-IP SSRF guard); provider-neutral `client.py`/`prompt.py`/`score.py` (GLM-4.5-Flash dev default, thinking disabled via `LLM_EXTRA_BODY`, code-composed score+band, retry-once); `evals/evaluate.py` + golden template (band accuracy + score MAE, `--model` bake-off); `cli.py`. 77 tests. Merge gates clean (security-review fixed a DNS-rebinding TOCTOU; code-review fixed a sub-score bounds gap; `/verify` real GLM end-to-end). Amber manually verified. Retro pitfalls logged: GLM unbounded-thinking (disable, don't raise tokens), z.ai base URL, schema range enforcement.

## Queued next: Phase 4 — Deploy & Harden
Streamlit Cloud URL, security review, ship `golden_set.csv` template. Exit gate: shareable link works; security review clean.

Then: **Phase 5 — Observability & Labeling Console** (thin JSONL/CSV front-end to browse logged verdicts and label them into golden rows; seeds the evals) → **Phase 6 — Real evals & tuning** (human rubric weights + golden labels → tuning loop + bargain-model bake-off). See `cocoonkitchen_product.md` roadmap + `architecture.md` 2026-07-11 decision.
