"""Rubric lexicons — the curated marker lists that ground the model's sub-scores.

Source of truth: ai_docs/llm_contracts.md Contract 2 (rubric). These lists live
in a dedicated ``rubric/lexicons.yaml`` — split out from ``rubric.yaml`` (weights,
band cutoffs, aliases, all hand-edited with comments) so the console can rewrite
the lists freely without clobbering the delicate human-owned weights file.

The **content is HUMAN-owned**: Claude drafts broad candidate lists; Amber curates
them (cut/keep/add, and for tiered lists, moves a marker between tiers) through
the Console "Lexicons" tab, whose Save button calls ``write_lexicons``. Nothing
here invents or edits a final list — it validates, normalizes, and transports.

Two lexicon shapes (v0.3):
- **flat** — ``list[str]``; presence pulls its dimension DOWN (``effect="down"``)
  or pushes it UP (``effect="up"``, the whole-food whitelist).
- **tiered** — a 1–5 quality ladder (``{level: [markers]}``) for dimensions where
  *which* ingredient matters, not just presence: ``added_sugar`` (monk fruit vs.
  HFCS), ``fat_quality`` (olive oil vs. hydrogenated), ``sodium_preservatives``
  (natural salt vs. nitrites). Each tier carries a target sub-score range; the
  model scores by the LOWEST (worst) tier prominently present.

``prompt.load_rubric`` merges the six keys into the rubric dict (tiered values are
dicts, flat values are lists), and ``prompt._rubric_reference`` renders them.

Pure module — no Streamlit, no network (architecture.md load-bearing rule).

Security note: every marker is normalized to a single stripped line (internal
whitespace/newlines collapsed) before it is stored or injected into the prompt,
so a stray newline can never break the prompt's line structure or the
``<<<RECIPE>>>`` delimiters. The lists are code-adjacent config, never user input.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import yaml

LEXICON_PATH = Path(__file__).resolve().parents[2] / "rubric" / "lexicons.yaml"

# Lexicon schema version — bump + log in llm_contracts.md on any shape change.
LEXICON_VERSION = "0.3"


class Tier(NamedTuple):
    """One rung of a 1–5 quality ladder for a tiered lexicon (5=best, 1=worst)."""

    level: int      # 5 (cleanest) … 1 (worst)
    label: str      # human heading for the tier
    target: str     # target sub-score when this is the worst prominent match


class LexiconSpec(NamedTuple):
    """One curated list: its key, the sub-score it grounds, and its shape."""

    key: str              # yaml key == merged rubric-dict key
    dimension: str        # the SubScores field this list calibrates
    label: str            # human heading (console section + prompt line)
    effect: str           # flat only: "down" lowers the dimension, "up" raises it
    help: str             # one-line guidance shown in the console
    tiers: tuple[Tier, ...] = ()   # non-empty ⇒ tiered (a {level: [markers]} map)

    @property
    def tiered(self) -> bool:
        return bool(self.tiers)


# Shared 1–5 target ladders. Harsher end per Amber (worst tier bottoms at 0);
# tune the numbers in review — they are scoring anchors, not band cutoffs.
_SUGAR_TIERS = (
    Tier(5, "Best — natural non-nutritive (monk fruit, stevia)", "75–95"),
    Tier(4, "Good natural whole sweeteners (honey, maple, agave)", "50–75"),
    Tier(3, "Less-refined cane / whole (coconut sugar, molasses)", "30–55"),
    Tier(2, "Refined sugars (white, brown, powdered)", "10–35"),
    Tier(1, "Industrial & synthetic — worst (HFCS, aspartame)", "0"),
)
_FAT_TIERS = (
    Tier(5, "Best — whole-food & cold-pressed (EVOO, avocado, nuts)", "80–100"),
    Tier(4, "Good traditional fats (butter, ghee, tallow, coconut oil)", "55–80"),
    Tier(3, "Neutral / refined-but-stable (refined olive, peanut)", "35–60"),
    Tier(2, "Refined seed & vegetable oils (canola, soybean, corn)", "10–35"),
    Tier(1, "Hydrogenated / industrial — worst (margarine, shortening)", "0"),
)
_SODIUM_TIERS = (
    Tier(5, "Natural salt — fine (sea salt, kosher, plain salt)", "80–100"),
    Tier(4, "Natural high-sodium ferments (soy sauce, miso, fish sauce)", "55–80"),
    Tier(3, "Processed salt blends (bouillon, seasoning/garlic salt)", "35–60"),
    Tier(2, "Functional sodium additives (MSG, sodium phosphates)", "15–40"),
    Tier(1, "Chemical preservatives — worst (nitrites, benzoates, BHT)", "0"),
)

# Order here is the render order in both the prompt and the console.
LEXICONS: list[LexiconSpec] = [
    LexiconSpec(
        "nova4_markers", "ultra_processing",
        "Ultra-processing (NOVA-4) markers", "down",
        "Industrial-formulation ingredients and recognizable ultra-processed "
        "products. Presence should pull ultra_processing DOWN.",
    ),
    LexiconSpec(
        "added_sugar_markers", "added_sugar",
        "Added / free sugars & sweeteners", "down",
        "Sweeteners graded 5 (best, e.g. monk fruit) → 1 (worst, e.g. HFCS & "
        "synthetic). Score added_sugar by the WORST sweetener prominently present.",
        tiers=_SUGAR_TIERS,
    ),
    LexiconSpec(
        "fat_quality_markers", "fat_quality",
        "Fat quality", "down",
        "Fats graded 5 (best, e.g. olive/avocado/whole-food) → 1 (worst, "
        "hydrogenated/industrial). Score fat_quality by the WORST fat prominently "
        "present.",
        tiers=_FAT_TIERS,
    ),
    LexiconSpec(
        "sodium_preservative_markers", "sodium_preservatives",
        "Sodium & chemical preservatives", "down",
        "Graded 5 (natural salt — fine) → 1 (chemical preservatives — worst). "
        "Natural salt is fine; the enemy is preservatives and sodium-loaded "
        "additives. Score by the WORST source prominently present.",
        tiers=_SODIUM_TIERS,
    ),
    LexiconSpec(
        "additive_markers", "additive_count",
        "Cosmetic additives (colors, emulsifiers, gums, flavors)", "down",
        "Dyes, emulsifiers, gums, stabilizers, and artificial/added flavorings. "
        "Presence should pull additive_count DOWN.",
    ),
    LexiconSpec(
        "whole_food_whitelist", "whole_food_ratio",
        "Whole, single-ingredient foods", "up",
        "FULLY natural single-ingredient foods only — think outside the grocery "
        "store. Grains/starches count ONLY in their explicit whole form (rolled "
        "oats, brown rice, wheat berries); processed derivatives (white bread, "
        "white flour) do NOT belong here. Presence should push whole_food_ratio UP.",
    ),
]

LEXICON_KEYS = [spec.key for spec in LEXICONS]
_SPEC_BY_KEY = {spec.key: spec for spec in LEXICONS}

# Header re-emitted on every write. The file is machine-written (the console
# rewrites it wholesale), so this keeps the human-owned discipline legible in the
# artifact itself.
_HEADER = f"""\
# CocoonKitchen rubric LEXICONS — curated marker lists (Contract 2).
#
# HUMAN-OWNED CONTENT. Claude drafts broad candidate lists; Amber curates them
# (cut / keep / add, and for tiered lists move a marker between tiers) via the
# Console "Lexicons" tab, whose Save button rewrites this file. These lists GROUND
# the model's six sub-scores in the scoring prompt.
#
# Shapes: flat lists (nova4_markers, additive_markers = pull DOWN;
# whole_food_whitelist = push UP) and 1–5 quality ladders keyed by tier level
# (added_sugar_markers, fat_quality_markers, sodium_preservative_markers), where
# 5 = cleanest and 1 = worst.
#
# Weights, band cutoffs, and aliases live in rubric.yaml (hand-edited, not here).
# Lexicon schema version: v{LEXICON_VERSION}.
"""


def _sanitize(entries: object) -> list[str]:
    """Normalize a raw list of marker strings for safe storage + prompt injection.

    Collapses internal whitespace/newlines to single spaces (nothing can break
    the prompt's line structure), strips, drops blanks, and de-duplicates
    case-insensitively while preserving first-seen display casing and order.
    """
    seen: set[str] = set()
    out: list[str] = []
    if not isinstance(entries, list):
        return out
    for raw in entries:
        item = " ".join(str(raw).split()).strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _clean_tiers(spec: LexiconSpec, raw: object) -> dict[int, list[str]]:
    """Normalize a tiered value into ``{level: [markers]}`` for every defined tier.

    Tolerates int or str tier keys (yaml round-trips ints; the console sends
    ints) and de-dupes a marker across tiers, keeping it in its WORST (lowest)
    listed tier — so a stray double-listing resolves to the stricter score.
    """
    mapping = raw if isinstance(raw, dict) else {}
    per_tier: dict[int, list[str]] = {}
    for tier in spec.tiers:
        vals = mapping.get(tier.level)
        if vals is None:
            vals = mapping.get(str(tier.level))
        per_tier[tier.level] = _sanitize(vals)
    # De-dupe across tiers, worst-tier-wins (ascending level = worst first).
    claimed: set[str] = set()
    for level in sorted(per_tier):  # 1,2,3,… → worst first
        kept: list[str] = []
        for marker in per_tier[level]:
            key = marker.lower()
            if key in claimed:
                continue
            claimed.add(key)
            kept.append(marker)
        per_tier[level] = kept
    return per_tier


def _clean_value(spec: LexiconSpec, raw: object):
    """Normalize one lexicon value by its shape (tiered → dict, flat → list)."""
    return _clean_tiers(spec, raw) if spec.tiered else _sanitize(raw)


def load_lexicons(path: Path | str = LEXICON_PATH) -> dict[str, object]:
    """Load the six lexicons; missing file/keys → empty (``[]`` or empty tiers).

    Always returns every ``LEXICON_KEYS`` entry so callers never branch on
    presence. Flat values are ``list[str]``; tiered values are ``{level: [markers]}``
    covering every defined tier. Values are sanitized on read.
    """
    data: object = {}
    p = Path(path)
    if p.exists():
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    mapping = data if isinstance(data, dict) else {}
    return {spec.key: _clean_value(spec, mapping.get(spec.key)) for spec in LEXICONS}


def write_lexicons(
    lists: dict[str, object], path: Path | str = LEXICON_PATH
) -> dict[str, object]:
    """Rewrite ``lexicons.yaml`` with the (sanitized) lexicons; return what was saved.

    The console's only write path. Sanitizes every value by its shape, emits the
    human-owned header, and dumps the keys in ``LEXICONS`` order (tiered keys as a
    ``{level: [...]}`` map). Unknown keys are ignored; absent keys become empty.
    """
    cleaned = {spec.key: _clean_value(spec, lists.get(spec.key)) for spec in LEXICONS}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        cleaned, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    p.write_text(_HEADER + "\n" + body, encoding="utf-8")
    return cleaned


def spec_for(key: str) -> LexiconSpec:
    """The :class:`LexiconSpec` for a lexicon key (KeyError if unknown)."""
    return _SPEC_BY_KEY[key]
