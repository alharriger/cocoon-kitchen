"""evaluate.py: metric math, golden-set loading/validation (Contract 4),
ingredient parsing, and an end-to-end harness run with ``score_recipe``
monkeypatched — NO NETWORK, no real API calls."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

# evals/ is not an installed package; put it on the path so we can import it.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "evals"))

import evaluate  # noqa: E402
from clean_recipe.schema import SubScores, Swap, Verdict  # noqa: E402


# ---- helpers ----------------------------------------------------------------

def result(recipe_id, tband, pband, tscore, pscore) -> evaluate.ResultRow:
    return evaluate.ResultRow(
        recipe_id=recipe_id,
        target_band=tband,
        predicted_band=pband,
        target_score=tscore,
        predicted_score=pscore,
    )


def canned_verdict(score: int = 90, band: str = "Clean") -> Verdict:
    return Verdict(
        score=score,
        band=band,
        sub_scores=SubScores(
            ultra_processing=90,
            added_sugar=90,
            fat_quality=90,
            sodium_preservatives=90,
            whole_food_ratio=90,
            additive_count=90,
        ),
        flagged_ingredients=[],
        swaps=[Swap(from_ingredient="a", to_ingredient="b", reason="r")],
    )


# ---- metric math (pure, no model) -------------------------------------------

def test_band_accuracy_two_of_three():
    results = [
        result("r1", "Clean", "Clean", 90, 90),          # match
        result("r2", "Processed", "Processed", 50, 50),  # match
        result("r3", "Clean", "Ultra-processed", 90, 10),  # miss
    ]
    assert evaluate.band_accuracy(results) == pytest.approx(2 / 3)


def test_score_mae_known_errors():
    results = [
        result("r1", "Clean", "Clean", 90, 80),   # abs err 10
        result("r2", "Clean", "Clean", 50, 56),   # abs err 6
        result("r3", "Clean", "Clean", 40, 42),   # abs err 2
    ]
    assert evaluate.score_mae(results) == pytest.approx((10 + 6 + 2) / 3)


def test_metrics_empty_are_zero():
    assert evaluate.band_accuracy([]) == 0.0
    assert evaluate.score_mae([]) == 0.0


# ---- ingredient parsing -----------------------------------------------------

def test_parse_ingredients_splits_on_semicolon():
    assert evaluate.parse_ingredients("a; b; c") == ["a", "b", "c"]


def test_parse_ingredients_strips_and_drops_blanks():
    assert evaluate.parse_ingredients("  olive oil ;  spinach ; ") == ["olive oil", "spinach"]


# ---- golden set (Contract 4) ------------------------------------------------

def test_golden_set_columns_and_row_count():
    with evaluate.DEFAULT_GOLDEN.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        data_rows = [r for r in reader if any(cell.strip() for cell in r)]
    assert header == evaluate.GOLDEN_COLUMNS
    assert len(data_rows) >= 2


def test_load_golden_parses_rows():
    rows = evaluate.load_golden(evaluate.DEFAULT_GOLDEN)
    assert len(rows) >= 2
    first = rows[0]
    assert isinstance(first.ingredients, list) and first.ingredients
    assert isinstance(first.target_score, int)


def test_load_golden_bad_columns_fails_loud(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("wrong,header\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        evaluate.load_golden(bad)


def test_load_golden_bad_score_fails_loud(tmp_path):
    bad = tmp_path / "bad.csv"
    header = ",".join(evaluate.GOLDEN_COLUMNS)
    bad.write_text(
        f"{header}\nr1,pasted,Soup,water; salt,Clean,notanint,,note\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        evaluate.load_golden(bad)


# ---- end-to-end harness run (score_recipe monkeypatched) --------------------

def test_run_eval_and_write_results(monkeypatch, tmp_path):
    golden = [
        evaluate.GoldenRow(
            recipe_id="g1",
            title="Clean Bowl",
            ingredients=["spinach", "olive oil"],
            target_band="Clean",
            target_score=90,
        ),
        evaluate.GoldenRow(
            recipe_id="g2",
            title="Junk",
            ingredients=["hfcs"],
            target_band="Ultra-processed",
            target_score=10,
        ),
    ]

    # Canned verdict (Clean/90) for every row — no network. Patch the name
    # evaluate imported.
    monkeypatch.setattr(evaluate, "score_recipe", lambda *a, **k: canned_verdict(90, "Clean"))

    results = evaluate.run_eval(golden, model="fake-model")
    assert len(results) == 2
    # g1 matches (Clean/90), g2 does not (predicted Clean vs Ultra-processed).
    assert evaluate.band_accuracy(results) == pytest.approx(0.5)
    # abs errors: |90-90|=0, |90-10|=80 -> MAE 40
    assert evaluate.score_mae(results) == pytest.approx(40.0)

    out = evaluate.write_results_csv(results, tmp_path, "fake-model")
    assert out.exists() and out.parent == tmp_path
    with out.open(newline="", encoding="utf-8") as f:
        written = list(csv.DictReader(f))
    assert [r["recipe_id"] for r in written] == ["g1", "g2"]
    assert written[1]["abs_error"] == "80"


def test_main_smoke(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(evaluate, "score_recipe", lambda *a, **k: canned_verdict(90, "Clean"))
    monkeypatch.setattr(evaluate, "RESULTS_DIR", tmp_path / "results")
    evaluate.main(["--model", "fake-model", "--limit", "1"])
    out = capsys.readouterr().out
    assert "Band accuracy:" in out
    assert "fake-model" in out
    assert (tmp_path / "results").exists()
