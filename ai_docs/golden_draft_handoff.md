# Handoff: generate golden-set drafts from the backlog

**You are a fresh Claude instance. This document is your whole brief — you don't
need the conversation that produced it.** Your job: turn the recipes Amber queued
in the backlog into *draft* golden rows she'll review in the CocoonKitchen
Console. You are the middle stage of a three-stage pipeline:

```
Amber curates        YOU (this task)           Amber reviews & grades
backlog.jsonl   ──►  golden_drafts.jsonl  ──►  golden_set.csv
```

## The one rule that overrides everything

**Golden labels are HUMAN-owned (a CLAUDE.md non-negotiable).** Everything you
write is a *draft* — a starting point Amber will confirm or correct. You are
allowed to *propose* `target_band` / `target_score` / `expected_swaps` / `notes`,
because Amber reviews every row before it becomes a real label. You must **never**:
- edit `rubric/rubric.yaml` weights or band cutoffs,
- write to `evals/golden_set.csv` (that's the promote step, and it's Amber's),
- fabricate the model verdict — you run the **real** scorer and record what it
  actually returned,
- fill in `swap_quality` — that 1–5 grade is Amber's primary feedback lever, so
  leave it blank (`null`).

## Prerequisites

- Work on the `phase-4/console` branch (or wherever the backlog lives), not a
  dirty `main`.
- The scorer needs `.env` (z.ai GLM key + `LLM_EXTRA_BODY={"thinking":{"type":"disabled"}}` —
  see `.env.example`). Confirm it's present before starting.
- Run Python via `.venv/bin/python` (bare `python` isn't on PATH — a logged
  pitfall). The import package is `clean_recipe`, not `cocoonkitchen`.

## Input: `evals/backlog.jsonl`

One JSON object per line (the `clean_recipe.golden.BacklogEntry` shape). Process
only entries with `"status": "submitted"`. Example line:

```json
{"recipe_id": "french-onion-soup", "source": "pasted", "title": "French Onion Soup", "ingredients": ["yellow onions", "butter", "beef broth", "gruyere", "baguette"], "status": "submitted", "added_ts": "2026-07-13T18:00:00+00:00"}
```

Skip entries that already have a draft in `evals/golden_drafts.jsonl` (match on
`recipe_id`) so re-running is safe.

## Task per submitted recipe

1. **Score it for real.** Call `score_recipe(title, ingredients, log=False)` from
   `clean_recipe.score`. `log=False` is required — draft-generation must not
   write to `data/logs/verdicts.jsonl`. If it raises `NotARecipeError` or
   `ScoringError`, skip that recipe and note it in your final summary (don't
   invent a verdict).
2. **Draft the labels**, informed by the model verdict *and* the rubric intent
   (six dimensions, higher = cleaner; bands Clean 80–100 / Mostly Clean 60–79 /
   Processed 40–59 / Ultra-processed 0–39 — placeholder cutoffs in `rubric.yaml`):
   - `target_band`, `target_score`: your best proposal. The model's composite is
     a reasonable prior, but use judgment — you're proposing what a careful human
     *should* land on, not just echoing the model.
   - `expected_swaps`: `from>to; from>to` — the swaps you'd expect a good answer
     to make (may match or improve on the model's).
   - `notes`: one or two lines on *why*, and especially where it's ambiguous —
     this is what makes a golden row useful. Flag genuinely hard calls.
   - `swap_quality`: **leave null.**
3. **Write one draft line** to `evals/golden_drafts.jsonl`.

## Output: `evals/golden_drafts.jsonl` (the `GoldenDraft` shape)

Use the helpers — don't hand-roll the JSON:

```python
from clean_recipe import golden
from clean_recipe.score import NotARecipeError, ScoringError, score_recipe

for entry in golden.read_backlog("evals/backlog.jsonl"):
    if entry.status != "submitted":
        continue
    try:
        verdict = score_recipe(entry.title, entry.ingredients, log=False)
    except (NotARecipeError, ScoringError) as e:
        print(f"skip {entry.recipe_id}: {type(e).__name__}: {e}")
        continue
    draft = golden.GoldenDraft(
        row=golden.GoldenRow(
            recipe_id=entry.recipe_id,
            source=entry.source,
            title=entry.title,
            raw_ingredients=entry.raw_ingredients,      # the "; "-joined cell
            target_band="Processed",                    # ← YOUR proposal
            target_score=52,                            # ← YOUR proposal
            expected_swaps="beef broth>low-sodium broth",  # ← YOUR proposal
            swap_quality=None,                          # ← always null; Amber's
            notes="Cheese + baguette pull this down; broth sodium is the main knob.",
        ),
        model_verdict=verdict,                          # the REAL model output
        status="draft",
    )
    golden.append_draft(draft, "evals/golden_drafts.jsonl")
```

`GoldenRow` validates on construction (band must be one of the four literals,
score 0–100, `expected_swaps` must be `from>to; …` or blank) — a `ValidationError`
means your proposal is malformed; fix it, don't work around it.

## Coverage

The recipes are whatever Amber submitted — you don't hunt for more. Contract 4
wants the *full* golden set (20–50 rows) to span obviously-clean,
obviously-ultra-processed, and many ambiguous middles; if the submitted batch
looks lopsided, say so in your summary so Amber can queue more. Don't pad it
yourself.

## Optional: fan out

50 recipes are independent, so this is a legitimate parallel-agent job (one
agent per recipe or per small batch). That's **billed + opt-in** per the sub-agent
rule (architecture.md) — only do it if Amber asked for it; otherwise a simple
sequential loop is fine (the scorer is ~1 req/sec anyway).

## When you're done

Report: how many drafts you wrote, which recipes you skipped and why, and any
coverage gaps you noticed. Then tell Amber to open the Console's **Review & grade**
tab. Do **not** promote anything to `golden_set.csv` — that's her call in the
Promote tab.
```

Source of truth for the shapes: `src/clean_recipe/golden.py` (`BacklogEntry`,
`GoldenDraft`, `GoldenRow`) and `ai_docs/llm_contracts.md` (Contract 4).
