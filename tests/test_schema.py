"""Verdict schema: valid input parses; malformed input fails loudly."""
import pytest
from pydantic import ValidationError

from clean_recipe.schema import SubScores, Verdict


def valid_verdict_dict():
    return {
        "score": 72,
        "band": "Mostly Clean",
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
            {
                "from_ingredient": "butter",
                "to_ingredient": "olive oil",
                "reason": "swap saturated for unsaturated fat",
            }
        ],
    }


def test_valid_verdict_parses():
    v = Verdict.model_validate(valid_verdict_dict())
    assert v.score == 72
    assert v.band == "Mostly Clean"
    assert isinstance(v.sub_scores, SubScores)
    assert v.sub_scores.ultra_processing == 70
    assert v.swaps[0].to_ingredient == "olive oil"


def test_missing_top_level_field_fails_loudly():
    d = valid_verdict_dict()
    del d["sub_scores"]
    with pytest.raises(ValidationError):
        Verdict.model_validate(d)


def test_missing_subscore_field_fails_loudly():
    d = valid_verdict_dict()
    del d["sub_scores"]["added_sugar"]
    with pytest.raises(ValidationError):
        Verdict.model_validate(d)


def test_bad_band_literal_fails_loudly():
    d = valid_verdict_dict()
    d["band"] = "Squeaky Clean"
    with pytest.raises(ValidationError):
        Verdict.model_validate(d)


def test_wrong_type_fails_loudly():
    d = valid_verdict_dict()
    d["score"] = "not a number"
    with pytest.raises(ValidationError):
        Verdict.model_validate(d)


def test_malformed_swap_fails_loudly():
    d = valid_verdict_dict()
    d["swaps"] = [{"from_ingredient": "butter"}]  # missing to_ingredient + reason
    with pytest.raises(ValidationError):
        Verdict.model_validate(d)


def test_out_of_range_subscore_fails_loudly():
    d = valid_verdict_dict()
    d["sub_scores"]["ultra_processing"] = 150  # > 100
    with pytest.raises(ValidationError):
        Verdict.model_validate(d)


def test_negative_subscore_fails_loudly():
    d = valid_verdict_dict()
    d["sub_scores"]["added_sugar"] = -5  # < 0
    with pytest.raises(ValidationError):
        Verdict.model_validate(d)
