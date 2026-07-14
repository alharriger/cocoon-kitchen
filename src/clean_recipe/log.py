"""Append-only JSONL logging of scoring inputs + verdicts, and the read side.

``log_verdict`` is called by ``score_recipe()`` on every scored recipe; the
reader functions below (Phase 4) are how the labeling console browses those
records. This module owns the JSONL record format for both directions.

Security notes:
- A log record contains ONLY recipe input and the resulting Verdict — never API
  keys, secrets, or unrelated PII. ``json.dumps`` escapes any newlines in the
  content, so each record stays on exactly one line (no log injection via
  crafted recipe text).
- Reading is defensive: every line is parsed inside try/except and re-validated
  through the ``Verdict`` schema; a malformed or hostile line is skipped and
  counted, never a crash and never un-validated data reaching a consumer.

Logs are written under ``data/logs/`` which is gitignored.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .schema import Verdict

DEFAULT_LOG_DIR = Path("data/logs")
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "verdicts.jsonl"


def log_verdict(
    title: str,
    ingredients: list[str],
    verdict: Verdict,
    path: Path | str = DEFAULT_LOG_FILE,
) -> Path:
    """Append one JSON line — timestamp + input + verdict — and return the path.

    Creates the parent directory if it does not exist. One JSON object per line
    (JSONL). The verdict is serialized via ``model_dump()`` so it round-trips
    through the schema.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "ingredients": ingredients,
        "verdict": verdict.model_dump(),
    }
    line = json.dumps(record, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


class LogRecord(BaseModel):
    """One parsed log line; the verdict re-validates through the schema."""

    ts: str
    title: str
    ingredients: list[str]
    verdict: Verdict


def read_log(path: Path | str) -> tuple[list[LogRecord], int]:
    """Read a JSONL log; return ``(records, skipped_count)``.

    Any line that isn't valid JSON in the ``log_verdict`` shape (including a
    schema-invalid verdict) is skipped and counted — a corrupt line must never
    brick the console. Order is preserved (oldest first, as written).
    """
    path = Path(path)
    records: list[LogRecord] = []
    skipped = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                records.append(LogRecord.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError):
                skipped += 1
    return records, skipped


def list_log_files(log_dir: Path | str = DEFAULT_LOG_DIR) -> list[Path]:
    """All ``*.jsonl`` files under ``log_dir``, sorted by name; [] if none."""
    log_dir = Path(log_dir)
    if not log_dir.is_dir():
        return []
    return sorted(log_dir.glob("*.jsonl"))
