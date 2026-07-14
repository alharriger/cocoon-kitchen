# Working Sprint — LIVE DOCUMENT

> This file tracks the **current phase only**. It is the handoff artifact between Claude sessions:
> update task status as work happens, log decisions and blockers immediately, and when the phase
> completes (retro done, merged to main), **refresh this file** for the next phase.

---

## Current phase: NEXT — Phase 5 (Deploy) or Phase 6 (Evals) — **Amber's call at kickoff**

> **Phase 4 is complete and merged to main** (2026-07-14, merge `4df5b0c`). See "Completed phases" below. The **52-row golden set now exists** (`evals/golden_set.csv`) — which unblocks **both** remaining tracks, so the next-phase order is genuinely open:
> - **Phase 5 — Deploy & Harden** (roadmap default): put the scorer on a public Streamlit Cloud URL.
> - **Phase 6 — Real evals & tuning** (now unblocked): Amber finalizes `rubric.yaml` weights → run `evaluate.py` on the 52-row set → bake-off + tuning. This is the "real product bet" (a rubric that agrees with a human).
>
> **Decide 5-vs-6 with Amber at the start of the next session.** Either way, **the first task is to PLAN, not code** (our loop): write the phase plan + security audit and get approval before writing anything. A likely-useful cheap slice regardless: run the current placeholder rubric against the 52 rows once to get a baseline band-accuracy/MAE number (informational — weights aren't finalized).

**Branch:** create `phase-5/deploy` (or `phase-6/evals`) off `main` once the phase is chosen and planned.

### Phase 5 — Deploy & Harden (if chosen): task skeleton
| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Plan Phase 5 + security audit; get approval | ⬜ | **← start here.** Deploy target, secrets handling, what's public |
| 2 | Streamlit Cloud deploy of **`app.py` only** | ⬜ | **`console.py` must NEVER be exposed** (architecture 2026-07-12); entrypoint = `app.py`, no `pages/` dir exists so the console stays inert on Cloud |
| 3 | Secrets via Streamlit Cloud secrets | ⬜ | `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`/`LLM_EXTRA_BODY` as Cloud secrets — never commit `.env` |
| 4 | Harden the public surface | ⬜ | errors never leak internals (already the case); `data/logs` is gitignored + ephemeral on Cloud; free z.ai key + public recipe text = acceptable v0 data posture (revisit if inputs get sensitive) |
| 5 | `/security-review` of the deployed surface + manual test (shareable link works) | ⬜ | |
| 6 | Merge gates + merge to main | ⬜ | |
| 7 | Retro → pitfalls → refresh this doc for Phase 6 | ⬜ | |

### Definition of done (Phase 5)
A shareable Streamlit Cloud URL where pasting a recipe (or link) returns a sane Verdict card; the labeling console is **not** reachable from it; secrets are in Cloud config, not the repo; security review clean; merged to main.

### Decisions carried in (for Phase 5/6)
- **`console.py` is LOCAL ONLY — never deploy** (architecture 2026-07-12). The Phase 5 deploy entrypoint is **`app.py`**; there is no `pages/` dir, so `console.py` stays inert on Streamlit Cloud. Any future remote console access must be access-gated first.
- **Golden labels + rubric weights are human-owned** (CLAUDE.md non-negotiable). The 52-row golden set is Amber's; `rubric.yaml` weights are still **placeholder** and only Amber finalizes them (that's the gate into Phase 6 tuning).
- **Model/provider is eval-selected, never by brand** (architecture 2026-07-11). Phase 6 runs the bake-off (GLM/Gemini/Groq/DeepSeek/Qwen) on the golden set; dev default stays GLM-4.5-Flash until a number says otherwise.
- **No new layer** (DB/RAG/auth/vector store) unless an eval number demands it. Still holds into deploy + evals.
- **Contract 4 is at v0.3** (`swap_quality` + `other_alternatives`/`concerns`); shape lives in `src/clean_recipe/golden.py`, imported by both `evaluate.py` and `console.py`.

### Environment reminders (from pitfalls)
- Import name is `clean_recipe`, NOT `cocoonkitchen`.
- Interactive terminal now auto-activates `.venv` via direnv (bare `python`/`streamlit`/`pytest` work in-project); **agent tool calls / scripts are non-interactive — keep using `.venv/bin/python`** (direnv's hook doesn't fire there).
- Run the app: `.venv/bin/streamlit run app.py` (or bare `streamlit run` in an interactive shell).
- Model calls need `.env` (z.ai GLM key + `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}`).
- When changing the model-I/O contract, walk the full blast radius (prompt + `_REPAIR_HINT` + all callers' `except` + validators) — see 2026-07-12 pitfall.

### Blockers
- None. Phase 4 merged to main; 202 tests green on main. Next phase (5 or 6) just needs Amber to pick + a plan.

### Handoff notes for next session
- **Phase 4 is done and merged** (`4df5b0c`). The golden-set builder console (`console.py`, 5 tabs: Backlog / Review & grade / Promote / Logs / Results) is on main; **`evals/golden_set.csv` holds 52 real golden rows** (8 Clean / 29 Mostly Clean / 12 Processed / 3 Ultra-processed). Contract 4 v0.3 shape in `src/clean_recipe/golden.py` (imported by `evaluate.py` + `console.py`).
- **First decision next session: Phase 5 (deploy) vs Phase 6 (evals)** — both unblocked now (see current-phase block above). Then plan → approve → build.
- **Golden-set coverage note for Phase 6:** the extremes are thin — only **3 Ultra-processed** and **8 Clean** rows (29 are Mostly Clean). If eval signal is weak at the ends, Amber may want to queue a handful more obviously-clean and obviously-ultra-processed recipes via the console before/during tuning. (52 total already meets the 20–50 target.)
- **Known v0.3 micro-format limit (low):** in the `other_alternatives` cell, an individual alternative that itself contains a comma would be split into two on load (comma is the alternatives separator). No current data hits this (verified: 0 of 29 concern rows). If it bites, either escape commas in `format_concerns`/`parse_concerns` or note it in the console help text.
- **Optional cleanup (Amber's opt-in):** some approved rows still carry v2-style prose in `notes` with empty `concerns` (they were left untouched during the v0.3 migration). Fine as-is; offer to restructure later if she wants uniformity.
- **Env pin (pitfall):** `pyproject.toml` pins `pyarrow==21.0.0` + `pandas==2.3.3` (pyarrow 25 segfaults `st.dataframe`). Re-run `pip install -e ".[dev]"` on stale venvs.
- **Untracked, left for Amber's call:** `.claude/` (Streamlit skill install + `settings.local.json`) and `.agents/` are untracked in the repo — decide whether to gitignore or commit them. Not part of Phase 4.
- **Cross-instance labeling worked** (golden creation done in a separate instance via `ai_docs/golden_draft_handoff.md`, finalized here) — but the returning session had to catch that promotion hadn't happened. See the 2026-07-14 pitfall.
- **Deferred (unchanged):** Contract 4's `raw_ingredients` file-path option (console always writes inline `"; "`); per-component MAE + automated swap-quality judging remain Phase 6.

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory; roadmap + practices approved. Merged to main.
- **Phase 1 — Scaffold, Schemas & Logging** ✅ (2026-07-10): repo layout; pinned deps; `schema.py` (Verdict/SubScores/Swap); placeholder `rubric.yaml`; `log.py`; 15 tests. Merged to main.
- **Phase 2 — Core Engines** ✅ (2026-07-11): `parse.py` (paste/URL, pinned-IP SSRF guard); provider-neutral `client.py`/`prompt.py`/`score.py` (GLM-4.5-Flash dev default, thinking disabled via `LLM_EXTRA_BODY`, code-composed score+band, retry-once); `evals/evaluate.py` + golden template (band accuracy + score MAE, `--model` bake-off); `cli.py`. 77 tests. Merge gates clean (security-review fixed a DNS-rebinding TOCTOU; code-review fixed a sub-score bounds gap; `/verify` real GLM end-to-end). Amber manually verified. Retro pitfalls logged: GLM unbounded-thinking (disable, don't raise tokens), z.ai base URL, schema range enforcement.
- **Phase 3 — UI & End-to-End** ✅ (2026-07-12): `app.py` Streamlit scorer (thin consumer; paste/link tabs; Verdict card = score + band pill, six weight-ordered bars, flagged list, 3 swaps, disclaimer; friendly error/empty states, never a traceback; untrusted strings md-escaped, `unsafe_allow_html` only for the schema-validated band pill). `streamlit==1.59.1` pinned. Two feedback-driven adds during manual test: (a) direnv `.envrc` so bare `python`/`streamlit` work in-project; (b) two-layer `is_recipe` validation (parse prose-guard + model gate → `NotARecipeError`) after a job posting scored as a recipe. 95 tests. Merge gates: code-review found 4 (stale `_REPAIR_HINT` breaking retry, eval-run abort on new raise, narrowed swaps validation, cli traceback) — all fixed + tested; security-review clean (band-pill HTML takes only validated/code-owned values). Retro pitfall logged: contract changes must ripple to every shape-dependent site. Roadmap gained Phase 7 (explainability/trust). Sub-agent rule added: fan out implementation only for ≥2 independent tracks (architecture 2026-07-12). Merged to main.
- **Phase 4 — Observability & Labeling Console (golden-set builder)** ✅ (2026-07-14, merge `4df5b0c`): `console.py` local-only entrypoint (5 tabs: Backlog / Review & grade / Promote / Logs / Results), built as a **backlog→drafts→grade→promote pipeline** after a v1 "author a row" form flopped in manual testing (author→grade pivot — pitfall logged). `src/clean_recipe/golden.py` is the single source of truth for the Contract-4 row + pipeline shapes (`GoldenRow`/`BacklogEntry`/`GoldenDraft`, append-only writer w/ formula-injection defang, promote). Contract 4 evolved **v0.1→v0.2 (`swap_quality`)→v0.3 (`other_alternatives`/`concerns` + axis doctrine)** from real labeling feedback. Forgiving recipe-text paste (strips site furniture, cuts at Directions) added to the core parser; link fetch (SSRF-guarded) wired into the backlog. Golden creation ran in a **separate Claude instance** via `ai_docs/golden_draft_handoff.md`; finalized here → **52-row golden set** promoted into `golden_set.csv`. Env pin: `pyarrow==21.0.0`/`pandas==2.3.3` (pyarrow-25 `st.dataframe` segfault — pitfall logged). 202 tests. Merge gates: code-review (1 low latent finding — comma-in-alternative round-trip, no data affected), security-review clean (zero `unsafe_allow_html`; CSV defang covers the new column; SSRF guard intact), `/verify` passed on the real 52-row data. Retro pitfalls logged: cross-instance handoff (verify end state), author→grade (validate workflow before building the entry UI). Merged to main.

## Queued next: Phase 5 — Deploy & Harden **or** Phase 6 — Real evals & tuning (Amber picks)
Both are unblocked now that the 52-row golden set exists.
- **Phase 5 — Deploy & Harden**: public Streamlit Cloud URL for **`app.py` only** (console.py never exposed), secrets via Cloud config, security review. Definition of done in the current-phase block above.
- **Phase 6 — Real evals & tuning**: Amber finalizes `rubric.yaml` weights → run `evaluate.py` on the golden set → band-accuracy/MAE targets + bargain-model bake-off (GLM/Gemini/Groq/DeepSeek/Qwen). This is the "rubric that agrees with a human" bet.

Then: **Phase 7 — Verdict explainability & trust** (recipe context + per-ingredient/sub-score rationale; ingredient-table accordion UX from the 2026-07-14 labeling retro) → **Phase 8 — Swap depth / "cleaner spectrum"** (tiered alternatives; brainstorm-gated; the v0.3 `other_alternatives` notes are its first data slice). See `cocoonkitchen_product.md` roadmap.
