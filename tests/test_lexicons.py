"""lexicons.py: load/write round-trip, sanitization, tiering, merged-rubric wiring.

Contents of the lists are human-owned; these tests only exercise transport,
normalization, and the flat/tiered shapes — never assert a specific curated
marker belongs to a specific list or tier.
"""
from clean_recipe import lexicons

FLAT_KEY = "nova4_markers"
TIERED_KEY = "added_sugar_markers"


def test_load_missing_file_returns_all_keys(tmp_path):
    got = lexicons.load_lexicons(tmp_path / "nope.yaml")
    assert set(got) == set(lexicons.LEXICON_KEYS)
    # flat → empty list; tiered → dict with every tier level present, all empty
    assert got[FLAT_KEY] == []
    tiered = got[TIERED_KEY]
    assert isinstance(tiered, dict)
    spec = lexicons.spec_for(TIERED_KEY)
    assert set(tiered) == {t.level for t in spec.tiers}
    assert all(v == [] for v in tiered.values())


def test_flat_round_trip(tmp_path):
    path = tmp_path / "lexicons.yaml"
    saved = lexicons.write_lexicons({FLAT_KEY: ["hot dog", "corn syrup"]}, path)
    assert saved[FLAT_KEY] == ["hot dog", "corn syrup"]
    assert lexicons.load_lexicons(path)[FLAT_KEY] == ["hot dog", "corn syrup"]


def test_tiered_round_trip(tmp_path):
    path = tmp_path / "lexicons.yaml"
    saved = lexicons.write_lexicons(
        {TIERED_KEY: {5: ["monk fruit"], 1: ["hfcs", "aspartame"]}}, path
    )
    assert saved[TIERED_KEY][5] == ["monk fruit"]
    assert saved[TIERED_KEY][1] == ["hfcs", "aspartame"]
    reloaded = lexicons.load_lexicons(path)[TIERED_KEY]
    assert reloaded[5] == ["monk fruit"]
    assert reloaded[1] == ["hfcs", "aspartame"]
    # untouched tiers come back empty
    assert reloaded[3] == []


def test_tiered_dedupes_to_worst_tier(tmp_path):
    path = tmp_path / "lexicons.yaml"
    # "honey" listed in both a better (4) and worse (2) tier resolves to worst.
    saved = lexicons.write_lexicons(
        {TIERED_KEY: {4: ["honey", "maple syrup"], 2: ["honey"]}}, path
    )
    assert "honey" not in saved[TIERED_KEY][4]
    assert saved[TIERED_KEY][2] == ["honey"]
    assert saved[TIERED_KEY][4] == ["maple syrup"]


def test_tiered_accepts_string_tier_keys(tmp_path):
    # yaml hand-edits may carry string keys; load must coerce.
    path = tmp_path / "lexicons.yaml"
    path.write_text("added_sugar_markers:\n  '5':\n  - monk fruit\n", encoding="utf-8")
    assert lexicons.load_lexicons(path)[TIERED_KEY][5] == ["monk fruit"]


def test_write_emits_human_owned_header(tmp_path):
    path = tmp_path / "lexicons.yaml"
    lexicons.write_lexicons({FLAT_KEY: ["x"]}, path)
    text = path.read_text(encoding="utf-8")
    assert "HUMAN-OWNED" in text
    assert f"v{lexicons.LEXICON_VERSION}" in text


def test_sanitize_strips_dedupes_and_collapses_whitespace(tmp_path):
    path = tmp_path / "lexicons.yaml"
    saved = lexicons.write_lexicons(
        {FLAT_KEY: ["  corn   syrup ", "corn syrup", "CORN SYRUP", "", "hot\ndog"]},
        path,
    )
    assert saved[FLAT_KEY] == ["corn syrup", "hot dog"]


def test_write_ignores_unknown_keys(tmp_path):
    path = tmp_path / "lexicons.yaml"
    saved = lexicons.write_lexicons({"bogus": ["nope"], FLAT_KEY: ["ok"]}, path)
    assert "bogus" not in saved
    assert saved[FLAT_KEY] == ["ok"]


def test_load_tolerates_wrong_type_values(tmp_path):
    path = tmp_path / "lexicons.yaml"
    path.write_text("nova4_markers: not-a-list\n", encoding="utf-8")
    assert lexicons.load_lexicons(path)[FLAT_KEY] == []


def test_every_subscore_has_exactly_one_lexicon():
    from clean_recipe.schema import SubScores

    grounded = {spec.dimension for spec in lexicons.LEXICONS}
    assert grounded == set(SubScores.model_fields)
    assert len(lexicons.LEXICONS) == len(SubScores.model_fields)


def test_tiered_specs_have_full_ladders():
    for spec in lexicons.LEXICONS:
        if spec.tiered:
            levels = [t.level for t in spec.tiers]
            assert levels == [5, 4, 3, 2, 1], f"{spec.key} tier order"
            assert all(t.target for t in spec.tiers)
