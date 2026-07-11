# Working Sprint — LIVE DOCUMENT

> This file tracks the **current phase only**. It is the handoff artifact between Claude sessions:
> update task status as work happens, log decisions and blockers immediately, and when the phase
> completes (retro done, merged to main), **refresh this file** for the next phase.

---

## Current phase: Phase 2 — Core Engines (parallel)

**Goal:** Build the three independent core tracks and integrate them so `score_recipe(title, ingredients) -> Verdict` runs end-to-end on real pasted recipes, with the eval harness able to run on sample rows.

**Branch:** create `phase-2/core-engines` off `main` (Phase 1 is merged to main).

**⚠️ First task is to PLAN, not code.** Per our working loop, write the detailed Phase 2 plan (files, tests, security notes, how the three tracks integrate) and get Amber's explicit approval BEFORE writing any code. Read `CLAUDE.md`, this file, then `ai_docs/pitfalls.md`. Contracts live in `ai_docs/llm_contracts.md` (schema/prompt/rubric); architecture + sub-agent build model in `ai_docs/architecture.md`.

### The three tracks (built independently, then integrated)
1. **`parse.py`** — recipe-scrapers path + wild-mode fallback + paste path → normalized ingredient list.
2. **`prompt.py` + `score.py::score_recipe()`** — build prompt from `rubric/rubric.yaml`, call model (cheap tier), validate output against `schema.py` (fail loudly), wire in `log.py`.
3. **`evals/evaluate.py` skeleton + `golden_set.csv` template** — runner + metrics scaffold; sample rows only (labels are human-owned).

### Tasks
| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Write detailed Phase 2 plan + security audit; get Amber's approval | ✅ Done | Approved as-is 2026-07-11; build style: B first, then A+C parallel |
| 2 | Track A — `parse.py` + tests | ✅ Done | paste + known-site + wild fallback; SSRF-guarded fetch (pinned IP); 22 tests |
| 3 | Track B — `prompt.py` + `client.py` + `score.py::score_recipe()` + tests | ✅ Done | provider seam; model returns sub_scores/flagged/swaps, code composes score+band; retry-once; 21 tests |
| 4 | Track C — `evals/evaluate.py` + `golden_set.csv` template + tests | ✅ Done | band accuracy + score MAE; `--model` bake-off flag; 3 SAMPLE rows; 11 tests |
| 5 | Integrate tracks on the branch; end-to-end smoke on real pasted recipes | ✅ Done | `cli.py` routes parse→score; verified on GLM (Verdict returned, logged) |
| 6 | Pause for Amber's manual test (with a concrete test script) | ✅ Done | Amber satisfied 2026-07-11. Surfaced a real bug (empty content — GLM unbounded thinking); fixed via LLM_EXTRA_BODY thinking-off |
| 7 | Merge gates: `/verify` + code-review sub-agent + `/security-review`; commit + merge to main | 🟡 In progress | `/security-review` done (TOCTOU fixed). `/verify` + code-review + merge underway |
| 8 | Phase 2 retrospective → log pitfalls → refresh this doc for Phase 3 | ⬜ Not started | |

### Definition of done (Phase 2)
`score_recipe()` returns schema-valid Verdicts on real pasted recipes; `parse.py` handles link + wild + paste inputs; `evals/evaluate.py` runs on the sample golden rows and emits metrics; every input+verdict is logged via `log.py`; unit tests green; docs in sync; merged to main. (Model calls need the provider key in `.env` — dev default a free **z.ai / GLM-4.5-Flash** key, no card. `.env.example` already ships the neutral `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` scheme.)

### Decisions carried in
- `score_recipe()` stays pure/UI-agnostic in `src/clean_recipe/`; never imports Streamlit (architecture.md load-bearing rule).
- **LLM provider is neutral/config-driven** (see architecture.md 2026-07-11 decision): **development default Zhipu GLM-4.5-Flash on z.ai (always free)** — build and test the whole system on it first; the bargain-model bake-off (Gemini/Groq/DeepSeek/Qwen/…) runs on the golden set later, model chosen by the eval, not brand. Track B builds `score_recipe` behind an **OpenAI-compatible client seam** (`base_url`+`api_key`+`model` from config) + **validate-and-retry-once** on malformed output. Track C's eval harness should be able to compare providers on the golden set.
- New deps arrive only as their track needs them: an **OpenAI-compatible client (`openai`, used with per-provider `base_url`)** for Track B, `recipe-scrapers` for Track A (anti-bloat; pin exact versions, log in architecture.md).
- Rubric weights + golden labels are human-owned placeholders; do NOT invent or edit them. Track C ships a template + sample rows only.
- Malformed model output must fail loudly (ValidationError), never coerce (retry once, then fail loud).

### Environment reminders (from Phase 1 pitfalls)
- Import name is `clean_recipe`, NOT `cocoonkitchen` (that's only the pip name).
- Run Python via `.venv/bin/python` (e.g. `.venv/bin/python -m pytest`); bare `python` isn't on PATH.

### Blockers
- Model calls require the provider key in a `.env` (dev default: a **free z.ai / GLM-4.5-Flash key**, no card — sign up at z.ai, Profile → API Keys). Amber to create it. Real golden labels are not needed until Phase 5 — samples suffice for the harness skeleton.

### Handoff notes for next session
- Phase 1 (scaffold, Verdict schema, placeholder rubric, JSONL logging, 15 tests) is merged to main and approved.
- Everything Phase 2 needs is documented: schema/prompt/rubric contracts in `llm_contracts.md`, core shape + sub-agent build model in `architecture.md`.
- Start by drafting the Phase 2 plan and presenting it for approval. Consider the parallel-worktree sub-agent model (architecture.md) for the three tracks.

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory (working-agreements, quality-practices, doc-system w/ doc-sync rule); roadmap + six practices approved by Amber. Merged to main.
- **Phase 1 — Scaffold, Schemas & Logging** ✅ (2026-07-10): repo layout; pinned phase-scoped deps (pydantic/pyyaml/pytest, Python 3.12); `schema.py` (Verdict/SubScores/Swap, verbatim from Contract 1); placeholder `rubric.yaml`/`rubric.md` (human-owned); append-only `log.py`; 15 unit tests. Merge gates clean (security-review + code-review). Merged to main. Retro pitfalls logged: package-vs-import name split, run Python via venv.
