"""log_verdict appends JSONL, round-trips, and creates its directory; the
reader side (read_log/list_log_files) tolerates malformed lines."""
import json

from clean_recipe.log import list_log_files, log_verdict, read_log
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


# ---- read side ----------------------------------------------------------------

def test_read_log_round_trips_written_records(tmp_path):
    p = tmp_path / "verdicts.jsonl"
    v = sample_verdict()
    log_verdict("a", ["x"], v, path=p)
    log_verdict("b", ["y", "z"], v, path=p)

    records, skipped = read_log(p)
    assert skipped == 0
    assert [r.title for r in records] == ["a", "b"]  # oldest first, as written
    assert records[1].ingredients == ["y", "z"]
    assert records[0].verdict == v
    assert records[0].ts


def test_read_log_skips_and_counts_malformed_lines(tmp_path):
    p = tmp_path / "verdicts.jsonl"
    log_verdict("good", ["x"], sample_verdict(), path=p)
    with p.open("a", encoding="utf-8") as f:
        f.write("{not json at all\n")                       # broken JSON
        f.write(json.dumps({"title": "wrong shape"}) + "\n")  # valid JSON, bad shape
        f.write("\n")                                        # blank line: ignored
    log_verdict("also good", ["y"], sample_verdict(), path=p)

    records, skipped = read_log(p)
    assert [r.title for r in records] == ["good", "also good"]
    assert skipped == 2


def test_read_log_skips_schema_invalid_verdict(tmp_path):
    p = tmp_path / "verdicts.jsonl"
    log_verdict("good", ["x"], sample_verdict(), path=p)
    bad = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    bad["verdict"]["score"] = 9000  # out of the 0–100 contract
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(bad) + "\n")

    records, skipped = read_log(p)
    assert len(records) == 1 and skipped == 1


def test_read_log_empty_file(tmp_path):
    p = tmp_path / "verdicts.jsonl"
    p.write_text("", encoding="utf-8")
    assert read_log(p) == ([], 0)


def test_list_log_files_sorted_and_filtered(tmp_path):
    (tmp_path / "b.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "a.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    assert [p.name for p in list_log_files(tmp_path)] == ["a.jsonl", "b.jsonl"]


def test_list_log_files_missing_dir_is_empty(tmp_path):
    assert list_log_files(tmp_path / "nope") == []
