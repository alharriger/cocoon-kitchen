"""Append-only JSONL logging of scoring inputs + verdicts.

Designed to be wired into ``score_recipe()`` in Phase 2; it is not called at
runtime yet.

Security note (carry into Phase 2): a log record must contain ONLY recipe input
and the resulting Verdict — never API keys, secrets, or unrelated PII. When this
is hooked into the model call, keep that invariant. ``json.dumps`` escapes any
newlines in the content, so each record stays on exactly one line (no log
injection via crafted recipe text).

Logs are written under ``data/logs/`` which is gitignored.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

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
