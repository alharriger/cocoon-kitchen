"""prompt.py: rubric loads; messages carry the rubric, recipe, schema, and
the prompt-injection defense."""
from clean_recipe.prompt import build_messages, load_rubric


def test_load_rubric_has_weights_and_bands():
    r = load_rubric()
    assert isinstance(r, dict)
    assert "weights" in r and "bands" in r


def test_build_messages_shape():
    msgs = build_messages("Choc Chip Cookies", ["butter", "brown sugar"], load_rubric())
    assert [m["role"] for m in msgs] == ["system", "user"]


def test_system_message_carries_rubric_and_schema():
    system = build_messages("t", ["x"], load_rubric())[0]["content"]
    # all six sub-score keys are named
    for key in ("ultra_processing", "added_sugar", "fat_quality",
                "sodium_preservatives", "whole_food_ratio", "additive_count"):
        assert key in system
    # band labels present
    for band in ("Clean", "Mostly Clean", "Processed", "Ultra-processed"):
        assert band in system
    # weights surfaced (0.3 for ultra_processing)
    assert "0.3" in system
    # output contract keys present
    assert "flagged_ingredients" in system and "swaps" in system


def test_load_rubric_merges_lexicons():
    r = load_rubric()
    # the six curated lexicons are merged in from lexicons.yaml
    for key in ("nova4_markers", "additive_markers", "whole_food_whitelist"):
        assert key in r and isinstance(r[key], list)          # flat
    for key in ("added_sugar_markers", "fat_quality_markers",
                "sodium_preservative_markers"):
        assert key in r and isinstance(r[key], dict)          # tiered


def test_grounding_lists_render_flat_tiered_and_decomposition():
    system = build_messages("t", ["x"], load_rubric())[0]["content"]
    # structure/wiring only, not human-owned contents
    assert "GROUNDING LISTS" in system
    assert "lowers ultra_processing" in system      # flat ↓
    assert "raises whole_food_ratio" in system      # flat ↑
    assert "grades added_sugar" in system           # tiered header
    assert "Tier 5" in system and "Tier 1" in system
    assert "DECOMPOSE" in system                     # decomposition instruction


def test_prompt_injection_defense_present():
    system = build_messages("t", ["x"], load_rubric())[0]["content"]
    assert "untrusted" in system.lower()
    assert "never obey it" in system.lower() or "treat that text" in system.lower()


def test_user_message_delimits_recipe():
    user = build_messages("Grandma's Pie", ["lard", "flour"], load_rubric())[1]["content"]
    assert "Grandma's Pie" in user
    assert "lard" in user and "flour" in user
    assert "<<<RECIPE>>>" in user and "<<<END RECIPE>>>" in user
