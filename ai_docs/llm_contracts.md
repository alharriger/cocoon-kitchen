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
- Model tier: cheapest capable tier (start with Haiku-class); upgrade only if evals demand it.

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
