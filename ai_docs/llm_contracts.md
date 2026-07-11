# LLM Contracts — Source of Truth

Every piece of LLM I/O in this project is governed here: output schema, prompt contract, rubric contract, and the change-control rules. If code and this doc disagree, this doc wins and the code is a bug.

## Contract 1: Verdict (structured output)

The model MUST return JSON validating against this Pydantic shape (`src/clean_recipe/schema.py`). Malformed output fails loudly — no silent coercion, no partial cards.

```python
class Swap(BaseModel):
    from_ingredient: str
    to_ingredient: str
    reason: str            # one line

class SubScores(BaseModel):           # all 0–100
    ultra_processing: float           # weight 0.30
    added_sugar: float                # weight 0.20
    fat_quality: float                # weight 0.15
    sodium_preservatives: float       # weight 0.15
    whole_food_ratio: float           # weight 0.15
    additive_count: float             # weight 0.05

class Verdict(BaseModel):
    score: int                        # 0–100 composite
    band: Literal["Clean", "Mostly Clean", "Processed", "Ultra-processed"]
    sub_scores: SubScores
    flagged_ingredients: list[str]
    swaps: list[Swap]                 # target 3
```

**Schema version:** v0.1 (placeholder weights — human-owned, not finalized). Bump the version and log it here on any field change.

## Contract 2: rubric.yaml

Machine-readable rubric: `weights`, `bands` (score cutoffs), `nova4_markers`, `refined_seed_oils`, `aliases`. Weights above are **starting hypotheses from the build plan** so the pipeline runs end-to-end; the human finalizes them. Mark the file header `# PLACEHOLDER — human-owned, do not tune without approval`.

## Contract 3: Scoring prompt

Built by `prompt.py` from rubric.yaml + normalized ingredients. Requirements:
- Recipe text is **untrusted data**, not instructions. The prompt must delimit it clearly and instruct the model to ignore any instructions embedded in recipe content (prompt-injection defense).
- Tone guardrail baked in: ingredient-processing **awareness**, never moral judgment or medical advice; non-shaming language in swaps and reasons.
- Model access: **provider-neutral** via an OpenAI-compatible client (`base_url` + `api_key` + `model` = config, not code). **Development default: Zhipu GLM-4.5-Flash on z.ai (always $0, OpenAI-compatible) — build and prove the whole pipeline on it, then run the multi-provider bake-off on the golden set.** Provider/model is chosen by the golden-set eval, **never by brand**; upgrade only if an eval number demands it. Bake-off candidates + full field survey in `architecture.md` 2026-07-11 decision.
- Validate every response against Contract 1 and **retry once** on malformed output (fail loud after) — this keeps cheap/free non-strict models safe.

## Contract 4: Golden-set label format

This is the contract between the human's labeling work and the eval harness. `evals/golden_set.csv` ships with exactly these columns (+ 2–3 example rows) so hand-labeling drops straight in. **Human-owned** — Claude ships the template and samples, never the real labels.

| Column | Meaning |
|---|---|
| `recipe_id` | stable short id |
| `source` | URL, or `pasted` |
| `title` | recipe name |
| `raw_ingredients` | ingredient list as-labeled (or a path to a text file) |
| `target_band` | Clean / Mostly Clean / Processed / Ultra-processed |
| `target_score` | rough 0–100 |
| `expected_swaps` | `from>to; from>to` (semicolon-separated) |
| `notes` | why / where it's ambiguous |

Target 20–50 rows spanning obviously-clean, obviously-ultra-processed, and many ambiguous middles.

## Eval harness metrics

`evals/evaluate.py` runs every golden row through `score_recipe`, compares to labels, writes a timestamped results CSV. Minimum metrics:
- **Band accuracy** — % landed in the correct bucket.
- **Score error** — mean absolute error vs. `target_score`.
- **Per-component error** — MAE per sub-score, to localize where it's wrong.
- **Swap quality** — did it catch the flagged swaps? Start as a manual 1–5 column the human fills; graduate to LLM-as-judge later.

## Change control (regression discipline)

- Any change to the prompt, schema, or rubric.yaml → re-run the FULL golden set before merging. A change that fixes three rows and breaks four is a loss.
- Log every contract change here: date, what changed, eval delta (band accuracy + score MAE before/after). Until real labels exist, note "pre-label change" instead of a delta.

### Change log
- 2026-07-09 — v0.1 initial contract, from handoff plan §5. Pre-label.
- 2026-07-10 — Phase 1: `schema.py` transcribes Contract 1 verbatim (no logic). `rubric.yaml` ships documented placeholder weights + **placeholder band cutoffs** (Clean 80–100 / Mostly Clean 60–79 / Processed 40–59 / Ultra-processed 0–39); `nova4_markers`/`refined_seed_oils`/`aliases` left empty for the human. No prompt yet. Pre-label — no eval delta.
- 2026-07-11 — Contract 3: provider strategy set to a **neutral OpenAI-compatible seam, free-tier-first** (Gemini Flash-Lite default, Groq backup), **eval-selected** model; validate-and-retry-once discipline added. Pricing/capabilities verified across OpenAI, Gemini, DeepSeek, Qwen, GLM, Groq, Together, OpenRouter, and Claude (see `architecture.md`). Pre-label — no eval delta.
