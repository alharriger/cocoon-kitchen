# Working Sprint — LIVE DOCUMENT

> This file tracks the **current phase only**. It is the handoff artifact between Claude sessions:
> update task status as work happens, log decisions and blockers immediately, and when the phase
> completes (retro done, merged to main), **refresh this file** for the next phase.

---

## Current phase: Phase 6 — Real evals & tuning (IN PROGRESS)

> **Amber chose Phase 6 over Phase 5 at kickoff (2026-07-16)**, after a baseline run made the case: the placeholder rubric is systematically **too lenient** — deploying it (Phase 5) would ship a scorer that calls Processed food "Clean." Fix the rubric first, deploy after. Phase 5 (Deploy & Harden) is now **queued behind Phase 6** — its task skeleton is preserved under "Queued next" below.
>
> **The bet:** a rubric that *agrees with Amber's labels* on the 52-row golden set. **Baseline (placeholder rubric, GLM-4.5-Flash, 2026-07-17):** band accuracy **~31–33%**, MAE **~14**, mean signed error **+13** (48/52 rows scored *too clean*). Per-band: Clean 8/8 · Mostly Clean 7/29 · Processed ~1/12 · Ultra-processed 1/3.

**Branch:** `phase-6/evals` (off `main`).

### Phase 6 task skeleton
| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Plan Phase 6 + security audit; approval | ✅ | Approved 2026-07-16. Human/Claude split: Amber owns weights/cutoffs/marker-list *contents*/targets; Claude owns harness/diagnostics/bake-off/docs. |
| 2 | **Diagnostic harness upgrade** | ✅ | `evaluate.py`: captures the 6 model sub-scores/row; prints per-band accuracy + band-confusion (cleaner/harsher) + mean signed error + **`subscore_means`** (the lever-finder) + per-row progress heartbeat. Results CSV gains `signed_error` + 6 sub-score cols. 210 tests. Gates: code-review (1 low → fixed: `BANDS`↔`schema.Band` sync assert), security-review clean. **Committed on `phase-6/evals`.** |
| 3 | **Populate rubric lexicons** (I draft, Amber curates) | ✅ | **DONE 2026-07-18.** Split marker lists into console-owned `rubric/lexicons.yaml` (new `src/clean_recipe/lexicons.py`); **3 flat + 3 tiered (1–5) lexicons** (added-sugar/fat/sodium graded by quality, per Amber). `prompt.py` renders a GROUNDING + CALIBRATION block (worst-tier scoring, ingredient **decomposition**, anti-leniency nudge). New Console **Lexicons** tab (per-tier editors) for Amber's curation. **Key finding:** passive lists did nothing (32.7%); the calibration rule + tiers moved it to **~40–44% band acc / MAE ~11** (from ~32% / ~14). 227 tests. Contract 2→v0.3, Contract 3 logged. **Surfaced the composite-dilution finding → next build (see OPEN FINDING + PROPOSAL below).** |
| 4 | Bargain-model bake-off | ⬜ | Run the tuned rubric across GLM/Gemini/Groq/DeepSeek/Qwen (`--model`). **Needs Amber's API keys** for the non-GLM providers. Recommend eval-selected default (never by brand). |
| 5 | Regression tracking + docs | ⬜ | Persist each run's headline numbers + rubric version; keep `llm_contracts.md`/architecture/product in sync. Sets up Phase 7's "no regression" gate. |
| 6 | Merge gates + merge to main | ⬜ | |
| 7 | Retro → pitfalls → refresh this doc for Phase 5 | ⬜ | |

### Definition of done (Phase 6)
Band accuracy / MAE meet Amber's targets on the 52-row set; a bake-off run with a recommended default model; every prompt/contract change logged in `llm_contracts.md`; merge gates clean; merged to main.

### Why the baseline can't be fixed by weights alone (the key finding)
The composite score/band are **computed in code** from `rubric.yaml` weights; the six **sub-scores come from the model**. `subscore_means` shows every dimension averaging **69–89** — uniformly generous. No convex combination of 69–89 produces a Processed-band composite, so **weight-tuning can't fix leniency.** The lever is the **empty marker lists** (they ground the model's sub-scores in the prompt). See architecture decision **2026-07-17**.

### OPEN FINDING + PROPOSAL — composite dilutes severe offenders (the NEXT build)
After Task 3 (tiered lexicons + calibration rule + decomposition), the model's sub-scores now **discriminate** processed dishes — leniency is largely fixed (uncurated draft **44.2% / MAE 10.65**; post-curation **40.4% / MAE 10.9**, up from ~32% / ~14). The residual miss flipped: processed recipes land **one band too high** (Processed → Mostly Clean; Processed-band 1/12).

**Root cause (Amber, 2026-07-18):** `score.compose_score` is a **pure weighted mean** — a convex combination bounded between the min and max sub-score. A single severe offender (her example: chicken + broccoli + *artificial flavor*) is averaged away — worst on `additive_count`, which weighs only 0.05 — so one bad ingredient can't visibly drop the band. Amber's requirement: *a bad ingredient must visibly tank the score even when everything else is clean.*

**Proposal — make the composite penalty-sensitive (worst axis caps cleanliness).** All knobs stay human-owned in `rubric.yaml`; measure before/after on the golden set.
- **Option 1 — worst-dimension pull (RECOMMENDED):** `composite = (1-α)·weighted_mean + α·min_subscore`. One knob α (~0.3–0.5). Uses the model's existing sub-scores, no new ingredient-parsing layer. Chicken+broccoli+artificial-flavor (additive_count≈20) → visibly drops toward Processed.
- **Option 2 — below-threshold penalty:** subtract points for each sub-score under a floor T. More expressive, more knobs (T + scale).
- **Option 3 — power-mean p<1:** sub-linear aggregation that punishes low dims; one knob p, less intuitive.
- **Option 4 — hard severity cap:** a tier-1/NOVA-4 marker caps the band — but needs code to match ingredients to lexicons (new layer); the model's low sub-score already encodes this, so prefer Option 1.

This **subsumes** the band-compression fix (Option 1 is the mechanism; band cutoffs/weights are the secondary knob). **Do not chase it with more prompt strictness.** Mirrored in architecture 2026-07-18 + product roadmap Phase 6 row. Needs Amber to pick an option + set α before build (weights/knobs are human-owned). **Must close before Phase 6 exits.**

### Task 3 kickoff (for the fresh instance) — read this first
Amber is starting Task 3 in a **new Claude instance**; run the full loop there (plan → approval → build → manual test → retro). What's already settled vs. open:
- **Approach (settled, Amber 2026-07-16):** "I draft, you curate." Claude drafts candidate marker lists from public sources; **Amber curates/approves every list** — the contents are human-owned. Curated **in-prompt lexicon, NOT RAG** (architecture 2026-07-17).
- **Draft size (settled, Amber 2026-07-17):** **draft BROAD** — generous lists (common + less-common markers) so Amber mostly *cuts*. "Easier to cut than add." (Same spirit as the swap-drafting feedback memory.)
- **Proposed schema shape (PROPOSED, not yet approved — the next instance should confirm with Amber in its plan):** expand `rubric.yaml` to one lexicon per punishable dimension —
  - `nova4_markers` → ultra_processing (exists, empty)
  - `refined_seed_oils` → fat_quality (exists, empty)
  - `added_sugar_markers` → added_sugar (NEW; ~60 sugar aliases)
  - `sodium_preservative_markers` → sodium_preservatives (NEW; nitrites, benzoates, …)
  - `additive_markers` → additive_count (NEW; colors, emulsifiers, carrageenan, …)
  - `aliases` → canonicalization (exists, empty)
- **Open question for the plan:** whether to also ground `whole_food_ratio` with a `whole_food_whitelist` (fuzzy/large — proposed to skip unless a number demands it).
- **Blast radius when the shape lands:** new `rubric.yaml` keys must be rendered in `prompt.py` `_rubric_reference`, and the prompt change logged in `llm_contracts.md` (Contract 3). This is a model-I/O contract change — walk the blast radius (2026-07-12 pitfall). The model's sub-scores *should* shift down for processed items — that's the whole point; measure with `evaluate.py` before/after.
- **Measurement discipline:** re-run `.venv/bin/python evals/evaluate.py` after each curation pass; compare `subscore_means` + band accuracy. Mind the ~2pp / ~1 MAE noise floor (temperature=0 still varies).

### Decisions carried in (Phase 6)
- **Marker lists = curated in-prompt lexicon, NOT RAG** (architecture 2026-07-17, Amber). Bounded well-known vocab fits in the prompt; no vector store. External nutrition-DB/product lookup is **deferred + eval-gated** (product roadmap Phase 9 — not approved).
- **Golden labels + rubric weights + marker-list contents are human-owned** (CLAUDE.md). Claude may *draft* candidate lexicons; Amber curates the final content. `rubric.yaml` weights are still placeholder until Amber finalizes.
- **Model/provider is eval-selected, never by brand** (architecture 2026-07-11). Dev default stays GLM-4.5-Flash until a bake-off number says otherwise.
- **Composite is code-computed from weights; model only judges the 6 sub-scores** (architecture 2026-07-11) — the reason weights alone can't fix leniency.
- **Contract 4 is at v0.3**; shape lives in `src/clean_recipe/golden.py`, imported by both `evaluate.py` and `console.py`.
- **Eval noise floor:** even at `temperature=0`, identical runs move ~2pp band accuracy / ~1 MAE. Treat sub-threshold swings as noise; average over N runs if needed.

### Environment reminders (from pitfalls)
- Import name is `clean_recipe`, NOT `cocoonkitchen`.
- Interactive terminal auto-activates `.venv` via direnv; **agent tool calls / scripts are non-interactive — use `.venv/bin/python`**.
- Run the eval: `.venv/bin/python evals/evaluate.py` (add `--limit N` for a quick slice; the progress heartbeat shows it's working, not hung — each row is a real ~2–4s model call).
- Model calls need `.env` (z.ai GLM key + `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}`).
- When changing the model-I/O contract, walk the full blast radius (prompt + `_REPAIR_HINT` + all callers' `except` + validators) — see 2026-07-12 pitfall.

### Blockers
- **Task 4 (bake-off)** needs Amber's API keys for the non-GLM providers (Gemini/Groq/DeepSeek/Qwen). Not blocking Task 3.

### Handoff notes for next session
- **Phase 6 Task 3 (rubric lexicons) is DONE — committed on `phase-6/evals`, retro complete.** Tiered lexicons (`rubric/lexicons.yaml` + `src/clean_recipe/lexicons.py`) + prompt calibration/decomposition + Console Lexicons tab. Numbers: ~40–44% band acc / MAE ~11 (from ~32% / ~14). Branch NOT merged (Phase 6 incomplete).
- **THE NEXT BUILD is the composite-composition change** — see "OPEN FINDING + PROPOSAL" above. `compose_score` weighted-mean dilutes single severe offenders; Amber wants one bad ingredient to visibly tank the score. Recommended Option 1 (worst-dimension pull, knob α in `rubric.yaml`). **Needs Amber to pick an option + set α (human-owned) before build.** Do the full plan→approval loop. This subsumes the band-cutoff-compression fix and is the likely key to landing the Processed band. Also pending: **Amber may retune band cutoffs/weights** in the same pass.
- **Phase 6 Task 2 (diagnostics) DONE** — committed `f35fe05`. `evaluate.py` prints the lever-finder; `.venv/bin/python evals/evaluate.py`.
- **Task 3 is the live work and starts in a fresh Claude instance** (Amber's call, 2026-07-16) — do the full loop there. **Read the "Task 3 kickoff" block above first**: approach + draft-size are settled, the schema shape is proposed-not-approved (confirm in the plan). Draft the per-dimension marker lexicons broad for Amber to curate, wire into `rubric.yaml` + `prompt.py`, log the Contract-3 prompt change, re-run to measure the delta.
- **Golden-set coverage caveat:** extremes are thin — only **3 Ultra-processed** and **8 Clean** rows (29 Mostly Clean). If tuning signal is weak at the ends, Amber may queue a few more clearly-clean / clearly-ultra-processed recipes via the console. Also: per-band n is small, so per-band accuracy swings are noisy.
- **Env pin (pitfall):** `pyproject.toml` pins `pyarrow==21.0.0` + `pandas==2.3.3`. Re-run `pip install -e ".[dev]"` on stale venvs.
- **Untracked, still Amber's call:** `.claude/` and `.agents/` remain untracked — decide whether to gitignore or commit.
- **Deferred (unchanged):** Contract 4's `raw_ingredients` file-path option; per-component MAE (no per-sub-score golden targets) + automated swap-quality judging remain in Phase 6's later reaches.

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory; roadmap + practices approved. Merged to main.
- **Phase 1 — Scaffold, Schemas & Logging** ✅ (2026-07-10): repo layout; pinned deps; `schema.py` (Verdict/SubScores/Swap); placeholder `rubric.yaml`; `log.py`; 15 tests. Merged to main.
- **Phase 2 — Core Engines** ✅ (2026-07-11): `parse.py` (paste/URL, pinned-IP SSRF guard); provider-neutral `client.py`/`prompt.py`/`score.py` (GLM-4.5-Flash dev default, thinking disabled via `LLM_EXTRA_BODY`, code-composed score+band, retry-once); `evals/evaluate.py` + golden template (band accuracy + score MAE, `--model` bake-off); `cli.py`. 77 tests. Merge gates clean (security-review fixed a DNS-rebinding TOCTOU; code-review fixed a sub-score bounds gap; `/verify` real GLM end-to-end). Amber manually verified. Retro pitfalls logged: GLM unbounded-thinking (disable, don't raise tokens), z.ai base URL, schema range enforcement.
- **Phase 3 — UI & End-to-End** ✅ (2026-07-12): `app.py` Streamlit scorer (thin consumer; paste/link tabs; Verdict card = score + band pill, six weight-ordered bars, flagged list, 3 swaps, disclaimer; friendly error/empty states, never a traceback; untrusted strings md-escaped, `unsafe_allow_html` only for the schema-validated band pill). `streamlit==1.59.1` pinned. Two feedback-driven adds during manual test: (a) direnv `.envrc` so bare `python`/`streamlit` work in-project; (b) two-layer `is_recipe` validation (parse prose-guard + model gate → `NotARecipeError`) after a job posting scored as a recipe. 95 tests. Merge gates: code-review found 4 (stale `_REPAIR_HINT` breaking retry, eval-run abort on new raise, narrowed swaps validation, cli traceback) — all fixed + tested; security-review clean (band-pill HTML takes only validated/code-owned values). Retro pitfall logged: contract changes must ripple to every shape-dependent site. Roadmap gained Phase 7 (explainability/trust). Sub-agent rule added: fan out implementation only for ≥2 independent tracks (architecture 2026-07-12). Merged to main.
- **Phase 4 — Observability & Labeling Console (golden-set builder)** ✅ (2026-07-14, merge `4df5b0c`): `console.py` local-only entrypoint (5 tabs: Backlog / Review & grade / Promote / Logs / Results), built as a **backlog→drafts→grade→promote pipeline** after a v1 "author a row" form flopped in manual testing (author→grade pivot — pitfall logged). `src/clean_recipe/golden.py` is the single source of truth for the Contract-4 row + pipeline shapes (`GoldenRow`/`BacklogEntry`/`GoldenDraft`, append-only writer w/ formula-injection defang, promote). Contract 4 evolved **v0.1→v0.2 (`swap_quality`)→v0.3 (`other_alternatives`/`concerns` + axis doctrine)** from real labeling feedback. Forgiving recipe-text paste (strips site furniture, cuts at Directions) added to the core parser; link fetch (SSRF-guarded) wired into the backlog. Golden creation ran in a **separate Claude instance** via `ai_docs/golden_draft_handoff.md`; finalized here → **52-row golden set** promoted into `golden_set.csv`. Env pin: `pyarrow==21.0.0`/`pandas==2.3.3` (pyarrow-25 `st.dataframe` segfault — pitfall logged). 202 tests. Merge gates: code-review (1 low latent finding — comma-in-alternative round-trip, no data affected), security-review clean (zero `unsafe_allow_html`; CSV defang covers the new column; SSRF guard intact), `/verify` passed on the real 52-row data. Retro pitfalls logged: cross-instance handoff (verify end state), author→grade (validate workflow before building the entry UI). Merged to main.

## Queued next: Phase 5 — Deploy & Harden (deferred behind Phase 6 at Amber's 2026-07-16 call)
Deploy waits until the rubric agrees with Amber's labels (Phase 6) — no point shipping a systematically-lenient scorer. Task skeleton, ready to resume when Phase 6 merges:
- **Phase 5 — Deploy & Harden**: public Streamlit Cloud URL for **`app.py` only** (console.py never exposed — architecture 2026-07-12), secrets via Cloud config (`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`/`LLM_EXTRA_BODY`, never commit `.env`), harden public surface (errors never leak internals; `data/logs` gitignored + ephemeral), `/security-review` + manual test of the shareable link, merge gates. **DoD:** a shareable URL where pasting a recipe returns a sane Verdict card, console unreachable, secrets in Cloud config, security review clean.

Then: **Phase 7 — Verdict explainability & trust** (recipe context + per-ingredient/sub-score rationale; ingredient-table accordion UX from the 2026-07-14 labeling retro) → **Phase 8 — Swap depth / "cleaner spectrum"** (tiered alternatives; brainstorm-gated; the v0.3 `other_alternatives` notes are its first data slice). See `cocoonkitchen_product.md` roadmap.
