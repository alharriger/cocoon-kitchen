"""rubric.yaml loads, has the required keys, and weights sum to 1.0."""
from pathlib import Path

import yaml

RUBRIC_PATH = Path(__file__).resolve().parents[1] / "rubric" / "rubric.yaml"

EXPECTED_WEIGHT_KEYS = {
    "ultra_processing",
    "added_sugar",
    "fat_quality",
    "sodium_preservatives",
    "whole_food_ratio",
    "additive_count",
}


def load_rubric():
    with RUBRIC_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_rubric_loads_as_mapping():
    assert isinstance(load_rubric(), dict)


def test_required_top_level_keys_present():
    r = load_rubric()
    for key in ("weights", "bands", "nova4_markers", "refined_seed_oils", "aliases"):
        assert key in r, f"missing rubric key: {key}"


def test_weight_keys_match_subscores():
    r = load_rubric()
    assert set(r["weights"]) == EXPECTED_WEIGHT_KEYS


def test_weights_sum_to_one():
    r = load_rubric()
    assert abs(sum(r["weights"].values()) - 1.0) < 1e-9


def test_bands_cover_all_four():
    r = load_rubric()
    assert set(r["bands"]) == {"Clean", "Mostly Clean", "Processed", "Ultra-processed"}
