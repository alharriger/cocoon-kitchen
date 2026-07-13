"""Golden-set row shape (Contract 4) — the single source of truth.

Source of truth: ai_docs/llm_contracts.md "Contract 4: Golden-set label format"
(v0.2 — added ``swap_quality``). Both consumers import from here: the eval
harness (``evals/evaluate.py``) reads rows, the labeling console (``console.py``)
writes them. If this file and the doc disagree, the doc wins and this is a bug.

The labels themselves are HUMAN-owned: this module validates and transports
rows, it never invents target bands/scores/swaps.

Pure module — no Streamlit, no network (architecture.md load-bearing rule).

Security notes:
- ``append_golden_row`` is the only write path. It is append-only, verifies the
  header matches Contract 4 before writing (no silent schema drift), and never
  creates, edits, or deletes rows.
- ``defang_cell`` guards against CSV formula injection: golden_set.csv gets
  opened in Excel/Numbers, and a logged recipe title like ``=HYPERLINK(...)``
  written verbatim would execute as a formula. A leading space neutralizes it,
  and is lossless for the harness because ``load_golden`` strips every cell.
"""
from __future__ import annotations

import csv
import json
import re
from itertools import count
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .schema import Band, Swap, Verdict

# Exact Contract 4 columns, in order. The golden CSV must match this verbatim.
GOLDEN_COLUMNS = [
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

# Cells starting with these run as formulas when the CSV is opened in a
# spreadsheet app. (tab/CR are quoting-bypass tricks in some importers.)
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class GoldenRow(BaseModel):
    """One validated golden-set row (Contract 4 v0.2)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    recipe_id: str = Field(min_length=1)
    source: str = "pasted"
    title: str = Field(min_length=1)
    raw_ingredients: str = Field(min_length=1)  # "; "-separated, as-labeled
    target_band: Band
    target_score: int = Field(ge=0, le=100)
    expected_swaps: str = ""  # "from>to; from>to", or blank
    swap_quality: int | None = Field(default=None, ge=1, le=5)
    notes: str = ""

    @field_validator("raw_ingredients")
    @classmethod
    def _at_least_one_ingredient(cls, v: str) -> str:
        if not parse_ingredients(v):
            raise ValueError("raw_ingredients contains no ingredients")
        return v

    @field_validator("expected_swaps")
    @classmethod
    def _swaps_format(cls, v: str) -> str:
        for segment in v.split(";"):
            segment = segment.strip()
            if not segment:
                continue  # tolerate a trailing/doubled semicolon
            left, sep, right = segment.partition(">")
            if not sep or not left.strip() or not right.strip() or ">" in right:
                raise ValueError(
                    f"expected_swaps segment {segment!r} is not 'from>to'"
                )
        return v

    @property
    def ingredients(self) -> list[str]:
        """The ``raw_ingredients`` cell split into a list."""
        return parse_ingredients(self.raw_ingredients)


def parse_ingredients(raw: str) -> list[str]:
    """Split a ``raw_ingredients`` cell ("a; b; c") into ["a", "b", "c"]."""
    return [part.strip() for part in raw.split(";") if part.strip()]


def join_ingredients(ingredients: list[str]) -> str:
    """Join an ingredient list into a ``raw_ingredients`` cell.

    ``;`` inside an ingredient name would corrupt the cell's own delimiter, so
    it is replaced with ``,`` (documented micro-lossy edge; names never need it).
    """
    return "; ".join(
        item.replace(";", ",").strip() for item in ingredients if item.strip()
    )


def _defang_name(name: str) -> str:
    """Make an ingredient name safe for the swap/ingredient micro-formats."""
    return name.replace(">", ",").replace(";", ",").strip()


def format_swaps(swaps: list[Swap]) -> str:
    """Render Verdict swaps as an ``expected_swaps`` pre-fill: ``from>to; …``."""
    return "; ".join(
        f"{_defang_name(s.from_ingredient)}>{_defang_name(s.to_ingredient)}"
        for s in swaps
    )


def defang_cell(value: str) -> str:
    """Neutralize spreadsheet formula injection with a leading space.

    Lossless for the harness: ``load_golden`` strips every cell it reads.
    """
    return " " + value if value.startswith(_FORMULA_PREFIXES) else value


def load_golden(path: Path | str) -> list[GoldenRow]:
    """Load + validate the golden CSV; fail loud on a malformed file/row."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != GOLDEN_COLUMNS:
            raise ValueError(
                f"golden set {path} has columns {reader.fieldnames}, "
                f"expected exactly {GOLDEN_COLUMNS} (Contract 4)"
            )
        rows: list[GoldenRow] = []
        for i, raw in enumerate(reader, start=2):  # start=2: header is line 1
            cells = {k: (v or "").strip() for k, v in raw.items()}
            if not any(cells.values()):
                continue  # skip a fully blank line
            try:
                rows.append(
                    GoldenRow(
                        recipe_id=cells["recipe_id"],
                        source=cells["source"] or "pasted",
                        title=cells["title"],
                        raw_ingredients=cells["raw_ingredients"],
                        target_band=cells["target_band"],  # type: ignore[arg-type]
                        target_score=_int_cell(cells["target_score"], "target_score"),
                        expected_swaps=cells["expected_swaps"],
                        swap_quality=(
                            _int_cell(cells["swap_quality"], "swap_quality")
                            if cells["swap_quality"]
                            else None
                        ),
                        notes=cells["notes"],
                    )
                )
            except (ValidationError, ValueError) as e:
                raise ValueError(f"{path} line {i}: {e}") from e
    if not rows:
        raise ValueError(f"golden set {path} has no data rows")
    return rows


def _int_cell(cell: str, name: str) -> int:
    try:
        return int(cell)
    except ValueError as e:
        raise ValueError(f"{name} {cell!r} is not an int") from e


def existing_recipe_ids(path: Path | str) -> set[str]:
    """All non-blank ``recipe_id`` values currently in the golden CSV."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {
            rid.strip()
            for row in reader
            if (rid := row.get("recipe_id") or "").strip()
        }


def suggest_recipe_id(title: str, existing: set[str]) -> str:
    """Slug the title into a stable short id, suffixing on collision."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    slug = slug or "recipe"
    if slug not in existing:
        return slug
    for n in count(2):
        candidate = f"{slug}-{n}"
        if candidate not in existing:
            return candidate
    raise AssertionError("unreachable")


def append_golden_row(row: GoldenRow, path: Path | str) -> int:
    """Append one validated row to the golden CSV; return the new row count.

    Append-only by construction: verifies the existing header equals Contract 4
    verbatim (refuses to append into a stale/foreign schema), never rewrites,
    reorders, or deletes rows, and never creates the file — the template ships
    in-repo.
    """
    path = Path(path)
    if not path.exists():
        raise ValueError(
            f"golden set {path} does not exist — this writer appends to the "
            "in-repo template, it never creates a new file"
        )
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header != GOLDEN_COLUMNS:
            raise ValueError(
                f"golden set {path} has columns {header}, "
                f"expected exactly {GOLDEN_COLUMNS} (Contract 4) — refusing to append"
            )
        existing_rows = sum(1 for r in reader if any(cell.strip() for cell in r))
        needs_newline = False
        f.seek(0)
        content = f.read()
        if content and not content.endswith("\n"):
            needs_newline = True

    cells = [
        row.recipe_id,
        row.source,
        row.title,
        row.raw_ingredients,
        row.target_band,
        str(row.target_score),
        row.expected_swaps,
        "" if row.swap_quality is None else str(row.swap_quality),
        row.notes,
    ]
    with path.open("a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        csv.writer(f).writerow([defang_cell(c) for c in cells])
    return existing_rows + 1


# ---- the golden-set builder pipeline -----------------------------------------
#
# The console (console.py) drives a three-stage assembly line, all thin JSONL/CSV
# (no DB — anti-bloat holds):
#
#   backlog.jsonl  ──►  golden_drafts.jsonl  ──►  golden_set.csv
#   (Amber curates      (a separate Claude       (the append-only,
#    recipes)            instance drafts          human-owned final set)
#                        labels + real verdict)
#
# BacklogEntry and GoldenDraft are the shapes for the first two files; the draft
# holds a full GoldenRow (Claude's proposed labels) plus the real model verdict
# so Amber can grade the model's swaps. Promotion extracts the row and appends it
# to golden_set.csv via the append-only writer above.


class BacklogEntry(BaseModel):
    """One recipe Amber has queued for labeling (a row of backlog.jsonl)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    recipe_id: str = Field(min_length=1)
    source: str = "pasted"  # URL, or "pasted"
    title: str = Field(min_length=1)
    ingredients: list[str] = Field(min_length=1)
    status: Literal["open", "submitted"] = "open"
    added_ts: str = ""  # ISO timestamp; set by the console at add time

    @property
    def raw_ingredients(self) -> str:
        """The ``ingredients`` list rendered as a Contract-4 cell."""
        return join_ingredients(self.ingredients)


class GoldenDraft(BaseModel):
    """One draft golden row awaiting Amber's review (a row of golden_drafts.jsonl).

    ``row`` is the proposed Contract-4 label (drafted by the separate instance,
    fully editable by Amber — she owns the final label). ``model_verdict`` is the
    real model output captured at draft time, shown read-only so she can grade the
    model's swaps into ``row.swap_quality``. ``status`` gates promotion.
    """

    row: GoldenRow
    model_verdict: Verdict | None = None
    status: Literal["draft", "approved"] = "draft"


def _read_jsonl(path: Path | str, model: type[BaseModel]) -> tuple[list, int]:
    """Read a JSONL file into ``model`` instances; tolerant of malformed lines.

    Returns ``(records, skipped_count)``. A missing file is an empty list, not an
    error (the console creates these on first write). One bad line never bricks
    the reader — the separate draft-generating instance writes ``golden_drafts``,
    so a partial/corrupt line must degrade gracefully.
    """
    path = Path(path)
    if not path.exists():
        return [], 0
    records: list = []
    skipped = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValidationError:
                skipped += 1
    return records, skipped


def _write_jsonl(records: list[BaseModel], path: Path | str) -> None:
    """Rewrite a JSONL file with ``records`` (one JSON object per line).

    These files are console-owned working state (unlike the shipped golden CSV),
    so a full rewrite on mutate is fine — they are small and we own every writer.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")


def read_backlog(path: Path | str) -> list[BacklogEntry]:
    """All backlog entries; [] if the file doesn't exist. Skips malformed lines."""
    records, _ = _read_jsonl(path, BacklogEntry)
    return records


def write_backlog(entries: list[BacklogEntry], path: Path | str) -> None:
    """Rewrite backlog.jsonl (used to add, remove, or mark entries submitted)."""
    _write_jsonl(entries, path)


def read_drafts(path: Path | str) -> tuple[list[GoldenDraft], int]:
    """All draft rows + count of malformed lines skipped; ([], 0) if no file."""
    return _read_jsonl(path, GoldenDraft)


def write_drafts(drafts: list[GoldenDraft], path: Path | str) -> None:
    """Rewrite golden_drafts.jsonl (used when Amber edits/approves a draft)."""
    _write_jsonl(drafts, path)


def append_draft(draft: GoldenDraft, path: Path | str) -> None:
    """Append one draft to golden_drafts.jsonl (used by the draft generator)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(draft.model_dump_json() + "\n")


def promote_approved(
    drafts: list[GoldenDraft], golden_csv: Path | str
) -> tuple[list[str], list[str]]:
    """Append every ``approved`` draft's row to the golden CSV (append-only).

    Returns ``(promoted_ids, skipped_ids)``. A draft whose ``recipe_id`` already
    exists in the golden set is skipped (dedup) — this also makes re-running
    promotion a safe no-op, so there is no separate "promoted" state to track.
    """
    existing = existing_recipe_ids(golden_csv)
    promoted: list[str] = []
    skipped: list[str] = []
    for draft in drafts:
        if draft.status != "approved":
            continue
        if draft.row.recipe_id in existing:
            skipped.append(draft.row.recipe_id)
            continue
        append_golden_row(draft.row, golden_csv)
        existing.add(draft.row.recipe_id)
        promoted.append(draft.row.recipe_id)
    return promoted, skipped
