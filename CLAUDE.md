# CocoonKitchen

LLM-powered recipe "clean eating" scorer. Paste a recipe or link → get a 0–100 score, band, flagged ingredients, and 3 swaps. Streamlit UI + eval harness, both importing one pure core: `score_recipe(title, ingredients) -> Verdict`.

## Read first, every session
1. `ai_docs/working_sprint.md` — current phase, task status, handoff notes. **Always start here.**
2. `ai_docs/pitfalls.md` — logged mistakes. Don't repeat one.

## Reference docs (read when relevant, keep them the source of truth)
- `ai_docs/architecture.md` — architecture decisions + decision log
- `ai_docs/llm_contracts.md` — Verdict schema, prompt, rubric contracts (source of truth for all LLM I/O)
- `ai_docs/cocoonkitchen_product.md` — strategy, roadmap, user stories (the PRD)
- `ai_docs/design_system.md` — UI/design system + tone rules

## Non-negotiables
- **Loop:** Plan → user approval → implement + tests → pause for manual test → fix → commit/push → retrospective. No code before explicit approval.
- All new work on a branch; merge to main only after tested + documented.
- Security audit is part of every plan, not an afterthought.
- No new layer (DB, RAG, auth, vector store) unless an eval number demands it.
- Rubric weights and golden-set labels are **human-owned**. Never invent or edit them.
- Keep docs in sync: any change updates the ai_doc(s) it touches in the same unit of work — updating docs is part of "done."
- This file stays light. New knowledge goes in the right ai_doc; add a pointer here only if it's needed every session.
