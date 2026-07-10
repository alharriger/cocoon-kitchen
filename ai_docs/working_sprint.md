# Working Sprint — LIVE DOCUMENT

> This file tracks the **current phase only**. It is the handoff artifact between Claude sessions:
> update task status as work happens, log decisions and blockers immediately, and when the phase
> completes (retro done, merged to main), **refresh this file** for the next phase.

---

## Current phase: Phase 1 — Scaffold, Schemas & Logging

**Goal:** Stand up the repo skeleton that everything else imports: layout, pinned deps, the Verdict schema, a clearly-marked placeholder rubric, and JSONL logging — with unit tests. No parsing, no model calls, no UI yet.

**Branch:** create `phase-1/scaffold` off `main` (Phase 0 is merged to main).

**⚠️ First task is to PLAN, not code.** Per our working loop, write the detailed Phase 1 plan (files, tests, security notes) and get Amber's explicit approval BEFORE writing any code. Read `CLAUDE.md`, then this file, then `ai_docs/pitfalls.md`. The relevant contracts already live in `ai_docs/llm_contracts.md` (schema + rubric) and the layout in `ai_docs/architecture.md`.

### Tasks
| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Write detailed Phase 1 plan + security audit; get Amber's approval | ⬜ Not started | Gate — no code before this |
| 2 | Repo scaffold: layout (`src/clean_recipe/`, `evals/`, `rubric/`, `data/logs/`), `pyproject.toml` w/ pinned deps, `.env.example`, `.gitignore`, README stub | ⬜ Not started | Layout in `architecture.md` §"Repo layout" |
| 3 | `schema.py`: `Verdict`, `SubScores`, `Swap` (Pydantic) | ⬜ Not started | Exact shape in `llm_contracts.md` Contract 1 |
| 4 | `rubric/rubric.yaml` from placeholder weights + `rubric.md` stub | ⬜ Not started | Header must read PLACEHOLDER — human-owned; do NOT tune |
| 5 | `log.py`: append-only JSONL (input + verdict), designed to wire into `score_recipe` in Phase 2 | ⬜ Not started | Logs to `data/logs/` (gitignored) |
| 6 | Unit tests: schema validation (valid + malformed-fails-loudly), rubric.yaml loads + weights sum to 1.0, log round-trip | ⬜ Not started | Testing best practices; tests green before manual test |
| 7 | Pause for Amber's manual test (with a concrete test script) | ⬜ Not started | Loop step 4 |
| 8 | Merge gates: code-review sub-agent + `/security-review`; then commit + merge to main | ⬜ Not started | `/verify` is thin here (no runtime yet) — note that |
| 9 | Phase 1 retrospective → log pitfalls → refresh this doc for Phase 2 | ⬜ Not started | |

### Definition of done (Phase 1)
Repo installs cleanly; `Verdict` validates good JSON and fails loudly on bad; `rubric.yaml` loads with weights summing to 1.0; `log.py` round-trips a record; unit tests green; docs still in sync; merged to main.

### Decisions carried in
- Streamlit v0, pure-Python core, FastAPI later (`architecture.md` decision log).
- No DB/RAG/auth/vector store until an eval number demands it.
- Rubric weights + golden labels are human-owned; Phase 1 ships placeholders only, clearly marked.

### Blockers
- None to start (planning can begin immediately). Real rubric weights + golden labels are only needed at Phase 5.

### Handoff notes for next session
- Phase 0 (working system + docs + memory + roadmap) is complete and approved by Amber; the original handoff document has been fully absorbed into the ai_docs and discarded — do not expect it in the repo.
- Everything Phase 1 needs is already documented: schema/rubric/eval contracts in `llm_contracts.md`, layout + decisions in `architecture.md`, roadmap + non-goals in `cleanplate_product.md`.
- Do NOT invent rubric weights or golden labels. Do NOT add DB/RAG/auth/UI in this phase.
- Start by drafting the Phase 1 plan and presenting it for approval.

---

## Completed phases
- **Phase 0 — Working System & Foundation Docs** ✅ (2026-07-09): light CLAUDE.md; six ai_docs; memory (working-agreements, quality-practices, doc-system w/ doc-sync rule); roadmap + six practices approved by Amber. Merged to main.

## Queued next: Phase 2 — Core Engines (parallel)
Three independent tracks built by parallel sub-agents in isolated worktrees, then integrated: `parse.py` (recipe-scrapers + wild-mode fallback + paste + normalize) · `prompt.py` + `score.py::score_recipe()` · `evals/evaluate.py` skeleton + `golden_set.csv` template. Exit gate: `score_recipe()` returns valid Verdicts on real pasted recipes; harness runs on sample rows.
