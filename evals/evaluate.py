"""Eval harness: run the golden set through ``score_recipe`` and score it.

Source of truth: ai_docs/llm_contracts.md — "Contract 4: Golden-set label
format" (the CSV columns this harness reads) and "Eval harness metrics" (the
numbers it computes). The golden labels and rubric weights are **human-owned**:
this file only consumes labels, it never invents or edits them.

Metrics implemented here are exactly the two the golden columns support today:
- **Band accuracy** — % of rows where ``verdict.band == target_band``.
- **Score MAE** — mean absolute error of ``verdict.score`` vs ``int(target_score)``.

Deliberately deferred (the golden set has no columns for them yet, so computing
them would be fabrication):
- **Per-component MAE** — needs per-sub-score targets that Contract 4 does not
  define. Left as a TODO placeholder below.
- **Swap quality** — a future manual 1–5 human grade / LLM-as-judge. TODO.

Malformed golden rows fail loud (Contract 4 is a hard contract), matching the
fail-loud discipline in score.py.
"""
from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from clean_recipe.score import score_recipe

# Exact Contract 4 columns, in order. The golden CSV must match this verbatim.
GOLDEN_COLUMNS = [
    "recipe_id",
    "source",
    "title",
    "raw_ingredients",
    "target_band",
    "target_score",
    "expected_swaps",
    "notes",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLDEN = REPO_ROOT / "evals" / "golden_set.csv"
RESULTS_DIR = REPO_ROOT / "evals" / "results"


@dataclass
class GoldenRow:
    """One parsed golden-set row (Contract 4)."""

    recipe_id: str
    title: str
    ingredients: list[str]
    target_band: str
    target_score: int


@dataclass
class ResultRow:
    """One scored row: golden target vs. model prediction."""

    recipe_id: str
    target_band: str
    predicted_band: str
    target_score: int
    predicted_score: int

    @property
    def band_correct(self) -> bool:
        return self.predicted_band == self.target_band

    @property
    def abs_error(self) -> int:
        return abs(self.predicted_score - self.target_score)


def parse_ingredients(raw: str) -> list[str]:
    """Split a ``raw_ingredients`` cell ("a; b; c") into ["a", "b", "c"]."""
    return [part.strip() for part in raw.split("; ") if part.strip()]


def load_golden(path: Path) -> list[GoldenRow]:
    """Load + validate the golden CSV; fail loud on a malformed file/row."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != GOLDEN_COLUMNS:
            raise ValueError(
                f"golden set {path} has columns {reader.fieldnames}, "
                f"expected exactly {GOLDEN_COLUMNS} (Contract 4)"
            )
        rows: list[GoldenRow] = []
        for i, raw in enumerate(reader, start=2):  # start=2: header is line 1
            title = (raw["title"] or "").strip()
            ingredients = parse_ingredients(raw["raw_ingredients"] or "")
            target_band = (raw["target_band"] or "").strip()
            score_cell = (raw["target_score"] or "").strip()
            if not title or not ingredients or not target_band or not score_cell:
                raise ValueError(
                    f"{path} line {i}: missing required Contract 4 field "
                    f"(title/raw_ingredients/target_band/target_score)"
                )
            try:
                target_score = int(score_cell)
            except ValueError as e:
                raise ValueError(
                    f"{path} line {i}: target_score {score_cell!r} is not an int"
                ) from e
            rows.append(
                GoldenRow(
                    recipe_id=(raw["recipe_id"] or "").strip(),
                    title=title,
                    ingredients=ingredients,
                    target_band=target_band,
                    target_score=target_score,
                )
            )
    if not rows:
        raise ValueError(f"golden set {path} has no data rows")
    return rows


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


# TODO (deferred — no golden columns for these yet, see module docstring):
#   - per_component_mae(results): needs per-sub-score targets (Contract 4 has none).
#   - swap_quality(results): future manual 1–5 human grade / LLM-as-judge.


def run_eval(golden: list[GoldenRow], model: str | None) -> list[ResultRow]:
    """Score every golden row and collect target-vs-prediction results."""
    results: list[ResultRow] = []
    for row in golden:
        verdict = score_recipe(row.title, row.ingredients, model=model, log=False)
        results.append(
            ResultRow(
                recipe_id=row.recipe_id,
                target_band=row.target_band,
                predicted_band=verdict.band,
                target_score=row.target_score,
                predicted_score=verdict.score,
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
            ]
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
                ]
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
    results = run_eval(golden, args.model)
    out = write_results_csv(results, RESULTS_DIR, model)

    acc = band_accuracy(results)
    mae = score_mae(results)
    print(f"Model:          {model}")
    print(f"Rows:           {len(results)}")
    print(f"Band accuracy:  {acc:.1%}")
    print(f"Score MAE:      {mae:.2f}")
    print("Per-component MAE / swap quality: deferred (no golden columns yet).")
    print(f"Results CSV:    {out}")


if __name__ == "__main__":
    main()
