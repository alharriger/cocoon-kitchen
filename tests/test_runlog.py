"""runlog.py: rubric fingerprinting, run-log appends, baseline round-trip, and
regression verdicts (Phase 6 Task 5). Pure file I/O on tmp paths — no network."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

# evals/ is not an installed package; put it on the path so we can import it.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "evals"))

import runlog  # noqa: E402


# ---- helpers ----------------------------------------------------------------

def record(**overrides) -> runlog.RunRecord:
    base = dict(
        timestamp="2026-07-20T12:00:00",
        kind="single",
        provider="",
        model="fake-model",
        rows=52,
        attempted=52,
        band_accuracy=0.60,
        score_mae=7.00,
        mean_signed_error=2.0,
        processed_correct=7,
        processed_total=12,
        rubric_version="v0.3",
        lexicon_version="v0.3",
        config_hash="abc123def0",
        results_csv="eval-x.csv",
        note="",
    )
    base.update(overrides)
    return runlog.RunRecord(**base)


# ---- rubric fingerprint -----------------------------------------------------

def test_fingerprint_reads_real_rubric_versions():
    fp = runlog.rubric_fingerprint()
    # The real files declare their schema versions in header comments.
    assert fp["rubric_version"].startswith("v")
    assert fp["lexicon_version"].startswith("v")
    assert len(fp["config_hash"]) == 10


def test_fingerprint_hash_changes_on_any_edit(tmp_path):
    rubric = tmp_path / "rubric.yaml"
    lex = tmp_path / "lexicons.yaml"
    rubric.write_text("# Rubric schema version: v0.3 (knob).\nweights: {}\n")
    lex.write_text("# Lexicon schema version: v0.3.\nnova4_markers: []\n")
    fp1 = runlog.rubric_fingerprint(rubric, lex)
    assert fp1["rubric_version"] == "v0.3"
    assert fp1["lexicon_version"] == "v0.3"

    # A content edit that does NOT touch the version comment still moves the
    # hash — that's the drift detector (curation without a version bump).
    lex.write_text("# Lexicon schema version: v0.3.\nnova4_markers: [maltodextrin]\n")
    fp2 = runlog.rubric_fingerprint(rubric, lex)
    assert fp2["lexicon_version"] == "v0.3"
    assert fp2["config_hash"] != fp1["config_hash"]


def test_fingerprint_parses_single_digit_versions(tmp_path):
    rubric = tmp_path / "rubric.yaml"
    lex = tmp_path / "lexicons.yaml"
    rubric.write_text("# Rubric schema version: v1\n")
    lex.write_text("# Lexicon schema version: v2.10.3.\n")
    fp = runlog.rubric_fingerprint(rubric, lex)
    assert fp["rubric_version"] == "v1"
    assert fp["lexicon_version"] == "v2.10.3"


def test_fingerprint_missing_file_is_unknown_not_crash(tmp_path):
    fp = runlog.rubric_fingerprint(tmp_path / "nope.yaml", tmp_path / "nada.yaml")
    assert fp["rubric_version"] == "unknown"
    assert fp["lexicon_version"] == "unknown"
    assert len(fp["config_hash"]) == 10


# ---- run log ----------------------------------------------------------------

def test_append_run_writes_header_once(tmp_path):
    log = tmp_path / "run_log.csv"
    runlog.append_run(record(), log)
    runlog.append_run(record(model="other-model"), log)
    with log.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert list(rows[0]) == runlog.RUN_LOG_COLUMNS
    assert rows[0]["model"] == "fake-model"
    assert rows[1]["model"] == "other-model"
    assert rows[0]["band_accuracy"] == "0.6000"
    assert rows[0]["score_mae"] == "7.00"


def test_append_run_defangs_formula_cells(tmp_path):
    log = tmp_path / "run_log.csv"
    runlog.append_run(record(note="=cmd|' /C calc'!A0", model="=SUM(A1)"), log)
    with log.open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    # A leading space neutralizes the formula prefix (same guard as golden.py).
    assert row["note"].startswith(" =")
    assert row["model"].startswith(" =")


# ---- baseline ---------------------------------------------------------------

def test_baseline_roundtrip(tmp_path):
    path = tmp_path / "baseline.json"
    rec = record(note="seeded")
    runlog.write_baseline(rec, path)
    loaded = runlog.load_baseline(path)
    assert loaded == rec
    # Human-readable on disk (a tracked, reviewable artifact).
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["model"] == "fake-model"


def test_load_baseline_missing_is_none(tmp_path):
    assert runlog.load_baseline(tmp_path / "nope.json") is None


def test_load_baseline_malformed_fails_loud(tmp_path):
    bad = tmp_path / "baseline.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        runlog.load_baseline(bad)


def test_load_baseline_schema_drift_names_the_fix(tmp_path):
    # A baseline written by an older/newer RunRecord must fail with the
    # re-seed instruction, not a bare TypeError at the end of a good run.
    stale = tmp_path / "baseline.json"
    stale.write_text(json.dumps({"timestamp": "t", "bogus_old_field": 1}))
    with pytest.raises(ValueError, match="--update-baseline"):
        runlog.load_baseline(stale)


# ---- comparison verdicts ----------------------------------------------------

def test_compare_within_noise():
    base = record()
    run = record(band_accuracy=0.61, score_mae=7.50)  # +1pp, +0.5 MAE
    verdict, lines = runlog.compare_to_baseline(run, base)
    assert verdict == "within-noise"
    assert any("noise floor" in ln for ln in lines)


def test_compare_regression_on_band_drop():
    verdict, lines = runlog.compare_to_baseline(record(band_accuracy=0.55), record())
    assert verdict == "regression"
    assert any("REGRESSION" in ln for ln in lines)


def test_compare_regression_on_mae_rise():
    verdict, _ = runlog.compare_to_baseline(record(score_mae=8.5), record())
    assert verdict == "regression"


def test_compare_mixed_reads_as_regression():
    # Band improved beyond noise but MAE regressed beyond noise → regression wins.
    verdict, _ = runlog.compare_to_baseline(
        record(band_accuracy=0.70, score_mae=8.5), record()
    )
    assert verdict == "regression"


def test_compare_improved():
    verdict, lines = runlog.compare_to_baseline(record(band_accuracy=0.65), record())
    assert verdict == "improved"
    assert any("--update-baseline" in ln for ln in lines)


def test_compare_different_model_is_incomparable():
    verdict, lines = runlog.compare_to_baseline(record(model="gpt-4o-mini"), record())
    assert verdict == "incomparable"
    assert any("bake-off" in ln for ln in lines)


def test_compare_calls_out_rubric_change():
    run = record(config_hash="ffffffffff")
    _, lines = runlog.compare_to_baseline(run, record())
    assert any("rubric/lexicons changed" in ln for ln in lines)


def test_compare_notes_partial_coverage():
    run = record(rows=48)  # 48/52 scored — skips make it approximate
    _, lines = runlog.compare_to_baseline(run, record())
    assert any("48/52" in ln for ln in lines)
