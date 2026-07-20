# Working Sprint — LIVE DOCUMENT

> This file tracks the **current phase only**. It is the handoff artifact between Claude sessions:
> update task status as work happens, log decisions and blockers immediately, and when the phase
> completes (retro done, merged to main), **refresh this file** for the next phase.

---

## Current phase: Safety & Ethics program — Task 1: Safety eval foundation (NOT STARTED)

> **Phase 6 (Real evals & tuning) closed + merged to main 2026-07-20.** Its charter — a rubric that
> *agrees with Amber's labels* on the 52-row golden set — is met (band ~57–59% / MAE ~7.1–7.3 /
> Processed 7/12, up from ~31% / ~14). See "Completed phases" for the summary.
>
> The **next body of work** is the Safety & Ethics program, opened after the 2026-07-20 Safety & Ethics
> review (`ai_docs/safety.md`). The review surfaced a **harm-class** surface our entire pitfalls catalog
> never named — unsafe swaps (a "cleaner" swap can introduce an allergen / violate a restriction /
> worsen a medical need), medical-claim leakage, dietary-constraint blindness, cuisine bias — and that
> the only *enforced* refusal today is `is_recipe:false`. Task 1 stands up the **measurement** for those
> harms; the fixes come later (see order of operations). **Per the amended Loop, this task plans-and-
> approves in its own instance — being queued here is NOT approval to build.**

**Branch:** open a fresh `safety/eval-foundation` off `main` (Phase 6 is merged).

### Task 1 DoD (Safety eval foundation)
Negative/harm-class eval slices run on the existing golden harness and produce **baseline harm-rate
numbers** (e.g. "unsafe-swap rate 18%", "medical-claim leak 3/40"), reported **separately** from band
accuracy and **kept out of** the tracked run-log/baseline. Detectors unit-tested as code. Human-curated
fixtures (allergen/restriction lexicon, medical-claim bait set, injection payloads) drafted broad by
Claude, curated by Amber. Docs synced (`safety.md` changelog + "Enforced by" column). Merge gates clean.

### Next body of work — "Safety eval foundation" kickoff (for the FRESH instance) — read this first
You are starting the Safety & Ethics program in a fresh Claude instance. **Run the full loop** (plan →
Amber approval → implement + tests → pause for manual test → fix → commit → retro under the adopt-
improvements rule). **Verify on-disk state first** (git log, run the suite). Read `ai_docs/safety.md` in
full before planning; it is the source of truth for the harm register, the refusal policy, and the
human-owned open decisions.

**The task:** stand up **negative / harm-class eval slices** on the existing golden harness
(`evals/evaluate.py` + `golden.py`), so the harm classes in `safety.md` become *measured numbers*, not
prose. The harness measures band accuracy / MAE only; nothing measures harm today. Candidate slices
(confirm scope with Amber in the plan):
- **Unsafe-swap** (H1, highest priority) — does a proposed swap introduce a common allergen or a
  restriction violation? Mostly code-based: a **common-allergen / restriction lexicon** (Claude drafts
  broad, Amber curates — same discipline as the scoring lexicons; a NEW safety lexicon, separate from
  the scoring lexicons, contents human-owned) matched against each swap's `to_ingredient`; report the %
  of swaps that introduce a top allergen without flagging it. No dietary-constraint *input* exists yet,
  so this slice measures *unconditioned* unsafe swaps — the baseline the Phase-13 fix must drive down.
- **Medical-claim** (H2) — a small **bait set** of inputs designed to elicit a health claim + a claim
  detector (keyword + optional LLM-judge) asserting the output never contains a medical/nutrition claim.
  Ties to the refusal policy (`safety.md` §2).
- **Cuisine-bias** (H6) — **cuisine-tag** the golden rows (Claude drafts tags, Amber curates) and report
  per-cuisine band accuracy + mean signed error; flag systematic harshness.
- **Injection red-team** (H7) — golden rows with embedded injection payloads; assert output stays
  schema-valid, the score is not manipulated, and no unsafe swap text survives.

**FIRST DECISIONS (open — resolve with Amber in the plan; human-owned):** (a) which slices this round
(recommend unsafe-swap + medical-claim first — highest harm, least label effort); (b) the
allergen/restriction lexicon contents and what counts as an "unsafe swap"; (c) whether the cuisine-bias
slice is worth the golden-labeling effort now; (d) the pass/fail **harm-rate thresholds** — these gate
deploy.

**What's settled:**
- `ai_docs/safety.md` is the register/source of truth. All 13 pitfalls are quality-class; the only
  enforced refusal today is `is_recipe:false`. These evals *measure* the gap; the *fixes* are later
  items (Phase 13 guardrails, Phase 5 filters) — **build the measurement in this task, not the fixes.**
- Human-owned discipline holds: Claude drafts candidate lexicons/tags/bait-sets broad; Amber curates. Do
  NOT touch rubric weights, `composition.alpha`, or the existing golden labels.
- No new scoring layer. Harm evals are measurement code alongside the existing harness; the
  Verdict/Contract shape does not change for this task (the fixes will change contracts later — log then).

**Blast radius (walk it in one unit of work — 2026-07-12 pitfall):**
- `evals/` — new harm-eval module(s)/slices; report harm rates alongside band accuracy, clearly labeled.
  **Keep harm slices OUT of the band-accuracy / regression numbers and the tracked run-log baseline**
  (`evals/baseline.json`, `evals/run_log.csv`) — a separate report, so harm measurement never corrupts
  the rubric-quality signal.
- New fixtures — the allergen/restriction lexicon + medical-claim bait set + injection payloads
  (human-curated contents; draft broad).
- `tests/` — unit-test the detectors (allergen match, claim detector) as code, not only via eval runs.
- Golden data — cuisine tags, if in scope, are a human-curated column; follow the Contract-4 /
  `golden.py` append discipline and verify the promote step (2026-07-14 pitfall).
- Docs — `safety.md` changelog + its refusal-policy "Enforced by" column updated as slices land;
  `llm_contracts.md` only if a contract actually changes (it should not for measurement).

**Measurement discipline:** these slices produce **harm-rate** numbers, not band accuracy — establish
and record the **baseline harm numbers**; they gate the deploy (#3) and guardrail (#2) decisions.

**Environment:** import name `clean_recipe`; run Python via `.venv/bin/python`; model calls need `.env`
(z.ai GLM key + `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}`); harness heartbeat = working, not
hung. **Subagents must NOT run live model calls** (2026-07-20 pitfall) — inspect code / run pytest only.

## Order of operations from here (Safety & Ethics program → existing roadmap)

Set 2026-07-20 after the Safety & Ethics review (`ai_docs/safety.md`); Phase 6 now closed. **Per the
amended Loop, each item plans-and-approves in its own instance; being queued here is NOT approval to
build.** Full register + SHIR sizing + human-owned open decisions: `ai_docs/safety.md`; roadmap rows:
`cocoonkitchen_product.md` "Safety & Ethics roadmap additions". This is Claude's proposed order — Amber
curates it.

**1. Safety eval foundation** *(the current task — kickoff above)*. Build negative/harm eval slices on
the golden harness; their numbers gate everything downstream. Maps to product roadmap "Phase 6 (amend)".

**2. Safe swaps & dietary-constraint policy** *(product Phase 13 — harm-class)*. The fix for the top harm
(H1/H3): a dietary-constraint channel, allergen-aware swaps, and a safe-failure path when no clean *and*
safe swap exists — relaxing the exactly-3 cardinality, which is why parked Phase 12 folds in here.
Scoping session first (`safety.md` §3). **Sequencing decision (Amber owns):** if #1 shows a high
unsafe-swap rate, this precedes public deploy; if a strong disclaimer + allergen caveat is judged
sufficient interim mitigation, deploy may precede it with documented residual risk.

**3. Deploy & Harden + safety hardening** *(product Phase 5 + amendments)*. The Phase-5 deploy skeleton
(preserved below), now bundling: disclaimer/scope **always** renders (Air Canada framing), a
**medical-claim output filter** (H2), **prompt-injection hardening** (H7), and a shipped
**`SAFETY.md` / model card** (H9). Gated on #1's numbers.

**4. Then existing roadmap:** **Phase 7 — Explainability & trust** (also folds in provenance disclosure +
uncertainty signaling to counter overtrust, H8) → **Phase 14 — Disordered-eating guardrail** (H5; can
move earlier if Amber prefers) → **Phase 8 — Swap depth / "cleaner spectrum"** → Phase 9+ (deferred).

### Phase 5 (item 3) — Deploy & Harden skeleton (preserved; safety amendments in #3 above)
Deploy waited until the rubric agrees with Amber's labels (Phase 6, done). Task skeleton, ready to
resume in sequence:
- **Phase 5 — Deploy & Harden**: public Streamlit Cloud URL for **`app.py` only** (console.py never
  exposed — architecture 2026-07-12), secrets via Cloud config (`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`/
  `LLM_EXTRA_BODY`, never commit `.env`), harden public surface (errors never leak internals; `data/logs`
  gitignored + ephemeral), `/security-review` + manual test of the shareable link, merge gates. **DoD:**
  a shareable URL where pasting a recipe returns a sane Verdict card, console unreachable, secrets in
  Cloud config, security review clean. **Safety amendments (2026-07-20):** disclaimer always renders,
  medical-claim output filter, prompt-injection hardening, shipped model card — see order-of-operations #3.

### Decisions carried in (still live)
- **Golden labels + rubric weights + marker-list contents are human-owned** (CLAUDE.md). Claude may
  *draft* candidate lexicons/lists/tags; Amber curates the final content.
- **Model/provider is eval-selected, never by brand** (architecture 2026-07-11). Dev/prod default stays
  **GLM-4.5-Flash** (Task-4 decision, 2026-07-19); re-run `evaluate.py --openrouter` at periodic
  check-ins to re-bake. Do NOT switch the default without Amber. ~$0.36/full pass — real money.
- **Composite is code-computed from human-owned knobs** (architecture 2026-07-11); `composition.alpha`
  (=0.4) lives in `rubric.yaml`. Do NOT reopen the penalty-sensitive-composite decision (Task 3.5).
- **Marker lists = curated in-prompt lexicon, NOT RAG** (architecture 2026-07-17). External
  nutrition-DB/product lookup is **deferred + eval-gated** (product roadmap Phase 9 — not approved).
- **Eval noise floor:** even at `temperature=0`, identical runs move ~2pp band accuracy / ~1 MAE. Treat
  sub-threshold swings as noise; average over N runs if needed. Encoded in `runlog.compare_to_baseline`.
- **Regression baseline (2026-07-20, GLM, rubric hash `57677e105c`):** band 58.8% / MAE 7.12 /
  Processed 7/12 on 51/52 (`evals/baseline.json`). Updated only via explicit `--update-baseline`
  (full-set, single-model, ≥90% coverage). Phase-7's merge gate can use `evaluate.py --fail-on-regression`.
- **Contract 4 is at v0.3**; shape lives in `src/clean_recipe/golden.py`, imported by both `evaluate.py`
  and `console.py`. **Contract 2 is at v0.3** (tiered lexicons + `composition.alpha`).

### Environment reminders (from pitfalls)
- Import name is `clean_recipe`, NOT `cocoonkitchen`.
- Interactive terminal auto-activates `.venv` via direnv; **agent tool calls / scripts are
  non-interactive — use `.venv/bin/python`** (e.g. `.venv/bin/python -m pytest`).
- Run the eval: `.venv/bin/python evals/evaluate.py` (add `--limit N` for a quick slice; the progress
  heartbeat shows it's working, not hung — each row is a real ~2–4s model call). **A full-set run
  auto-appends a row to the TRACKED `evals/run_log.csv`** — inspect `git status` after any run.
- Model calls need `.env` (z.ai GLM key + `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}`).
- When changing the model-I/O contract, walk the full blast radius (prompt + `_REPAIR_HINT` + all
  callers' `except` + validators) — see 2026-07-12 pitfall.
- After editing an imported module used by a running `streamlit run` server, **fully restart** it
  (2026-07-18 pitfall) — a browser refresh serves the stale module.
- Env pin: `pyproject.toml` pins `pyarrow==21.0.0` + `pandas==2.3.3`. Re-run `pip install -e ".[dev]"`
  on stale venvs.

### Golden-set coverage caveat (carried)
Extremes are thin — only **3 Ultra-processed** and **8 Clean** rows (29 Mostly Clean). Per-band n is
small, so per-band accuracy swings are noisy. If tuning/harm signal is weak at the ends, Amber may queue
a few more clearly-clean / clearly-ultra-processed recipes via the console.

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory; roadmap + practices approved. Merged to main.
- **Phase 1 — Scaffold, Schemas & Logging** ✅ (2026-07-10): repo layout; pinned deps; `schema.py` (Verdict/SubScores/Swap); placeholder `rubric.yaml`; `log.py`; 15 tests. Merged to main.
- **Phase 2 — Core Engines** ✅ (2026-07-11): `parse.py` (paste/URL, pinned-IP SSRF guard); provider-neutral `client.py`/`prompt.py`/`score.py` (GLM-4.5-Flash dev default, thinking disabled via `LLM_EXTRA_BODY`, code-composed score+band, retry-once); `evals/evaluate.py` + golden template (band accuracy + score MAE, `--model` bake-off); `cli.py`. 77 tests. Merge gates clean (security-review fixed a DNS-rebinding TOCTOU; code-review fixed a sub-score bounds gap; `/verify` real GLM end-to-end). Amber manually verified. Retro pitfalls logged: GLM unbounded-thinking (disable, don't raise tokens), z.ai base URL, schema range enforcement.
- **Phase 3 — UI & End-to-End** ✅ (2026-07-12): `app.py` Streamlit scorer (thin consumer; paste/link tabs; Verdict card = score + band pill, six weight-ordered bars, flagged list, 3 swaps, disclaimer; friendly error/empty states, never a traceback; untrusted strings md-escaped, `unsafe_allow_html` only for the schema-validated band pill). `streamlit==1.59.1` pinned. Two feedback-driven adds during manual test: (a) direnv `.envrc` so bare `python`/`streamlit` work in-project; (b) two-layer `is_recipe` validation (parse prose-guard + model gate → `NotARecipeError`) after a job posting scored as a recipe. 95 tests. Merge gates: code-review found 4 (stale `_REPAIR_HINT` breaking retry, eval-run abort on new raise, narrowed swaps validation, cli traceback) — all fixed + tested; security-review clean (band-pill HTML takes only validated/code-owned values). Retro pitfall logged: contract changes must ripple to every shape-dependent site. Roadmap gained Phase 7 (explainability/trust). Sub-agent rule added: fan out implementation only for ≥2 independent tracks (architecture 2026-07-12). Merged to main.
- **Phase 4 — Observability & Labeling Console (golden-set builder)** ✅ (2026-07-14, merge `4df5b0c`): `console.py` local-only entrypoint (5 tabs: Backlog / Review & grade / Promote / Logs / Results), built as a **backlog→drafts→grade→promote pipeline** after a v1 "author a row" form flopped in manual testing (author→grade pivot — pitfall logged). `src/clean_recipe/golden.py` is the single source of truth for the Contract-4 row + pipeline shapes (`GoldenRow`/`BacklogEntry`/`GoldenDraft`, append-only writer w/ formula-injection defang, promote). Contract 4 evolved **v0.1→v0.2 (`swap_quality`)→v0.3 (`other_alternatives`/`concerns` + axis doctrine)** from real labeling feedback. Forgiving recipe-text paste (strips site furniture, cuts at Directions) added to the core parser; link fetch (SSRF-guarded) wired into the backlog. Golden creation ran in a **separate Claude instance** via `ai_docs/golden_draft_handoff.md`; finalized here → **52-row golden set** promoted into `golden_set.csv`. Env pin: `pyarrow==21.0.0`/`pandas==2.3.3` (pyarrow-25 `st.dataframe` segfault — pitfall logged). 202 tests. Merge gates: code-review (1 low latent finding), security-review clean, `/verify` passed on the real 52-row data. Retro pitfalls logged: cross-instance handoff (verify end state), author→grade (validate workflow before building the entry UI). Merged to main.
- **Phase 6 — Real evals & tuning** ✅ (2026-07-20): the placeholder rubric was systematically **too lenient** (~31–33% band accuracy, +13 too-clean skew, 48/52 rows scored cleaner than label). Fixed the rubric *before* deploying. **Task 2** — eval diagnostics / lever-finder (`evaluate.py` prints per-band accuracy, band confusion, mean signed error, `subscore_means`; the key finding: every sub-score dim averaged 69–89, so no weighted mean can land Processed → the lever is the empty marker lists, not the weights). **Task 3** — tiered rubric lexicons + prompt calibration/decomposition: split marker lists into console-owned `rubric/lexicons.yaml` (new `src/clean_recipe/lexicons.py`), 3 flat + 3 tiered (1–5) lexicons, prompt renders a GROUNDING + CALIBRATION block, new Console Lexicons tab; pitfall logged (grounding a cheap model needs a decision RULE, not just data). **Task 3.5** — penalty-sensitive composite (Amber: Option 1 worst-dimension pull, `composition.alpha=0.4` in `rubric.yaml`): band 39.2%→59.6%, MAE 10.96→7.33, Processed 1/12→7/12. **Task 4** — provider-profile registry (`evals/providers.py`) + `--provider/--all-providers/--openrouter` bake-off (preflight, per-row API-error skip, coverage guard, eval-selected pick); `gpt-4o-mini` led (63.5% / 6.77 / 11-12) but Amber **kept `glm-4.5-flash`** (free, close 2nd), re-bake at check-ins; ~$0.36 spent; pitfalls logged (measure real free-tier limits; exclude truncated runs). **Task 5** — tracked run log + explicit regression baseline (`evals/runlog.py`, TRACKED `run_log.csv` + `baseline.json` w/ rubric fingerprint; noise-floor-aware `compare_to_baseline`; `--fail-on-regression` gate); pitfall logged (review subagent ran the live harness → stray tracked row, trimmed). Also this phase: dev-cycle discipline amendments (plan-gate + adopt-improvements retro + doc-freshness sweep, CLAUDE.md non-negotiables) and the Safety & Ethics review (`ai_docs/safety.md` harm register). Ended at band ~57–59% / MAE ~7.1–7.3 / Processed 7/12 (GLM, tuned rubric v0.3). 288 tests. Merge gates: branch-wide code-review (no correctness blockers; 1 low cosmetic console item noted), security-review clean, pre-commit artifact inspection clean. Retro under the adopt-improvements rule: **no new pitfalls** — the two Task-5 process pitfalls' adopted improvements (plan-gate held; subagent-live-harness avoided by inline reviews) were **validated live** this cycle. Contract 2→v0.3, Contract 4 v0.3. Merged to main (`--no-ff`).
