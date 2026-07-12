# cocoonkitchen

A webapp that turns your existing recipe into a clean eating alternative without sacrificing flavor.

LLM-powered recipe "clean eating" scorer. Paste a recipe or link → get a 0–100
score, band, flagged ingredients, and 3 swaps. Streamlit UI + eval harness, both
importing one pure core: `score_recipe(title, ingredients) -> Verdict`.

## Status
Phase 4 — observability & labeling console (the golden-set builder) on top of the Phase 3 scorer UI. Not deployed yet.

## Layout
- `app.py` — Streamlit UI (thin consumer of the core)
- `console.py` — internal labeling console (`streamlit run console.py`, **local only — never deploy**)
- `src/clean_recipe/` — pure, UI-agnostic core (`parse.py`, `score.py`, `schema.py`, `log.py`, …)
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

## Run the app
```bash
cp .env.example .env       # add your LLM key (dev default: z.ai GLM-4.5-Flash)
streamlit run app.py       # opens at http://localhost:8501
streamlit run console.py   # internal labeling console (local only)
```

This repo ships a direnv `.envrc` that auto-activates `.venv` when you `cd` in, so
bare `python`, `pytest`, and `streamlit` resolve to the venv. First-time setup:
```bash
brew install direnv                          # once, machine-wide
eval "$(direnv hook bash)"                    # add to ~/.bashrc (zsh: ~/.zshrc)
direnv allow                                  # trust this repo's .envrc, once
```
Without direnv, prefix the venv explicitly: `.venv/bin/streamlit run app.py`,
`.venv/bin/python -m pytest`. (direnv only activates *interactive* shells; scripts
and CI should use the explicit `.venv/bin/...` paths.)

See `CLAUDE.md` and `ai_docs/` for the working process and contracts.
