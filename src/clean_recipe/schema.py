"""Verdict schema — the structured output every scorer must return.

Source of truth: ai_docs/llm_contracts.md Contract 1. If this file and that doc
disagree, the doc wins and this is a bug.

Pure Pydantic definitions only. There is deliberately NO score-composition or
band-derivation logic here — that is Phase 2 scoring. Malformed model output
must fail loudly (ValidationError); we never silently coerce or emit a partial
card.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Swap(BaseModel):
    from_ingredient: str
    to_ingredient: str
    reason: str  # one line


# Each sub-score is 0–100 (higher = cleaner). The bounds are ENFORCED here so an
# out-of-range value from a flaky/cheap model raises ValidationError → the model
# output fails loud (retry-once, never a silently-clamped card). Weights
# (human-owned, placeholder) live in rubric.yaml, not here.
class SubScores(BaseModel):
    ultra_processing: float = Field(ge=0, le=100)       # weight 0.30
    added_sugar: float = Field(ge=0, le=100)            # weight 0.20
    fat_quality: float = Field(ge=0, le=100)            # weight 0.15
    sodium_preservatives: float = Field(ge=0, le=100)   # weight 0.15
    whole_food_ratio: float = Field(ge=0, le=100)       # weight 0.15
    additive_count: float = Field(ge=0, le=100)         # weight 0.05


Band = Literal["Clean", "Mostly Clean", "Processed", "Ultra-processed"]


class Verdict(BaseModel):
    score: int = Field(ge=0, le=100)  # 0–100 composite (computed in code)
    band: Band
    sub_scores: SubScores
    flagged_ingredients: list[str]
    swaps: list[Swap]             # target 3


# Schema version: v0.1 (placeholder weights — human-owned, not finalized).
# Bump and log in ai_docs/llm_contracts.md on any field change.
SCHEMA_VERSION = "0.1"
