"""Tiny manual-test entrypoint for the scoring core.

Loads ``.env`` (so the provider seam is configured) and scores one pasted
recipe, printing the Verdict as JSON. This is a dev/manual-test tool — the real
UI is Phase 3 (Streamlit). Unlike the pure core, this entrypoint is allowed to
load python-dotenv.

Usage:
    .venv/bin/python -m clean_recipe.cli recipe.txt      # first line = title, rest = ingredients
    printf "Title\\nflour\\nsugar\\n" | .venv/bin/python -m clean_recipe.cli
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv


def _read(source: str) -> tuple[str, list[str]]:
    lines = [ln.strip() for ln in source.splitlines() if ln.strip()]
    if not lines:
        raise SystemExit("No recipe provided. Give a title on line 1, ingredients after.")
    return lines[0], lines[1:]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    load_dotenv()  # reads .env from the current working directory

    if argv:
        text = Path(argv[0]).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    title, ingredients = _read(text)

    # Imported here so `--help`-style misuse doesn't require a configured provider.
    from .score import score_recipe

    verdict = score_recipe(title, ingredients)
    print(verdict.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
