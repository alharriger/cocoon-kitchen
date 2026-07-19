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
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import get_args

from dotenv import load_dotenv
from openai import OpenAIError

# Provider-profile registry for the cross-provider bake-off (Phase 6 Task 4).
# evals/ is on sys.path when this module is imported (script dir for a direct
# run; inserted by tests), so a bare import resolves.
from providers import (
    PROVIDERS,
    MissingKeyError,
    Provider,
    activate,
    capture_active_credentials,
    openrouter_est_cost,
    openrouter_providers,
    restore_credentials,
    select_provider,
)

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
    golden: list[GoldenRow],
    model: str | None,
    *,
    progress: bool = False,
    min_interval: float = 0.0,
) -> list[ResultRow]:
    """Score every golden row and collect target-vs-prediction results.

    A single row that fails to score is warned and skipped — one flaky judgment
    must not abort a whole bake-off run. Skipped rows are excluded from the
    metrics; the warning names them so the human can investigate. Three failure
    kinds are tolerated per row: the model rejects it as not-a-recipe
    (``NotARecipeError``), it can't produce a valid Verdict after retry
    (``ScoringError``), or the provider API errors transiently
    (``OpenAIError`` — e.g. a mid-run 429 rate-limit on a free tier). A hard/total
    failure (bad key, dead model) surfaces as every row skipping; the bake-off's
    per-provider preflight catches that up front so it isn't 52 warnings deep.

    ``min_interval`` paces calls: at least this many seconds elapse between the
    START of consecutive scoring calls, to respect a provider's free-tier RPM
    ceiling (0 → no pacing). Real calls already take seconds, so this only sleeps
    the remainder when a call returns faster than the ceiling allows.

    ``progress=True`` prints a per-row heartbeat to stderr. Each row is a real,
    sequential model call (seconds each, no output until the end otherwise), so
    the CLI passes this to prove it's working rather than hung.
    """
    results: list[ResultRow] = []
    total = len(golden)
    last_start = 0.0
    for i, row in enumerate(golden, 1):
        if min_interval > 0:
            wait = min_interval - (time.monotonic() - last_start)
            if wait > 0:
                time.sleep(wait)
        last_start = time.monotonic()
        if progress:
            print(
                f"  [{i}/{total}] scoring {row.recipe_id or row.title!r}…",
                file=sys.stderr,
                flush=True,
            )
        try:
            verdict = score_recipe(row.title, row.ingredients, model=model, log=False)
        except (NotARecipeError, ScoringError, OpenAIError) as e:
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


# A provider must score at least this fraction of the attempted golden rows for
# its metrics to be comparable / eligible for the recommendation. Below it, a
# free-tier cap (Groq's tokens-per-day, Gemini's RPM) has truncated the run to a
# non-random early-alphabet slice — e.g. 13/52 rows at a flattering 77% is a
# small-sample artifact, NOT a real win. Incomplete providers stay in the table
# (flagged) but are excluded from the recommendation (no silent cap).
MIN_COVERAGE = 0.90


@dataclass
class BakeoffSummary:
    """One provider's headline numbers for the cross-provider comparison table.

    ``skipped_reason`` set ⇒ the provider was not run (no key, or preflight
    failed); all metric fields are then meaningless and the table shows the
    reason instead. The key value is never stored here — only ``name``/``model``.

    ``rows`` is how many golden rows actually scored; ``attempted`` is how many
    were tried (the golden-set size). ``coverage`` below flags a run truncated by
    a free-tier cap so it doesn't masquerade as a full-set result.
    """

    name: str
    model: str
    rows: int = 0
    attempted: int = 0
    band_acc: float = 0.0
    mae: float = 0.0
    mean_signed: float = 0.0
    processed_in_band: tuple[int, int] = (0, 0)
    avg_latency_s: float = 0.0
    results_csv: str = ""
    skipped_reason: str = ""

    @property
    def coverage(self) -> float:
        """Fraction of attempted rows that scored (0.0 if nothing attempted)."""
        return self.rows / self.attempted if self.attempted else 0.0

    @property
    def complete(self) -> bool:
        """True if enough rows scored for the metrics to be comparable."""
        return not self.skipped_reason and self.coverage >= MIN_COVERAGE


def preflight(golden: list[GoldenRow]) -> tuple[bool, str]:
    """Score ONE golden row to prove the active provider works before the full run.

    Returns ``(ok, message)``. A keyless/unfunded/dead provider fails every row,
    so we probe with a single call first: on any error return ``(False, reason)``
    so the bake-off can skip this provider (report it) instead of emitting 52
    identical warnings. A ``NotARecipeError`` on a real golden row would itself be
    a red flag, so it counts as a failed preflight too.
    """
    if not golden:
        return False, "no golden rows to preflight"
    row = golden[0]
    try:
        score_recipe(row.title, row.ingredients, log=False)
    except Exception as e:  # noqa: BLE001 — preflight must catch anything the API throws
        return False, f"{type(e).__name__}: {e}"
    return True, "ok"


def run_bakeoff(
    golden: list[GoldenRow], providers: list[Provider], results_dir: Path
) -> list[BakeoffSummary]:
    """Run the tuned rubric against each provider profile, one at a time.

    For each provider: activate its env profile (never touching the on-disk
    ``.env``), preflight one row, and — if that passes — score the full golden
    set with the provider's pacing, writing a per-provider results CSV. A missing
    key or failed preflight records a skip and moves on; one dead provider must
    not sink the comparison. Providers run sequentially to keep each within its
    own rate/token budget.
    """
    # Snapshot the incumbent .env credentials BEFORE the loop mutates LLM_API_KEY,
    # so the glm entry (whose key lives in LLM_API_KEY) survives other providers'
    # activation clobbering it (see providers.capture_active_credentials).
    incumbent = capture_active_credentials()

    summaries: list[BakeoffSummary] = []
    for provider in providers:
        name = provider.name
        print(f"\n=== {name} ({provider.model}) ===", file=sys.stderr, flush=True)
        try:
            if name == "glm":
                # Incumbent dev default: restore the pre-loop .env credentials
                # verbatim rather than re-reading the now-clobbered LLM_API_KEY.
                restore_credentials(incumbent)
                if not os.environ.get("LLM_API_KEY"):
                    raise MissingKeyError(
                        "glm: LLM_API_KEY is not set in .env (the dev-default key)."
                    )
            else:
                activate(provider)
        except MissingKeyError as e:
            print(f"  skipped: {e}", file=sys.stderr)
            summaries.append(
                BakeoffSummary(
                    name=name, model=provider.model,
                    attempted=len(golden), skipped_reason=str(e),
                )
            )
            continue

        ok, msg = preflight(golden)
        if not ok:
            print(f"  skipped: preflight failed — {msg}", file=sys.stderr)
            summaries.append(
                BakeoffSummary(
                    name=name, model=provider.model, attempted=len(golden),
                    skipped_reason=f"preflight: {msg}",
                )
            )
            continue

        start = time.monotonic()
        results = run_eval(
            golden, provider.model, progress=True, min_interval=provider.min_interval
        )
        elapsed = time.monotonic() - start
        if not results:
            summaries.append(
                BakeoffSummary(
                    name=name, model=provider.model, attempted=len(golden),
                    skipped_reason="all rows failed",
                )
            )
            continue

        out = write_results_csv(results, results_dir, f"{name}-{provider.model}")
        summaries.append(
            BakeoffSummary(
                name=name,
                model=provider.model,
                rows=len(results),
                attempted=len(golden),
                band_acc=band_accuracy(results),
                mae=score_mae(results),
                mean_signed=mean_signed_error(results),
                processed_in_band=per_band_accuracy(results).get("Processed", (0, 0)),
                # NOTE: includes any pacing sleeps, so "lat/s" overstates true
                # model latency for a PACED direct provider (e.g. gemini at 10s).
                # The recommended OpenRouter path is unpaced → accurate there.
                avg_latency_s=elapsed / len(results),
                results_csv=str(out),
            )
        )
    return summaries


def recommend_default(summaries: list[BakeoffSummary]) -> BakeoffSummary | None:
    """Pick the eval-selected default: best band accuracy, then lowest MAE.

    Eval-selected, never by brand (architecture 2026-07-11). Only providers that
    COMPLETED the set (``coverage >= MIN_COVERAGE``) are eligible — a run
    truncated by a free-tier cap is a non-random slice and not comparable.
    Returns ``None`` if no provider completed.
    """
    eligible = [s for s in summaries if s.complete]
    if not eligible:
        return None
    return min(eligible, key=lambda s: (-s.band_acc, s.mae))


def print_bakeoff_table(summaries: list[BakeoffSummary]) -> None:
    """Print the cross-provider comparison + the eval-selected recommendation.

    Incomplete providers (truncated by a free-tier cap) stay in the table with a
    coverage flag but are called out as excluded from the recommendation — a
    bounded run must never read as a full-set result (no silent caps).
    """
    # Row count comes from the runs (via `attempted`), not a hardcoded 52 — the
    # header must not claim "52-row" under --limit N or a grown golden set.
    n = max((s.attempted for s in summaries), default=0)
    print("\n" + "=" * 78)
    print(f"BAKE-OFF RESULTS ({n}-row golden set, tuned rubric — Phase 6 Task 4)")
    print("=" * 78)
    header = (
        f"{'provider':10} {'model':26} {'rows':>7} {'band':>6} "
        f"{'MAE':>6} {'signed':>7} {'Proc':>6} {'lat/s':>6}"
    )
    print(header)
    print("-" * len(header))
    for s in summaries:
        if s.skipped_reason:
            print(f"{s.name:10} {s.model:26}   —  skipped: {s.skipped_reason}")
            continue
        rows = f"{s.rows}/{s.attempted}"
        proc = f"{s.processed_in_band[0]}/{s.processed_in_band[1]}"
        flag = "" if s.complete else f"  ⚠ incomplete ({s.coverage:.0%}) — excluded"
        print(
            f"{s.name:10} {s.model:26} {rows:>7} {s.band_acc:>5.1%} "
            f"{s.mae:>6.2f} {s.mean_signed:>+7.1f} {proc:>6} {s.avg_latency_s:>6.1f}"
            f"{flag}"
        )
    print("-" * len(header))

    # Name the excluded providers explicitly so a capped/blocked run is never
    # silently dropped from the reader's mental model.
    incomplete = [s for s in summaries if not s.skipped_reason and not s.complete]
    if incomplete:
        print(
            f"\nExcluded from recommendation (incomplete — under {MIN_COVERAGE:.0%} "
            "of rows scored; a rate/token cap, API errors, or empty responses "
            "left a non-random slice):"
        )
        for s in incomplete:
            print(f"  {s.name}: {s.rows}/{s.attempted} rows ({s.coverage:.0%})")

    best = recommend_default(summaries)
    if best is None:
        print(
            "\nNo provider completed the set — nothing to recommend "
            "(check keys / free-tier balance / daily caps)."
        )
        return
    print(
        f"\nEval-selected default (by the numbers, not by brand): "
        f"{best.name} / {best.model}"
        f"  —  band {best.band_acc:.1%} on {best.rows}/{best.attempted} rows, "
        f"MAE {best.mae:.2f}, Processed {best.processed_in_band[0]}/{best.processed_in_band[1]}."
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=None,
        help="Override LLM_MODEL for a provider bake-off (default: env LLM_MODEL).",
    )
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDERS),
        default=None,
        help=(
            "Run one registered provider profile (sets its base_url/model/"
            "extra_body in-process from its *_API_KEY env var; leaves .env alone). "
            "Without this, the active .env credentials are used."
        ),
    )
    parser.add_argument(
        "--all-providers",
        action="store_true",
        help=(
            "Cross-provider bake-off: run every registered provider (skipping any "
            "without a key), print a comparison table, and recommend an "
            "eval-selected default. Overrides --provider/--model."
        ),
    )
    parser.add_argument(
        "--openrouter",
        action="store_true",
        help=(
            "OpenRouter bake-off: run the curated OpenRouter model set (one funded "
            "key/base_url) plus the free glm-4.5-flash incumbent, print a "
            "comparison table + eval-selected default. Prints a projected-cost "
            "heads-up first. Overrides --provider/--model/--all-providers."
        ),
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

    # OpenRouter bake-off: the incumbent (free, direct) + the curated OpenRouter
    # set (one funded key). Print a projected-cost heads-up before spending.
    if args.openrouter:
        n_rows = len(golden)
        scale = n_rows / 52 if n_rows else 1.0
        print(
            f"Projected OpenRouter spend: ~${openrouter_est_cost() * scale:.2f} "
            f"({len(openrouter_providers())} models × {n_rows} rows; estimate, "
            "glm incumbent is free/direct).",
            file=sys.stderr,
        )
        providers = [select_provider("glm")] + openrouter_providers()
        summaries = run_bakeoff(golden, providers, RESULTS_DIR)
        print_bakeoff_table(summaries)
        return

    # Cross-provider bake-off: run every registered (direct) provider and compare.
    if args.all_providers:
        providers = [select_provider(n) for n in sorted(PROVIDERS)]
        summaries = run_bakeoff(golden, providers, RESULTS_DIR)
        print_bakeoff_table(summaries)
        return

    # Single registered provider: point the client seam at its profile in-process
    # (the on-disk .env is never modified). --model still overrides the name.
    if args.provider:
        provider = select_provider(args.provider)
        activate(provider)
        if args.model is None:
            args.model = provider.model

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
