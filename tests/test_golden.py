"""clean_recipe.golden: the Contract-4 golden-row shape, validation, and the
console's append-only write path. Pure — no Streamlit, no network."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest
from pydantic import ValidationError

from clean_recipe import golden
from clean_recipe.schema import SubScores, Swap, Verdict

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_GOLDEN = REPO_ROOT / "evals" / "golden_set.csv"


def row(**overrides) -> golden.GoldenRow:
    base = dict(
        recipe_id="test-01",
        source="pasted",
        title="Test Soup",
        raw_ingredients="water; salt",
        target_band="Clean",
        target_score=90,
    )
    base.update(overrides)
    return golden.GoldenRow(**base)


def seed_csv(path: Path, rows: list[golden.GoldenRow] = ()) -> Path:
    """Write a valid Contract-4 file: header + optional rows."""
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(golden.GOLDEN_COLUMNS)
    for r in rows:
        golden.append_golden_row(r, path)
    return path


# ---- the contract itself -----------------------------------------------------

def test_golden_columns_are_contract_4_v02():
    assert golden.GOLDEN_COLUMNS == [
        "recipe_id",
        "source",
        "title",
        "raw_ingredients",
        "target_band",
        "target_score",
        "expected_swaps",
        "swap_quality",
        "notes",
    ]


def test_shipped_template_validates():
    rows = golden.load_golden(SHIPPED_GOLDEN)
    assert len(rows) >= 2
    # The template demonstrates both a graded and an ungraded row.
    qualities = {r.swap_quality for r in rows}
    assert None in qualities and any(q is not None for q in qualities)


# ---- GoldenRow validation ----------------------------------------------------

def test_row_happy_path_defaults():
    r = row()
    assert r.source == "pasted"
    assert r.expected_swaps == "" and r.notes == ""
    assert r.swap_quality is None
    assert r.ingredients == ["water", "salt"]


@pytest.mark.parametrize("band", ["clean", "Sparkling", ""])
def test_bad_band_rejected(band):
    with pytest.raises(ValidationError):
        row(target_band=band)


@pytest.mark.parametrize("score", [-1, 101])
def test_score_out_of_range_rejected(score):
    with pytest.raises(ValidationError):
        row(target_score=score)


@pytest.mark.parametrize("quality", [0, 6])
def test_swap_quality_out_of_range_rejected(quality):
    with pytest.raises(ValidationError):
        row(swap_quality=quality)


def test_swap_quality_none_and_valid_accepted():
    assert row(swap_quality=None).swap_quality is None
    assert row(swap_quality=5).swap_quality == 5


@pytest.mark.parametrize("field", ["recipe_id", "title", "raw_ingredients"])
def test_required_fields_nonempty(field):
    with pytest.raises(ValidationError):
        row(**{field: "   "})


def test_raw_ingredients_must_contain_an_ingredient():
    with pytest.raises(ValidationError):
        row(raw_ingredients=" ; ; ")


@pytest.mark.parametrize(
    "swaps", ["a>b", "a>b; c>d", "a > b ;  c > d", "a>b;", ""]
)
def test_expected_swaps_good_formats(swaps):
    assert row(expected_swaps=swaps).expected_swaps == swaps.strip()


@pytest.mark.parametrize("swaps", ["a", "a>", ">b", "a>b>c", "a>b; c"])
def test_expected_swaps_bad_formats_rejected(swaps):
    with pytest.raises(ValidationError):
        row(expected_swaps=swaps)


# ---- micro-format helpers ----------------------------------------------------

def test_parse_join_ingredients_round_trip():
    items = ["olive oil", "spinach", "sea salt"]
    assert golden.parse_ingredients(golden.join_ingredients(items)) == items


def test_join_ingredients_sanitizes_delimiter():
    joined = golden.join_ingredients(["weird; name", "salt"])
    assert golden.parse_ingredients(joined) == ["weird, name", "salt"]


def test_format_swaps_output_revalidates():
    swaps = [
        Swap(from_ingredient="palm oil", to_ingredient="olive oil", reason="r"),
        Swap(from_ingredient="odd>name; x", to_ingredient="plain", reason="r"),
    ]
    formatted = golden.format_swaps(swaps)
    # Sanitized names keep the from>to; from>to micro-format parseable.
    assert row(expected_swaps=formatted).expected_swaps == formatted
    assert formatted == "palm oil>olive oil; odd,name, x>plain"


def test_suggest_recipe_id_slugs_and_suffixes():
    assert golden.suggest_recipe_id("Grandma's French Onion Soup!", set()) == (
        "grandma-s-french-onion-soup"
    )
    assert golden.suggest_recipe_id("Soup", {"soup"}) == "soup-2"
    assert golden.suggest_recipe_id("Soup", {"soup", "soup-2"}) == "soup-3"
    assert golden.suggest_recipe_id("!!!", set()) == "recipe"
    assert len(golden.suggest_recipe_id("x" * 200, set())) <= 40


@pytest.mark.parametrize("value", ["=SUM(A1)", "+1", "-1", "@cmd", "\tx", "\rx"])
def test_defang_cell_neutralizes_formula_prefixes(value):
    defanged = golden.defang_cell(value)
    assert defanged.startswith(" ")
    assert defanged.strip() == value.strip()  # lossless after load's strip


def test_defang_cell_leaves_plain_text_alone():
    assert golden.defang_cell("plain title") == "plain title"


# ---- load_golden ---------------------------------------------------------------

def test_load_golden_happy_path_incl_blank_quality(tmp_path):
    path = seed_csv(
        tmp_path / "g.csv",
        [row(), row(recipe_id="test-02", swap_quality=3, expected_swaps="a>b")],
    )
    rows = golden.load_golden(path)
    assert [r.swap_quality for r in rows] == [None, 3]
    assert rows[0].ingredients == ["water", "salt"]


def test_load_golden_wrong_header_fails_loud(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("wrong,header\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Contract 4"):
        golden.load_golden(bad)


def test_load_golden_bad_row_names_the_line(tmp_path):
    bad = tmp_path / "bad.csv"
    header = ",".join(golden.GOLDEN_COLUMNS)
    bad.write_text(
        f"{header}\nok,pasted,Soup,water,Clean,90,,,\n"
        "bad,pasted,Junk,hfcs,NotABand,10,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 3"):
        golden.load_golden(bad)


def test_load_golden_empty_fails_loud(tmp_path):
    path = seed_csv(tmp_path / "empty.csv")
    with pytest.raises(ValueError, match="no data rows"):
        golden.load_golden(path)


# ---- append_golden_row (the only write path) -----------------------------------

def test_append_exact_column_order_and_round_trip(tmp_path):
    path = seed_csv(tmp_path / "g.csv")
    tricky = row(
        title='Comma, "quote"',
        raw_ingredients="olive oil; spinach",
        notes="line one\nline two",
        expected_swaps="a>b; c>d",
        swap_quality=4,
    )
    count = golden.append_golden_row(tricky, path)
    assert count == 1

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        assert next(reader) == golden.GOLDEN_COLUMNS

    (loaded,) = golden.load_golden(path)
    assert loaded == tricky  # commas/quotes/newlines survive csv quoting


def test_append_returns_growing_count(tmp_path):
    path = seed_csv(tmp_path / "g.csv", [row()])
    assert golden.append_golden_row(row(recipe_id="test-02"), path) == 2


def test_append_defangs_formula_cells(tmp_path):
    path = seed_csv(tmp_path / "g.csv")
    golden.append_golden_row(row(title="=HYPERLINK(evil)"), path)
    raw = path.read_text(encoding="utf-8")
    assert "=HYPERLINK" in raw and '"=HYPERLINK' not in raw.replace('" =', "")
    # The written cell starts with a space, and load strips it back.
    assert " =HYPERLINK(evil)" in raw
    (loaded,) = golden.load_golden(path)
    assert loaded.title == "=HYPERLINK(evil)"


def test_append_refuses_stale_header(tmp_path):
    stale = tmp_path / "stale.csv"
    stale.write_text("recipe_id,source,title\n", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to append"):
        golden.append_golden_row(row(), stale)


def test_append_never_creates_a_file(tmp_path):
    missing = tmp_path / "missing.csv"
    with pytest.raises(ValueError, match="never creates"):
        golden.append_golden_row(row(), missing)
    assert not missing.exists()


def test_append_handles_missing_trailing_newline(tmp_path):
    path = seed_csv(tmp_path / "g.csv", [row()])
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
    golden.append_golden_row(row(recipe_id="test-02"), path)
    assert [r.recipe_id for r in golden.load_golden(path)] == ["test-01", "test-02"]


def test_existing_recipe_ids(tmp_path):
    path = seed_csv(tmp_path / "g.csv", [row(), row(recipe_id="test-02")])
    assert golden.existing_recipe_ids(path) == {"test-01", "test-02"}


# ---- backlog -------------------------------------------------------------------

def backlog_entry(**overrides) -> golden.BacklogEntry:
    base = dict(recipe_id="soup-01", title="Soup", ingredients=["water", "salt"])
    base.update(overrides)
    return golden.BacklogEntry(**base)


def test_backlog_entry_defaults_and_raw_ingredients():
    e = backlog_entry()
    assert e.status == "open" and e.source == "pasted"
    assert e.raw_ingredients == "water; salt"


@pytest.mark.parametrize("field", ["recipe_id", "title"])
def test_backlog_entry_required_fields(field):
    with pytest.raises(ValidationError):
        backlog_entry(**{field: "  "})


def test_backlog_entry_needs_an_ingredient():
    with pytest.raises(ValidationError):
        backlog_entry(ingredients=[])


def test_backlog_round_trip_and_missing_file(tmp_path):
    path = tmp_path / "backlog.jsonl"
    assert golden.read_backlog(path) == []  # missing file → empty, no error
    golden.write_backlog(
        [backlog_entry(), backlog_entry(recipe_id="soup-02", status="submitted")], path
    )
    loaded = golden.read_backlog(path)
    assert [e.recipe_id for e in loaded] == ["soup-01", "soup-02"]
    assert [e.status for e in loaded] == ["open", "submitted"]


def test_read_backlog_skips_malformed_line(tmp_path):
    path = tmp_path / "backlog.jsonl"
    golden.write_backlog([backlog_entry()], path)
    with path.open("a", encoding="utf-8") as f:
        f.write("{not json\n")
        f.write('{"recipe_id": "x"}\n')  # valid json, missing required fields
    assert [e.recipe_id for e in golden.read_backlog(path)] == ["soup-01"]


# ---- drafts + promote ----------------------------------------------------------

def make_verdict() -> Verdict:
    return Verdict(
        score=48,
        band="Processed",
        sub_scores=SubScores(
            ultra_processing=40, added_sugar=30, fat_quality=70,
            sodium_preservatives=70, whole_food_ratio=40, additive_count=50,
        ),
        flagged_ingredients=["sugar"],
        swaps=[Swap(from_ingredient="butter", to_ingredient="olive oil", reason="fat")],
    )


def draft(recipe_id="draft-01", status="draft", **row_overrides) -> golden.GoldenDraft:
    return golden.GoldenDraft(
        row=row(recipe_id=recipe_id, **row_overrides),
        model_verdict=make_verdict(),
        status=status,
    )


def test_draft_round_trip_preserves_verdict(tmp_path):
    path = tmp_path / "drafts.jsonl"
    assert golden.read_drafts(path) == ([], 0)
    golden.append_draft(draft(), path)
    golden.append_draft(draft(recipe_id="draft-02", status="approved"), path)
    drafts, skipped = golden.read_drafts(path)
    assert skipped == 0
    assert [d.row.recipe_id for d in drafts] == ["draft-01", "draft-02"]
    assert drafts[0].model_verdict == make_verdict()
    assert drafts[1].status == "approved"


def test_read_drafts_skips_malformed(tmp_path):
    path = tmp_path / "drafts.jsonl"
    golden.append_draft(draft(), path)
    with path.open("a", encoding="utf-8") as f:
        f.write("garbage\n")
    drafts, skipped = golden.read_drafts(path)
    assert len(drafts) == 1 and skipped == 1


def test_write_drafts_rewrites_after_edit(tmp_path):
    path = tmp_path / "drafts.jsonl"
    golden.write_drafts([draft(), draft(recipe_id="draft-02")], path)
    drafts, _ = golden.read_drafts(path)
    drafts[0].status = "approved"
    drafts[0].row.swap_quality = 5
    golden.write_drafts(drafts, path)
    reloaded, _ = golden.read_drafts(path)
    assert reloaded[0].status == "approved" and reloaded[0].row.swap_quality == 5


def test_promote_only_approved_and_dedups(tmp_path):
    golden_csv = seed_csv(tmp_path / "golden.csv")
    drafts = [
        draft(recipe_id="d-approved", status="approved"),
        draft(recipe_id="d-draft", status="draft"),  # not approved → skipped
        draft(recipe_id="d-approved-2", status="approved"),
    ]
    promoted, skipped = golden.promote_approved(drafts, golden_csv)
    assert promoted == ["d-approved", "d-approved-2"]
    assert skipped == []
    assert golden.existing_recipe_ids(golden_csv) == {"d-approved", "d-approved-2"}

    # Re-running is a safe no-op: already-promoted ids are skipped as dupes.
    promoted2, skipped2 = golden.promote_approved(drafts, golden_csv)
    assert promoted2 == []
    assert set(skipped2) == {"d-approved", "d-approved-2"}


def test_promote_row_lands_in_contract4_shape(tmp_path):
    golden_csv = seed_csv(tmp_path / "golden.csv")
    d = draft(recipe_id="fettuccine-alfredo", swap_quality=2, expected_swaps="a>b")
    d.status = "approved"
    golden.promote_approved([d], golden_csv)
    (loaded,) = golden.load_golden(golden_csv)
    assert loaded.recipe_id == "fettuccine-alfredo"
    assert loaded.swap_quality == 2 and loaded.expected_swaps == "a>b"
