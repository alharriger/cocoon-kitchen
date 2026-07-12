"""CocoonKitchen — the Streamlit UI.

A thin consumer of the scoring core (architecture.md load-bearing rule): this
file wires ``parse_recipe`` → ``score_recipe`` and renders the Verdict card.
No scoring, banding, or logging logic lives here — logging happens inside
``score_recipe``. Voice and layout follow ai_docs/design_system.md: awareness,
not judgment; band color is never the only signal.

SECURITY: recipe text, URLs, and everything the model returns are UNTRUSTED.
Untrusted strings are markdown-escaped before rendering (Streamlit already
strips HTML by default); ``unsafe_allow_html`` is used only for the band pill,
which interpolates schema-validated values and a code-owned color map. Errors
render as friendly messages — never a traceback.

Run: streamlit run app.py
"""
from __future__ import annotations

import re

import streamlit as st
from dotenv import load_dotenv

from clean_recipe.parse import ParsedRecipe, ParseError, parse_recipe
from clean_recipe.schema import Verdict
from clean_recipe.score import NotARecipeError, ScoringError, score_recipe

load_dotenv()  # entrypoints load .env; the pure core reads os.environ

# Band → pill color (design_system.md palette). Keys mirror schema.Band; the
# band name is ALWAYS rendered next to the color (accessibility rule).
BAND_COLORS: dict[str, str] = {
    "Clean": "#2e7d32",
    "Mostly Clean": "#9e9d24",
    "Processed": "#ef6c00",
    "Ultra-processed": "#c62828",
}

# (SubScores attribute, display label) in rubric weight order.
SUB_SCORE_ROWS: list[tuple[str, str]] = [
    ("ultra_processing", "Ultra-processing"),
    ("added_sugar", "Added sugar"),
    ("fat_quality", "Fat quality"),
    ("sodium_preservatives", "Sodium & preservatives"),
    ("whole_food_ratio", "Whole-food ratio"),
    ("additive_count", "Additive count"),
]

DISCLAIMER = (
    "CocoonKitchen describes how processed a recipe's ingredients are — "
    "it isn't medical or nutrition advice."
)

_RESULT_KEY = "cocoon_result"

_MD_SPECIALS = re.compile(r"([\\`*_{}\[\]()#+\-.!>|~])")


def md_escape(text: str) -> str:
    """Backslash-escape markdown so untrusted text renders literally."""
    return _MD_SPECIALS.sub(r"\\\1", text)


def _render_score(verdict: Verdict) -> None:
    """Big score + band pill. The ONLY unsafe_allow_html in the app: ``score``
    is a schema-validated int, ``band`` a schema Literal, and the color comes
    from the code-owned map — nothing untrusted is interpolated."""
    color = BAND_COLORS[verdict.band]
    st.markdown(
        '<div style="display:flex;align-items:center;gap:1rem;margin:0.25rem 0 0.75rem">'
        f'<span style="font-size:3.5rem;font-weight:800;line-height:1">{verdict.score}</span>'
        f'<span style="background:{color};color:#fff;padding:0.3rem 0.9rem;'
        f'border-radius:999px;font-weight:600">{verdict.band}</span>'
        "</div>",
        unsafe_allow_html=True,
    )


def _render_card(recipe: ParsedRecipe, verdict: Verdict) -> None:
    st.divider()
    st.subheader(md_escape(recipe.title))
    if recipe.source != "pasted":
        st.caption(md_escape(recipe.source))

    _render_score(verdict)

    for attr, label in SUB_SCORE_ROWS:
        value = getattr(verdict.sub_scores, attr)
        st.progress(value / 100, text=f"{label} — {value:.0f}")

    st.markdown("##### Flagged ingredients")
    if verdict.flagged_ingredients:
        st.markdown(
            "\n".join(f"- 🚩 {md_escape(item)}" for item in verdict.flagged_ingredients)
        )
    else:
        st.markdown("Nothing flagged — this one is about as whole as it gets.")

    st.markdown("##### Swaps to try")
    for swap in verdict.swaps:
        st.markdown(
            f"**{md_escape(swap.from_ingredient)}** → **{md_escape(swap.to_ingredient)}**"
        )
        st.caption(md_escape(swap.reason))

    st.divider()
    st.caption(DISCLAIMER)


def _score_source(source: str) -> None:
    """Run the parse → score pipeline and stash the result for rendering.
    Every failure becomes a friendly message — never a traceback."""
    st.session_state.pop(_RESULT_KEY, None)
    try:
        with st.spinner("Reading your recipe…"):
            recipe = parse_recipe(source)
        with st.spinner("Scoring the ingredients…"):
            verdict = score_recipe(recipe.title, recipe.ingredients)
    except ParseError as e:
        # Friendly summary up top; the raw parse.py message goes in the
        # expander as literal code — st.warning renders markdown, which
        # autolinks URLs (escapes show as literal backslashes inside links)
        # and would surface fetch internals like the pinned IP.
        st.warning(
            "We couldn't get a recipe out of that. Paste the recipe text "
            "instead — title on the first line, one ingredient per line."
        )
        with st.expander("What happened"):
            st.code(str(e), language=None)
    except NotARecipeError:
        # App-owned copy (no untrusted text), safe to render as markdown.
        st.warning(
            "That doesn't look like a recipe. Paste a dish with its ingredients — "
            "a title on the first line, then one ingredient per line."
        )
    except ScoringError as e:
        st.error(
            "The kitchen hiccupped — we couldn't score this one. "
            "Give it another try in a moment."
        )
        with st.expander("Technical details"):
            st.code(str(e), language=None)
    except RuntimeError as e:
        # client.py raises RuntimeError for missing/invalid .env config.
        st.error(
            "The scorer isn't configured yet — check your `.env` "
            "(start from `.env.example`)."
        )
        with st.expander("Technical details"):
            st.code(str(e), language=None)
    except Exception as e:
        st.error("Something unexpected went wrong — sorry! Give it another try.")
        with st.expander("Technical details"):
            st.code(f"{type(e).__name__}: {e}", language=None)
    else:
        st.session_state[_RESULT_KEY] = (recipe, verdict)


def main() -> None:
    st.set_page_config(page_title="CocoonKitchen", page_icon="🦋")
    st.title("🦋 CocoonKitchen")
    st.caption(
        "Paste a recipe (or drop in a link) and see how processed it really is — "
        "awareness, not judgment."
    )

    paste_tab, link_tab = st.tabs(["📋 Paste a recipe", "🔗 Score a link"])

    with paste_tab:
        pasted = st.text_area(
            "Recipe text",
            height=220,
            max_chars=20_000,
            placeholder="Grandma's french onion soup\n4 yellow onions\n2 tbsp butter\n…",
            help="First line is the title; every following line is one ingredient.",
        )
        if st.button("Score it", type="primary", key="score_paste"):
            if pasted.strip():
                _score_source(pasted)
            else:
                st.info(
                    "Paste a recipe above to get started — title on the first "
                    "line, one ingredient per line after it."
                )

    with link_tab:
        url = st.text_input(
            "Recipe link",
            placeholder="https://example.com/best-french-onion-soup",
        )
        if st.button("Score it", type="primary", key="score_link"):
            stripped = url.strip()
            if not stripped:
                st.info("Pop in a recipe link to get started.")
            elif not stripped.startswith(("http://", "https://")):
                st.warning(
                    "That doesn't look like a link — try a full https://… URL, "
                    "or paste the recipe text instead."
                )
            else:
                _score_source(stripped)

    result = st.session_state.get(_RESULT_KEY)
    if result:
        _render_card(*result)


if __name__ == "__main__":
    main()
