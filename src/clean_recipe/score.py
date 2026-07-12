"""The scoring core: ``score_recipe(title, ingredients) -> Verdict``.

This is the pure, UI-agnostic function the whole stack imports (architecture.md
load-bearing rule). It never imports Streamlit. The flow:

1. Build the prompt from the rubric + recipe (prompt.py).
2. Call the model in JSON mode (client.py) — provider is env config.
3. Validate the model's JSON into ``ModelOutput`` (fail loud, no coercion).
   If the model judged the input isn't a recipe, raise ``NotARecipeError``.
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

from pydantic import BaseModel, ValidationError, model_validator

from .client import complete_json
from .log import log_verdict
from .prompt import build_messages, load_rubric
from .schema import Band, SubScores, Swap, Verdict


class ModelOutput(BaseModel):
    """The partial the model returns; ``score``/``band`` are computed.

    ``is_recipe`` gates scoring: when the model judges the input is not a recipe
    it returns ``is_recipe=false`` and omits the scoring fields. For a real recipe
    the scoring fields are required — the validator below fails loud otherwise, so
    a recipe that comes back without sub-scores hits the malformed/retry path
    rather than silently yielding an empty card.
    """

    is_recipe: bool
    # None (field absent) vs [] (present-but-empty) must stay distinguishable:
    # for a real recipe every scoring field must be *present* (a clean recipe may
    # still send flagged_ingredients: []), so the model omitting one fails loud
    # rather than defaulting to an empty card. Non-recipe output omits them all.
    sub_scores: SubScores | None = None
    flagged_ingredients: list[str] | None = None
    swaps: list[Swap] | None = None

    @model_validator(mode="after")
    def _recipe_has_scores(self) -> "ModelOutput":
        if self.is_recipe and (
            self.sub_scores is None
            or self.flagged_ingredients is None
            or self.swaps is None
        ):
            raise ValueError("is_recipe is true but scoring fields are missing")
        return self


class ScoringError(RuntimeError):
    """Raised when the model output can't be parsed into a valid Verdict."""


class NotARecipeError(ValueError):
    """Raised when the input isn't a recipe.

    This is a *valid, final* judgment (the model decided the text is not a food
    recipe), not malformed output — so unlike ScoringError it is never retried.
    The caller (UI/CLI) turns it into a friendly "that's not a recipe" message.
    """


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
    # All three guaranteed non-None here: is_recipe gate + ModelOutput validator.
    assert output.sub_scores is not None
    assert output.flagged_ingredients is not None
    assert output.swaps is not None
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
        "again with ONLY the JSON object. Always include is_recipe (boolean); "
        "when is_recipe is true also include sub_scores (the six named 0–100 "
        "integers), flagged_ingredients (list), and swaps (exactly three objects "
        "with from_ingredient, to_ingredient, reason). No prose."
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

    if not output.is_recipe:
        # A valid, final judgment — not malformed output, so never retried.
        raise NotARecipeError(
            "That doesn't look like a recipe. Paste a dish with its ingredients — "
            "a title line, then one ingredient per line."
        )

    verdict = _build_verdict(output, rubric)
    if log:
        log_verdict(title, ingredients, verdict)
    return verdict
