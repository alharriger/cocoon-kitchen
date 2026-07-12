# Working Sprint — LIVE DOCUMENT

> This file tracks the **current phase only**. It is the handoff artifact between Claude sessions:
> update task status as work happens, log decisions and blockers immediately, and when the phase
> completes (retro done, merged to main), **refresh this file** for the next phase.

---

## Current phase: Phase 4 — Observability & Labeling Console (golden-set builder)

**Goal:** A lightweight internal front-end — the tool Amber uses to build the 20–50-row golden set that gates the evals. Two modes: **author** (paste/enter a recipe, optionally pre-score to pre-fill, then set target_band/target_score/expected_swaps/notes → a Contract-4 golden row; needs zero prior logs) and **label-from-log** (browse `data/logs/*.jsonl`, correct/confirm real Verdicts into golden rows + swap-quality grades). Exports to `evals/golden_set.csv`; views `evals/results/`. Thin JSONL/CSV front-end — **no DB, no auth, no vector store** until an eval number or a public deployment demands it.

**Branch:** create `phase-4/console` off `main` (Phase 3 is merged to main).

**⚠️ First task is to PLAN, not code.** Per our working loop, write the detailed Phase 4 plan (files, both modes' flows, Contract-4 write path, security notes — the console exposes ALL logged recipes so a public deploy would need gating, local use doesn't) and get Amber's approval BEFORE writing any code. Read `CLAUDE.md`, this file, `ai_docs/pitfalls.md`, `ai_docs/llm_contracts.md` (Contract 4 = the golden-row format, human-owned), and `ai_docs/architecture.md` (2026-07-11 console decision + 2026-07-12 sub-agent rule).

### Tasks
| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Write detailed Phase 4 plan + security audit; get Amber's approval | ⬜ Not started | **← start here.** Cover: page structure (separate `pages/` from the scorer), author + label-from-log flows, Contract-4 CSV write, log reader, no-DB guardrail, access note for future public deploy |
| 2 | Log reader: browse/paginate `data/logs/*.jsonl` (read-only) | ⬜ Not started | reuse `log.py` format; no new persistence layer |
| 3 | Author mode: recipe → optional pre-score (`score_recipe`) → editable Contract-4 golden row → append to `golden_set.csv` | ⬜ Not started | Contract 4 columns verbatim (see llm_contracts). **Labels are human-owned — Claude ships UI + template, never invents labels/weights** |
| 4 | Label-from-log mode: pick a logged verdict → correct into a golden row + swap-quality grade | ⬜ Not started | |
| 5 | Pause for Amber's manual test (build a few real golden rows end-to-end) | ⬜ Not started | |
| 6 | Merge gates: `/verify` + code-review + `/security-review`; merge to main | ⬜ Not started | security focus: the console surfaces all logged inputs |
| 7 | Phase 4 retrospective → log pitfalls → refresh this doc for Phase 5 | ⬜ Not started | |

### Definition of done (Phase 4)
Amber can open the console locally, author golden rows from recipes (and correct logged verdicts into rows), and export a Contract-4 `golden_set.csv` — enough to start assembling the 20–50-row golden set. No new persistence layer; unit tests green; docs in sync; merged to main.

### Decisions carried in
- **Console before deploy** (decided 2026-07-11): the golden set is the human long-pole gating evals; author mode needs no live traffic, so it isn't blocked by deploy. Order: 3 scorer → **4 console** → 5 deploy → 6 evals → 7 explainability.
- **Thin JSONL/CSV front-end** — reads the append-only log, writes golden rows to CSV. No DB/auth/vector store unless an eval number (or public console deploy) demands it (architecture 2026-07-11).
- **Golden labels + rubric weights are human-owned** (CLAUDE.md non-negotiable): the console is Amber's labeling tool; Claude never fills in target bands/scores/weights.
- Likely shape: a separate Streamlit page under `pages/`, distinct from the user-facing scorer (`app.py`).
- **Fan-out check** (2026-07-12 rule): decide at planning time whether the two modes are independent enough to build as parallel worktree agents, or one cohesive page built solo. Note the call in the plan.

### Environment reminders (from pitfalls)
- Import name is `clean_recipe`, NOT `cocoonkitchen`.
- Interactive terminal now auto-activates `.venv` via direnv (bare `python`/`streamlit`/`pytest` work in-project); **agent tool calls / scripts are non-interactive — keep using `.venv/bin/python`** (direnv's hook doesn't fire there).
- Run the app: `.venv/bin/streamlit run app.py` (or bare `streamlit run` in an interactive shell).
- Model calls need `.env` (z.ai GLM key + `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}`).
- When changing the model-I/O contract, walk the full blast radius (prompt + `_REPAIR_HINT` + all callers' `except` + validators) — see 2026-07-12 pitfall.

### Blockers
- None. Scorer (`app.py`) + core are merged and verified. `data/logs/verdicts.jsonl` already accumulates real verdicts to label from.

### Handoff notes for next session
- Phase 3 merged to main (commit `4a2ff15`, merge `c1d2b76`), manually verified by Amber. Scorer UI is `app.py`; the core is `parse_recipe`/`score_recipe`.
- `log.py` already appends every verdict to `data/logs/verdicts.jsonl` (gitignored) — the label-from-log source. Contract 4 (golden-row format) is in `llm_contracts.md`.
- Deferred (from Phase 2, still open): Contract 4's `raw_ingredients` "path to a text file" option isn't implemented in `evaluate.py` (only inline `"; "`-separated); confirm with Amber when real labels land. Per-component MAE + swap-quality metrics await golden columns.
- Start by drafting the Phase 4 plan and presenting it for approval.

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory; roadmap + practices approved. Merged to main.
- **Phase 1 — Scaffold, Schemas & Logging** ✅ (2026-07-10): repo layout; pinned deps; `schema.py` (Verdict/SubScores/Swap); placeholder `rubric.yaml`; `log.py`; 15 tests. Merged to main.
- **Phase 2 — Core Engines** ✅ (2026-07-11): `parse.py` (paste/URL, pinned-IP SSRF guard); provider-neutral `client.py`/`prompt.py`/`score.py` (GLM-4.5-Flash dev default, thinking disabled via `LLM_EXTRA_BODY`, code-composed score+band, retry-once); `evals/evaluate.py` + golden template (band accuracy + score MAE, `--model` bake-off); `cli.py`. 77 tests. Merge gates clean (security-review fixed a DNS-rebinding TOCTOU; code-review fixed a sub-score bounds gap; `/verify` real GLM end-to-end). Amber manually verified. Retro pitfalls logged: GLM unbounded-thinking (disable, don't raise tokens), z.ai base URL, schema range enforcement.
- **Phase 3 — UI & End-to-End** ✅ (2026-07-12): `app.py` Streamlit scorer (thin consumer; paste/link tabs; Verdict card = score + band pill, six weight-ordered bars, flagged list, 3 swaps, disclaimer; friendly error/empty states, never a traceback; untrusted strings md-escaped, `unsafe_allow_html` only for the schema-validated band pill). `streamlit==1.59.1` pinned. Two feedback-driven adds during manual test: (a) direnv `.envrc` so bare `python`/`streamlit` work in-project; (b) two-layer `is_recipe` validation (parse prose-guard + model gate → `NotARecipeError`) after a job posting scored as a recipe. 95 tests. Merge gates: code-review found 4 (stale `_REPAIR_HINT` breaking retry, eval-run abort on new raise, narrowed swaps validation, cli traceback) — all fixed + tested; security-review clean (band-pill HTML takes only validated/code-owned values). Retro pitfall logged: contract changes must ripple to every shape-dependent site. Roadmap gained Phase 7 (explainability/trust). Sub-agent rule added: fan out implementation only for ≥2 independent tracks (architecture 2026-07-12). Merged to main.

## Queued next: Phase 4 — Observability & Labeling Console (golden-set builder)
Decided 2026-07-11 (console before deploy): a lightweight internal front-end — **author mode** (recipe → Contract-4 golden row, no logs needed) + **label-from-log mode** (correct logged verdicts into golden rows + swap-quality grades), exporting to `golden_set.csv`. This is how Amber builds the 20–50-row golden set — the human long-pole that gates the evals. Thin JSONL/CSV front-end, no DB/auth until an eval number or public deployment demands it.

Then: **Phase 5 — Deploy & Harden** (Streamlit Cloud URL, security review) → **Phase 6 — Real evals & tuning** (human rubric weights + the golden set → tuning loop + bargain-model bake-off across GLM/Gemini/Groq/DeepSeek/Qwen) → **Phase 7 — Verdict explainability & trust** (recipe context + per-ingredient/sub-score rationale on the card; after Phase 6 so we only justify a validated score — added 2026-07-12 per Amber). See `cocoonkitchen_product.md` roadmap + `architecture.md` 2026-07-11 decisions.
