"""CocoonKitchen Console — internal observability & labeling tool.

LOCAL ONLY — NEVER DEPLOY. This console surfaces every logged recipe and
verdict; if it ever needs remote access, add access gating FIRST
(architecture.md 2026-07-12 decision). It is deliberately a separate Streamlit
entrypoint — not a page under ``pages/`` — so the public deploy of ``app.py``
can never serve it.

This is Amber's golden-set builder (working_sprint.md Phase 4): browse the
verdict log, author Contract-4 golden rows from recipes, correct logged
verdicts into golden rows (+ swap-quality grades), and view eval results.
Labels are HUMAN-owned — every band/score/swap label is typed or confirmed by
Amber; model output only ever appears as clearly-marked, editable pre-fill.

SECURITY: log lines, recipe text, verdict strings, and results CSVs are all
UNTRUSTED. They are rendered only through non-markdown widgets (st.dataframe /
st.json / st.code / selectbox labels) — no unsafe_allow_html anywhere in this
file, and no untrusted string is interpolated into markdown. All paths are
fixed repo-relative constants (env-overridable for tests); file pickers choose
from glob results, never typed paths. The only write in the whole console is
``golden.append_golden_row`` — append-only, header-verified.

Run: streamlit run console.py
"""
from __future__ import annotations

import csv
import math
import os
from pathlib import Path
from typing import get_args

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from clean_recipe import golden
from clean_recipe import log as vlog
from clean_recipe.parse import ParseError, parse_recipe
from clean_recipe.schema import Band, Verdict
from clean_recipe.score import NotARecipeError, ScoringError, score_recipe

load_dotenv()  # entrypoints load .env; the pure core reads os.environ

# Fixed repo-relative paths (anchored to this file). The COCOON_* env vars are
# a test/dev seam only — never user input from the UI.
_ROOT = Path(__file__).resolve().parent
LOG_DIR = Path(os.environ.get("COCOON_LOG_DIR", _ROOT / "data" / "logs"))
GOLDEN_CSV = Path(os.environ.get("COCOON_GOLDEN_CSV", _ROOT / "evals" / "golden_set.csv"))
RESULTS_DIR = Path(os.environ.get("COCOON_RESULTS_DIR", _ROOT / "evals" / "results"))

PAGE_SIZE = 20

SUGGESTION_BANNER = (
    "**Model suggestion — pre-filled below.** Review and correct; the label is yours."
)


# ---- shared helpers ----------------------------------------------------------

def _friendly_scoring_errors(fn):
    """Run a parse/score step, turning every failure into a friendly message
    (never a traceback — same discipline as app.py). Returns None on failure."""
    try:
        return fn()
    except ParseError as e:
        st.warning(
            "We couldn't get a recipe out of that. Title on the first line, "
            "one ingredient per line."
        )
        with st.expander("What happened"):
            st.code(str(e), language=None)
    except NotARecipeError:
        st.warning(
            "The model says that doesn't look like a recipe. Check the pasted text."
        )
    except ScoringError as e:
        st.error("The model couldn't score this one — try again in a moment.")
        with st.expander("Technical details"):
            st.code(str(e), language=None)
    except RuntimeError as e:
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
    return None


def _render_verdict(verdict: Verdict, ingredients: list[str]) -> None:
    """Read-only verdict display via non-markdown widgets (untrusted strings)."""
    st.text(f"Score {verdict.score} · {verdict.band}")
    st.code("\n".join(ingredients), language=None)
    st.dataframe(
        [{"sub-score": k, "value": v} for k, v in verdict.sub_scores.model_dump().items()],
        hide_index=True,
    )
    if verdict.flagged_ingredients:
        st.dataframe(
            [{"flagged": item} for item in verdict.flagged_ingredients],
            hide_index=True,
        )
    if verdict.swaps:
        st.dataframe(
            [
                {"from": s.from_ingredient, "to": s.to_ingredient, "reason": s.reason}
                for s in verdict.swaps
            ],
            hide_index=True,
        )


def _existing_ids() -> set[str]:
    try:
        return golden.existing_recipe_ids(GOLDEN_CSV)
    except OSError:
        return set()


def _set_form(
    prefix: str,
    *,
    title: str,
    ingredients: list[str],
    source: str = "pasted",
    verdict: Verdict | None = None,
) -> None:
    """Populate the golden-row form's session keys. Must run BEFORE the form
    widgets render (buttons sit above the form). Model-derived values are set
    only when a verdict is passed, and are always editable."""
    ss = st.session_state
    ss[f"{prefix}_recipe_id"] = golden.suggest_recipe_id(title, _existing_ids())
    ss[f"{prefix}_source"] = source
    ss[f"{prefix}_title"] = title
    ss[f"{prefix}_raw"] = golden.join_ingredients(ingredients)
    ss[f"{prefix}_band"] = verdict.band if verdict else None
    ss[f"{prefix}_score"] = verdict.score if verdict else None
    ss[f"{prefix}_swaps"] = golden.format_swaps(verdict.swaps) if verdict else ""
    ss[f"{prefix}_quality"] = None
    ss[f"{prefix}_notes"] = ""


def _golden_row_form(prefix: str, *, require_swap_quality: bool) -> None:
    """The shared Contract-4 form (author + label-from-log). No band/score
    defaults — an accidental Save can never invent a label."""
    ss = st.session_state
    st.text_input("recipe_id", key=f"{prefix}_recipe_id")
    st.text_input("source (URL, or 'pasted')", key=f"{prefix}_source")
    st.text_input("title", key=f"{prefix}_title")
    st.text_area("raw_ingredients (separated by '; ')", key=f"{prefix}_raw", height=90)
    st.selectbox(
        "target_band — your label",
        list(get_args(Band)),
        index=None,
        placeholder="Pick the band you judge correct",
        key=f"{prefix}_band",
    )
    st.number_input(
        "target_score (0–100) — your label",
        min_value=0,
        max_value=100,
        value=None,
        key=f"{prefix}_score",
    )
    st.text_input("expected_swaps (from>to; from>to)", key=f"{prefix}_swaps")
    st.selectbox(
        "swap_quality — your 1–5 grade of the model's swaps"
        + (" (required here)" if require_swap_quality else " (optional)"),
        [None, 1, 2, 3, 4, 5],
        format_func=lambda v: "not graded" if v is None else str(v),
        key=f"{prefix}_quality",
    )
    st.text_area("notes (why / where it's ambiguous)", key=f"{prefix}_notes", height=70)

    if st.button("Save golden row", type="primary", key=f"{prefix}_save"):
        _save_golden_row(prefix, require_swap_quality=require_swap_quality)

    if any(rid.startswith("sample-") for rid in _existing_ids()):
        st.caption(
            "ℹ️ The template's sample-* rows are still in golden_set.csv — "
            "delete them once real labels land."
        )


def _save_golden_row(prefix: str, *, require_swap_quality: bool) -> None:
    ss = st.session_state
    band = ss.get(f"{prefix}_band")
    score = ss.get(f"{prefix}_score")
    quality = ss.get(f"{prefix}_quality")
    title = (ss.get(f"{prefix}_title") or "").strip()
    recipe_id = (ss.get(f"{prefix}_recipe_id") or "").strip()

    problems: list[str] = []
    if band is None:
        problems.append("target_band is required — pick the band you judge correct.")
    if score is None:
        problems.append("target_score is required.")
    if require_swap_quality and quality is None:
        problems.append(
            "swap_quality is required when labeling from a log — grade the model's swaps 1–5."
        )
    if not recipe_id and title:
        problems.append(
            f"recipe_id is required — e.g. "
            f"'{golden.suggest_recipe_id(title, _existing_ids())}'."
        )
    if problems:
        st.error("Not saved:\n\n" + "\n".join(f"- {p}" for p in problems))
        return

    try:
        row = golden.GoldenRow(
            recipe_id=recipe_id,
            source=(ss.get(f"{prefix}_source") or "").strip() or "pasted",
            title=title,
            raw_ingredients=ss.get(f"{prefix}_raw") or "",
            target_band=band,
            target_score=int(score),
            expected_swaps=ss.get(f"{prefix}_swaps") or "",
            swap_quality=quality,
            notes=ss.get(f"{prefix}_notes") or "",
        )
    except ValidationError as e:
        st.error(
            "Not saved — fix these fields:\n\n"
            + "\n".join(
                f"- **{'.'.join(str(loc) for loc in err['loc'])}**: {err['msg']}"
                for err in e.errors()
            )
        )
        return

    existing = _existing_ids()
    if row.recipe_id in existing:
        st.error(
            f"Not saved — recipe_id '{row.recipe_id}' already exists in "
            f"golden_set.csv (duplicates would corrupt eval metrics). "
            f"Try '{golden.suggest_recipe_id(row.title, existing)}'."
        )
        return

    try:
        count = golden.append_golden_row(row, GOLDEN_CSV)
    except (ValueError, OSError) as e:
        st.error(f"Not saved — couldn't write golden_set.csv: {e}")
        return
    st.success(f"Saved — golden_set.csv now has {count} rows.")


# ---- tab: logs -----------------------------------------------------------------

def _logs_tab() -> None:
    files = vlog.list_log_files(LOG_DIR)
    if not files:
        st.info(
            "No logs yet — score a few recipes in the scorer "
            "(`streamlit run app.py`) and they'll show up here."
        )
        return
    file = st.selectbox("Log file", files, format_func=lambda p: p.name, key="logs_file")
    records, skipped = vlog.read_log(file)
    if skipped:
        st.caption(f"⚠️ {skipped} malformed line(s) skipped.")
    if not records:
        st.info("This log file is empty.")
        return

    newest_first = list(reversed(records))
    pages = math.ceil(len(newest_first) / PAGE_SIZE)
    page = 1
    if pages > 1:
        page = st.number_input("Page", min_value=1, max_value=pages, value=1, key="logs_page")
    shown = newest_first[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    st.caption(f"{len(records)} verdicts, newest first — page {page}/{pages}")
    st.dataframe(
        [
            {
                "when": r.ts,
                "title": r.title,
                "band": r.verdict.band,
                "score": r.verdict.score,
                "flagged": len(r.verdict.flagged_ingredients),
                "swaps": len(r.verdict.swaps),
            }
            for r in shown
        ],
        hide_index=True,
    )

    idx = st.selectbox(
        "Inspect a verdict",
        range(len(shown)),
        format_func=lambda i: f"{shown[i].ts} — {shown[i].title[:60]}",
        key="logs_detail",
    )
    record = shown[idx]
    st.json(record.verdict.model_dump())
    st.code("\n".join(record.ingredients), language=None)


# ---- tab: author ----------------------------------------------------------------

def _author_tab() -> None:
    st.caption(
        "Paste a recipe, load it into the form, and set the labels yourself. "
        "Pre-scoring is optional and only ever a suggestion."
    )
    pasted = st.text_area(
        "Recipe text",
        height=160,
        max_chars=20_000,
        placeholder="Grandma's french onion soup\n4 yellow onions\n2 tbsp butter\n…",
        help="First line is the title; every following line is one ingredient.",
        key="author_text",
    )
    source_url = st.text_input(
        "Source URL (optional — metadata only, never fetched)", key="author_source_url"
    )

    col_load, col_prescore = st.columns(2)
    with col_load:
        load_clicked = st.button("Load into form (no model call)", key="author_load")
    with col_prescore:
        prescore_clicked = st.button("Pre-score with the model (optional)", key="author_prescore")

    if load_clicked or prescore_clicked:
        if not pasted.strip():
            st.info("Paste a recipe above first — title line, one ingredient per line.")
        else:
            recipe = _friendly_scoring_errors(lambda: parse_recipe(pasted))
            if recipe is not None:
                verdict = None
                if prescore_clicked:
                    # log=False: labeling-session calls must not pollute
                    # data/logs/verdicts.jsonl — the label-from-log source.
                    verdict = _friendly_scoring_errors(
                        lambda: score_recipe(recipe.title, recipe.ingredients, log=False)
                    )
                st.session_state["author_verdict"] = verdict
                if load_clicked or verdict is not None:
                    _set_form(
                        "author",
                        title=recipe.title,
                        ingredients=recipe.ingredients,
                        source=source_url.strip() or "pasted",
                        verdict=verdict,
                    )

    verdict = st.session_state.get("author_verdict")
    if verdict is not None:
        st.info(SUGGESTION_BANNER)
        with st.expander("Model verdict (suggestion)", expanded=False):
            _render_verdict(verdict, golden.parse_ingredients(st.session_state.get("author_raw", "")))

    st.divider()
    _golden_row_form("author", require_swap_quality=False)


# ---- tab: label from log ---------------------------------------------------------

def _label_tab() -> None:
    files = vlog.list_log_files(LOG_DIR)
    if not files:
        st.info("No logs to label yet — score a few recipes in the scorer first.")
        return
    file = st.selectbox("Log file", files, format_func=lambda p: p.name, key="label_file")
    records, skipped = vlog.read_log(file)
    if skipped:
        st.caption(f"⚠️ {skipped} malformed line(s) skipped.")
    if not records:
        st.info("This log file is empty.")
        return

    newest_first = list(reversed(records))
    idx = st.selectbox(
        "Logged verdict",
        range(len(newest_first)),
        format_func=lambda i: f"{newest_first[i].ts} — {newest_first[i].title[:60]}",
        key="label_record",
    )
    record = newest_first[idx]

    st.caption("Logged model verdict — correct it into your label below.")
    _render_verdict(record.verdict, record.ingredients)

    if st.button("Load this verdict into the labeling form", key="label_load"):
        # source: the log doesn't record where the recipe came from (known
        # limitation) — default to "pasted"; editable in the form.
        _set_form(
            "label",
            title=record.title,
            ingredients=record.ingredients,
            verdict=record.verdict,
        )
        st.session_state["label_loaded"] = True

    st.divider()
    if st.session_state.get("label_loaded"):
        st.info(SUGGESTION_BANNER)
        _golden_row_form("label", require_swap_quality=True)
    else:
        st.caption("Pick a verdict and load it to start labeling.")


# ---- tab: results ----------------------------------------------------------------

def _results_tab() -> None:
    files = sorted(RESULTS_DIR.glob("*.csv"), reverse=True) if RESULTS_DIR.is_dir() else []
    if not files:
        st.info(
            "No eval results yet — run `.venv/bin/python evals/evaluate.py` "
            "once real golden rows exist."
        )
        return
    file = st.selectbox(
        "Results file (newest first)", files, format_func=lambda p: p.name, key="results_file"
    )
    with file.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        st.info("This results file is empty.")
        return

    # Recompute the headline numbers defensively — cells are untrusted text.
    correct = [r.get("band_correct") == "True" for r in rows]
    errors = []
    for r in rows:
        try:
            errors.append(abs(int(r.get("abs_error", ""))))
        except ValueError:
            pass
    summary = f"{len(rows)} rows · band accuracy {sum(correct) / len(rows):.1%}"
    if errors:
        summary += f" · score MAE {sum(errors) / len(errors):.2f}"
    st.caption(summary)
    st.dataframe(rows, hide_index=True)


# ---- entrypoint -------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="CocoonKitchen Console", page_icon="🏷️")
    st.title("🏷️ CocoonKitchen Console")
    st.caption(
        "Internal labeling tool — local only, never deployed. "
        "Labels are yours; the model only suggests."
    )

    logs_tab, author_tab, label_tab, results_tab = st.tabs(
        ["📜 Logs", "✍️ Author", "🏷️ Label from log", "📊 Results"]
    )
    with logs_tab:
        _logs_tab()
    with author_tab:
        _author_tab()
    with label_tab:
        _label_tab()
    with results_tab:
        _results_tab()


if __name__ == "__main__":
    main()
