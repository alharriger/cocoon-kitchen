"""Run log + regression baseline for the eval harness (Phase 6 Task 5).

The bake-off already writes per-row detail CSVs to ``evals/results/`` — but that
directory is **gitignored**, so a run's headline numbers evaporate unless they
are hand-copied into the change-log. This module makes them durable:

- ``evals/run_log.csv`` (tracked in git) — one appended row per **full-set**
  eval run: timestamp, provider/model, headline metrics, and the rubric
  fingerprint that produced them. ``--limit`` slices are never logged (a
  truncated slice is not comparable — same discipline as the bake-off's
  coverage guard).
- ``evals/baseline.json`` (tracked in git) — the accepted regression baseline.
  Updated only via an explicit ``--update-baseline`` run (never silently), so
  "the number to beat" is a deliberate human-visible act, not a side effect.
- ``compare_to_baseline`` — the Phase-7 "no regression" gate's engine: verdicts
  respect the documented eval noise floor (~2pp band accuracy / ~1 MAE at
  temperature=0; see working_sprint "Decisions carried in").

Rubric fingerprinting: every row records the human-owned config that produced
it — the declared schema versions parsed from ``rubric/rubric.yaml`` and
``rubric/lexicons.yaml`` plus a short content hash of both files. The hash
catches drift the version comments miss (e.g. Amber curating lexicon contents,
an alpha retune) so two runs are only ever compared knowing whether the rubric
changed between them.

This file consumes metrics; it never edits the human-owned rubric or labels.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

# CSV formula-injection guard, shared with the golden-set writer. Model names /
# notes land in a tracked CSV a human will open in a spreadsheet; a value like
# "=cmd" must not execute (same threat model as golden.py).
from clean_recipe.golden import defang_cell

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LOG = REPO_ROOT / "evals" / "run_log.csv"
BASELINE_PATH = REPO_ROOT / "evals" / "baseline.json"
RUBRIC_YAML = REPO_ROOT / "rubric" / "rubric.yaml"
LEXICONS_YAML = REPO_ROOT / "rubric" / "lexicons.yaml"

# Eval noise floor at temperature=0 (measured, Phase 6): identical runs move
# ~2pp band accuracy / ~1 MAE. A delta inside the floor is "within noise", not
# a regression or an improvement.
NOISE_BAND = 0.02
NOISE_MAE = 1.0

# Comparison verdicts — shared constants so the gate in evaluate.py matches by
# name, not by re-spelling the string (a rename fails loud at import).
REGRESSION = "regression"
IMPROVED = "improved"
WITHIN_NOISE = "within-noise"
INCOMPARABLE = "incomparable"

_RUBRIC_VERSION_RE = re.compile(r"Rubric schema version:\s*(v\d+(?:\.\d+)*)")
_LEXICON_VERSION_RE = re.compile(r"Lexicon schema version:\s*(v\d+(?:\.\d+)*)")

RUN_LOG_COLUMNS = [
    "timestamp",
    "kind",  # "single" | "bakeoff"
    "provider",
    "model",
    "rows",
    "attempted",
    "band_accuracy",  # fraction 0–1
    "score_mae",
    "mean_signed_error",
    "processed_correct",
    "processed_total",
    "rubric_version",
    "lexicon_version",
    "config_hash",
    "results_csv",
    "note",
]


def _parse_version(path: Path, pattern: re.Pattern[str]) -> str:
    """Pull the declared schema version out of a rubric file's header comment.

    Falls back to ``"unknown"`` rather than raising: the fingerprint must never
    block an eval run, and the content hash still catches any change.
    """
    try:
        match = pattern.search(path.read_text(encoding="utf-8"))
    except OSError:
        return "unknown"
    return match.group(1) if match else "unknown"


def rubric_fingerprint(
    rubric_path: Path | None = None, lexicons_path: Path | None = None
) -> dict[str, str]:
    """Identify the human-owned config a run was measured against.

    Returns ``rubric_version`` / ``lexicon_version`` (declared, from the file
    headers) and ``config_hash`` (sha256 over both files' bytes, first 10 hex
    chars). The hash is the drift detector: it changes on ANY edit — a curated
    lexicon term, an alpha retune — even when the declared versions don't.
    """
    rubric_path = rubric_path or RUBRIC_YAML
    lexicons_path = lexicons_path or LEXICONS_YAML
    digest = hashlib.sha256()
    for p in (rubric_path, lexicons_path):
        try:
            digest.update(p.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")  # file boundary: content can't shift between files
    return {
        "rubric_version": _parse_version(rubric_path, _RUBRIC_VERSION_RE),
        "lexicon_version": _parse_version(lexicons_path, _LEXICON_VERSION_RE),
        "config_hash": digest.hexdigest()[:10],
    }


@dataclass
class RunRecord:
    """One full-set eval run's headline numbers + provenance.

    Mirrors what the CLI prints (and what the change-log has been recording by
    hand): the metrics, how complete the run was, and the rubric fingerprint.
    """

    timestamp: str  # ISO-8601, seconds precision
    kind: str  # "single" | "bakeoff"
    provider: str  # registry name ("glm", "openrouter", …) or "" for env default
    model: str
    rows: int
    attempted: int
    band_accuracy: float
    score_mae: float
    mean_signed_error: float
    processed_correct: int
    processed_total: int
    rubric_version: str
    lexicon_version: str
    config_hash: str
    results_csv: str  # basename of the per-row detail CSV (gitignored dir)
    note: str = ""

    @property
    def coverage(self) -> float:
        return self.rows / self.attempted if self.attempted else 0.0


def append_run(record: RunRecord, path: Path | None = None) -> Path:
    """Append one run to the tracked run log, writing the header on first use.

    Free-text-ish cells (model/provider/note/results_csv) are defanged against
    spreadsheet formula injection; numeric formatting is fixed-precision so the
    log diffs cleanly in git.
    """
    path = path or RUN_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(RUN_LOG_COLUMNS)
        writer.writerow(
            [
                record.timestamp,
                record.kind,
                defang_cell(record.provider),
                defang_cell(record.model),
                record.rows,
                record.attempted,
                f"{record.band_accuracy:.4f}",
                f"{record.score_mae:.2f}",
                f"{record.mean_signed_error:+.1f}",
                record.processed_correct,
                record.processed_total,
                record.rubric_version,
                record.lexicon_version,
                record.config_hash,
                defang_cell(record.results_csv),
                defang_cell(record.note),
            ]
        )
    return path


def write_baseline(record: RunRecord, path: Path | None = None) -> Path:
    """Persist a run as the accepted regression baseline (deliberate act only).

    The caller (evaluate.py ``--update-baseline``) enforces eligibility: a
    full-set, coverage-complete, single-model run. This function just writes.
    """
    path = path or BASELINE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(record)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return path


def load_baseline(path: Path | None = None) -> RunRecord | None:
    """Load the accepted baseline, or ``None`` if none has been set yet.

    A malformed baseline file fails loud (it's a tracked, hand-visible artifact
    — silent fallback would let a corrupted gate pass as "no baseline").
    """
    path = path or BASELINE_PATH
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    try:
        return RunRecord(**data)
    except TypeError as e:
        # A schema-drifted baseline (older/newer field set) must not read as a
        # cryptic crash at the end of an otherwise-good eval run.
        raise ValueError(
            f"{path} does not match the current RunRecord schema ({e}). "
            "Re-seed it with: evaluate.py --update-baseline"
        ) from e


def compare_to_baseline(
    record: RunRecord, baseline: RunRecord
) -> tuple[str, list[str]]:
    """Judge a run against the baseline. Returns ``(verdict, report_lines)``.

    Verdicts: ``"regression"`` (either metric worse than the noise floor
    allows — checked first, so a mixed result reads as a regression),
    ``"improved"`` (either metric better beyond the floor, none worse),
    ``"within-noise"`` (all deltas inside the floor), ``"incomparable"``
    (different model — cross-model deltas are a bake-off's job, not a gate's).
    A rubric-config change doesn't block comparison — measuring a rubric edit
    against the old baseline is the point — but it is called out in the report.
    """
    lines: list[str] = []
    if record.model != baseline.model:
        lines.append(
            f"baseline model is {baseline.model!r}, this run is {record.model!r} "
            "— no regression verdict across models (use the bake-off to compare)."
        )
        return INCOMPARABLE, lines

    d_band = record.band_accuracy - baseline.band_accuracy
    d_mae = record.score_mae - baseline.score_mae
    lines.append(
        f"baseline ({baseline.timestamp}): band {baseline.band_accuracy:.1%}, "
        f"MAE {baseline.score_mae:.2f}  →  this run: band "
        f"{record.band_accuracy:.1%} ({d_band:+.1%}), MAE {record.score_mae:.2f} "
        f"({d_mae:+.2f})"
    )
    if record.config_hash != baseline.config_hash:
        lines.append(
            f"rubric/lexicons changed since baseline (hash {baseline.config_hash} "
            f"→ {record.config_hash}) — a real delta is expected, not noise."
        )
    if record.coverage < 1.0:
        lines.append(
            f"note: this run scored {record.rows}/{record.attempted} rows "
            "(skips make the comparison approximate)."
        )

    regressed = d_band < -NOISE_BAND or d_mae > NOISE_MAE
    improved = d_band > NOISE_BAND or d_mae < -NOISE_MAE
    if regressed:
        verdict = REGRESSION
        lines.append(
            f"REGRESSION: beyond the noise floor (±{NOISE_BAND:.0%} band / "
            f"±{NOISE_MAE:.0f} MAE)."
        )
    elif improved:
        verdict = IMPROVED
        lines.append(
            "Improved beyond the noise floor. If this should become the new "
            "number-to-beat, re-run with --update-baseline."
        )
    else:
        verdict = WITHIN_NOISE
        lines.append(
            f"Within the noise floor (±{NOISE_BAND:.0%} band / ±{NOISE_MAE:.0f} "
            "MAE) — treat as unchanged."
        )
    return verdict, lines
