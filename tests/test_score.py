"""score.py: composition math, band derivation, and the score_recipe flow
(happy path, retry-once, fail-loud, logging) — all with a mocked client, no
network."""
import json

import pytest

from clean_recipe import score as score_mod
from clean_recipe.prompt import load_rubric
from clean_recipe.schema import SubScores, Verdict
from clean_recipe.score import (
    NotARecipeError,
    ScoringError,
    compose_score,
    derive_band,
    score_recipe,
)

RUBRIC = load_rubric()


def model_output(**overrides) -> dict:
    payload = {
        "is_recipe": True,
        "sub_scores": {
            "ultra_processing": 70,
            "added_sugar": 80,
            "fat_quality": 65,
            "sodium_preservatives": 60,
            "whole_food_ratio": 75,
            "additive_count": 90,
        },
        "flagged_ingredients": ["butter", "brown sugar"],
        "swaps": [
            {"from_ingredient": "butter", "to_ingredient": "olive oil", "reason": "unsaturated fat"},
            {"from_ingredient": "brown sugar", "to_ingredient": "date paste", "reason": "whole-food sweetener"},
            {"from_ingredient": "white flour", "to_ingredient": "oat flour", "reason": "less refined"},
        ],
    }
    payload.update(overrides)
    return payload


# ---- composition math -------------------------------------------------------

def test_compose_score_all_max_is_100():
    subs = SubScores.model_validate({k: 100 for k in (
        "ultra_processing", "added_sugar", "fat_quality",
        "sodium_preservatives", "whole_food_ratio", "additive_count")})
    assert compose_score(subs, RUBRIC["weights"]) == 100


def test_compose_score_all_zero_is_0():
    subs = SubScores.model_validate({k: 0 for k in (
        "ultra_processing", "added_sugar", "fat_quality",
        "sodium_preservatives", "whole_food_ratio", "additive_count")})
    assert compose_score(subs, RUBRIC["weights"]) == 0


def test_compose_score_weighted_mix():
    subs = SubScores.model_validate(model_output()["sub_scores"])
    # 0.30*70 + 0.20*80 + 0.15*65 + 0.15*60 + 0.15*75 + 0.05*90 = 71.5 -> 72
    assert compose_score(subs, RUBRIC["weights"]) == 72


@pytest.mark.parametrize("score,band", [
    (100, "Clean"), (80, "Clean"), (79, "Mostly Clean"), (60, "Mostly Clean"),
    (59, "Processed"), (40, "Processed"), (39, "Ultra-processed"), (0, "Ultra-processed"),
])
def test_derive_band_boundaries(score, band):
    assert derive_band(score, RUBRIC["bands"]) == band


# ---- score_recipe flow (mocked client) --------------------------------------

def test_happy_path_returns_verdict(monkeypatch):
    monkeypatch.setattr(score_mod, "complete_json", lambda *a, **k: json.dumps(model_output()))
    v = score_recipe("Cookies", ["butter", "brown sugar"], log=False)
    assert isinstance(v, Verdict)
    assert v.score == 72
    assert v.band == "Mostly Clean"
    assert len(v.swaps) == 3
    assert v.sub_scores.ultra_processing == 70


def test_retry_once_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        return "not json at all" if calls["n"] == 1 else json.dumps(model_output())

    monkeypatch.setattr(score_mod, "complete_json", flaky)
    v = score_recipe("Cookies", ["butter"], log=False)
    assert calls["n"] == 2  # failed once, retried, succeeded
    assert isinstance(v, Verdict)


def test_fails_loud_after_retry(monkeypatch):
    monkeypatch.setattr(score_mod, "complete_json", lambda *a, **k: "still not json")
    with pytest.raises(ScoringError):
        score_recipe("Cookies", ["butter"], log=False)


def test_missing_subscore_key_is_malformed(monkeypatch):
    bad = model_output()
    del bad["sub_scores"]["added_sugar"]
    monkeypatch.setattr(score_mod, "complete_json", lambda *a, **k: json.dumps(bad))
    with pytest.raises(ScoringError):
        score_recipe("Cookies", ["butter"], log=False)


def test_out_of_range_subscore_fails_loud_not_clamped(monkeypatch):
    # A flaky model returning 1000 must fail loud, not get silently clamped into
    # a clean-looking composite.
    bad = model_output()
    bad["sub_scores"]["ultra_processing"] = 1000
    monkeypatch.setattr(score_mod, "complete_json", lambda *a, **k: json.dumps(bad))
    with pytest.raises(ScoringError):
        score_recipe("Cookies", ["butter"], log=False)


def test_not_a_recipe_raises_and_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def not_recipe(*a, **k):
        calls["n"] += 1
        return json.dumps({"is_recipe": False})

    monkeypatch.setattr(score_mod, "complete_json", not_recipe)
    with pytest.raises(NotARecipeError):
        score_recipe("Job Posting", ["turkey sausage", "unlimited PTO"], log=False)
    assert calls["n"] == 1  # a valid judgment — no retry


def test_not_a_recipe_is_not_logged(monkeypatch):
    monkeypatch.setattr(score_mod, "complete_json",
                        lambda *a, **k: json.dumps({"is_recipe": False}))
    logged = {"n": 0}
    monkeypatch.setattr(score_mod, "log_verdict",
                        lambda *a, **k: logged.__setitem__("n", logged["n"] + 1))
    with pytest.raises(NotARecipeError):
        score_recipe("Not food", ["lorem ipsum"], log=True)
    assert logged["n"] == 0  # no verdict → nothing to log


def test_recipe_true_without_subscores_is_malformed(monkeypatch):
    # is_recipe true but no sub_scores → fail loud (retry-once, then ScoringError),
    # never a silent empty card.
    monkeypatch.setattr(score_mod, "complete_json",
                        lambda *a, **k: json.dumps({"is_recipe": True}))
    with pytest.raises(ScoringError):
        score_recipe("Cookies", ["butter"], log=False)


def test_recipe_missing_swaps_is_malformed(monkeypatch):
    # A recipe response that omits the swaps key must fail loud (not default to an
    # empty "Swaps to try" card) — the scoring fields are required when is_recipe.
    bad = model_output()
    del bad["swaps"]
    monkeypatch.setattr(score_mod, "complete_json", lambda *a, **k: json.dumps(bad))
    with pytest.raises(ScoringError):
        score_recipe("Cookies", ["butter"], log=False)


def test_repair_hint_mentions_is_recipe():
    # The corrective retry must ask for is_recipe; otherwise a compliant retry
    # omits the now-required field and validation fails, defeating retry-once.
    assert "is_recipe" in score_mod._REPAIR_HINT["content"]


def test_logs_when_enabled(monkeypatch):
    captured = {}
    monkeypatch.setattr(score_mod, "complete_json", lambda *a, **k: json.dumps(model_output()))
    monkeypatch.setattr(score_mod, "log_verdict",
                        lambda title, ingredients, verdict, **k: captured.update(
                            title=title, ingredients=ingredients, verdict=verdict))
    score_recipe("Cookies", ["butter", "sugar"], log=True)
    assert captured["title"] == "Cookies"
    assert captured["ingredients"] == ["butter", "sugar"]
    assert isinstance(captured["verdict"], Verdict)
