"""CocoonKitchen Console — internal golden-set builder.

LOCAL ONLY — NEVER DEPLOY. This console surfaces every logged recipe and
verdict; if it ever needs remote access, add access gating FIRST
(architecture.md 2026-07-12 decision). It is deliberately a separate Streamlit
entrypoint — not a page under ``pages/`` — so the public deploy of ``app.py``
can never serve it.

This is Amber's golden-set builder (working_sprint.md Phase 4), a three-stage
assembly line over thin JSONL/CSV files (no DB):

    Backlog          →  Review & grade         →  Promote
    backlog.jsonl       golden_drafts.jsonl        golden_set.csv
    (curate recipes)    (grade drafts a           (append-only,
                         separate Claude           human-owned final set)
                         instance produced)

Draft *generation* does not happen here — a separate Claude instance reads the
submitted backlog and writes drafts per ai_docs/golden_draft_handoff.md. The
console curates the backlog, lets Amber grade/correct drafts (her primary levers
are swap_quality 1–5 + notes), and promotes approved drafts. Labels are
HUMAN-owned: every band/score/swap label is typed or confirmed by Amber; the
draft's model verdict is shown only as read-only grading context.

SECURITY: log lines, recipe text, verdict strings, and results CSVs are all
UNTRUSTED. They are rendered only through non-markdown widgets (st.dataframe /
st.json / st.code / st.text / selectbox labels) — no unsafe_allow_html anywhere
in this file, and no untrusted string is interpolated into markdown. All paths
are fixed repo-relative constants (env-overridable for tests only); recipe URLs
are fetched through parse.py's SSRF-guarded fetcher. The only writes are to the
console-owned pipeline files (backlog / drafts) and the append-only golden CSV.

Run: streamlit run console.py
"""
from __future__ import annotations

import csv
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from clean_recipe import golden
from clean_recipe import log as vlog
from clean_recipe.parse import ParseError, parse_pasted_ingredients, parse_recipe
from clean_recipe.schema import Band, Verdict
from clean_recipe.score import NotARecipeError, ScoringError, score_recipe

load_dotenv()  # entrypoints load .env; the pure core reads os.environ

# Fixed repo-relative paths (anchored to this file). The COCOON_* env vars are a
# test/dev seam only — never user input from the UI.
_ROOT = Path(__file__).resolve().parent
_evals = _ROOT / "evals"
LOG_DIR = Path(os.environ.get("COCOON_LOG_DIR", _ROOT / "data" / "logs"))
GOLDEN_CSV = Path(os.environ.get("COCOON_GOLDEN_CSV", _evals / "golden_set.csv"))
RESULTS_DIR = Path(os.environ.get("COCOON_RESULTS_DIR", _evals / "results"))
BACKLOG = Path(os.environ.get("COCOON_BACKLOG", _evals / "backlog.jsonl"))
DRAFTS = Path(os.environ.get("COCOON_DRAFTS", _evals / "golden_drafts.jsonl"))

PAGE_SIZE = 20
BAND_OPTIONS = list(get_args(Band))
QUALITY_OPTIONS = [None, 1, 2, 3, 4, 5]


# ---- shared helpers ----------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _friendly_parse(source: str):
    """Parse paste/URL input, turning every failure into a friendly message
    (never a traceback). Returns a ParsedRecipe or None."""
    try:
        return parse_recipe(source)
    except ParseError as e:
        st.warning(
            "We couldn't get a recipe out of that. For a link, use a full "
            "https://… URL; for paste, put the title on the first line and one "
            "ingredient per line."
        )
        with st.expander("What happened"):
            st.code(str(e), language=None)
    except Exception as e:  # defensive: never surface a traceback
        st.error("Something unexpected went wrong reading that recipe.")
        with st.expander("Technical details"):
            st.code(f"{type(e).__name__}: {e}", language=None)
    return None


def _all_known_ids() -> set[str]:
    """Every recipe_id already in play (golden set + backlog + drafts), so a
    freshly suggested id is unique across the whole pipeline."""
    ids: set[str] = set()
    try:
        ids |= golden.existing_recipe_ids(GOLDEN_CSV)
    except OSError:
        pass
    ids |= {e.recipe_id for e in golden.read_backlog(BACKLOG)}
    drafts, _ = golden.read_drafts(DRAFTS)
    ids |= {d.row.recipe_id for d in drafts}
    return ids


def _verdict_swaps_rows(verdict: Verdict) -> list[dict]:
    return [
        {"from": s.from_ingredient, "to": s.to_ingredient, "reason": s.reason}
        for s in verdict.swaps
    ]


def _render_model_verdict(verdict: Verdict) -> None:
    """Read-only model-verdict display (untrusted strings via safe widgets)."""
    st.text(f"Model verdict: {verdict.score} · {verdict.band}")
    cols = st.columns(2)
    with cols[0]:
        st.caption("Sub-scores")
        st.dataframe(
            [{"dimension": k, "score": v}
             for k, v in verdict.sub_scores.model_dump().items()],
            hide_index=True,
        )
    with cols[1]:
        st.caption("Flagged")
        st.dataframe(
            [{"ingredient": i} for i in verdict.flagged_ingredients] or [{"ingredient": "—"}],
            hide_index=True,
        )
    st.caption("Model's swaps (this is what your 1–5 grade is judging)")
    st.dataframe(_verdict_swaps_rows(verdict) or [{"from": "—", "to": "—", "reason": "—"}],
                 hide_index=True)


# ---- tab: backlog ------------------------------------------------------------

def _parse_for_preview() -> None:
    """Stage 1 → parse the paste/link into an editable preview (or friendly error).

    Runs on the "Parse recipe" click. A link goes through the SSRF-guarded
    scraper; a paste goes through the forgiving ingredient cleaner (with a
    separate title, since site copies rarely include one). The result lands in
    ``bk_preview`` for the editable confirm step; parsing never writes anything."""
    ss = st.session_state
    url = (ss.get("bk_url") or "").strip()
    title = (ss.get("bk_title") or "").strip()
    paste = ss.get("bk_paste") or ""

    if url:
        recipe = _friendly_parse(url)
        if recipe is None:
            return
        preview = {"title": recipe.title, "ingredients": recipe.ingredients,
                   "source": recipe.source}
    elif paste.strip():
        if not title:
            st.info("Add a title — recipe-site copies usually don't include one.")
            return
        try:
            recipe = parse_pasted_ingredients(title, paste)
        except ParseError as e:
            st.warning("We couldn't find an ingredient list in that paste.")
            with st.expander("What happened"):
                st.code(str(e), language=None)
            return
        preview = {"title": recipe.title, "ingredients": recipe.ingredients,
                   "source": "pasted"}
    else:
        st.info("Paste an ingredient list (with a title) or drop in a link.")
        return

    ss["bk_preview"] = preview
    ss.pop("bk_prev_title", None)   # re-seed the edit widgets from the new preview
    ss.pop("bk_prev_ings", None)


def _commit_backlog() -> bool:
    """Stage 2 → add the (edited) preview to the backlog and reset the form.

    Returns True on success (caller reruns to refresh), False if blocked."""
    ss = st.session_state
    title = (ss.get("bk_prev_title") or "").strip()
    ings = [ln.strip() for ln in (ss.get("bk_prev_ings") or "").splitlines() if ln.strip()]
    if not title or not ings:
        st.error("Need a title and at least one ingredient before adding.")
        return False
    entry = golden.BacklogEntry(
        recipe_id=golden.suggest_recipe_id(title, _all_known_ids()),
        source=ss.get("bk_preview", {}).get("source", "pasted"),
        title=title, ingredients=ings, status="open", added_ts=_now_iso(),
    )
    entries = golden.read_backlog(BACKLOG)
    entries.append(entry)
    golden.write_backlog(entries, BACKLOG)
    for k in ("bk_preview", "bk_prev_title", "bk_prev_ings", "bk_title", "bk_paste", "bk_url"):
        ss.pop(k, None)
    ss["bk_flash"] = f"Added “{title}” to the backlog ({len(entries)} queued)."
    return True


def _backlog_tab() -> None:
    flash = st.session_state.pop("bk_flash", None)
    if flash:
        st.success(flash)
    st.caption(
        "Queue the recipes you want labeled — paste the ingredients (with a title) "
        "or drop in a link, check the preview, then add. When you're done, submit "
        "the batch for a Claude instance to draft."
    )

    with st.container(border=True):
        st.text_input("Title", key="bk_title",
                      placeholder="Pull-Apart Chopped Cheese")
        st.text_area(
            "Paste the ingredients", height=150, max_chars=20_000, key="bk_paste",
            help="Paste straight off the recipe page — headings, section labels, "
                 "and the directions section are cleaned out automatically.",
            placeholder="1/4 cup mayonnaise\n2 tablespoons ketchup\n…",
        )
        st.text_input("…or a recipe link", key="bk_url",
                      placeholder="https://example.com/chopped-cheese")
        if st.button("Parse recipe", type="primary", key="bk_parse"):
            _parse_for_preview()

    preview = st.session_state.get("bk_preview")
    if preview:
        with st.container(border=True):
            st.caption("Preview — edit anything, then add. Drop stray lines the "
                       "cleaner missed; one ingredient per line.")
            st.text_input("Title", value=preview["title"], key="bk_prev_title")
            st.text_area(
                "Ingredients (one per line)",
                value="\n".join(preview["ingredients"]),
                height=200, key="bk_prev_ings",
            )
            add_col, discard_col = st.columns(2)
            with add_col:
                if st.button("Add to backlog", type="primary", key="bk_add"):
                    if _commit_backlog():
                        st.rerun()
            with discard_col:
                if st.button("Discard", key="bk_discard"):
                    st.session_state.pop("bk_preview", None)
                    st.rerun()

    entries = golden.read_backlog(BACKLOG)
    if not entries:
        st.info("Backlog is empty — add a recipe above to get started.")
        return

    n_open = sum(1 for e in entries if e.status == "open")
    n_sub = sum(1 for e in entries if e.status == "submitted")
    st.caption(f"{len(entries)} queued · {n_open} open · {n_sub} submitted")
    st.dataframe(
        [
            {"status": e.status, "recipe_id": e.recipe_id, "title": e.title,
             "source": e.source, "ingredients": len(e.ingredients)}
            for e in entries
        ],
        hide_index=True,
    )

    col_submit, col_remove = st.columns(2)
    with col_submit:
        if st.button(
            f"Submit {n_open} open recipe(s) for review",
            type="primary",
            disabled=n_open == 0,
            key="backlog_submit",
        ):
            for e in entries:
                if e.status == "open":
                    e.status = "submitted"
            golden.write_backlog(entries, BACKLOG)
            st.success(f"Marked {n_open} recipe(s) submitted — now generate drafts.")
    with col_remove:
        to_remove = st.multiselect(
            "Remove from backlog", [e.recipe_id for e in entries], key="backlog_remove"
        )
        if st.button("Remove selected", disabled=not to_remove, key="backlog_remove_btn"):
            kept = [e for e in entries if e.recipe_id not in set(to_remove)]
            golden.write_backlog(kept, BACKLOG)
            st.success(f"Removed {len(entries) - len(kept)} recipe(s).")

    if n_sub:
        with st.expander("How to generate drafts from submitted recipes"):
            st.markdown(
                "Open a **separate** Claude instance in this repo and point it at "
                "`ai_docs/golden_draft_handoff.md`. It reads the submitted entries "
                "from `evals/backlog.jsonl`, runs the real scorer on each, drafts "
                "the labels, and appends them to `evals/golden_drafts.jsonl`. Then "
                "come back to the **Review & grade** tab."
            )


# ---- tab: review & grade -----------------------------------------------------

def _nav(delta: int) -> None:
    st.session_state.grade_idx = st.session_state.get("grade_idx", 0) + delta


def _save_draft(drafts: list[golden.GoldenDraft], idx: int, *, approve: bool) -> None:
    """Read the current grading widgets into the draft, validate, and persist."""
    rid = drafts[idx].row.recipe_id
    ss = st.session_state
    band = ss.get(f"g_{rid}_band")
    score = ss.get(f"g_{rid}_score")
    if band is None or score is None:
        st.error("Set both a target band and a target score before saving.")
        return
    try:
        new_row = golden.GoldenRow(
            recipe_id=rid,
            source=(ss.get(f"g_{rid}_source") or "").strip() or "pasted",
            title=ss.get(f"g_{rid}_title") or "",
            raw_ingredients=ss.get(f"g_{rid}_raw") or "",
            target_band=band,
            target_score=int(score),
            expected_swaps=ss.get(f"g_{rid}_swaps") or "",
            swap_quality=ss.get(f"g_{rid}_quality"),
            notes=ss.get(f"g_{rid}_notes") or "",
        )
    except ValidationError as e:
        st.error(
            "Couldn't save — fix these fields:\n\n"
            + "\n".join(
                f"- **{'.'.join(str(x) for x in err['loc'])}**: {err['msg']}"
                for err in e.errors()
            )
        )
        return
    drafts[idx].row = new_row
    if approve:
        drafts[idx].status = "approved"
    golden.write_drafts(drafts, DRAFTS)
    if approve:
        st.session_state.grade_idx = idx + 1  # advance past the one just approved
    st.toast("Approved." if approve else "Saved.")
    st.rerun()


def _review_tab() -> None:
    drafts, skipped = golden.read_drafts(DRAFTS)
    if skipped:
        st.caption(f"⚠️ {skipped} malformed draft line(s) skipped.")
    if not drafts:
        st.info(
            "No drafts yet. Queue recipes in the **Backlog** tab, submit them, then "
            "run the draft generator (see `ai_docs/golden_draft_handoff.md`)."
        )
        return

    n = len(drafts)
    idx = max(0, min(st.session_state.get("grade_idx", 0), n - 1))
    st.session_state.grade_idx = idx
    n_approved = sum(1 for d in drafts if d.status == "approved")
    draft = drafts[idx]
    rid = draft.row.recipe_id

    st.caption(f"Draft {idx + 1} of {n} · {n_approved} approved · this one: {draft.status}")

    with st.container(border=True):
        st.subheader(draft.row.title or rid)
        st.text(f"recipe_id: {rid}   ·   source: {draft.row.source}")
        st.code("\n".join(draft.row.ingredients), language=None)
        if draft.model_verdict is not None:
            _render_model_verdict(draft.model_verdict)
        else:
            st.caption("No model verdict was captured for this draft.")

    st.markdown("#### Your grade")
    st.selectbox(
        "Swap quality — your 1–5 grade of the model's swaps above",
        QUALITY_OPTIONS,
        index=QUALITY_OPTIONS.index(draft.row.swap_quality),
        format_func=lambda v: "not graded" if v is None else str(v),
        key=f"g_{rid}_quality",
    )
    st.text_area(
        "Notes — why, or where it's ambiguous",
        value=draft.row.notes,
        key=f"g_{rid}_notes",
        height=90,
    )

    with st.expander("Adjust the drafted labels (band, score, swaps, recipe text)"):
        st.selectbox(
            "Target band",
            BAND_OPTIONS,
            index=BAND_OPTIONS.index(draft.row.target_band)
            if draft.row.target_band in BAND_OPTIONS else None,
            placeholder="Pick the band you judge correct",
            key=f"g_{rid}_band",
        )
        st.number_input(
            "Target score (0–100)",
            min_value=0, max_value=100, value=draft.row.target_score,
            key=f"g_{rid}_score",
        )
        st.text_input(
            "Expected swaps (from>to; from>to)",
            value=draft.row.expected_swaps, key=f"g_{rid}_swaps",
        )
        st.text_input("Title", value=draft.row.title, key=f"g_{rid}_title")
        st.text_area(
            "Raw ingredients (separated by '; ')",
            value=draft.row.raw_ingredients, key=f"g_{rid}_raw", height=80,
        )
        st.text_input("Source", value=draft.row.source, key=f"g_{rid}_source")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("Approve & next", type="primary", key=f"g_{rid}_approve"):
            _save_draft(drafts, idx, approve=True)
    with c2:
        if st.button("Save", key=f"g_{rid}_save"):
            _save_draft(drafts, idx, approve=False)
    with c3:
        st.button("← Prev", disabled=idx == 0, on_click=_nav, args=(-1,), key=f"g_{rid}_prev")
    with c4:
        st.button("Next →", disabled=idx >= n - 1, on_click=_nav, args=(1,), key=f"g_{rid}_next")


# ---- tab: promote ------------------------------------------------------------

def _promote_tab() -> None:
    drafts, _ = golden.read_drafts(DRAFTS)
    approved = [d for d in drafts if d.status == "approved"]
    try:
        already = golden.existing_recipe_ids(GOLDEN_CSV)
    except OSError:
        already = set()
    pending = [d for d in approved if d.row.recipe_id not in already]

    st.caption(
        f"{len(drafts)} drafts · {len(approved)} approved · "
        f"{len(pending)} ready to promote (not yet in golden_set.csv)"
    )
    if approved:
        st.dataframe(
            [
                {"recipe_id": d.row.recipe_id, "title": d.row.title,
                 "band": d.row.target_band, "score": d.row.target_score,
                 "swap_quality": d.row.swap_quality,
                 "in golden set": d.row.recipe_id in already}
                for d in approved
            ],
            hide_index=True,
        )

    if st.button(
        f"Promote {len(pending)} approved row(s) to golden_set.csv",
        type="primary", disabled=not pending, key="promote_btn",
    ):
        try:
            promoted, skipped = golden.promote_approved(drafts, GOLDEN_CSV)
        except (ValueError, OSError) as e:
            st.error(f"Couldn't promote: {e}")
            return
        st.success(
            f"Promoted {len(promoted)} row(s) to golden_set.csv."
            + (f" Skipped {len(skipped)} duplicate(s)." if skipped else "")
        )


# ---- tab: logs (read-only) ---------------------------------------------------

def _logs_tab() -> None:
    files = vlog.list_log_files(LOG_DIR)
    if not files:
        st.info("No logs yet — score recipes in the scorer (`streamlit run app.py`).")
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
        page = st.number_input("Page", 1, pages, 1, key="logs_page")
    shown = newest_first[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    st.caption(f"{len(records)} verdicts, newest first — page {page}/{pages}")
    st.dataframe(
        [
            {"when": r.ts, "title": r.title, "band": r.verdict.band,
             "score": r.verdict.score, "flagged": len(r.verdict.flagged_ingredients),
             "swaps": len(r.verdict.swaps)}
            for r in shown
        ],
        hide_index=True,
    )
    idx = st.selectbox(
        "Inspect a verdict", range(len(shown)),
        format_func=lambda i: f"{shown[i].ts} — {shown[i].title[:60]}",
        key="logs_detail",
    )
    st.json(shown[idx].verdict.model_dump())
    st.code("\n".join(shown[idx].ingredients), language=None)


# ---- tab: results (read-only) ------------------------------------------------

def _results_tab() -> None:
    files = sorted(RESULTS_DIR.glob("*.csv"), reverse=True) if RESULTS_DIR.is_dir() else []
    if not files:
        st.info("No eval results yet — run `.venv/bin/python evals/evaluate.py`.")
        return
    file = st.selectbox(
        "Results file (newest first)", files, format_func=lambda p: p.name, key="results_file"
    )
    with file.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        st.info("This results file is empty.")
        return

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


# ---- entrypoint --------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="CocoonKitchen Console", page_icon="🏷️")
    st.title("🏷️ CocoonKitchen Console")
    st.caption(
        "Internal golden-set builder — local only, never deployed. "
        "Labels are yours; the model only suggests."
    )

    backlog, review, promote, logs, results = st.tabs(
        ["Backlog", "Review & grade", "Promote", "Logs", "Results"]
    )
    with backlog:
        _backlog_tab()
    with review:
        _review_tab()
    with promote:
        _promote_tab()
    with logs:
        _logs_tab()
    with results:
        _results_tab()


if __name__ == "__main__":
    main()
