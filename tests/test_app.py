"""UI tests for app.py via streamlit's AppTest — no live model or network.

The core functions are monkeypatched at their source modules
(``clean_recipe.parse.parse_recipe`` / ``clean_recipe.score.score_recipe``);
app.py re-imports them on every AppTest run, so the patches take effect.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from clean_recipe.parse import ParsedRecipe, ParseError
from clean_recipe.schema import SubScores, Swap, Verdict
from clean_recipe.score import NotARecipeError, ScoringError

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = str(ROOT / "app.py")


def _verdict() -> Verdict:
    return Verdict(
        score=72,
        band="Mostly Clean",
        sub_scores=SubScores(
            ultra_processing=80,
            added_sugar=60,
            fat_quality=70,
            sodium_preservatives=65,
            whole_food_ratio=85,
            additive_count=90,
        ),
        flagged_ingredients=["granulated sugar", "vegetable oil"],
        swaps=[
            Swap(from_ingredient="vegetable oil", to_ingredient="olive oil", reason="better fat"),
            Swap(from_ingredient="white flour", to_ingredient="whole wheat", reason="more fiber"),
            Swap(from_ingredient="table salt", to_ingredient="sea salt", reason="less additives"),
        ],
    )


def _recipe() -> ParsedRecipe:
    return ParsedRecipe(title="Test Soup", ingredients=["1 onion"], source="pasted")


def _run_paste(at: AppTest, text: str) -> AppTest:
    at.run()
    at.text_area[0].set_value(text)
    at.button(key="score_paste").click()
    return at.run()


def _page_text(at: AppTest) -> str:
    """All rendered text the user could read, flattened for assertions."""
    parts = [el.value for el in at.markdown]
    parts += [el.value for el in at.caption]
    parts += [el.value for el in at.subheader]
    parts += [el.value for el in at.error]
    parts += [el.value for el in at.warning]
    parts += [el.value for el in at.info]
    return "\n".join(str(p) for p in parts)


def test_renders_inputs():
    at = AppTest.from_file(APP_PATH).run()
    assert not at.exception
    assert len(at.tabs) == 2
    assert at.text_area  # paste box
    assert at.text_input  # link box
    assert at.button(key="score_paste") and at.button(key="score_link")


def test_paste_happy_path_renders_card(monkeypatch):
    monkeypatch.setattr("clean_recipe.parse.parse_recipe", lambda source: _recipe())
    monkeypatch.setattr(
        "clean_recipe.score.score_recipe", lambda title, ingredients, **kw: _verdict()
    )
    at = _run_paste(AppTest.from_file(APP_PATH), "Test Soup\n1 onion")
    assert not at.exception

    text = _page_text(at)
    assert "Test Soup" in text
    assert "Mostly Clean" in text and "72" in text  # score + band written out
    assert "granulated sugar" in text and "vegetable oil" in text  # flags
    assert text.count("→") == 3  # three swaps
    assert "isn't medical or nutrition advice" in text  # disclaimer
    # six sub-score bars, weight order
    bars = [el.text for el in at.get("progress")]
    assert len(bars) == 6
    assert bars[0].startswith("Ultra-processing")


def test_parse_error_shows_friendly_warning(monkeypatch):
    def boom(source):
        raise ParseError("could not fetch it. Paste the recipe text instead.")

    monkeypatch.setattr("clean_recipe.parse.parse_recipe", boom)
    at = _run_paste(AppTest.from_file(APP_PATH), "whatever")
    assert not at.exception
    assert at.warning
    assert "Paste the recipe text" in at.warning[0].value
    assert "Traceback" not in _page_text(at)
    # the raw parse.py message lives in the details expander, as literal code
    codes = [el.value for el in at.get("code")]
    assert any("could not fetch it" in c for c in codes)


def test_scoring_error_shows_friendly_message(monkeypatch):
    monkeypatch.setattr("clean_recipe.parse.parse_recipe", lambda source: _recipe())

    def boom(title, ingredients, **kw):
        raise ScoringError("model did not return JSON")

    monkeypatch.setattr("clean_recipe.score.score_recipe", boom)
    at = _run_paste(AppTest.from_file(APP_PATH), "Test Soup\n1 onion")
    assert not at.exception
    assert at.error and "kitchen hiccupped" in at.error[0].value
    assert "Traceback" not in _page_text(at)
    # the raw error is available, but only inside the collapsed details expander
    codes = [el.value for el in at.get("code")]
    assert any("model did not return JSON" in c for c in codes)


def test_not_a_recipe_shows_friendly_message(monkeypatch):
    monkeypatch.setattr("clean_recipe.parse.parse_recipe", lambda source: _recipe())

    def boom(title, ingredients, **kw):
        raise NotARecipeError("That doesn't look like a recipe.")

    monkeypatch.setattr("clean_recipe.score.score_recipe", boom)
    at = _run_paste(AppTest.from_file(APP_PATH), "Job posting\nturkey sausage")
    assert not at.exception
    assert at.warning and "doesn't look like a recipe" in at.warning[0].value
    assert "Traceback" not in _page_text(at)


def test_config_error_points_at_env(monkeypatch):
    monkeypatch.setattr("clean_recipe.parse.parse_recipe", lambda source: _recipe())

    def boom(title, ingredients, **kw):
        raise RuntimeError("LLM_API_KEY is not set. Copy .env.example to .env.")

    monkeypatch.setattr("clean_recipe.score.score_recipe", boom)
    at = _run_paste(AppTest.from_file(APP_PATH), "Test Soup\n1 onion")
    assert not at.exception
    assert at.error and ".env" in at.error[0].value


def test_empty_paste_nudges_without_calling_core(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "clean_recipe.parse.parse_recipe", lambda source: calls.append(source)
    )
    at = AppTest.from_file(APP_PATH).run()
    at.button(key="score_paste").click()
    at.run()
    assert not at.exception
    assert at.info  # gentle nudge
    assert calls == []


def test_link_tab_rejects_non_urls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "clean_recipe.parse.parse_recipe", lambda source: calls.append(source)
    )
    at = AppTest.from_file(APP_PATH).run()
    at.text_input[0].set_value("chicken soup")
    at.button(key="score_link").click()
    at.run()
    assert not at.exception
    assert at.warning and "look like a link" in at.warning[0].value
    assert calls == []


# ---- pure helpers (import app.py as a module; main() is __main__-guarded) ----

@pytest.fixture(scope="module")
def app_module():
    spec = importlib.util.spec_from_file_location("app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_band_colors_cover_every_band(app_module):
    from clean_recipe.schema import Band
    import typing

    assert set(app_module.BAND_COLORS) == set(typing.get_args(Band))
    assert all(v.startswith("#") for v in app_module.BAND_COLORS.values())


def test_md_escape_neutralizes_markdown(app_module):
    hostile = "[click](https://evil) *bold* `code`"
    escaped = app_module.md_escape(hostile)
    assert "[click](" not in escaped and "*bold*" not in escaped
