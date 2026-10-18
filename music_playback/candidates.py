"""Build general-operation analysis copies without changing weather scores."""
from __future__ import annotations

import csv
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .seasonality import POLICY_VERSION, OccasionDecision, policy_document, screen_track

WEATHERS = ("CLEAR", "CLOUDY", "OVERCAST", "RAIN", "SNOW")
MIXED = "RAIN_SNOW_INTERSECTION"
TARGET, MINIMUM, MAXIMUM = 10_800_000, 10_560_000, 11_040_000
SOURCE_SHA256 = "b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd"
SIDECAR_FIELDS = list(OccasionDecision("", "", "", (), (), (), "").as_row())[1:]


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def write_csv(path: Path, fields: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def screen_source(source: Path, source_hash: str, overrides: dict | None = None):
    _, rows = read_csv(source)
    by_id: dict[str, dict] = {}
    for row in rows:
        track_id = row["track_id"]
        if track_id in by_id:
            if any(row[key] != by_id[track_id][key] for key in ("track_name", "artists", "album_name")):
                by_id[track_id]["metadata_conflict"] = True
        else:
            by_id[track_id] = row
    overrides = overrides or {}
    unknown = set(overrides) - by_id.keys()
    if unknown:
        raise ValueError("override contains unknown track ids: " + ",".join(sorted(unknown)))
    decisions = {key: screen_track(row, overrides.get(key), source_hash) for key, row in by_id.items()}
    return by_id, decisions, len(rows)


def filter_general(rows: list[dict], decisions: dict[str, OccasionDecision]) -> list[dict]:
    """Fail closed if a pool row has no screened source decision."""
    result = []
    seen = set()
    for row in rows:
        key = row["track_id"]
        if key in seen:
            raise ValueError("duplicate track_id in weather pool: " + key)
        seen.add(key)
        decision = decisions.get(key)
        if decision is None:
            raise ValueError("missing occasion decision: " + key)
        if decision.occasion_status == "GENERAL":
            result.append({**row, **{k: v for k, v in decision.as_row().items() if k != "track_id"}})
    return result


def duration_stats(rows: list[dict]) -> dict:
    total = sum(int(row["duration_ms"]) for row in rows)
    return {"track_count": len(rows), "duration_ms": total, "duration_minutes": total / 60_000}


def _reachable(durations: list[int], limit: int, target: int, block: int = 32):
    bits, checkpoints = 1, {0: 1}
    mask = (1 << (limit + 1)) - 1
    processed = 0
    for index, duration in enumerate(durations, 1):
        bits |= (bits << duration) & mask
        processed = index
        if index % block == 0:
            checkpoints[index] = bits
        if (bits >> target) & 1:
            break
    return bits, checkpoints, processed


def _reconstruct(durations, checkpoints, processed, chosen_total, limit, block=32):
    chosen, remainder, end = [], chosen_total, processed
    mask = (1 << (limit + 1)) - 1
    while end:
        start = ((end - 1) // block) * block
        states = [checkpoints[start]]
        for index in range(start, end):
            previous = states[-1]
            states.append(previous | ((previous << durations[index]) & mask))
        for index in range(end - 1, start - 1, -1):
            if (states[index - start] >> remainder) & 1:
                continue
            duration = durations[index]
            if remainder < duration or not ((states[index - start] >> (remainder - duration)) & 1):
                raise AssertionError("invalid subset reconstruction")
            chosen.append(index)
            remainder -= duration
        end = start
    if remainder:
        raise AssertionError("nonzero subset remainder")
    return sorted(chosen)


def choose_playlist(rows: list[dict], allowed_speeds: list[str], score_field="weather_score_exact",
                    target=TARGET, minimum=MINIMUM, maximum=MAXIMUM):
    """Exact integer duration search; never shortens or restores held tracks.

    This analysis builder proves duration feasibility. It only proves quality
    optimality when every selected score attains the source policy's 100 cap.
    """
    if not 0 < minimum <= target <= maximum:
        raise ValueError("invalid duration bounds")
    candidates = [row for row in rows if row["speed"] in allowed_speeds and 0 < int(row["duration_ms"]) <= maximum]
    candidates.sort(key=lambda row: (-Fraction(row[score_field]), row["track_id"]))
    if len({row["track_id"] for row in candidates}) != len(candidates):
        raise ValueError("duplicate playlist candidate")
    if any(row.get("occasion_status") != "GENERAL" for row in candidates):
        raise ValueError("non-GENERAL playlist candidate")
    count = len(candidates)
    size = min(200, count)
    windows = []
    chosen = None
    while size:
        windows.append(size)
        durations = [int(row["duration_ms"]) for row in candidates[:size]]
        bits, checkpoints, processed = _reachable(durations, maximum, target)
        selected_total = target if ((bits >> target) & 1) else None
        if selected_total is None and size == count:
            above = (bits >> (target + 1)) & ((1 << (maximum - target)) - 1)
            if above:
                selected_total = target + 1 + (above & -above).bit_length() - 1
            else:
                below = (bits >> minimum) & ((1 << (target - minimum)) - 1)
                if below:
                    selected_total = minimum + below.bit_length() - 1
        if selected_total is not None:
            indices = _reconstruct(durations, checkpoints, processed, selected_total, maximum)
            chosen = [candidates[index] for index in indices]
            break
        if size == count:
            break
        size = min(size * 2, count)
    if chosen is None:
        return [], {"status": "CANDIDATE_SHORTAGE", "searched_full_pool": True,
                    "candidate_pool": duration_stats(candidates), "searched_prefix_sizes": windows,
                    "automatic_shortening": False, "held_tracks_restored": False}
    total = sum(int(row["duration_ms"]) for row in chosen)
    quality = sum(int(row["duration_ms"]) * Fraction(row[score_field]) for row in chosen) / total
    all_100 = all(Fraction(row[score_field]) == 100 for row in chosen)
    return chosen, {"status": "ANALYSIS_FEASIBLE_NOT_PRODUCTION_ACCEPTANCE", "selected": duration_stats(chosen),
                    "candidate_pool": duration_stats(candidates), "searched_prefix_sizes": windows,
                    "exact_target_achieved": total == target, "within_allowed_duration": minimum <= total <= maximum,
                    "quality_time_weighted_exact": str(quality),
                    "quality_optimality": "PROVEN_GLOBAL_UPPER_BOUND_100" if all_100 else "NOT_PROVEN",
                    "tie_optimality": "NOT_PROVEN", "automatic_shortening": False, "held_tracks_restored": False}


def build(source: Path, analysis_dir: Path, output: Path | None = None, overrides_path: Path | None = None):
    source, analysis_dir = source.resolve(), analysis_dir.resolve()
    output = (output or analysis_dir / "general").resolve()
    reserved = [analysis_dir / name for name in ("pools", "examples", "archive", "diagnostics_20261016")]
    if (output == analysis_dir or output in source.parents or source == output
            or any(output == path or path in output.parents for path in reserved)):
        raise ValueError("output must not overwrite source or original analysis")
    source_hash = sha256(source)
    if source_hash != SOURCE_SHA256:
        raise ValueError("source CSV SHA-256 does not match the declared V2 source")
    policy_path, baseline_path = analysis_dir / "policy.json", analysis_dir / "summary.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if baseline["source"]["sha256"] != source_hash:
        raise ValueError("baseline source SHA-256 mismatch")
    override_list = json.loads(overrides_path.read_text(encoding="utf-8")) if overrides_path else []
    overrides = {entry["track_id"]: entry for entry in override_list}
    if len(overrides) != len(override_list):
        raise ValueError("duplicate override track_id")
    source_rows, decisions, row_count = screen_source(source, source_hash, overrides)
    output.mkdir(parents=True, exist_ok=True)
    decision_rows = [{**decisions[key].as_row(), **{name: source_rows[key][name] for name in ("track_name", "artists", "album_name")}}
                     for key in sorted(decisions)]
    fields = list(decision_rows[0])
    write_csv(output / "occasion_decisions.csv", fields, decision_rows)
    write_csv(output / "occasion_review.csv", fields, [row for row in decision_rows if row["occasion_status"] in ("REVIEW_REQUIRED", "UNSCREENED")])
    write_json(output / "seasonality_policy.json", policy_document())
    summary = {"status": "ANALYSIS_ONLY_NOT_READY", "occasion_policy_version": POLICY_VERSION,
               "score_formula_version": policy["policy_version"], "source_dataset_sha256": source_hash,
               "source_data_rows": row_count, "source_unique_track_ids": len(source_rows),
               "source_screen_counts": dict(Counter(d.occasion_status for d in decisions.values())),
               "general_is_metadata_screen_only": True, "listening_review_completed": False,
               "operational_ready_catalog_confirmed": False, "weather": {}, "examples": {}}
    original_ids, general_ids, inputs = set(), set(), {}
    general_pools = {}
    for code in (*WEATHERS, MIXED):
        path = analysis_dir / "pools" / (code + ".csv")
        columns, rows = read_csv(path)
        inputs[str(path.relative_to(analysis_dir)).replace("\\", "/")] = sha256(path)
        if any(row.get("source_dataset_sha256") != source_hash or row.get("score_formula_version") != policy["policy_version"] for row in rows):
            raise ValueError("weather pool source/formula version mismatch: " + code)
        filtered = filter_general(rows, decisions)
        score_field = "ranking_score_exact" if code == MIXED else "weather_score_exact"
        filtered.sort(key=lambda row: (-Fraction(row[score_field]), row["track_id"]))
        general_pools[code] = filtered
        if code in WEATHERS:
            original_ids.update(row["track_id"] for row in rows)
            general_ids.update(row["track_id"] for row in filtered)
        write_csv(output / "pools" / (code + ".csv"), columns + SIDECAR_FIELDS, filtered)
        counts = Counter(decisions[row["track_id"]].occasion_status for row in rows)
        summary["weather"][code] = {"original_pool": duration_stats(rows), "general_pool": duration_stats(filtered),
                                     "occasion_status_counts": dict(counts)}
        speeds = policy["weather"][code]["example_allowed_speeds"] if code in WEATHERS else ["slow", "medium", "fast", "fastest"]
        chosen, metadata = choose_playlist(filtered, speeds, score_field)
        write_csv(output / "examples" / (code + "_180min.csv"), ["position"] + columns + SIDECAR_FIELDS,
                  [{"position": index, **row} for index, row in enumerate(chosen, 1)])
        summary["examples"][code] = {**metadata, "allowed_speeds": speeds,
                                     "mixed_speed_is_preview_initial_value": code == MIXED}
    expected_general = {key for key in original_ids if decisions[key].occasion_status == "GENERAL"}
    if len(original_ids) != baseline["coverage"]["denominator"]:
        raise ValueError("input weather union differs from the baseline eligible denominator")
    if general_ids != expected_general:
        raise AssertionError("general weather union lost a screened eligible track")
    if {row["track_id"] for row in general_pools[MIXED]} != ({row["track_id"] for row in general_pools["RAIN"]} & {row["track_id"] for row in general_pools["SNOW"]}):
        raise AssertionError("mixed pool is not the exact rain/snow intersection")
    summary["coverage"] = {"original_base_track_count": len(original_ids), "general_base_track_count": len(expected_general),
                           "held_or_event_track_count": len(original_ids - expected_general),
                           "general_weather_union_track_count": len(general_ids), "unmatched_general_track_count": 0,
                           "original_weather_assignment_unchanged": True, "fallback_assignment_used": False,
                           "original_base_occasion_status_counts": dict(sorted(Counter(decisions[key].occasion_status for key in original_ids).items()))}
    summary["baseline_example_comparison"] = {}
    for code in WEATHERS:
        _, old = read_csv(analysis_dir / "examples" / (code + "_180min.csv"))
        summary["baseline_example_comparison"][code] = {"original_track_count": len(old),
            "occasion_status_counts": dict(Counter(decisions[row["track_id"]].occasion_status for row in old)),
            "not_general_track_ids": [row["track_id"] for row in old if decisions[row["track_id"]].occasion_status != "GENERAL"]}
    summary["checks"] = {"source_sha256_matched": True, "original_scores_copied_without_recalculation": True,
                          "general_weather_union_equals_general_base": True, "mixed_exact_intersection": True,
                          "all_examples_general_only": True, "all_examples_unique": True,
                          "automatic_shortening": False, "held_tracks_restored": False}
    write_json(output / "summary.json", summary)
    manifest = {"schema_version": "GENERAL_CANDIDATES_MANIFEST_V1", "source_dataset_sha256": source_hash,
                "score_formula_version": policy["policy_version"], "occasion_policy_version": POLICY_VERSION,
                "inputs": {"policy.json": sha256(policy_path), "summary.json": sha256(baseline_path), **inputs},
                "human_overrides_sha256": sha256(overrides_path) if overrides_path else None,
                "artifacts": {str(path.relative_to(output)).replace("\\", "/"): sha256(path)
                              for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"
                              and not path.name.startswith("routing-audit") and path.name != "verification.json"}}
    write_json(output / "manifest.json", manifest)
    return summary
