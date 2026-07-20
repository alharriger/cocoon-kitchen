# cocoonkitchen

A webapp that turns your existing recipe into a clean eating alternative without sacrificing flavor.

LLM-powered recipe "clean eating" scorer. Paste a recipe or link → get a 0–100
score, band, flagged ingredients, and 3 swaps. Streamlit UI + eval harness, both
importing one pure core: `score_recipe(title, ingredients) -> Verdict`.

## Status
Phase 6 — real evals & tuning: the scorer UI (Phase 3) + labeling console (Phase 4) sit on a 52-row golden set with a tuned rubric (tiered lexicons, penalty-sensitive composite), a cross-provider bake-off, and regression tracking (tracked run log + baseline). Not deployed yet — Phase 5 (deploy & harden) is queued behind Phase 6. See `ai_docs/working_sprint.md` for live status.

## Layout
- `app.py` — Streamlit UI (thin consumer of the core)
- `console.py` — golden-set builder console (`streamlit run console.py`, **local only — never deploy**): queue recipes → draft (via `ai_docs/golden_draft_handoff.md`) → grade → promote to `golden_set.csv`
- `src/clean_recipe/` — pure, UI-agnostic core (`parse.py`, `score.py`, `schema.py`, `log.py`, …)
- `rubric/` — `rubric.yaml` (machine) + `rubric.md` (human). **Human-owned; placeholder weights.**
- `evals/` — golden set (`golden_set.csv`), eval harness (`evaluate.py` + `providers.py`), and regression tracking (`runlog.py` → tracked `run_log.csv` + `baseline.json`)
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
