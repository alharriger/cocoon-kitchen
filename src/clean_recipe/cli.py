"""Tiny manual-test entrypoint for the full ingest → score pipeline.

Loads ``.env`` (so the provider seam is configured), turns input into a
normalized recipe via ``parse_recipe`` (URL or pasted text), scores it with
``score_recipe``, and prints the Verdict as JSON. This is a dev/manual-test tool
— the real UI is Phase 3 (Streamlit). Unlike the pure core, this entrypoint is
allowed to load python-dotenv.

Usage:
    .venv/bin/python -m clean_recipe.cli recipe.txt      # a file of pasted text
    .venv/bin/python -m clean_recipe.cli https://site/recipe   # a recipe URL
    printf "Title\\nflour\\nsugar\\n" | .venv/bin/python -m clean_recipe.cli
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv


def _resolve_source(argv: list[str]) -> str:
    """An http(s) arg is a URL (passed through); any other arg is a file whose
    contents are pasted text; no arg reads pasted text from stdin."""
    if not argv:
        return sys.stdin.read()
    arg = argv[0]
    if arg.startswith(("http://", "https://")):
        return arg
    return Path(arg).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    load_dotenv()  # reads .env from the current working directory

    source = _resolve_source(argv)

    # Imported here so misuse doesn't require a configured provider up front.
    from .parse import ParseError, parse_recipe
    from .score import NotARecipeError, score_recipe

    # Unusable input (bad/unparseable source, or judged not-a-recipe) is a clean
    # one-liner, not a traceback. Genuine failures (ScoringError, config errors)
    # still propagate so a dev sees the stack.
    try:
        recipe = parse_recipe(source)
        verdict = score_recipe(recipe.title, recipe.ingredients)
    except (ParseError, NotARecipeError) as e:
        print(f"not scored: {e}", file=sys.stderr)
        return 2

    print(f"# {recipe.title}  ({recipe.source})")
    print(verdict.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
