"""log_verdict appends JSONL, round-trips, and creates its directory."""
import json

from clean_recipe.log import log_verdict
from clean_recipe.schema import Verdict


def sample_verdict():
    return Verdict.model_validate(
        {
            "score": 72,
            "band": "Mostly Clean",
            "sub_scores": {
                "ultra_processing": 70,
                "added_sugar": 80,
                "fat_quality": 65,
                "sodium_preservatives": 60,
                "whole_food_ratio": 75,
                "additive_count": 90,
            },
            "flagged_ingredients": ["butter"],
            "swaps": [
                {
                    "from_ingredient": "butter",
                    "to_ingredient": "olive oil",
                    "reason": "swap saturated for unsaturated fat",
                }
            ],
        }
    )


def test_log_round_trip(tmp_path):
    p = tmp_path / "logs" / "verdicts.jsonl"
    v = sample_verdict()
    returned = log_verdict("Choc Chip Cookies", ["butter", "sugar"], v, path=p)
    assert returned == p

    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["title"] == "Choc Chip Cookies"
    assert rec["ingredients"] == ["butter", "sugar"]
    assert rec["verdict"] == v.model_dump()
    assert "ts" in rec


def test_log_appends_one_line_per_call(tmp_path):
    p = tmp_path / "verdicts.jsonl"
    v = sample_verdict()
    log_verdict("a", ["x"], v, path=p)
    log_verdict("b", ["y"], v, path=p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["title"] == "a"
    assert json.loads(lines[1])["title"] == "b"


def test_log_creates_missing_dirs(tmp_path):
    p = tmp_path / "nested" / "deep" / "verdicts.jsonl"
    log_verdict("a", ["x"], sample_verdict(), path=p)
    assert p.exists()


def test_log_newline_in_content_stays_one_line(tmp_path):
    p = tmp_path / "verdicts.jsonl"
    log_verdict("multi\nline\ntitle", ["a\nb"], sample_verdict(), path=p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["title"] == "multi\nline\ntitle"
