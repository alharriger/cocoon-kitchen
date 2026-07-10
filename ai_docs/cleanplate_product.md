# CleanPlate — Product Document

## Why (the strategy)

Most recipe tools count calories and macros. Almost none answer the question a health-conscious cook actually asks at the moment of choosing: **"how processed is this, really — and what's the one-ingredient fix?"** CleanPlate scores a recipe's ingredient quality (ultra-processing, added sugar, fat quality, sodium/preservatives, whole-food ratio, additives), names the offenders, and offers three practical swaps. The stance is a chef's and a physician's at once: food should be delicious first, whole second, and never moralized — we raise awareness of processing, we don't shame plates or give medical advice.

**The real product bet:** the moat is not the UI, it's a scoring rubric that agrees with an expert human. That's why the eval harness and golden set are first-class citizens from day one, and why no feature ships unless an eval number earns it.

## What (v0 scope)

Paste a recipe or a link → get a Verdict card: 0–100 score, band (Clean / Mostly Clean / Processed / Ultra-processed), sub-scores, flagged ingredients, 3 swaps.

**Definition of done for v0:** a shareable Streamlit URL where pasting a recipe returns a sane card; every input/output logged; `evaluate.py` runs cleanly and prints band accuracy + score MAE on sample rows.

## Non-goals / tripwires (do NOT build)
Vector DB, embeddings, RAG, accounts/auth, real database, shopping lists, meal planning, scraper edge-case heroics (paste is the fallback). Each must later earn its place by moving an eval number.

## Roadmap

| Phase | Name | Delivers | Gate to exit |
|-------|------|----------|--------------|
| 0 | Working system | ai_docs, memory, agreements, roadmap | User approves roadmap + Phase 1 plan |
| 1 | Scaffold, schemas & logging | Repo layout, deps, schema.py, placeholder rubric.yaml, log.py, tests | Manual review; unit tests green |
| 2 | Core engines (parallel) | parse.py · prompt.py+score.py · evaluate.py skeleton — built by parallel sub-agents, then integrated | `score_recipe()` returns valid Verdicts on real pasted recipes; harness runs on sample rows |
| 3 | UI & end-to-end | app.py Streamlit card, paste/link toggle, logging wired | User manually tests the full flow locally |
| 4 | Deploy & harden | Streamlit Cloud URL, security review, golden_set.csv template shipped | Shareable link works; security review clean |
| 5 | Real evals (blocked on human) | Human rubric.yaml + 20–50 golden labels → tuning loop | Band accuracy / MAE targets the human sets |

## User stories

### Functional (v0 — being built)
- As a home cook, I paste recipe text and get a score, band, and flagged ingredients in one card.
- As a home cook, I paste a recipe URL and it parses automatically (paste as fallback when scraping fails).
- As a home cook, I get 3 practical, non-shaming swaps with one-line reasons.
- As the product owner, every scored recipe is logged (input + verdict) so I can audit behavior.
- As the product owner, I can run the eval harness against the golden set and see band accuracy, score MAE, and per-component error.

### Next up (post-v0, each must earn its place)
- Rubric tuning loop with regression tracking across prompt versions.
- LLM-as-judge for swap quality (replaces manual 1–5 grading).
- Knowledge base for additive/ingredient facts (CSV/SQLite) — only if eval errors localize to ingredient knowledge.
- Prettier front end (FastAPI/Next.js) — only when someone other than us uses it enough to care.
