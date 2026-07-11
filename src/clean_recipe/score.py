"""The scoring core: ``score_recipe(title, ingredients) -> Verdict``.

This is the pure, UI-agnostic function the whole stack imports (architecture.md
load-bearing rule). It never imports Streamlit. The flow:

1. Build the prompt from the rubric + recipe (prompt.py).
2. Call the model in JSON mode (client.py) — provider is env config.
3. Validate the model's JSON into ``ModelOutput`` (fail loud, no coercion).
4. Compose the composite ``score`` and ``band`` from the rubric weights/cutoffs
   — the arithmetic is deterministic and lives in code, not the model, so the
   human-owned weights in rubric.yaml stay authoritative.
5. Assemble and validate the full ``Verdict``.
6. Log the input + verdict (log.py).

On malformed model output we retry once with a corrective nudge; if it still
fails, we raise loudly rather than emit a partial card (Contract 1 / Contract 3).
"""
from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from .client import complete_json
from .log import log_verdict
from .prompt import build_messages, load_rubric
from .schema import Band, SubScores, Swap, Verdict


class ModelOutput(BaseModel):
    """The partial the model is asked to return; ``score``/``band`` are computed."""

    sub_scores: SubScores
    flagged_ingredients: list[str]
    swaps: list[Swap]


class ScoringError(RuntimeError):
    """Raised when the model output can't be parsed into a valid Verdict."""


def _parse(raw: str) -> ModelOutput:
    """Parse+validate one raw model response; raises on malformed output."""
    if not raw.strip():
        raise ScoringError(
            "model returned empty content — it likely spent its whole token budget "
            "on hidden reasoning before emitting JSON. Disable the provider's thinking "
            'mode (e.g. set LLM_EXTRA_BODY={"thinking":{"type":"disabled"}} for GLM).'
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ScoringError(f"model did not return JSON: {e}") from e
    try:
        return ModelOutput.model_validate(data)
    except ValidationError as e:
        raise ScoringError(f"model JSON failed schema validation: {e}") from e


def compose_score(sub_scores: SubScores, weights: dict[str, float]) -> int:
    """Weighted composite of the sub-scores, rounded and clamped to 0–100."""
    values = sub_scores.model_dump()
    total = sum(weights[k] * values[k] for k in values)
    return max(0, min(100, round(total)))


def derive_band(score: int, bands: dict[str, list[int]]) -> Band:
    """Look up the band whose inclusive [min, max] span contains ``score``."""
    for band, (low, high) in bands.items():
        if low <= score <= high:
            return band  # type: ignore[return-value]
    raise ScoringError(f"score {score} fell outside every band cutoff in rubric.yaml")


def _build_verdict(output: ModelOutput, rubric: dict) -> Verdict:
    score = compose_score(output.sub_scores, rubric["weights"])
    band = derive_band(score, rubric["bands"])
    return Verdict(
        score=score,
        band=band,
        sub_scores=output.sub_scores,
        flagged_ingredients=output.flagged_ingredients,
        swaps=output.swaps,
    )


_REPAIR_HINT = {
    "role": "user",
    "content": (
        "Your previous reply was not valid JSON in the required shape. Reply "
        "again with ONLY the JSON object — keys sub_scores (the six named "
        "0–100 integers), flagged_ingredients (list), and swaps (exactly three "
        "objects with from_ingredient, to_ingredient, reason). No prose."
    ),
}


def score_recipe(
    title: str,
    ingredients: list[str],
    *,
    model: str | None = None,
    log: bool = True,
) -> Verdict:
    """Score a recipe and return a validated Verdict.

    ``model`` overrides ``LLM_MODEL`` (used by the eval bake-off to compare
    providers). ``log=False`` skips the JSONL log (used by tests/evals).
    Raises ``ScoringError`` if the model can't produce a valid Verdict after a
    single retry — we never emit a partial card.
    """
    rubric = load_rubric()
    messages = build_messages(title, ingredients, rubric)

    raw = complete_json(messages, model=model)
    try:
        output = _parse(raw)
    except ScoringError:
        # One corrective retry before failing loud, with extra headroom as a
        # safety net for providers whose thinking can't be fully disabled.
        raw = complete_json(messages + [_REPAIR_HINT], model=model, max_tokens=4096)
        output = _parse(raw)

    verdict = _build_verdict(output, rubric)
    if log:
        log_verdict(title, ingredients, verdict)
    return verdict
