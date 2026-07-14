# Working Sprint — LIVE DOCUMENT

> This file tracks the **current phase only**. It is the handoff artifact between Claude sessions:
> update task status as work happens, log decisions and blockers immediately, and when the phase
> completes (retro done, merged to main), **refresh this file** for the next phase.

---

## Current phase: Phase 4 — Observability & Labeling Console (golden-set builder)

**Goal:** A lightweight internal front-end — the tool Amber uses to build the 20–50-row golden set that gates the evals. Two modes: **author** (paste/enter a recipe, optionally pre-score to pre-fill, then set target_band/target_score/expected_swaps/notes → a Contract-4 golden row; needs zero prior logs) and **label-from-log** (browse `data/logs/*.jsonl`, correct/confirm real Verdicts into golden rows + swap-quality grades). Exports to `evals/golden_set.csv`; views `evals/results/`. Thin JSONL/CSV front-end — **no DB, no auth, no vector store** until an eval number or a public deployment demands it.

**Branch:** create `phase-4/console` off `main` (Phase 3 is merged to main).

**⚠️ First task is to PLAN, not code.** Per our working loop, write the detailed Phase 4 plan (files, both modes' flows, Contract-4 write path, security notes — the console exposes ALL logged recipes so a public deploy would need gating, local use doesn't) and get Amber's approval BEFORE writing any code. Read `CLAUDE.md`, this file, `ai_docs/pitfalls.md`, `ai_docs/llm_contracts.md` (Contract 4 = the golden-row format, human-owned), and `ai_docs/architecture.md` (2026-07-11 console decision + 2026-07-12 sub-agent rule).

> **2026-07-13 pivot (Amber's manual test → v2 console).** The v1 console (author + label-from-log, both appending straight to `golden_set.csv`) was built and merged-ready, but hand-authoring 20–50 rows in a form was too slow and Amber's real feedback lever is *grading*, not authoring. Reworked into a **backlog→drafts→promote pipeline** (see architecture 2026-07-13): Amber queues recipes (Backlog), a **separate Claude instance** drafts labels + captures the real model verdict (`ai_docs/golden_draft_handoff.md`), Amber grades one-at-a-time (swap_quality 1–5 + notes front-and-center), then promotes approved rows. Link-in-the-backlog now really fetches (was metadata-only). Roadmap gained **Phase 8 — "cleaner spectrum"** (tiered alternatives; brainstorm-gated) per Amber's fettuccine-alfredo insight.

### Tasks
| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Write Phase 4 plan + security audit; approval | ✅ Done | v1 approved 2026-07-12; **v2 pipeline approved 2026-07-13** after manual-test feedback |
| 2 | Log reader (read-only) | ✅ Done | `read_log`/`list_log_files` in `log.py`; Logs tab paginates 20/page, tolerant of malformed lines |
| 3 | Backlog: queue recipes (paste **or link**) → `backlog.jsonl`; submit-for-review | ✅ Done | link fetches via parse.py SSRF guard; ids unique across golden+backlog+drafts |
| 4 | Draft pipeline: `GoldenDraft` shape + handoff doc + Review&grade queue + Promote | ✅ Done | separate instance drafts (`golden_draft_handoff.md`); review = swap_quality+notes primary, band/score/swaps editable; promote appends approved → `golden_set.csv` (append-only kept) |
| 5 | Pause for Amber's manual test (end-to-end: queue → draft → grade → promote) | 🟡 **← waiting on Amber** | `streamlit run console.py`; then run the handoff in a separate instance on a couple of real recipes |
| 6 | Merge gates: `/verify` + code-review + `/security-review`; merge to main | ⬜ Not started | security focus: console surfaces all logged inputs; untrusted strings via non-markdown widgets only |
| 7 | Phase 4 retrospective → log pitfalls → refresh this doc for Phase 5 | ⬜ Not started | pyarrow-segfault pitfall already logged; capture the "author→grade" pivot lesson |

### Definition of done (Phase 4)
Amber can open the console locally, queue recipes into a backlog, hand the batch to a separate Claude instance that drafts labels, grade/correct those drafts (swap_quality + notes), and promote approved rows into a Contract-4 `golden_set.csv` — enough to assemble the 20–50-row golden set. No new persistence layer (thin JSONL/CSV); unit tests green; docs in sync; merged to main.

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
- **2026-07-14 — Contract 4 v0.2 → v0.3 (draft-review feedback, on `phase-4/console`, not yet committed).** Amber's mid-labeling feedback drove three changes (her plan items 1–3):
  1. **`other_alternatives` column** (last position) for flagged items that get **no** swap — structured `GoldenRow.concerns` (`list[Concern]` of `item`/`why`/`alternatives`); CSV cell uses the `item>why>alt, alt; …` micro-format (`format_concerns`/`parse_concerns`, defanged like `expected_swaps`). Console renders concerns as a read-only "items of concern → alternatives" table (with a `suggestion: no swap` column) and has an edit field in the adjust-labels expander.
  2. **Axis doctrine** in `llm_contracts.md` Contract 4 — swaps state their axis (less-processed primary / healthier / sourcing). Labeling convention, not a scoring rule; does NOT edit rubric weights.
  3. **Collapsed v1-history block** — `GoldenDraft.review` (`ReviewNote`, console-internal, NOT Contract 4) holds a superseded draft + Amber's verbatim feedback; console shows it in an expander instead of a notes wall.
  - **`golden_drafts.jsonl` migrated** (scratchpad `migrate_drafts_v3.py`; backups `.bak-pre-v2`, `.bak-pre-v3`): 29 draft rows moved concern/history prose out of `notes` into structured fields. **The 17 approved rows were left untouched per Amber's explicit instruction** — they still carry the v2 prose in `notes` and have empty `concerns` (offer to migrate them later, her opt-in). No label (band/score/swaps/swap_quality) changed on any row.
  - **Status when handed off:** 17/52 approved, 35 draft (2 of those carry a `review` block: raspberry-bread grade 4, paccheri no-grade). 202 tests green (3× full runs, no pyarrow segfault). **Not committed — awaiting Amber's manual test** of the console (concerns render/edit, history block, promote carries `other_alternatives`).
- **v2 pipeline is complete on `phase-4/console`** (2026-07-13). `console.py` now has 5 tabs — **Backlog / Review & grade / Promote / Logs / Results** (the v1 Author + Label-from-log tabs are gone). `src/clean_recipe/golden.py` holds the Contract-4 shape (`GoldenRow`, `load_golden`, append-only `append_golden_row`) **plus** the pipeline shapes `BacklogEntry` / `GoldenDraft` and helpers (`read/write_backlog`, `read/write/append_draft`, `promote_approved`, `suggest_recipe_id`). Tolerant reader in `log.py`. Handoff brief for the draft-generating instance: `ai_docs/golden_draft_handoff.md`.
- **The full loop:** Amber queues recipes in Backlog → submits → **a separate Claude instance** runs `golden_draft_handoff.md` (reads `evals/backlog.jsonl`, real-scores each, drafts labels → `evals/golden_drafts.jsonl`) → Amber grades in Review & grade → Promote appends approved rows → `evals/golden_set.csv`.
- **Env pin (pitfall logged):** `pyproject.toml` pins `pyarrow==21.0.0` + `pandas==2.3.3` (pyarrow 25 segfaults `st.dataframe`). Re-run `pip install -e ".[dev]"` on stale venvs.
- **Manual test for Amber:** `streamlit run console.py` → Backlog: add a recipe by paste and by link (link now really fetches), submit → open a separate Claude instance on `golden_draft_handoff.md` for a couple of recipes → Review & grade (set swap_quality + notes, Approve) → Promote → eyeball `golden_set.csv`. Delete the `sample-*` template rows when real labels land.
- **New files are committed (not gitignored):** `evals/backlog.jsonl` + `evals/golden_drafts.jsonl` hold real review work (grades) — 0-data-loss. They're created on first write.
- Roadmap: **Phase 8 — "cleaner spectrum"** added (tiered alternatives; needs a brainstorming session before it's scoped — Amber's call on when).
- Deferred (unchanged): Contract 4's `raw_ingredients` file-path option (console always writes inline `"; "`); per-component MAE + automated swap judging remain Phase 6.

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory; roadmap + practices approved. Merged to main.
- **Phase 1 — Scaffold, Schemas & Logging** ✅ (2026-07-10): repo layout; pinned deps; `schema.py` (Verdict/SubScores/Swap); placeholder `rubric.yaml`; `log.py`; 15 tests. Merged to main.
- **Phase 2 — Core Engines** ✅ (2026-07-11): `parse.py` (paste/URL, pinned-IP SSRF guard); provider-neutral `client.py`/`prompt.py`/`score.py` (GLM-4.5-Flash dev default, thinking disabled via `LLM_EXTRA_BODY`, code-composed score+band, retry-once); `evals/evaluate.py` + golden template (band accuracy + score MAE, `--model` bake-off); `cli.py`. 77 tests. Merge gates clean (security-review fixed a DNS-rebinding TOCTOU; code-review fixed a sub-score bounds gap; `/verify` real GLM end-to-end). Amber manually verified. Retro pitfalls logged: GLM unbounded-thinking (disable, don't raise tokens), z.ai base URL, schema range enforcement.
- **Phase 3 — UI & End-to-End** ✅ (2026-07-12): `app.py` Streamlit scorer (thin consumer; paste/link tabs; Verdict card = score + band pill, six weight-ordered bars, flagged list, 3 swaps, disclaimer; friendly error/empty states, never a traceback; untrusted strings md-escaped, `unsafe_allow_html` only for the schema-validated band pill). `streamlit==1.59.1` pinned. Two feedback-driven adds during manual test: (a) direnv `.envrc` so bare `python`/`streamlit` work in-project; (b) two-layer `is_recipe` validation (parse prose-guard + model gate → `NotARecipeError`) after a job posting scored as a recipe. 95 tests. Merge gates: code-review found 4 (stale `_REPAIR_HINT` breaking retry, eval-run abort on new raise, narrowed swaps validation, cli traceback) — all fixed + tested; security-review clean (band-pill HTML takes only validated/code-owned values). Retro pitfall logged: contract changes must ripple to every shape-dependent site. Roadmap gained Phase 7 (explainability/trust). Sub-agent rule added: fan out implementation only for ≥2 independent tracks (architecture 2026-07-12). Merged to main.

## Queued next: Phase 4 — Observability & Labeling Console (golden-set builder)
Decided 2026-07-11 (console before deploy): a lightweight internal front-end — **author mode** (recipe → Contract-4 golden row, no logs needed) + **label-from-log mode** (correct logged verdicts into golden rows + swap-quality grades), exporting to `golden_set.csv`. This is how Amber builds the 20–50-row golden set — the human long-pole that gates the evals. Thin JSONL/CSV front-end, no DB/auth until an eval number or public deployment demands it.

Then: **Phase 5 — Deploy & Harden** (Streamlit Cloud URL, security review) → **Phase 6 — Real evals & tuning** (human rubric weights + the golden set → tuning loop + bargain-model bake-off across GLM/Gemini/Groq/DeepSeek/Qwen) → **Phase 7 — Verdict explainability & trust** (recipe context + per-ingredient/sub-score rationale on the card; after Phase 6 so we only justify a validated score — added 2026-07-12 per Amber). See `cocoonkitchen_product.md` roadmap + `architecture.md` 2026-07-11 decisions.
