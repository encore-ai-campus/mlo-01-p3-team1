"""Independent persisted-CSV checks for the general-operation analysis copy."""
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path

from .candidates import MAXIMUM, MINIMUM, MIXED, SOURCE_SHA256, WEATHERS, read_csv, sha256, write_json
from .seasonality import POLICY_VERSION


def verify_general(source: Path, analysis_dir: Path, output: Path | None = None) -> dict:
    source, analysis_dir = source.resolve(), analysis_dir.resolve()
    output = (output or analysis_dir / "general").resolve()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert sha256(source) == SOURCE_SHA256 == manifest["source_dataset_sha256"]
    for name, expected in manifest["inputs"].items():
        assert sha256(analysis_dir / name) == expected, "changed input: " + name
    for name, expected in manifest["artifacts"].items():
        assert sha256(output / name) == expected, "changed artifact: " + name
    _, decision_rows = read_csv(output / "occasion_decisions.csv")
    decisions = {row["track_id"]: row for row in decision_rows}
    assert len(decisions) == len(decision_rows) == summary["source_unique_track_ids"]
    assert dict(Counter(row["occasion_status"] for row in decision_rows)) == summary["source_screen_counts"]
    assert all(row["occasion_policy_version"] == POLICY_VERSION and row["occasion_decision_version"] for row in decision_rows)
    pools, all_original, all_general, example_results = {}, set(), set(), {}
    score_checks = 0
    for code in (*WEATHERS, MIXED):
        columns, old_rows = read_csv(analysis_dir / "pools" / (code + ".csv"))
        originals = {row["track_id"]: row for row in old_rows}
        _, rows = read_csv(output / "pools" / (code + ".csv"))
        by_id = {row["track_id"]: row for row in rows}
        assert len(by_id) == len(rows)
        expected = {key for key in originals if decisions[key]["occasion_status"] == "GENERAL"}
        assert set(by_id) == expected
        score = "ranking_score_exact" if code == MIXED else "weather_score_exact"
        assert rows == sorted(rows, key=lambda row: (-Fraction(row[score]), row["track_id"]))
        for key, row in by_id.items():
            assert all(row[name] == originals[key][name] for name in columns), "changed source values: " + key
            assert all(row[name] == decisions[key][name] for name in decisions[key]
                       if name not in ("track_name", "artists", "album_name"))
            assert Fraction(row[score]) >= 75
            score_checks += 1
        pools[code] = set(by_id)
        if code in WEATHERS:
            all_original.update(originals)
            all_general.update(by_id)
        _, example = read_csv(output / "examples" / (code + "_180min.csv"))
        metadata = summary["examples"][code]
        if metadata["status"] == "CANDIDATE_SHORTAGE":
            assert not example and metadata["searched_full_pool"]
            example_results[code] = {"status": "CANDIDATE_SHORTAGE"}
            continue
        assert example and len({row["track_id"] for row in example}) == len(example)
        assert [int(row["position"]) for row in example] == list(range(1, len(example) + 1))
        total = sum(int(row["duration_ms"]) for row in example)
        assert MINIMUM <= total <= MAXIMUM
        assert total == metadata["selected"]["duration_ms"]
        for row in example:
            reference = by_id[row["track_id"]]
            assert all(row[name] == value for name, value in reference.items())
            assert row["occasion_status"] == "GENERAL" and row["speed"] in metadata["allowed_speeds"]
        quality = sum(int(row["duration_ms"]) * Fraction(row[score]) for row in example) / total
        assert quality == Fraction(metadata["quality_time_weighted_exact"])
        example_results[code] = {"track_count": len(example), "duration_ms": total, "all_general": True}
    assert pools[MIXED] == pools["RAIN"] & pools["SNOW"]
    assert all_general == {key for key in all_original if decisions[key]["occasion_status"] == "GENERAL"}
    assert len(all_original) == summary["coverage"]["original_base_track_count"]
    assert len(all_general) == summary["coverage"]["general_base_track_count"]
    result = {"status": "PASS", "scope": "PERSISTED_ANALYSIS_CSV_NOT_LIVE_PLAYBACK", "source_dataset_sha256": SOURCE_SHA256,
              "occasion_policy_version": POLICY_VERSION, "checked_pool_rows": score_checks,
              "source_and_original_analysis_hashes_unchanged": True, "manifest_artifact_hashes_matched": True,
              "original_all_column_strings_preserved": True, "all_occasion_decisions_matched": True,
              "general_union_equals_screened_base": True, "mixed_exact_intersection": True, "examples": example_results,
              "listening_or_live_streaming_verified": False}
    write_json(output / "verification.json", result)
    return result
