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

def result(recipe_id, tband, pband, tscore, pscore, sub_scores=None) -> evaluate.ResultRow:
    return evaluate.ResultRow(
        recipe_id=recipe_id,
        target_band=tband,
        predicted_band=pband,
        target_score=tscore,
        predicted_score=pscore,
        sub_scores=sub_scores or {},
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
    assert evaluate.mean_signed_error([]) == 0.0


# ---- diagnostics (Phase 6 lever-finder) -------------------------------------

def test_signed_error_sign_convention():
    # Predicted cleaner (higher) than target ⇒ positive signed error.
    assert result("r", "Processed", "Clean", 50, 85).signed_error == 35
    assert result("r", "Clean", "Processed", 85, 50).signed_error == -35


def test_mean_signed_error_detects_clean_skew():
    results = [
        result("r1", "Processed", "Clean", 50, 85),   # +35
        result("r2", "Mostly Clean", "Clean", 70, 90),  # +20
    ]
    assert evaluate.mean_signed_error(results) == pytest.approx((35 + 20) / 2)


def test_per_band_accuracy_groups_by_target():
    results = [
        result("r1", "Clean", "Clean", 90, 90),          # correct
        result("r2", "Processed", "Clean", 50, 85),      # miss
        result("r3", "Processed", "Processed", 50, 50),  # correct
    ]
    per = evaluate.per_band_accuracy(results)
    assert per["Clean"] == (1, 1)
    assert per["Processed"] == (1, 2)


def test_confusion_counts_and_direction():
    results = [
        result("r1", "Processed", "Clean", 50, 85),
        result("r2", "Processed", "Clean", 50, 85),
        result("r3", "Clean", "Processed", 85, 50),
    ]
    conf = evaluate.confusion_counts(results)
    assert conf[("Processed", "Clean")] == 2
    assert conf[("Clean", "Processed")] == 1
    assert evaluate._band_direction("Processed", "Clean") == "cleaner"
    assert evaluate._band_direction("Clean", "Processed") == "harsher"


def test_subscore_means_averages_reported_dims():
    hi = {k: 90.0 for k in evaluate.SUBSCORE_KEYS}
    lo = {k: 30.0 for k in evaluate.SUBSCORE_KEYS}
    results = [
        result("r1", "Clean", "Clean", 90, 90, sub_scores=hi),
        result("r2", "Clean", "Clean", 90, 90, sub_scores=lo),
    ]
    means = evaluate.subscore_means(results)
    assert means["ultra_processing"] == pytest.approx(60.0)
    # Rows without sub_scores contribute nothing (no crash, no key).
    bare = [result("r3", "Clean", "Clean", 90, 90)]
    assert evaluate.subscore_means(bare) == {}


def test_print_diagnostics_smoke(capsys):
    results = [
        result("r1", "Processed", "Clean", 50, 85,
               sub_scores={k: 88.0 for k in evaluate.SUBSCORE_KEYS}),
        result("r2", "Clean", "Clean", 90, 90,
               sub_scores={k: 92.0 for k in evaluate.SUBSCORE_KEYS}),
    ]
    evaluate.print_diagnostics(results)
    out = capsys.readouterr().out
    assert "Per-band accuracy:" in out
    assert "Mean signed score error" in out
    assert "Band confusion" in out
    assert "Model sub-score means" in out
    assert "cleaner" in out  # r1 predicted cleaner than its Processed label


def test_print_diagnostics_empty_is_safe(capsys):
    evaluate.print_diagnostics([])
    assert "nothing to diagnose" in capsys.readouterr().out


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
        f"{header}\nr1,pasted,Soup,water; salt,Clean,notanint,,,note\n",
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
            raw_ingredients="spinach; olive oil",
            target_band="Clean",
            target_score=90,
        ),
        evaluate.GoldenRow(
            recipe_id="g2",
            title="Junk",
            raw_ingredients="hfcs",
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
    # Phase 6: results carry direction + the model's raw sub-scores.
    assert written[1]["signed_error"] == "80"   # predicted 90 - target 10
    for key in evaluate.SUBSCORE_KEYS:
        assert written[0][key] == "90.0"        # canned_verdict sub-scores


def test_run_eval_skips_failing_row_without_aborting(monkeypatch, capsys):
    from clean_recipe.score import NotARecipeError

    golden = [
        evaluate.GoldenRow(recipe_id="g1", title="Clean Bowl",
                           raw_ingredients="spinach", target_band="Clean", target_score=90),
        evaluate.GoldenRow(recipe_id="bad", title="Not Food",
                           raw_ingredients="lorem", target_band="Clean", target_score=90),
        evaluate.GoldenRow(recipe_id="g3", title="Also Clean",
                           raw_ingredients="kale", target_band="Clean", target_score=90),
    ]

    def flaky(title, ingredients, **k):
        if title == "Not Food":
            raise NotARecipeError("nope")
        return canned_verdict(90, "Clean")

    monkeypatch.setattr(evaluate, "score_recipe", flaky)

    results = evaluate.run_eval(golden, model="fake-model")
    # The bad row is skipped, not fatal — the other two still score.
    assert [r.recipe_id for r in results] == ["g1", "g3"]
    assert "skipping 'bad'" in capsys.readouterr().err


def test_run_eval_progress_heartbeat(monkeypatch, capsys):
    golden = [
        evaluate.GoldenRow(recipe_id="g1", title="Bowl",
                           raw_ingredients="kale", target_band="Clean", target_score=90),
        evaluate.GoldenRow(recipe_id="g2", title="Soup",
                           raw_ingredients="water", target_band="Clean", target_score=90),
    ]
    monkeypatch.setattr(evaluate, "score_recipe", lambda *a, **k: canned_verdict(90, "Clean"))

    # Default: no heartbeat (keeps test/library output quiet).
    evaluate.run_eval(golden, model="fake")
    assert "scoring" not in capsys.readouterr().err

    # progress=True: one stderr line per row, numbered.
    evaluate.run_eval(golden, model="fake", progress=True)
    err = capsys.readouterr().err
    assert "[1/2] scoring 'g1'" in err
    assert "[2/2] scoring 'g2'" in err


def test_main_smoke(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(evaluate, "score_recipe", lambda *a, **k: canned_verdict(90, "Clean"))
    monkeypatch.setattr(evaluate, "RESULTS_DIR", tmp_path / "results")
    evaluate.main(["--model", "fake-model", "--limit", "1"])
    out = capsys.readouterr().out
    assert "Band accuracy:" in out
    assert "fake-model" in out
    assert (tmp_path / "results").exists()
