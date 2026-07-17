"""Eval harness: run the golden set through ``score_recipe`` and score it.

Source of truth: ai_docs/llm_contracts.md — "Contract 4: Golden-set label
format" (the row shape lives in ``clean_recipe.golden``, shared with the
labeling console) and "Eval harness metrics" (the numbers this file computes).
The golden labels and rubric weights are **human-owned**: this file only
consumes labels, it never invents or edits them.

Metrics implemented here are exactly the two the golden columns support today:
- **Band accuracy** — % of rows where ``verdict.band == target_band``.
- **Score MAE** — mean absolute error of ``verdict.score`` vs ``int(target_score)``.

The ``swap_quality`` column (Contract 4 v0.2 — Amber's manual 1–5 grade of the
model's swaps) is summarized informationally (rows graded + mean); it grades
previously-seen swaps, so it is NOT a per-model metric for the bake-off.

Deliberately deferred (no golden columns / no automation yet):
- **Per-component MAE** — needs per-sub-score targets that Contract 4 does not
  define. Left as a TODO placeholder below.
- **Swap quality as an eval metric** — LLM-as-judge automation is Phase 6. TODO.

Malformed golden rows fail loud (Contract 4 is a hard contract), matching the
fail-loud discipline in score.py.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import get_args

from dotenv import load_dotenv

# Contract 4 shape — single source of truth shared with console.py. Re-exported
# names (GOLDEN_COLUMNS, GoldenRow, load_golden, parse_ingredients) keep this
# module the harness-side entry point for the golden set.
from clean_recipe.golden import (  # noqa: F401  (re-exports)
    GOLDEN_COLUMNS,
    GoldenRow,
    load_golden,
    parse_ingredients,
)
from clean_recipe.schema import Band, SubScores
from clean_recipe.score import NotARecipeError, ScoringError, score_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN = REPO_ROOT / "evals" / "golden_set.csv"
RESULTS_DIR = REPO_ROOT / "evals" / "results"

# Bands from cleanest to most-processed. Ordering lets us describe a confusion
# as "cleaner" vs "harsher" than the human label — the direction of a miss is
# the whole story of the Phase-6 baseline (the model skews clean). schema.Band
# owns the *names*; this list adds the ordering. Assert membership stays in sync
# so a band rename in the schema fails loud at import, not mid-run in
# _band_direction (a validated golden band absent from BANDS would crash there).
BANDS = ["Clean", "Mostly Clean", "Processed", "Ultra-processed"]
assert set(BANDS) == set(get_args(Band)), "evaluate.BANDS out of sync with schema.Band"

# Canonical sub-score keys, in schema/prompt order (weight-descending).
SUBSCORE_KEYS = list(SubScores.model_fields)


@dataclass
class ResultRow:
    """One scored row: golden target vs. model prediction.

    ``sub_scores`` carries the model's six raw dimension scores (0–100) so the
    diagnostics can show *where* a miss comes from — e.g. whether the model is
    uniformly lenient (all dims high, which no weight tuning can fix) or actually
    discriminating but mapped through miscalibrated weights/cutoffs. Defaults to
    ``{}`` so hand-built ResultRows (tests, metric math) need not supply them.
    """

    recipe_id: str
    target_band: str
    predicted_band: str
    target_score: int
    predicted_score: int
    sub_scores: dict[str, float] = field(default_factory=dict)

    @property
    def band_correct(self) -> bool:
        return self.predicted_band == self.target_band

    @property
    def abs_error(self) -> int:
        return abs(self.predicted_score - self.target_score)

    @property
    def signed_error(self) -> int:
        """Predicted minus target: >0 means the model scored it too CLEAN."""
        return self.predicted_score - self.target_score


def band_accuracy(results: list[ResultRow]) -> float:
    """Fraction (0.0–1.0) of rows whose predicted band matches the target."""
    if not results:
        return 0.0
    correct = sum(1 for r in results if r.band_correct)
    return correct / len(results)


def score_mae(results: list[ResultRow]) -> float:
    """Mean absolute error of predicted vs. target score."""
    if not results:
        return 0.0
    return sum(r.abs_error for r in results) / len(results)


def mean_signed_error(results: list[ResultRow]) -> float:
    """Mean of (predicted - target). Positive ⇒ the model skews too clean."""
    if not results:
        return 0.0
    return sum(r.signed_error for r in results) / len(results)


def per_band_accuracy(results: list[ResultRow]) -> dict[str, tuple[int, int]]:
    """Map each target band → (correct, total). Bands with no rows are omitted."""
    stats: dict[str, list[int]] = {}
    for r in results:
        counts = stats.setdefault(r.target_band, [0, 0])
        counts[1] += 1
        if r.band_correct:
            counts[0] += 1
    return {b: (c, n) for b, (c, n) in stats.items()}


def confusion_counts(results: list[ResultRow]) -> dict[tuple[str, str], int]:
    """Count (target_band, predicted_band) pairs — the band confusion matrix."""
    conf: dict[tuple[str, str], int] = {}
    for r in results:
        key = (r.target_band, r.predicted_band)
        conf[key] = conf.get(key, 0) + 1
    return conf


def subscore_means(results: list[ResultRow]) -> dict[str, float]:
    """Mean of each model sub-score across rows that reported it.

    This is the lever-finder: if every dimension averages high, the leniency is
    in the model's judgment (fix via prompt grounding / marker lists), not in the
    weights — no convex combination of high sub-scores yields a low composite.
    """
    means: dict[str, float] = {}
    for key in SUBSCORE_KEYS:
        vals = [r.sub_scores[key] for r in results if key in r.sub_scores]
        if vals:
            means[key] = sum(vals) / len(vals)
    return means


def _band_direction(target: str, predicted: str) -> str:
    """'cleaner' if predicted is a cleaner band than target, else 'harsher'."""
    return "cleaner" if BANDS.index(predicted) < BANDS.index(target) else "harsher"


def print_diagnostics(results: list[ResultRow]) -> None:
    """Print the where-are-the-misses breakdown beneath the headline metrics.

    Everything here is descriptive — it reads the golden labels and model output
    but never edits the human-owned rubric. It just makes the tuning target
    legible: which bands miss, in which direction, and whether the model's raw
    sub-scores are discriminating or uniformly lenient.
    """
    if not results:
        print("No rows scored — nothing to diagnose.")
        return

    print("\nPer-band accuracy:")
    per_band = per_band_accuracy(results)
    for band in BANDS:
        if band in per_band:
            correct, total = per_band[band]
            print(f"  {band:16} {correct}/{total}")

    signed = mean_signed_error(results)
    skew = "too clean" if signed > 0 else "too harsh" if signed < 0 else "balanced"
    over = sum(1 for r in results if r.signed_error > 0)
    under = sum(1 for r in results if r.signed_error < 0)
    print(
        f"\nMean signed score error (pred - target): {signed:+.1f}  ({skew})\n"
        f"  rows scored cleaner than label: {over}/{len(results)};  harsher: {under}"
    )

    conf = confusion_counts(results)
    misses = sorted(
        ((t, p, n) for (t, p), n in conf.items() if t != p),
        key=lambda x: -x[2],
    )
    if misses:
        print("\nBand confusion (target → predicted), misses only:")
        for target, predicted, n in misses:
            print(
                f"  {target:16} → {predicted:16} {n:2}  ({_band_direction(target, predicted)})"
            )

    means = subscore_means(results)
    if means:
        print("\nModel sub-score means (0–100, higher = cleaner):")
        for key in SUBSCORE_KEYS:
            if key in means:
                print(f"  {key:22} {means[key]:5.1f}")


# TODO (deferred — no golden columns for these yet, see module docstring):
#   - per_component_mae(results): needs per-sub-score targets (Contract 4 has none).
#   - swap_quality(results): future manual 1–5 human grade / LLM-as-judge.


def run_eval(
    golden: list[GoldenRow], model: str | None, *, progress: bool = False
) -> list[ResultRow]:
    """Score every golden row and collect target-vs-prediction results.

    A single row that fails to score (the model rejects it as not-a-recipe, or
    can't produce a valid Verdict after retry) is warned and skipped — one flaky
    judgment must not abort a whole bake-off run. Skipped rows are excluded from
    the metrics; the warning names them so the human can investigate.

    ``progress=True`` prints a per-row heartbeat to stderr. Each row is a real,
    sequential model call (seconds each, no output until the end otherwise), so
    the CLI passes this to prove it's working rather than hung.
    """
    results: list[ResultRow] = []
    total = len(golden)
    for i, row in enumerate(golden, 1):
        if progress:
            print(
                f"  [{i}/{total}] scoring {row.recipe_id or row.title!r}…",
                file=sys.stderr,
                flush=True,
            )
        try:
            verdict = score_recipe(row.title, row.ingredients, model=model, log=False)
        except (NotARecipeError, ScoringError) as e:
            print(
                f"  ! skipping {row.recipe_id or row.title!r}: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            continue
        results.append(
            ResultRow(
                recipe_id=row.recipe_id,
                target_band=row.target_band,
                predicted_band=verdict.band,
                target_score=row.target_score,
                predicted_score=verdict.score,
                sub_scores=verdict.sub_scores.model_dump(),
            )
        )
    return results


def write_results_csv(
    results: list[ResultRow], results_dir: Path, model: str
) -> Path:
    """Write per-row detail to a timestamped CSV under ``results_dir``."""
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = "".join(c if c.isalnum() or c in "-._" else "_" for c in model)
    out = results_dir / f"eval-{stamp}-{safe_model}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "recipe_id",
                "target_band",
                "predicted_band",
                "band_correct",
                "target_score",
                "predicted_score",
                "abs_error",
                "signed_error",
            ]
            + SUBSCORE_KEYS
        )
        for r in results:
            writer.writerow(
                [
                    r.recipe_id,
                    r.target_band,
                    r.predicted_band,
                    r.band_correct,
                    r.target_score,
                    r.predicted_score,
                    r.abs_error,
                    r.signed_error,
                ]
                + [r.sub_scores.get(k, "") for k in SUBSCORE_KEYS]
            )
    return out


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=None,
        help="Override LLM_MODEL for a provider bake-off (default: env LLM_MODEL).",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=DEFAULT_GOLDEN,
        help="Path to the golden-set CSV (default: evals/golden_set.csv).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on the number of golden rows to run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = _parse_args(argv)

    golden = load_golden(args.golden)
    if args.limit is not None:
        golden = golden[: args.limit]

    model = args.model or os.getenv("LLM_MODEL") or "(env default)"
    results = run_eval(golden, args.model, progress=True)
    out = write_results_csv(results, RESULTS_DIR, model)

    acc = band_accuracy(results)
    mae = score_mae(results)
    graded = [r.swap_quality for r in golden if r.swap_quality is not None]
    print(f"Model:          {model}")
    print(f"Rows:           {len(results)}")
    print(f"Band accuracy:  {acc:.1%}")
    print(f"Score MAE:      {mae:.2f}")
    print_diagnostics(results)
    print()
    if graded:
        print(
            f"Swap quality:   {len(graded)}/{len(golden)} rows graded, "
            f"mean {sum(graded) / len(graded):.1f}/5 "
            "(human grade of previously-seen swaps — not a per-model metric)"
        )
    else:
        print(f"Swap quality:   0/{len(golden)} rows graded (human 1–5 column)")
    print("Per-component MAE / automated swap judging: deferred to Phase 6.")
    print(f"Results CSV:    {out}")


if __name__ == "__main__":
    main()
