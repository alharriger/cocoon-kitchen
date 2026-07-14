"""UI tests for console.py via streamlit's AppTest — no live model or network.

Paths are redirected through the COCOON_* env vars (console.py's test seam).
score_recipe/parse_recipe are patched at their source modules when a test needs
them; console.py re-imports on every AppTest run so the patch takes effect
(same pattern as tests/test_app.py)."""
from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from clean_recipe import golden
from clean_recipe.log import log_verdict
from clean_recipe.parse import ParsedRecipe
from clean_recipe.schema import SubScores, Swap, Verdict

ROOT = Path(__file__).resolve().parents[1]
CONSOLE_PATH = str(ROOT / "console.py")


def make_verdict(score: int = 48, band: str = "Processed") -> Verdict:
    return Verdict(
        score=score, band=band,
        sub_scores=SubScores(
            ultra_processing=40, added_sugar=30, fat_quality=70,
            sodium_preservatives=70, whole_food_ratio=40, additive_count=50,
        ),
        flagged_ingredients=["sugar"],
        swaps=[Swap(from_ingredient="butter", to_ingredient="olive oil", reason="fat")],
    )


def make_draft(recipe_id="d-01", status="draft", swap_quality=None,
               band="Processed", score=48) -> golden.GoldenDraft:
    return golden.GoldenDraft(
        row=golden.GoldenRow(
            recipe_id=recipe_id, title="Test Dish", raw_ingredients="water; salt",
            target_band=band, target_score=score, swap_quality=swap_quality,
        ),
        model_verdict=make_verdict(),
        status=status,
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Empty log/results dirs, a header-only golden CSV, and pipeline file paths
    (backlog/drafts don't exist yet — the console creates them)."""
    log_dir = tmp_path / "logs"; log_dir.mkdir()
    results_dir = tmp_path / "results"; results_dir.mkdir()
    golden_csv = tmp_path / "golden_set.csv"
    with golden_csv.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(golden.GOLDEN_COLUMNS)
    backlog = tmp_path / "backlog.jsonl"
    drafts = tmp_path / "golden_drafts.jsonl"
    monkeypatch.setenv("COCOON_LOG_DIR", str(log_dir))
    monkeypatch.setenv("COCOON_GOLDEN_CSV", str(golden_csv))
    monkeypatch.setenv("COCOON_RESULTS_DIR", str(results_dir))
    monkeypatch.setenv("COCOON_BACKLOG", str(backlog))
    monkeypatch.setenv("COCOON_DRAFTS", str(drafts))
    return SimpleNamespace(
        log_file=log_dir / "verdicts.jsonl", golden_csv=golden_csv,
        results_dir=results_dir, backlog=backlog, drafts=drafts,
    )


def run_console() -> AppTest:
    return AppTest.from_file(CONSOLE_PATH, default_timeout=15).run()


def click_by_label(at: AppTest, label: str):
    """Click a button by its label (form-submit buttons get auto-generated keys)."""
    return next(b for b in at.button if b.label == label).click()


# ---- smoke -------------------------------------------------------------------

def test_smoke_empty_everything(env):
    at = run_console()
    assert not at.exception
    # Backlog, Review, Promote(no button but caption), Logs, Results empty states.
    assert len(at.info) >= 3


# ---- backlog -----------------------------------------------------------------

def test_backlog_paste_cleans_furniture_then_adds(env):
    at = run_console()
    at.text_input(key="bk_title").set_value("Chopped Cheese")
    at.text_area(key="bk_paste").set_value(
        "Ingredients\nDeselect All\nSauce:\n1/4 cup mayonnaise\n"
        "2 tablespoons ketchup\nDirections\nPreheat the oven and cook."
    )
    at.button(key="bk_parse").click().run()

    # Preview appears with the furniture stripped and directions cut.
    assert at.text_input(key="bk_prev_title").value == "Chopped Cheese"
    prev = at.text_area(key="bk_prev_ings").value
    assert "1/4 cup mayonnaise" in prev and "Directions" not in prev

    at.button(key="bk_add").click().run()
    (entry,) = golden.read_backlog(env.backlog)
    assert entry.title == "Chopped Cheese"
    assert entry.ingredients == ["1/4 cup mayonnaise", "2 tablespoons ketchup"]
    assert entry.status == "open" and entry.source == "pasted"


def test_backlog_preview_is_editable_before_add(env):
    at = run_console()
    at.text_input(key="bk_title").set_value("Soup")
    at.text_area(key="bk_paste").set_value("1 onion\n1 cup broth\nmystery line")
    at.button(key="bk_parse").click().run()
    # Amber removes a stray line in the preview before adding.
    at.text_area(key="bk_prev_ings").set_value("1 onion\n1 cup broth")
    at.button(key="bk_add").click().run()

    (entry,) = golden.read_backlog(env.backlog)
    assert entry.ingredients == ["1 onion", "1 cup broth"]


def test_backlog_add_link_uses_parser_not_network(env, monkeypatch):
    called = {}

    def fake_parse(source):
        called["source"] = source
        return ParsedRecipe(title="Linked Dish", ingredients=["kale", "oil"],
                            source=source)

    monkeypatch.setattr("clean_recipe.parse.parse_recipe", fake_parse)
    at = run_console()
    at.text_input(key="bk_url").set_value("https://example.com/dish")
    at.button(key="bk_parse").click().run()
    assert at.text_input(key="bk_prev_title").value == "Linked Dish"

    at.button(key="bk_add").click().run()
    assert called["source"] == "https://example.com/dish"
    (entry,) = golden.read_backlog(env.backlog)
    assert entry.source == "https://example.com/dish"
    assert entry.title == "Linked Dish"


def test_backlog_paste_without_title_shows_hint(env):
    at = run_console()
    at.text_area(key="bk_paste").set_value("1 onion\n1 cup broth")
    at.button(key="bk_parse").click().run()
    assert any("Add a title" in i.value for i in at.info)
    assert "bk_preview" not in at.session_state


def test_backlog_submit_marks_all_open_submitted(env):
    golden.write_backlog(
        [golden.BacklogEntry(recipe_id="a", title="A", ingredients=["x"]),
         golden.BacklogEntry(recipe_id="b", title="B", ingredients=["y"])],
        env.backlog,
    )
    at = run_console()
    at.button(key="backlog_submit").click().run()
    assert {e.status for e in golden.read_backlog(env.backlog)} == {"submitted"}


# ---- review & grade ----------------------------------------------------------

def test_review_grade_and_approve_persists(env):
    golden.write_drafts([make_draft(recipe_id="d-01")], env.drafts)
    at = run_console()
    at.selectbox(key="g_d-01_quality").select(4)
    at.text_area(key="g_d-01_notes").set_value("swaps miss the pasta itself")
    at.button(key="g_d-01_approve").click().run()

    drafts, _ = golden.read_drafts(env.drafts)
    d = drafts[0]
    assert d.status == "approved"
    assert d.row.swap_quality == 4
    assert d.row.notes == "swaps miss the pasta itself"


def test_review_navigation_moves_between_drafts(env):
    golden.write_drafts(
        [make_draft(recipe_id="d-01"), make_draft(recipe_id="d-02")], env.drafts
    )
    at = run_console()
    assert any("Draft 1 of 2" in c.value for c in at.caption)
    at.button(key="g_d-01_next").click().run()
    assert any("Draft 2 of 2" in c.value for c in at.caption)


def test_review_empty_state(env):
    at = run_console()
    assert any("No drafts yet" in i.value for i in at.info)


def test_review_skips_malformed_draft_line(env):
    golden.write_drafts([make_draft(recipe_id="d-01")], env.drafts)
    with env.drafts.open("a", encoding="utf-8") as f:
        f.write("garbage line\n")
    at = run_console()
    assert any("1 malformed" in c.value for c in at.caption)
    assert any("Draft 1 of 1" in c.value for c in at.caption)


# ---- promote -----------------------------------------------------------------

def test_promote_moves_approved_into_golden_set(env):
    golden.write_drafts(
        [make_draft(recipe_id="approved-01", status="approved", swap_quality=3),
         make_draft(recipe_id="still-draft", status="draft")],
        env.drafts,
    )
    at = run_console()
    at.button(key="promote_btn").click().run()

    assert at.success
    rows = golden.load_golden(env.golden_csv)
    assert [r.recipe_id for r in rows] == ["approved-01"]
    assert rows[0].swap_quality == 3


def test_promote_button_disabled_with_nothing_ready(env):
    golden.write_drafts([make_draft(status="draft")], env.drafts)
    at = run_console()
    assert at.button(key="promote_btn").disabled


# ---- logs / results (read-only) ----------------------------------------------

def test_logs_tab_counts_malformed(env):
    log_verdict("Cookies", ["butter"], make_verdict(), path=env.log_file)
    with env.log_file.open("a", encoding="utf-8") as f:
        f.write("{corrupt\n")
    at = run_console()
    assert any("1 malformed" in c.value for c in at.caption)
    assert any("1 verdicts" in c.value for c in at.caption)


def test_results_tab_summary(env):
    out = env.results_dir / "eval-20260712-000000-fake.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["recipe_id", "target_band", "predicted_band", "band_correct",
                    "target_score", "predicted_score", "abs_error"])
        w.writerow(["g1", "Clean", "Clean", "True", "90", "90", "0"])
        w.writerow(["g2", "Clean", "Processed", "False", "90", "50", "40"])
    at = run_console()
    assert any("band accuracy 50.0%" in c.value for c in at.caption)
    assert any("MAE 20.00" in c.value for c in at.caption)
