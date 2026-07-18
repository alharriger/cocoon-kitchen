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

## Contract 2: rubric.yaml + lexicons.yaml

Machine-readable rubric, split across two files that `prompt.load_rubric()` merges into one flat mapping:

- **`rubric/rubric.yaml`** (hand-edited, comment-rich): `weights`, `bands` (score cutoffs), `aliases`. Weights are **starting hypotheses from the build plan** so the pipeline runs end-to-end; the human finalizes them. File header marked `# PLACEHOLDER — human-owned, do not tune without approval`. Rubric schema **v0.2**.
- **`rubric/lexicons.yaml`** (console-owned, machine-written): the six curated marker lexicons, one per sub-score. Shape + spec list live in `src/clean_recipe/lexicons.py` (`LEXICONS`, `LEXICON_KEYS`, `Tier`). Lexicon schema **v0.3** (tiered lexicons). Two shapes:

| Lexicon key | Grounds sub-score | Shape |
|---|---|---|
| `nova4_markers` | `ultra_processing` | flat — ↓ presence lowers |
| `added_sugar_markers` | `added_sugar` | **tiered 1–5** — score by worst present |
| `fat_quality_markers` | `fat_quality` | **tiered 1–5** — score by worst present |
| `sodium_preservative_markers` | `sodium_preservatives` | **tiered 1–5** — score by worst present |
| `additive_markers` | `additive_count` | flat — ↓ presence lowers |
| `whole_food_whitelist` | `whole_food_ratio` | flat — ↑ presence raises |

**Flat** lexicons are `list[str]`. **Tiered** lexicons (added sugar, fat quality, sodium/preservatives) are a `{level: [markers]}` map over a 1–5 quality ladder (**5 = cleanest, 1 = worst**); each tier carries a target sub-score range (defined in `lexicons.py`, e.g. sugar Tier 1 → `0`), and the model scores the dimension by the **worst (lowest) tier prominently present**. A marker listed in more than one tier resolves to its worst tier (dedup on write).

**Lexicon contents are HUMAN-owned.** Claude drafts broad candidate lists (from public NOVA-4 / additive nomenclature); Amber curates them (cut/keep/add, and for tiered lists moves a marker between tiers) via the Console **Lexicons** tab, whose Save is the only write path (`lexicons.write_lexicons`). Every entry is normalized to a single stripped line (whitespace collapsed) on read and write, so nothing can break the prompt's line structure. The **`whole_food_whitelist`** carries a specific doctrine: *fully natural single-ingredient foods only* — grains/starches count **only** in their explicit whole form (`rolled oats`, `brown rice`, `wheat berries`); processed derivatives (`white bread`, `white flour`) do not belong. The tier target ranges are scoring **anchors in the prompt**, distinct from the human-owned band cutoffs/weights in `rubric.yaml`. `aliases` remains a `rubric.yaml` placeholder (not yet wired into the console).

## Contract 3: Scoring prompt

Built by `prompt.py` from the merged rubric (rubric.yaml + lexicons.yaml) + normalized ingredients. Requirements:
- Recipe text is **untrusted data**, not instructions. The prompt must delimit it clearly and instruct the model to ignore any instructions embedded in recipe content (prompt-injection defense).
- **Grounding lists + calibration rule:** once a lexicon is populated, `_rubric_reference` renders a `GROUNDING LISTS + CALIBRATION RULE` block. It carries: (a) a **decomposition** instruction — break compound/packaged ingredients (e.g. pancake mix) into base components before scoring, so one product drags down several dimensions; (b) **flat-list rules** (markers on `nova4_markers`/`additive_markers` pull their dimension down; `whole_food_whitelist` is a share-based ↑); (c) **tiered-list rules** — for `added_sugar_markers`/`fat_quality_markers`/`sodium_preservative_markers`, score by the worst (lowest) tier present toward that tier's target range (5 = cleanest → 1 = worst, worst tier → 0); and (d) an anti-leniency nudge ("be willing to score in the 20s–40s"). Passive lists alone did **not** move the baseline — the calibration rule + tiers are what force the model off its uniform-high default. This changes what the model returns, so it is a Contract-3 change measured before/after on the golden set. The lists are reference vocabulary, not instructions — the untrusted-recipe delimiting is unchanged.
- Tone guardrail baked in: ingredient-processing **awareness**, never moral judgment or medical advice; non-shaming language in swaps and reasons.
- **Model output shape:** the model returns `is_recipe` (bool) plus, **only when `is_recipe` is true**, `sub_scores` (the six named 0–100 values), `flagged_ingredients`, and `swaps` (target 3) — JSON mode (`response_format=json_object`). Each sub-score is **0–100 where 100 = cleanest/best** on that dimension, so the weighted composite aligns with the band cutoffs. The composite `score` and `band` are **computed in code** (`score.py`) from the rubric weights/cutoffs — the human-owned weights in `rubric.yaml` stay authoritative; the model never does the roll-up arithmetic.
- **Non-recipe handling (`is_recipe` gate):** the model first judges whether the input is genuinely a food recipe. If not (prose, an article, a job posting, a lone stray item, random text), it returns `{"is_recipe": false}` and nothing else; `score.py` raises `NotARecipeError` (a **valid, final** judgment — never retried, never logged as a verdict) and the UI/CLI shows a friendly "that's not a recipe" message. `is_recipe: true` missing any of its scoring fields (`sub_scores`, `flagged_ingredients`, `swaps`) is **malformed** → the normal retry-once-then-fail-loud path (never a silent empty card); the corrective retry hint restates `is_recipe` so a compliant retry doesn't drop it. A cheap structural pre-guard in `parse.py` also rejects pasted prose (any ingredient line > 250 chars) before a model call is spent; the `is_recipe` gate is the semantic backstop for junk that slips past it.
- Model access: **provider-neutral** via an OpenAI-compatible client (`base_url` + `api_key` + `model` = config, not code). **Development default: Zhipu GLM-4.5-Flash on z.ai (always $0, OpenAI-compatible) — build and prove the whole pipeline on it, then run the multi-provider bake-off on the golden set.** Provider/model is chosen by the golden-set eval, **never by brand**; upgrade only if an eval number demands it. Bake-off candidates + full field survey in `architecture.md` 2026-07-11 decision.
- Validate every response against Contract 1 and **retry once** on malformed output (fail loud after) — this keeps cheap/free non-strict models safe.

## Contract 4: Golden-set label format

This is the contract between the human's labeling work and the eval harness. `evals/golden_set.csv` ships with exactly these columns (+ 2–3 example rows) so hand-labeling drops straight in. **Human-owned** — Claude ships the template and samples, never the real labels.

**Format version: v0.3.** The row shape lives in code in `src/clean_recipe/golden.py` (`GOLDEN_COLUMNS` + `GoldenRow`) — the single source of truth imported by both the eval harness (`evals/evaluate.py`) and the labeling console (`console.py`).

| Column | Meaning |
|---|---|
| `recipe_id` | stable short id |
| `source` | URL, or `pasted` |
| `title` | recipe name |
| `raw_ingredients` | ingredient list as-labeled (or a path to a text file) |
| `target_band` | Clean / Mostly Clean / Processed / Ultra-processed |
| `target_score` | rough 0–100 |
| `expected_swaps` | `from>to; from>to` (semicolon-separated) |
| `swap_quality` | human 1–5 grade of the model's swaps for this recipe; blank = not graded (v0.2) |
| `notes` | why / where it's ambiguous |
| `other_alternatives` | flagged items that get **no** swap, each with alternatives to consider (v0.3). Micro-format: `item>why>alt, alt; item2>why2>alt3` — `;` separates concerns, `>` separates the three fields, alternatives are `, `-joined inside the third field. Blank = no such items. |

Where `expected_swaps` records "flagged → do this instead", `other_alternatives` records "flagged, but deliberately **not** swapping it — here's why, and here are options if you want to go further." It is the labeling-time seed of the Phase 8 "cleaner spectrum". In code this is the structured `GoldenRow.concerns` (`list[Concern]`, each `item`/`why`/`alternatives`); the micro-format is only the CSV serialization.

**Swap-reasoning axes (labeling convention, not yet a scoring rule).** Every swap and every listed alternative names *why* it's cleaner along one axis: **less processed** (the primary axis — the score measures processing), **healthier** (nutrition: fat, sodium, sugar — the secondary axis), or **better sourcing** (e.g. block cheese vs. pre-shredded — the tiebreaker). When axes conflict, less-processed leads. This convention keeps the reasoning legible and comparable across rows; it is a drafting/review discipline pending rubric validation in Phase 6, and does **not** edit rubric weights or band cutoffs (those stay human-owned). Concrete preferences captured during labeling (fresh-aisle cheese is fine, no "halve it" swaps, the homemade→veggie→legume pasta ladder, honey as an accepted sweetener) live with the review feedback, not here.

Target 20–50 rows spanning obviously-clean, obviously-ultra-processed, and many ambiguous middles.

**How rows get built (the console pipeline).** Rows are assembled through a three-stage flow — `backlog.jsonl` (recipes Amber queues) → `golden_drafts.jsonl` (a separate Claude instance drafts proposed labels + captures the real model verdict, per `ai_docs/golden_draft_handoff.md`) → `golden_set.csv` (Amber reviews/corrects, then promotes). The intermediate shapes `BacklogEntry` and `GoldenDraft` live in `src/clean_recipe/golden.py`; they are working state, **not** part of this contract — only the `golden_set.csv` columns above are. The human-owned rule holds: drafted labels are proposals Amber confirms/overrides before promotion, and `swap_quality` is always left blank by the drafter (it is Amber's grade to enter).

## Eval harness metrics

`evals/evaluate.py` runs every golden row through `score_recipe`, compares to labels, writes a timestamped results CSV. Minimum metrics:
- **Band accuracy** — % landed in the correct bucket.
- **Score error** — mean absolute error vs. `target_score`.
- **Per-component error** — MAE per sub-score, to localize where it's wrong.
- **Swap quality** — did it catch the flagged swaps? The manual 1–5 column exists as of v0.2 (`swap_quality`, filled via the console); `evaluate.py` reports rows-graded + mean informationally (it grades previously-seen swaps, so it is not a per-model bake-off metric). Graduate to LLM-as-judge later (Phase 6).

## Change control (regression discipline)

- Any change to the prompt, schema, or rubric.yaml → re-run the FULL golden set before merging. A change that fixes three rows and breaks four is a loss.
- Log every contract change here: date, what changed, eval delta (band accuracy + score MAE before/after). Until real labels exist, note "pre-label change" instead of a delta.

### Change log
- 2026-07-17 — Phase 6 Task 3: **Contract 2 rubric v0.1 → v0.3 + Contract 3 grounding/calibration.** Split the marker lexicons out of `rubric.yaml` into a dedicated console-owned `rubric/lexicons.yaml` (shape in `src/clean_recipe/lexicons.py`) with **six per-dimension lexicons** — three flat (`nova4_markers`, `additive_markers` ↓; `whole_food_whitelist` ↑) and **three 1–5 quality ladders** (`added_sugar_markers`, `fat_quality_markers` [renamed from `refined_seed_oils`], `sodium_preservative_markers`), each tier carrying a target sub-score (worst tier → 0). `prompt.load_rubric()` merges the two files; `_rubric_reference` renders a **GROUNDING LISTS + CALIBRATION RULE** block: ingredient **decomposition**, flat ↓/↑ rules, tiered "score by worst tier present" rules, and an anti-leniency nudge. Added a Console **Lexicons** tab (per-tier text areas for tiered lists) so Amber curates the human-owned lists in place (Save = `lexicons.write_lexicons`). Claude seeded **broad** candidates for Amber to cut/re-tier. **Motivation + measured finding:** the baseline showed every model sub-score averaging 69–89 (uniform leniency); passive lists alone did nothing (band acc 32.7%, MAE 17.1 — no better than baseline). Adding the **calibration rule** moved it to **36.5% / MAE 13.5**; adding the **tiers + decomposition** reached **44.2% / MAE 10.65** (uncurated), **40.4% / MAE 10.9** after Amber's sodium curation — vs. baseline ~31–33% / MAE ~14. Tiers (per Amber) grade sweetener/fat/sodium *quality* instead of flat presence. **Residual:** processed dishes still land one band high — traced to `compose_score` being a weighted mean that dilutes single severe offenders; the fix (penalty-sensitive composition) is the next build (architecture 2026-07-18). `aliases` stays a `rubric.yaml` placeholder (deferred).
- 2026-07-14 — Phase 4: **Contract 4 v0.2 → v0.3** — added the `other_alternatives` column (last position) for flagged items that get **no** swap, each with a `why` and a list of alternatives. Backed by a structured `GoldenRow.concerns` (`list[Concern]`) in `golden.py`; the CSV cell uses the `item>why>alt, alt; …` micro-format (`format_concerns`/`parse_concerns`, defanged like `expected_swaps`). Template + one sample row updated (ultra sample shows a TBHQ concern). Also added the **swap-reasoning axes** labeling convention (less-processed / healthier / sourcing) and, as console-internal working state (NOT part of this contract), `GoldenDraft.review` (`ReviewNote`) — a superseded draft + the human's verbatim feedback, so re-drafted rows show a collapsed history block instead of a wall of notes and the original swap grade isn't lost. Motivated by Amber's mid-labeling feedback (2026-07-13/14): swaps needed to state their axis, cover every flagged item or say "no swap", and stop using quantity-reduction swaps. Pre-label — no eval delta.
- 2026-07-09 — v0.1 initial contract, from handoff plan §5. Pre-label.
- 2026-07-10 — Phase 1: `schema.py` transcribes Contract 1 verbatim (no logic). `rubric.yaml` ships documented placeholder weights + **placeholder band cutoffs** (Clean 80–100 / Mostly Clean 60–79 / Processed 40–59 / Ultra-processed 0–39); `nova4_markers`/`refined_seed_oils`/`aliases` left empty for the human. No prompt yet. Pre-label — no eval delta.
- 2026-07-11 — Contract 3: provider strategy set to a **neutral OpenAI-compatible seam, free-tier-first** (Gemini Flash-Lite default, Groq backup), **eval-selected** model; validate-and-retry-once discipline added. Pricing/capabilities verified across OpenAI, Gemini, DeepSeek, Qwen, GLM, Groq, Together, OpenRouter, and Claude (see `architecture.md`). Pre-label — no eval delta.
- 2026-07-11 — Phase 2 build: Contract 3 prompt implemented in `prompt.py`; model returns `sub_scores`/`flagged_ingredients`/`swaps` only (JSON mode), `score.py` composes the composite `score` + `band` from rubric weights/cutoffs (weights authoritative in yaml). Sub-scores defined 0–100 higher=cleaner. Contract 4 harness (`evals/evaluate.py`) implemented with band accuracy + score MAE; per-component MAE + swap-quality deferred (no golden columns yet). Verified end-to-end on GLM-4.5-Flash. Pre-label — no eval delta.
- 2026-07-13 — Phase 4 (post-manual-test): golden rows are now built via a backlog→drafts→promote **pipeline** (console + a separate draft-generating instance, `golden_draft_handoff.md`). Contract 4 columns **unchanged**; the pipeline's `BacklogEntry`/`GoldenDraft` shapes are working state in `golden.py`, not contract. Pre-label — no eval delta.
- 2026-07-12 — Phase 4: **Contract 4 v0.1 → v0.2** — added optional `swap_quality` column (human 1–5 grade of the model's swaps; blank = not graded), positioned between `expected_swaps` and `notes`. Row shape extracted to `src/clean_recipe/golden.py` (single source of truth for harness + labeling console); `evaluate.py` imports it and reports swap-quality informationally. Template + sample rows updated (one sample shows a grade). The console requires the grade in label-from-log mode (model swaps are on screen) and leaves it optional in author mode — a UI rule, not a contract rule. Pre-label — no eval delta.
- 2026-07-12 — Phase 3 (during manual test): added the **`is_recipe` gate** to Contract 3. Model now returns `is_recipe` first and only scores real recipes; non-recipe input (job posting, prose, stray item) returns `{"is_recipe": false}` → `score.py` raises `NotARecipeError` (final, not retried/logged). Prompt updated (`prompt.py`), `ModelOutput` gained `is_recipe` + optional scoring fields with a validator that fails loud when a recipe omits sub-scores. Cheap parse-layer prose guard added (`parse.py`, >250-char line). Verdict schema (Contract 1) **unchanged** — a non-recipe never produces a Verdict. Motivated by a real false-positive: a job-posting blob with one "turkey sausage" line scored as a recipe. Pre-label — no eval delta (revisit against the golden set for is_recipe false-positive/negative rate once labels land).
