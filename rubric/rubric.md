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

## Marker lists (to be populated by human)

- `nova4_markers` — ingredient tokens signaling NOVA group-4 ultra-processing
- `refined_seed_oils` — refined/industrial seed oils
- `aliases` — ingredient alias → canonical name map

These are intentionally empty in v0.1; Claude does not invent their contents.
