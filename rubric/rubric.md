# Rubric — Human-Readable (HUMAN-OWNED)

> **PLACEHOLDER.** This document and `rubric.yaml` are human-owned. Claude ships
> structure plus the documented placeholder weights only — it does **not** tune
> weights, band cutoffs, or marker/alias lists without Amber's approval.
>
> Machine contract source of truth: `ai_docs/llm_contracts.md` Contract 2.

## Sub-scores and weights (placeholder)

Each sub-score is 0–100. The composite is a weighted sum; weights **must sum to 1.0**.

| Sub-score | Weight | Meaning |
|---|---|---|
| `ultra_processing` | 0.30 | degree of ultra-processing (NOVA-4 style) |
| `added_sugar` | 0.20 | added/free sugars |
| `fat_quality` | 0.15 | fat quality (whole vs refined/industrial) |
| `sodium_preservatives` | 0.15 | sodium + chemical preservatives |
| `whole_food_ratio` | 0.15 | share of whole-food ingredients |
| `additive_count` | 0.05 | count of additives (colors, emulsifiers, etc.) |

## Bands (placeholder cutoffs)

| Band | Score range |
|---|---|
| Clean | 80–100 |
| Mostly Clean | 60–79 |
| Processed | 40–59 |
| Ultra-processed | 0–39 |

## Composition — how sub-scores combine (human-owned)

The composite is **not** a pure weighted mean. A weighted mean is a convex
combination bounded between the min and max sub-score, so a single severe
offender on a low-weight axis (e.g. an artificial flavor, which only touches
`additive_count` at weight 0.05) gets averaged away and can't drop the band. To
honor "one bad ingredient should visibly tank the score," the composite blends
the weighted mean with the single **worst** sub-score:

```
composite = round( (1 - alpha) * weighted_mean + alpha * min(sub_scores) )
```

| Knob | Value | Meaning |
|---|---|---|
| `composition.alpha` | **0.4** | weight on the worst axis. `0` = pure weighted mean (old behavior); `1` = score is the single worst axis. |

`alpha` is deliberately **weight-independent** (it acts on `min()`, not through
the weights) because the worst offender is often the lowest-weight dimension.
Chosen `alpha=0.4` (Amber, 2026-07-18): the smallest value that pulls a single
severe offender out of the Clean band while leaving genuinely-clean and
uniformly-mid recipes essentially unchanged (a spike detector — it only moves a
band when `mean − min` is large). `alpha` is clamped to [0, 1] in code.

## Marker lexicons (human-owned, curated in the console)

As of v0.3 the marker lists live in a separate **`rubric/lexicons.yaml`** (this
keeps the delicate weights/bands here hand-edited, while the console rewrites the
lists freely). `prompt.load_rubric()` merges the two files. There are six lists,
one per sub-score — three **flat** and three graded into **1–5 quality tiers**:

| Lexicon | Grounds | Shape |
|---|---|---|
| `nova4_markers` | `ultra_processing` | flat — a match pulls it down |
| `added_sugar_markers` | `added_sugar` | **tiered 1–5** (5 best sweetener → 1 worst) |
| `fat_quality_markers` | `fat_quality` | **tiered 1–5** (5 best fat → 1 worst) |
| `sodium_preservative_markers` | `sodium_preservatives` | **tiered 1–5** (5 natural salt → 1 chemical preservative) |
| `additive_markers` | `additive_count` | flat — a match pulls it down |
| `whole_food_whitelist` | `whole_food_ratio` | flat — a match pushes it up |

**Tiers** grade *which* ingredient it is, not just presence: honey (good) vs. HFCS
(worst) for sugar; olive oil vs. hydrogenated for fat; natural salt (fine) vs.
nitrites for sodium. The model scores the dimension by the **worst tier present**;
each tier has a target sub-score (worst tier → 0). The scorer prompt also
**decomposes** compound products (e.g. pancake mix → flour + sugar + seed oil +
additives) so one packaged item drags several dimensions down.

**How they're curated:** Claude drafts **broad** candidate lists from public
nomenclature; Amber cuts/keeps/adds them — and re-tiers where she disagrees — in
the Console **Lexicons** tab (Save writes `lexicons.yaml`). The contents are
human-owned — Claude never finalizes a list.

**`whole_food_whitelist` doctrine:** fully natural, single-ingredient foods only —
think outside the grocery store. Grains and starches count **only** in their
explicit whole form (`rolled oats`, `brown rice`, `wheat berries`); processed
derivatives (`white bread`, `white flour`, `white rice`) do **not** go on the list.

`aliases` (ingredient alias → canonical name) stays an empty placeholder in
`rubric.yaml` for now — not yet wired into the console.
