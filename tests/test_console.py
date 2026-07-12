"""UI tests for console.py via streamlit's AppTest — no live model or network.

Paths are redirected through the COCOON_* env vars (console.py's test seam);
``score_recipe`` is monkeypatched at its source module (the console re-imports
it on every AppTest run, so the patch takes effect — same pattern as
tests/test_app.py)."""
from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from clean_recipe import golden
from clean_recipe.log import log_verdict
from clean_recipe.schema import SubScores, Swap, Verdict

ROOT = Path(__file__).resolve().parents[1]
CONSOLE_PATH = str(ROOT / "console.py")


def make_verdict(score: int = 72, band: str = "Mostly Clean") -> Verdict:
    return Verdict(
        score=score,
        band=band,
        sub_scores=SubScores(
            ultra_processing=70,
            added_sugar=80,
            fat_quality=65,
            sodium_preservatives=60,
            whole_food_ratio=75,
            additive_count=90,
        ),
        flagged_ingredients=["butter"],
        swaps=[
            Swap(from_ingredient="butter", to_ingredient="olive oil", reason="better fat"),
        ],
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Empty log/results dirs + a header-only golden CSV, wired via env vars."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    golden_csv = tmp_path / "golden_set.csv"
    with golden_csv.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(golden.GOLDEN_COLUMNS)
    monkeypatch.setenv("COCOON_LOG_DIR", str(log_dir))
    monkeypatch.setenv("COCOON_GOLDEN_CSV", str(golden_csv))
    monkeypatch.setenv("COCOON_RESULTS_DIR", str(results_dir))
    return SimpleNamespace(
        log_dir=log_dir,
        log_file=log_dir / "verdicts.jsonl",
        golden_csv=golden_csv,
        results_dir=results_dir,
    )


def run_console() -> AppTest:
    return AppTest.from_file(CONSOLE_PATH, default_timeout=10).run()


def fill_author_form(at: AppTest, recipe_id="real-01", band="Clean", score=90) -> AppTest:
    at.text_input(key="author_recipe_id").set_value(recipe_id)
    at.text_input(key="author_title").set_value("Real Soup")
    at.text_area(key="author_raw").set_value("water; salt")
    if band is not None:
        at.selectbox(key="author_band").select(band)
    if score is not None:
        at.number_input(key="author_score").set_value(score)
    return at


# ---- smoke / empty states ------------------------------------------------------

def test_smoke_empty_everything(env):
    at = run_console()
    assert not at.exception
    # Logs, Label-from-log, and Results tabs each show a friendly empty state.
    assert len(at.info) >= 3
    # The author form is available even with zero logs (author mode needs none).
    assert at.button(key="author_save")


# ---- logs tab --------------------------------------------------------------------

def test_logs_tab_lists_records_and_counts_malformed(env):
    log_verdict("First Cookies", ["butter"], make_verdict(), path=env.log_file)
    log_verdict("Second Salad", ["kale"], make_verdict(90, "Clean"), path=env.log_file)
    with env.log_file.open("a", encoding="utf-8") as f:
        f.write("{corrupt line\n")

    at = run_console()
    assert not at.exception
    assert any("1 malformed" in c.value for c in at.caption)
    assert any("2 verdicts" in c.value for c in at.caption)


# ---- author tab --------------------------------------------------------------------

def test_author_happy_path_appends_one_valid_row(env):
    at = fill_author_form(run_console())
    at.button(key="author_save").click().run()

    assert at.success, "expected a success message after save"
    (row,) = golden.load_golden(env.golden_csv)
    assert row.recipe_id == "real-01"
    assert row.title == "Real Soup"
    assert row.ingredients == ["water", "salt"]
    assert row.target_band == "Clean" and row.target_score == 90
    assert row.swap_quality is None  # optional in author mode


def test_author_missing_band_and_score_blocked(env):
    at = fill_author_form(run_console(), band=None, score=None)
    at.button(key="author_save").click().run()

    assert any("target_band" in e.value for e in at.error)
    assert any("target_score" in e.value for e in at.error)
    # Nothing written: the CSV is still header-only.
    assert env.golden_csv.read_text(encoding="utf-8").count("\n") == 1


def test_author_duplicate_recipe_id_blocked(env):
    golden.append_golden_row(
        golden.GoldenRow(
            recipe_id="dup-01",
            title="Already There",
            raw_ingredients="water",
            target_band="Clean",
            target_score=95,
        ),
        env.golden_csv,
    )
    at = fill_author_form(run_console(), recipe_id="dup-01")
    at.button(key="author_save").click().run()

    assert any("already exists" in e.value for e in at.error)
    assert len(golden.load_golden(env.golden_csv)) == 1  # unchanged


def test_author_prescore_uses_log_false_and_prefills_as_suggestion(env, monkeypatch):
    calls = {}

    def fake_score(title, ingredients, **kwargs):
        calls["title"] = title
        calls["kwargs"] = kwargs
        return make_verdict(score=48, band="Processed")

    monkeypatch.setattr("clean_recipe.score.score_recipe", fake_score)

    at = run_console()
    at.text_area(key="author_text").set_value("Test Soup\nwater\nsalt")
    at.button(key="author_prescore").click()
    at.run()

    assert calls["title"] == "Test Soup"
    assert calls["kwargs"]["log"] is False  # never pollutes the verdict log
    assert any("Model suggestion" in i.value for i in at.info)
    # Model output lands as editable pre-fill, visibly marked.
    assert at.selectbox(key="author_band").value == "Processed"
    assert at.number_input(key="author_score").value == 48
    assert at.text_input(key="author_swaps").value == "butter>olive oil"
    assert at.text_input(key="author_title").value == "Test Soup"


# ---- label-from-log tab ---------------------------------------------------------------

def test_label_from_log_prefills_and_requires_swap_quality(env):
    log_verdict("Logged Cookies", ["butter", "sugar"], make_verdict(), path=env.log_file)

    at = run_console()
    at.button(key="label_load").click().run()

    # Form pre-filled from the logged record, marked as a suggestion.
    assert at.text_input(key="label_title").value == "Logged Cookies"
    assert at.text_area(key="label_raw").value == "butter; sugar"
    assert at.selectbox(key="label_band").value == "Mostly Clean"
    assert at.number_input(key="label_score").value == 72
    assert at.text_input(key="label_swaps").value == "butter>olive oil"

    # swap_quality is required in this mode: save without it is blocked.
    at.button(key="label_save").click().run()
    assert any("swap_quality" in e.value for e in at.error)
    assert env.golden_csv.read_text(encoding="utf-8").count("\n") == 1

    at.selectbox(key="label_quality").select(4)
    at.button(key="label_save").click().run()
    assert at.success
    (row,) = golden.load_golden(env.golden_csv)
    assert row.title == "Logged Cookies"
    assert row.swap_quality == 4
    assert row.source == "pasted"  # log records don't store source


# ---- results tab ----------------------------------------------------------------------

def test_results_tab_renders_read_only_summary(env):
    out = env.results_dir / "eval-20260712-000000-fake.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["recipe_id", "target_band", "predicted_band", "band_correct",
             "target_score", "predicted_score", "abs_error"]
        )
        writer.writerow(["g1", "Clean", "Clean", "True", "90", "90", "0"])
        writer.writerow(["g2", "Clean", "Processed", "False", "90", "50", "40"])

    at = run_console()
    assert not at.exception
    assert any("band accuracy 50.0%" in c.value for c in at.caption)
    assert any("MAE 20.00" in c.value for c in at.caption)
