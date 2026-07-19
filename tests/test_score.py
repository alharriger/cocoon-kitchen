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
    # No alpha passed => alpha defaults to 0.0 => pure weighted mean (old behavior).
    assert compose_score(subs, RUBRIC["weights"]) == 72


# ---- penalty-sensitive composition (Option 1: worst-dimension pull) ----------

def test_compose_score_alpha_zero_is_pure_weighted_mean():
    # alpha=0 must reduce EXACTLY to the old weighted mean — the regression guard
    # that keeps every pre-Task-3.5 composite unchanged.
    subs = SubScores.model_validate(model_output()["sub_scores"])
    assert compose_score(subs, RUBRIC["weights"], 0.0) == 72


def test_compose_score_alpha_pulls_toward_worst_axis():
    # weighted_mean 71.5, min sub-score 60 (sodium_preservatives).
    # 0.6*71.5 + 0.4*60 = 42.9 + 24 = 66.9 -> 67.
    subs = SubScores.model_validate(model_output()["sub_scores"])
    assert compose_score(subs, RUBRIC["weights"], 0.4) == 67


def test_severe_single_offender_drops_the_band():
    # Chicken + broccoli + artificial flavor: clean everywhere but one severe axis.
    # Pure weighted mean would read Clean (~83) and average the offender away; the
    # alpha pull must visibly tank it out of the Clean band.
    subs = SubScores.model_validate({
        "ultra_processing": 80,
        "added_sugar": 95,
        "fat_quality": 88,
        "sodium_preservatives": 85,
        "whole_food_ratio": 85,
        "additive_count": 20,  # artificial flavor
    })
    clean_mean = compose_score(subs, RUBRIC["weights"], 0.0)
    pulled = compose_score(subs, RUBRIC["weights"], 0.4)
    assert derive_band(clean_mean, RUBRIC["bands"]) == "Clean"
    assert pulled < clean_mean
    assert derive_band(pulled, RUBRIC["bands"]) == "Processed"


def test_uniformly_clean_recipe_stays_clean_under_alpha():
    # When min ~= mean there is nothing to pull, so a genuinely clean recipe is
    # not collateral damage: alpha only bites on a real spike.
    subs = SubScores.model_validate({k: 90 for k in (
        "ultra_processing", "added_sugar", "fat_quality",
        "sodium_preservatives", "whole_food_ratio", "additive_count")})
    assert compose_score(subs, RUBRIC["weights"], 0.4) == 90


def test_compose_score_clamps_alpha_to_unit_interval():
    # A malformed knob must not invert the blend. alpha>1 clamps to 1 (pure min),
    # alpha<0 clamps to 0 (pure weighted mean) — never anything in between broken.
    subs = SubScores.model_validate(model_output()["sub_scores"])
    worst = min(model_output()["sub_scores"].values())  # 60
    assert compose_score(subs, RUBRIC["weights"], 5.0) == worst
    assert compose_score(subs, RUBRIC["weights"], -1.0) == 72


def test_build_verdict_uses_rubric_alpha():
    # score_recipe -> _build_verdict must read composition.alpha from the rubric,
    # so the shipped composite is penalty-sensitive (not the raw weighted mean).
    assert RUBRIC.get("composition", {}).get("alpha") == 0.4


def test_empty_composition_block_degrades_to_weighted_mean(monkeypatch):
    # A present-but-empty `composition:` in rubric.yaml parses as None; scoring
    # must degrade to alpha=0.0 (old weighted mean), not crash on None.get().
    rubric = dict(RUBRIC)
    rubric["composition"] = None  # YAML `composition:` with no body
    monkeypatch.setattr(score_mod, "load_rubric", lambda *a, **k: rubric)
    monkeypatch.setattr(score_mod, "complete_json",
                        lambda *a, **k: json.dumps(model_output()))
    v = score_recipe("Cookies", ["butter"], log=False)
    assert v.score == 72  # pure weighted mean, alpha defaulted to 0.0


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
    # Through the rubric, composition.alpha=0.4 pulls toward the worst axis (60):
    # 0.6*71.5 + 0.4*60 = 66.9 -> 67 (still Mostly Clean).
    assert v.score == 67
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
