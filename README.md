# cocoonkitchen

A webapp that turns your existing recipe into a clean eating alternative without sacrificing flavor.

LLM-powered recipe "clean eating" scorer. Paste a recipe or link → get a 0–100
score, band, flagged ingredients, and 3 swaps. Streamlit UI + eval harness, both
importing one pure core: `score_recipe(title, ingredients) -> Verdict`.

## Status
Phase 1 — scaffold, schemas & logging. No parsing, model calls, or UI yet.

## Layout
- `src/clean_recipe/` — pure, UI-agnostic core (`schema.py`, `log.py`; more in later phases)
- `rubric/` — `rubric.yaml` (machine) + `rubric.md` (human). **Human-owned; placeholder weights.**
- `evals/` — golden set + eval harness (later phases)
- `data/logs/` — runtime JSONL (gitignored)
- `ai_docs/` — the documentation system (start at `working_sprint.md`)

## Develop
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

See `CLAUDE.md` and `ai_docs/` for the working process and contracts.
