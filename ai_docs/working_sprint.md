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
| 1 | Write detailed Phase 4 plan + security audit; get Amber's approval | ✅ Done | Approved 2026-07-12. Key calls: `console.py` separate entrypoint (NOT `pages/` — would ride the Phase 5 public deploy); Contract 4 v0.2 adds `swap_quality`; pre-score uses `log=False`; solo build (fan-out rule: modes share the form + write path) |
| 2 | Log reader: browse/paginate `data/logs/*.jsonl` (read-only) | ✅ Done | `read_log`/`list_log_files` in `log.py` — malformed lines skip + count, never crash; Logs tab paginates 20/page |
| 3 | Author mode: recipe → optional pre-score (`score_recipe`) → editable Contract-4 golden row → append to `golden_set.csv` | ✅ Done | Shape lives in `src/clean_recipe/golden.py` (shared with `evaluate.py`). Pre-fill is banner-marked model suggestion; band/score have NO defaults — a save can't invent a label |
| 4 | Label-from-log mode: pick a logged verdict → correct into a golden row + swap-quality grade | ✅ Done | swap_quality (1–5) required in this mode, optional in author mode (UI rule; blank is legal in the contract) |
| 5 | Pause for Amber's manual test (build a few real golden rows end-to-end) | 🟡 **← waiting on Amber** | `streamlit run console.py` — author a couple of real rows + label a logged verdict; check the form flow feels right |
| 6 | Merge gates: `/verify` + code-review + `/security-review`; merge to main | ⬜ Not started | security focus: the console surfaces all logged inputs |
| 7 | Phase 4 retrospective → log pitfalls → refresh this doc for Phase 5 | ⬜ Not started | pyarrow-segfault pitfall already logged (bit us mid-phase) |

### Definition of done (Phase 4)
Amber can open the console locally, author golden rows from recipes (and correct logged verdicts into rows), and export a Contract-4 `golden_set.csv` — enough to start assembling the 20–50-row golden set. No new persistence layer; unit tests green; docs in sync; merged to main.

### Decisions carried in
- **Console before deploy** (decided 2026-07-11): the golden set is the human long-pole gating evals; author mode needs no live traffic, so it isn't blocked by deploy. Order: 3 scorer → **4 console** → 5 deploy → 6 evals → 7 explainability.
- **Thin JSONL/CSV front-end** — reads the append-only log, writes golden rows to CSV. No DB/auth/vector store unless an eval number (or public console deploy) demands it (architecture 2026-07-11).
- **Golden labels + rubric weights are human-owned** (CLAUDE.md non-negotiable): the console is Amber's labeling tool; Claude never fills in target bands/scores/weights.
- ~~Likely shape: a separate Streamlit page under `pages/`~~ → **Decided in the approved plan: root-level `console.py`, its own entrypoint, NO `pages/` dir** — `pages/` auto-attaches to the deployed entrypoint and would have exposed all logged recipes on the Phase 5 public deploy (architecture 2026-07-12).
- **Fan-out check** (2026-07-12 rule): **called solo** in the approved plan — author and label-from-log share the golden-row form, validation, and write path; not independent tracks.

### Environment reminders (from pitfalls)
- Import name is `clean_recipe`, NOT `cocoonkitchen`.
- Interactive terminal now auto-activates `.venv` via direnv (bare `python`/`streamlit`/`pytest` work in-project); **agent tool calls / scripts are non-interactive — keep using `.venv/bin/python`** (direnv's hook doesn't fire there).
- Run the app: `.venv/bin/streamlit run app.py` (or bare `streamlit run` in an interactive shell).
- Model calls need `.env` (z.ai GLM key + `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}`).
- When changing the model-I/O contract, walk the full blast radius (prompt + `_REPAIR_HINT` + all callers' `except` + validators) — see 2026-07-12 pitfall.

### Blockers
- **Task 5: Amber's manual test.** Everything through task 4 is built and green (156 tests) on `phase-4/console`; merge gates run after her pass.

### Handoff notes for next session
- **Build is complete on `phase-4/console`** (implementation 2026-07-12, plan approved same day). New: `src/clean_recipe/golden.py` (Contract-4 v0.2 shape — `GoldenRow`, `load_golden`, append-only `append_golden_row` with header check + formula-injection defang, slug suggester), `console.py` (4 tabs: Logs / Author / Label-from-log / Results; zero `unsafe_allow_html`; untrusted strings only through non-markdown widgets), tolerant reader in `log.py`, `tests/test_golden.py` + `tests/test_console.py`. Changed: `evaluate.py` imports the shared shape + prints swap-quality info; `golden_set.csv` template has the v0.2 header; README + contracts/architecture docs updated.
- **Env fix (pitfall logged):** pyarrow 25.0.0 segfaulted `st.dataframe` in Streamlit script threads; `pyproject.toml` now pins `pyarrow==21.0.0` + `pandas==2.3.3`. Re-run `pip install -e ".[dev]"` on stale venvs.
- Manual test for Amber: `streamlit run console.py` → author a real golden row (with and without pre-score), label one logged verdict (18 real verdicts already in `data/logs/verdicts.jsonl`), eyeball `golden_set.csv`. Delete the `sample-*` template rows whenever real labels land (console reminds you).
- Deferred (from Phase 2, still open): Contract 4's `raw_ingredients` "path to a text file" option isn't implemented in `evaluate.py` (only inline `"; "`-separated) — console always writes inline, so console-authored rows never hit the gap; confirm with Amber when real labels land. Per-component MAE + automated swap judging remain Phase 6.
- Known limitation (documented in console.py): log records don't store `source`, so label-from-log rows default to `pasted` (editable in the form).

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory; roadmap + practices approved. Merged to main.
- **Phase 1 — Scaffold, Schemas & Logging** ✅ (2026-07-10): repo layout; pinned deps; `schema.py` (Verdict/SubScores/Swap); placeholder `rubric.yaml`; `log.py`; 15 tests. Merged to main.
- **Phase 2 — Core Engines** ✅ (2026-07-11): `parse.py` (paste/URL, pinned-IP SSRF guard); provider-neutral `client.py`/`prompt.py`/`score.py` (GLM-4.5-Flash dev default, thinking disabled via `LLM_EXTRA_BODY`, code-composed score+band, retry-once); `evals/evaluate.py` + golden template (band accuracy + score MAE, `--model` bake-off); `cli.py`. 77 tests. Merge gates clean (security-review fixed a DNS-rebinding TOCTOU; code-review fixed a sub-score bounds gap; `/verify` real GLM end-to-end). Amber manually verified. Retro pitfalls logged: GLM unbounded-thinking (disable, don't raise tokens), z.ai base URL, schema range enforcement.
- **Phase 3 — UI & End-to-End** ✅ (2026-07-12): `app.py` Streamlit scorer (thin consumer; paste/link tabs; Verdict card = score + band pill, six weight-ordered bars, flagged list, 3 swaps, disclaimer; friendly error/empty states, never a traceback; untrusted strings md-escaped, `unsafe_allow_html` only for the schema-validated band pill). `streamlit==1.59.1` pinned. Two feedback-driven adds during manual test: (a) direnv `.envrc` so bare `python`/`streamlit` work in-project; (b) two-layer `is_recipe` validation (parse prose-guard + model gate → `NotARecipeError`) after a job posting scored as a recipe. 95 tests. Merge gates: code-review found 4 (stale `_REPAIR_HINT` breaking retry, eval-run abort on new raise, narrowed swaps validation, cli traceback) — all fixed + tested; security-review clean (band-pill HTML takes only validated/code-owned values). Retro pitfall logged: contract changes must ripple to every shape-dependent site. Roadmap gained Phase 7 (explainability/trust). Sub-agent rule added: fan out implementation only for ≥2 independent tracks (architecture 2026-07-12). Merged to main.

## Queued next: Phase 4 — Observability & Labeling Console (golden-set builder)
Decided 2026-07-11 (console before deploy): a lightweight internal front-end — **author mode** (recipe → Contract-4 golden row, no logs needed) + **label-from-log mode** (correct logged verdicts into golden rows + swap-quality grades), exporting to `golden_set.csv`. This is how Amber builds the 20–50-row golden set — the human long-pole that gates the evals. Thin JSONL/CSV front-end, no DB/auth until an eval number or public deployment demands it.

Then: **Phase 5 — Deploy & Harden** (Streamlit Cloud URL, security review) → **Phase 6 — Real evals & tuning** (human rubric weights + the golden set → tuning loop + bargain-model bake-off across GLM/Gemini/Groq/DeepSeek/Qwen) → **Phase 7 — Verdict explainability & trust** (recipe context + per-ingredient/sub-score rationale on the card; after Phase 6 so we only justify a validated score — added 2026-07-12 per Amber). See `cocoonkitchen_product.md` roadmap + `architecture.md` 2026-07-11 decisions.
