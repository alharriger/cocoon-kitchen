# CocoonKitchen — Product Document

## Why (the strategy)

Most recipe tools count calories and macros. Almost none answer the question a health-conscious cook actually asks at the moment of choosing: **"how processed is this, really — and what's the one-ingredient fix?"** CocoonKitchen scores a recipe's ingredient quality (ultra-processing, added sugar, fat quality, sodium/preservatives, whole-food ratio, additives), names the offenders, and offers three practical swaps. The stance is a chef's and a physician's at once: food should be delicious first, whole second, and never moralized — we raise awareness of processing, we don't shame plates or give medical advice.

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
| 4 | Observability & Labeling Console (**golden-set builder**) | Lightweight internal front-end, two modes: (a) **author** — paste/enter a recipe, optionally pre-score to pre-fill, then set target_band/target_score/expected_swaps/notes → a Contract-4 golden row (works with zero prior logs); (b) **label-from-log** — browse `data/logs/*.jsonl`, correct/confirm real Verdicts into golden rows + swap-quality grades. Exports to `golden_set.csv`; views `evals/results/`. **This is the tool used to create the golden set.** | The 20–50-row golden set exists (spanning clean / ultra-processed / ambiguous), authored via the console |
| 5 | Deploy & harden | Streamlit Cloud URL, security review, golden_set.csv template shipped | Shareable link works; security review clean |
| 6 | Real evals & tuning (blocked on human golden set) | Human finalizes rubric.yaml weights + the golden set from Phase 4 → tuning loop + bargain-model bake-off across GLM/Gemini/Groq/DeepSeek/Qwen | Band accuracy / MAE targets the human sets |
| 7 | Verdict explainability & trust | Richer output so the cook can trust the score, not just read it: recipe context on the card (title + **full** ingredient list, not only the flagged ones) and **per-ingredient / per-sub-score transparency** — why each ingredient was flagged and how each dimension got its number. Likely a Contract-1/3 change (model returns per-ingredient rationale, possibly a confidence signal) + a design pass. **Deliberately after Phase 6:** explaining and justifying scores is only credible once the rubric is validated — otherwise we're rationalizing numbers we don't yet trust. (Cheapest slice — showing the full ingredient list for context — can be pulled forward as a small UX win before then.) | Card shows recipe context + per-ingredient rationale; cooks report the scoring feels trustworthy/legible; any contract change ships with **no band-accuracy / MAE regression** on the golden set |
| 8 | Swap depth — the "cleaner spectrum" (**brainstorm first**) | Move beyond one swap per offender to a **ranked spectrum of alternatives** per ingredient, each tagged with its trade-off (time, effort, cost, flavor fidelity), so the cook chooses how far to go rather than being handed a single answer. Motivating example: fettuccine alfredo — the pasta itself is the processed offender, and the ladder runs zucchini/vegetable noodles → homemade pasta → non-wheat/legume noodles (higher protein) → refined wheat. The stance stays non-prescriptive: cleaner options cost more time/energy/flavor, and the choice is always the user's. Likely a Contract-1/3 change (swaps become a small ranked list with trade-off metadata) + design + rubric implications. | A dedicated **brainstorming session** defines scope first (this row is a placeholder for that session, not an approved build); then normal plan→build; ships only with **no golden-set regression** |

## User stories

### Functional (v0 — being built)
- As a home cook, I paste recipe text and get a score, band, and flagged ingredients in one card.
- As a home cook, I paste a recipe URL and it parses automatically (paste as fallback when scraping fails).
- As a home cook, I get 3 practical, non-shaming swaps with one-line reasons.
- As the product owner, every scored recipe is logged (input + verdict) so I can audit behavior.
- As the product owner, I can run the eval harness against the golden set and see band accuracy, score MAE, and per-component error.
- As the product owner, I can open an **observability & labeling console** to (a) author golden rows from a recipe directly and (b) correct/label real logged verdicts into golden rows + swap-quality grades, exporting to `golden_set.csv` — this is how I build the 20–50-row golden set the evals need (Phase 4).

### Next up (post-v0, each must earn its place)
- As a home cook, I want to see the whole recipe in context on the card (its title and full ingredient list, not just the flagged items) and understand *why* each ingredient was flagged and how each sub-score was reached — so I can trust the number instead of taking it on faith. (Phase 7 — explainability & trust; depends on a validated rubric from Phase 6.)
- As a home cook, when an ingredient is flagged I want to see a *ladder* of cleaner alternatives — not just one — each with its trade-off (more time, more effort, some flavor change), so I decide how far to go. (Phase 8 — "cleaner spectrum"; needs a brainstorming session to scope before it's built.)
- Rubric tuning loop with regression tracking across prompt versions.
- LLM-as-judge for swap quality (replaces manual 1–5 grading).
- Knowledge base for additive/ingredient facts (CSV/SQLite) — only if eval errors localize to ingredient knowledge.
- Prettier front end (FastAPI/Next.js) — only when someone other than us uses it enough to care.
