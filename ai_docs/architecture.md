# Architecture

Source of truth for architecture decisions. Every significant decision gets a log entry (date, decision, why, revisit-when). Keep entries short; this is a decision record, not a tutorial.

## Core shape (v0)

```
recipe link / pasted text
   → parse.py (recipe-scrapers + wild-mode fallback + paste path)
   → normalize ingredients
   → score.py: score_recipe(title, ingredients) -> Verdict
        ├─ builds prompt from rubric/rubric.yaml (prompt.py)
        ├─ calls model (cheap tier)
        └─ validates JSON against schema.py — fail loudly on malformed output
   → consumed by BOTH app.py (Streamlit card) and evals/evaluate.py (harness)
   → log.py appends every input + verdict to JSONL
```

**The load-bearing rule:** `score_recipe()` is a pure, UI-agnostic function in `src/clean_recipe/`. It never imports Streamlit. The UI and the eval harness are both thin consumers. This is what makes the stack swappable later (FastAPI/Next.js) without moving the brains.

## Repo layout (target, from handoff plan §4)

```
cleanplate/
├── CLAUDE.md, README.md, pyproject.toml, .env.example, .gitignore
├── ai_docs/                  # this documentation system
├── rubric/
│   ├── rubric.md             # human-readable (HUMAN-OWNED)
│   └── rubric.yaml           # machine-readable weights/bands/lists (placeholder until human finalizes)
├── src/clean_recipe/
│   ├── schema.py  parse.py  prompt.py  score.py  log.py
├── app.py                    # Streamlit UI
├── evals/
│   ├── golden_set.csv        # HUMAN-OWNED labels; template + sample rows only
│   ├── evaluate.py           # runner + metrics → results/
└── data/logs/                # runtime JSONL (gitignored)
```

## Decision log

### 2026-07-09 — Streamlit for v0, FastAPI as upgrade path
Pure-Python end-to-end (recipe-scrapers is Python-only), free one-push deploy, card UI is Streamlit's sweet spot. Low UI ceiling accepted for a demo. **Revisit when:** UI needs exceed a card, or a customer needs an API.

### 2026-07-09 — No DB, no RAG, no auth, no vector store in v0
JSONL log is the only persistence. Each layer must later earn its place by moving an eval number. **Revisit when:** an eval number demands it.

### 2026-07-09 — Weights live in rubric.yaml, never in code
Tuning the rubric must never touch Python. Prompt is built from the yaml at runtime.

### 2026-07-09 — Docs system
CLAUDE.md = pointers only. ai_docs/ = source of truth per domain. working_sprint.md = live phase tracker / session handoff. Memory files = cross-session working practices only.

## Sub-agent usage model
- **Research/recon:** Explore or code-explorer agents — keep file-dumps out of the main context.
- **Phase planning:** Plan / code-architect agent produces the blueprint; main session edits + presents for approval.
- **Parallel build (Phase 2):** independent tracks (parser / scoring core / eval harness) as parallel agents in isolated worktrees, integrated on one branch afterward.
- **Quality gates:** code-reviewer agent + /security-review before any merge to main; /verify (end-to-end) before commit.
