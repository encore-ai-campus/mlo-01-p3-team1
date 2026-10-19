"""Build a deterministic human-review target sample; never call an LLM/API.

Only llm_review_sample.csv and review_sample_summary.json are generated here.
The source CSV, frozen V2 artifacts and other diagnostic outputs are read-only.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parent.parent
SOURCE = Path(r"C:\Users\이해나\Downloads\spotify_dataset (1).csv")
WEATHERS = ("CLEAR", "CLOUDY", "OVERCAST", "RAIN", "SNOW")
SEED = "weather-music-review-target-20261016-v1"
VERSION = "LLM_REVIEW_TARGET_SAMPLE_20261016_V1"
SAMPLE_SIZE = 500
AUDIO = ["danceability", "energy", "key", "loudness", "mode", "speechiness",
         "acousticness", "instrumentalness", "liveness", "valence", "tempo", "time_signature"]
FACTS = ["artists", "album_name", "track_name", "duration_ms", "explicit"] + AUDIO
NUMERIC = ["duration_ms"] + AUDIO
# Round-robin deliberately puts instrumentalness last; its large global flag
# count must not consume the entire outlier-review quota.
FLAG_FEATURE_ORDER = ("energy", "acousticness", "valence", "danceability", "tempo",
                      "loudness", "speechiness", "liveness", "duration_ms", "instrumentalness")
EMPTY_PROPOSAL_FIELDS = (
    "llm_proposed_genre_codes", "llm_proposed_mood_codes", "llm_proposed_main_inst",
    "llm_proposed_value", "llm_weather_y", "llm_evidence_ref", "llm_provider",
    "llm_model_version", "human_review_decision", "human_review_notes",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def order_hash(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{SEED}\0{namespace}\0{value}".encode("utf-8")).hexdigest()


def js(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def true(value) -> bool:
    assert str(value).lower() in {"true", "false"}, value
    return str(value).lower() == "true"


def main() -> None:
    profile_path = HERE / "profile_review_flags.csv"
    sensitivity_path = HERE / "pertrack_sensitivity_flags.csv"
    manifest_path = HERE / "baseline_manifest.json"
    required = [SOURCE, BASE / "policy.json", BASE / "summary.json", profile_path,
                HERE / "profile_summary.json", HERE / "profile_review_criteria.csv",
                sensitivity_path, HERE / "sensitivity_summary.json", manifest_path]
    required += [BASE / "pools" / f"{w}.csv" for w in WEATHERS]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"Required real analysis input is missing: {path}")
    input_hashes = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha256(p)
                    for p in required}
    baseline = json.loads((BASE / "summary.json").read_text(encoding="utf-8"))
    policy = json.loads((BASE / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sensitivity_metadata = json.loads((HERE / "sensitivity_summary.json").read_text(encoding="utf-8"))
    source_hash = sha256(SOURCE)
    policy_hash = sha256(BASE / "policy.json")
    assert source_hash == baseline["source"]["sha256"]
    assert policy_hash == baseline["source"]["policy_sha256"]
    assert baseline["policy_version"] == policy["policy_version"] == "WEATHER_SCORE_PROPOSAL_20261016_V2"
    for path in [BASE / "policy.json", BASE / "summary.json"] + [BASE / "pools" / f"{w}.csv" for w in WEATHERS]:
        entry = manifest["baseline_files"][path.relative_to(ROOT).as_posix()]
        assert sha256(path) == entry["sha256"], f"Frozen baseline changed: {path}"

    source = pd.read_csv(SOURCE, dtype=str, keep_default_na=False)
    assert len(source) == 114000 and source.track_id.nunique() == 89741
    unique_source = source.drop_duplicates("track_id", keep="first").set_index("track_id")
    source_genres = source.groupby("track_id", sort=True).track_genre.agg(lambda s: ";".join(sorted(set(s))))
    source_counts = source.track_id.value_counts()
    first_lines = source.reset_index().drop_duplicates("track_id").set_index("track_id")["index"] + 2
    pool_columns = ["track_id"] + FACTS + ["raw_track_genres", "service_genre_codes", "speed",
        "instrumental_auto", "selected_pattern_id", "selected_pattern_kind", "pass_pattern_ids",
        "weather_score_exact", "policy_version", "source_dataset_sha256"]
    pools = {w: pd.read_csv(BASE / "pools" / f"{w}.csv", usecols=pool_columns,
                          dtype=str, keep_default_na=False) for w in WEATHERS}
    joined = pd.concat(list(pools.values()), ignore_index=True)
    base_ids = set(joined.track_id)
    assert len(base_ids) == 61931 == baseline["coverage"]["denominator"]
    assert set(base_ids) <= set(unique_source.index)
    # Shared factual fields must agree across all weather memberships.
    shared_cols = ["track_id"] + FACTS + ["raw_track_genres", "service_genre_codes", "speed", "instrumental_auto"]
    facts = joined[shared_cols].drop_duplicates()
    assert len(facts) == len(base_ids) and facts.track_id.is_unique
    facts = facts.set_index("track_id").sort_index()
    assert facts.raw_track_genres.eq(source_genres.loc[facts.index]).all()
    numeric_serialization_differences = Counter()
    for column in FACTS:
        left, right = facts[column], unique_source.loc[facts.index, column]
        if column in NUMERIC:
            for track_id, a, b in zip(facts.index, left, right):
                assert math.isfinite(float(a)) and math.isfinite(float(b))
                assert math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12), (track_id, column, a, b)
                if a != b:
                    numeric_serialization_differences[column] += 1
        elif column == "explicit":
            assert left.str.lower().eq(right.str.lower()).all()
        else:
            assert left.eq(right).all(), column
    for frame in pools.values():
        assert frame.track_id.is_unique
        assert frame.policy_version.eq(policy["policy_version"]).all()
        assert frame.source_dataset_sha256.eq(source_hash).all()

    membership = defaultdict(dict)
    primary_pass_ids = set()
    for weather, frame in pools.items():
        for row in frame.itertuples(index=False):
            passing = row.pass_pattern_ids.split(";")
            if any(p.endswith("_PRIMARY") for p in passing):
                primary_pass_ids.add(row.track_id)
            membership[row.track_id][weather] = {
                "selected_pattern_id": row.selected_pattern_id,
                "selected_pattern_kind": row.selected_pattern_kind,
                "pass_pattern_ids": passing,
                "weather_score_exact": row.weather_score_exact,
            }
    support_only_ids = base_ids - primary_pass_ids
    sensitivity = pd.read_csv(sensitivity_path, dtype={"track_id": str}).set_index("track_id")
    assert sensitivity.index.is_unique and set(sensitivity.index) == base_ids
    for column in ("scenario_pass_flip_count", "any_weather_changed_count", "baseline_min_abs_score_margin_to75"):
        assert column in sensitivity.columns and sensitivity[column].notna().all()
    profile = pd.read_csv(profile_path, dtype=str, keep_default_na=False)
    assert set(profile.track_id) <= base_ids
    flags = defaultdict(list)
    feature_ids = defaultdict(set)
    for row in profile.itertuples(index=False):
        iqr, mad = true(row.iqr_flag), true(row.mad_flag)
        assert iqr or mad
        flags[row.track_id].append({"feature": row.feature, "iqr": iqr, "mad": mad})
        feature_ids[row.feature].add(row.track_id)

    selected = []
    selected_set = set()
    stratum_by_id = {}
    detail_by_id = {}

    def add(track_id: str, stratum: str, detail: str) -> None:
        assert track_id in base_ids and track_id not in selected_set
        selected.append(track_id)
        selected_set.add(track_id)
        stratum_by_id[track_id] = stratum
        detail_by_id[track_id] = detail

    ranked_sensitive = sensitivity.loc[sensitivity.scenario_pass_flip_count.gt(0)].reset_index().sort_values(
        ["scenario_pass_flip_count", "any_weather_changed_count", "track_id"], ascending=[False, False, True])
    for row in ranked_sensitive.head(150).itertuples(index=False):
        add(row.track_id, "SENSITIVITY_PRIORITY", "scenario_pass_flip_count DESC; any_weather_changed_count DESC; track_id ASC")

    feature_order = [f for f in FLAG_FEATURE_ORDER if feature_ids[f]] + sorted(set(feature_ids) - set(FLAG_FEATURE_ORDER))
    flag_queues = {f: deque(sorted(feature_ids[f], key=lambda i: (order_hash("flag:" + f, i), i))) for f in feature_order}
    flag_selected = 0
    while flag_selected < 100:
        progress = False
        for feature in feature_order:
            queue = flag_queues[feature]
            while queue and queue[0] in selected_set:
                queue.popleft()
            if queue:
                add(queue.popleft(), "GLOBAL_IQR_MAD_FEATURE_ROUND_ROBIN", feature)
                flag_selected += 1
                progress = True
                if flag_selected == 100:
                    break
        if not progress:
            break

    support_ranked = sorted(support_only_ids - selected_set, key=lambda i: (order_hash("support-only", i), i))
    for track_id in support_ranked[:100]:
        add(track_id, "SUPPORT_ONLY_NO_PRIMARY_IN_ANY_WEATHER", "No PRIMARY pattern qualifies in any of the five weather pools")

    control_needed = SAMPLE_SIZE - len(selected)
    assert control_needed >= 150
    cells = defaultdict(set)
    for track_id in sorted(base_ids - selected_set):
        row = facts.loc[track_id]
        for genre in row.service_genre_codes.split(";"):
            for weather, value in membership[track_id].items():
                cell = (genre, row.speed, weather, value["selected_pattern_id"])
                cells[cell].add(track_id)
    cell_order = sorted(cells, key=lambda c: (order_hash("control-cell", "|".join(c)), c))
    queues = {c: deque(sorted(cells[c], key=lambda i: (order_hash("control-id:" + "|".join(c), i), i))) for c in cell_order}
    controls = 0
    while controls < control_needed:
        progress = False
        for cell in cell_order:
            queue = queues[cell]
            while queue and queue[0] in selected_set:
                queue.popleft()
            if queue:
                add(queue.popleft(), "BALANCED_COMPARISON_CONTROL", "|".join(cell))
                controls += 1
                progress = True
                if controls == control_needed:
                    break
        if not progress:
            raise RuntimeError("Insufficient real baseline tracks to reach the exact sample size")

    rows = []
    for rank, track_id in enumerate(selected, 1):
        raw, fact = unique_source.loc[track_id], facts.loc[track_id]
        diagnostic = membership[track_id]
        sens = sensitivity.loc[track_id]
        reasons = []
        if sens.scenario_pass_flip_count > 0:
            reasons.append("SENSITIVITY_PASS_CHANGE")
        if flags[track_id]:
            reasons.append("GLOBAL_DISTRIBUTION_REVIEW_FLAG")
        if track_id in support_only_ids:
            reasons.append("NO_PRIMARY_MATCH_IN_ANY_WEATHER")
        row = {"sample_rank": rank, "track_id": track_id,
            "selection_stratum": stratum_by_id[track_id], "selection_detail": detail_by_id[track_id],
            "all_review_reasons": ";".join(reasons), "source_first_csv_line": int(first_lines[track_id]),
            "source_record_count": int(source_counts[track_id]),
            **{column: raw[column] for column in FACTS},
            "source_track_genres": source_genres[track_id],
            "service_genre_codes": fact.service_genre_codes, "speed": fact.speed,
            "instrumental_auto_unreviewed": fact.instrumental_auto,
            "scenario_pass_flip_count": int(sens.scenario_pass_flip_count),
            "any_weather_changed_count": int(sens.any_weather_changed_count),
            "baseline_min_abs_score_margin_to75": sens.baseline_min_abs_score_margin_to75,
            "global_iqr_mad_flags_for_human_review": js(sorted(flags[track_id], key=lambda value: value["feature"])),
            "passing_weathers_for_human_diagnosis_only": ";".join(w for w in WEATHERS if w in diagnostic),
            "baseline_pattern_and_score_for_human_diagnosis_only": js(diagnostic),
            "no_primary_match_in_any_weather": track_id in support_only_ids,
            "stage": "REVIEW_TARGET_ONLY", "send_status": "NOT_SENT", "api_payload_ready": False,
            "sample_selection_version": VERSION, "score_formula_version": policy["policy_version"],
            "source_dataset_sha256": source_hash,
            **{column: "" for column in EMPTY_PROPOSAL_FIELDS}}
        rows.append(row)
    sample = pd.DataFrame(rows)
    assert len(sample) == SAMPLE_SIZE and sample.track_id.is_unique
    assert set(sample.track_id) <= base_ids
    assert sample.loc[sample.selection_stratum.eq("BALANCED_COMPARISON_CONTROL")].shape[0] >= 150
    for column in EMPTY_PROPOSAL_FIELDS:
        assert sample[column].eq("").all()
    # Check every source factual output against the exact original CSV strings.
    for row in rows:
        assert all(str(row[c]) == unique_source.loc[row["track_id"], c] for c in FACTS)
    for path in required:
        key = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        assert sha256(path) == input_hashes[key], f"Input changed during sample construction: {path}"

    csv_path = HERE / "llm_review_sample.csv"
    sample.to_csv(csv_path, index=False, encoding="utf-8-sig", lineterminator="\n")
    saved = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    assert len(saved) == SAMPLE_SIZE and saved.track_id.is_unique
    assert saved["stage"].eq("REVIEW_TARGET_ONLY").all() and saved.send_status.eq("NOT_SENT").all()
    assert all(saved[c].eq("").all() for c in EMPTY_PROPOSAL_FIELDS)
    for column in FACTS:
        assert saved.set_index("track_id")[column].eq(unique_source.loc[saved.track_id, column]).all()

    strata_counts = Counter(sample.selection_stratum)
    feature_selection_counts = Counter(sample.loc[sample.selection_stratum.eq("GLOBAL_IQR_MAD_FEATURE_ROUND_ROBIN"), "selection_detail"])
    genre_counts = Counter(genre for track_id in selected for genre in facts.loc[track_id].service_genre_codes.split(";"))
    weather_counts = Counter(weather for track_id in selected for weather in membership[track_id])
    pattern_counts = Counter(value["selected_pattern_id"] for track_id in selected for value in membership[track_id].values())
    comparison_ids = [i for i in selected if stratum_by_id[i] == "BALANCED_COMPARISON_CONTROL"]
    summary = {
        "sample_selection_version": VERSION, "seed": SEED, "policy_version": policy["policy_version"],
        "status": "REVIEW_TARGET_ONLY_NOT_SENT_NOT_API_PAYLOAD", "model_version": None,
        "source": {"path": str(SOURCE), "sha256": source_hash, "policy_sha256": policy_hash},
        "input_hashes": input_hashes, "script_sha256": sha256(Path(__file__)),
        "output_csv": {"path": csv_path.relative_to(ROOT).as_posix(), "sha256": sha256(csv_path), "rows": SAMPLE_SIZE},
        "denominators": {"raw_rows": len(source), "raw_unique_track_ids": len(unique_source),
            "frozen_v2_pool_union_unique_ids": len(base_ids), "sensitivity_unique_ids": len(sensitivity)},
        "selection_rules": {
            "order": ["SENSITIVITY_PRIORITY", "GLOBAL_IQR_MAD_FEATURE_ROUND_ROBIN", "SUPPORT_ONLY_NO_PRIMARY_IN_ANY_WEATHER", "BALANCED_COMPARISON_CONTROL"],
            "maximum_quotas": {"sensitivity": 150, "global_review_flags": 100, "support_only": 100},
            "comparison_minimum": 150, "total_exact": SAMPLE_SIZE,
            "sensitivity_rank": ["scenario_pass_flip_count DESC", "any_weather_changed_count DESC", "track_id ASC"],
            "global_flag_feature_order": feature_order,
            "global_flag_rank": "One unused ID per feature per round; SHA256(seed,NUL,namespace,NUL,track_id), then ID",
            "support_only": "No *_PRIMARY in pass_pattern_ids in any weather; SHA256 support-only order",
            "comparison_balance": "Round-robin nonempty genre x speed x weather x representative_pattern cells. Cells and IDs use deterministic SHA256 order; selected IDs are globally skipped.",
            "overlap_rule": "Earlier strata own the ID; unmet problem-group quota is filled only by comparison/control tracks.",
            "multi_label_note": "Genre/weather/pattern memberships can overlap. Balanced cell traversal does not establish representative marginal probabilities."},
        "actual_counts": {"strata": dict(strata_counts), "global_flag_selection_feature": dict(feature_selection_counts),
            "sample_genre_memberships": dict(sorted(genre_counts.items())), "sample_speed": dict(Counter(sample.speed)),
            "sample_weather_memberships": dict(weather_counts), "sample_pattern_memberships": dict(sorted(pattern_counts.items())),
            "support_only_available_in_baseline": len(support_only_ids),
            "sample_tracks_with_any_global_flag": int(sample.global_iqr_mad_flags_for_human_review.ne("[]").sum()),
            "sample_tracks_with_sensitivity_flip": int(sample.scenario_pass_flip_count.gt(0).sum())},
        "comparison_balance_diagnostics": {
            "track_count": len(comparison_ids),
            "genre_memberships": dict(sorted(Counter(g for i in comparison_ids for g in facts.loc[i].service_genre_codes.split(";")).items())),
            "speed": dict(Counter(facts.loc[i].speed for i in comparison_ids)),
            "weather_memberships": dict(Counter(w for i in comparison_ids for w in membership[i])),
            "pattern_memberships": dict(sorted(Counter(v["selected_pattern_id"] for i in comparison_ids for v in membership[i].values()).items())),
            "note": "These overlapping marginal counts describe the deterministic cell-balanced comparison sample, not random inclusion probabilities."},
        "sensitivity_input_interpretation": {
            "pertrack_field_definitions": sensitivity_metadata.get("pertrack_flags"),
            "assumptions": sensitivity_metadata.get("assumptions"),
            "scenario_count_including_baseline": sensitivity_metadata.get("scenario_count_including_baseline"),
            "use": "Nominal pass-change counts prioritize review under this finite scenario set; unresolved nonlinear boundary diagnostics in sensitivity_summary remain limitations, not error labels or probabilities."},
        "checks": {"exactly_500_rows": len(saved) == 500, "duplicate_track_ids": int(saved.track_id.duplicated().sum()),
            "all_sample_ids_in_frozen_base": set(saved.track_id) <= base_ids,
            "baseline_pool_union_equals_61931": len(base_ids) == 61931,
            "sensitivity_ids_equal_pool_union": set(sensitivity.index) == base_ids,
            "all_source_factual_strings_exactly_preserved": True,
            "all_proposals_and_llm_y_are_null": True, "no_llm_api_called": True,
            "all_inputs_unchanged": True, "saved_csv_reloaded_and_verified": True},
        "numeric_provenance": {"sample_factual_values": "Exact original CSV strings, including raw audio values; never model estimates",
            "pool_serialization_format_differences_by_feature": dict(numeric_serialization_differences),
            "pool_numeric_correspondence_check": "Finite numeric values compared with relative/absolute tolerance 1e-12 only for existing pool serialization; original source strings are used in sample output."},
        "interpretation_limits": [
            "500 is a diagnostic review-target sample size, not an API request count, approved budget or inference batch size.",
            "All rows are NOT_SENT. LLM proposal values, weather y and model fields are null. No human listening validation was performed.",
            "The problem-enriched and balanced-comparison sample is not a random representative sample; population error rates cannot be estimated from it.",
            "IQR/MAD flags identify distribution review targets, not confirmed errors; none are automatically deleted or corrected.",
            "Sensitivity counts depend on the selected scenario set and its numeric boundary treatment; they are not error rates, failure probabilities or listening labels.",
            "This file is not reusable as an LLM API payload. Baseline rule scores, expected weather memberships and representative patterns are human diagnostic context, not ground truth and must not be forwarded as target answers.",
            "If a future payload is implemented, use an explicit field allowlist and separate evidence/field proposals. Do not train or self-validate weather suitability using generated labels as listening truth.",
            "Raw facts, source/provenance and current policy are preserved. The sample does not approve READY catalog publication or overwrite reviewed fields."],
    }
    (HERE / "review_sample_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(saved), "strata": dict(strata_counts), "feature_round_robin": dict(feature_selection_counts),
        "duplicates": 0, "csv_sha256": sha256(csv_path), "checks": summary["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
