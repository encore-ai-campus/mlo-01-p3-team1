"""Reproduce the V2 multi-pattern planning proposal without changing source data."""
from __future__ import annotations

import hashlib
import itertools
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCE = Path(r"C:\Users\이해나\Downloads\spotify_dataset (1).csv")
POLICY_PATH = HERE / "policy.json"
MAPPING_PATH = ROOT / "docs/handoff/music/테마_장르_정의.md"
FEATURES = ["energy", "acousticness", "valence"]
AUDIO = ["danceability", "energy", "key", "loudness", "mode", "speechiness", "acousticness", "instrumentalness", "liveness", "valence", "tempo", "time_signature"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fraction(value):
    return Fraction(str(value))


def component_exact(value, parameters):
    x = fraction(value)
    lo, hi, width = map(fraction, parameters)
    return 100 * max(Fraction(0), 1 - max(lo - x, Fraction(0), x - hi) / width)


def pattern_params(weather, pattern):
    return {**pattern, "weights": weather["weights"]}


def score_exact(row, params):
    if any(row[name] is None or pd.isna(row[name]) for name in FEATURES):
        return None, None
    components = {name: component_exact(row[name], params[name]) for name in FEATURES}
    mode = row.get("mode")
    components["mode"] = Fraction(100 if mode is not None and not pd.isna(mode) and int(mode) == params["preferred_mode"] else 0)
    total = fraction(params["ceiling"]) * sum(params["weights"][name] * value for name, value in components.items()) / 10000
    return total, components


def select_exact(row, weather, threshold, core_min):
    results = []
    for pattern in sorted(weather["patterns"], key=lambda value: value["pattern_id"]):
        score, components = score_exact(row, pattern_params(weather, pattern))
        if score is None:
            continue
        core_passes = all(components[name] >= core_min for name in ["energy", "acousticness"])
        passes = score >= threshold and core_passes
        results.append({"pattern": pattern, "score": score, "components": components, "core_passes": core_passes, "passes": passes})
    if not results:
        return {"passes": False, "selected": None, "pass_pattern_ids": [], "status": "HOLD_WITH_NULL_SCORE"}
    eligible = [result for result in results if result["passes"]]
    core_eligible = [result for result in results if result["core_passes"]]
    selected = min(core_eligible or results, key=lambda value: (-value["score"], value["pattern"]["pattern_id"]))
    status = "QUALIFIED" if eligible else "CORE_PASS_SCORE_BELOW_THRESHOLD" if core_eligible else "RAW_MAX_DIAGNOSTIC_ONLY"
    return {"passes": bool(eligible), "selected": selected, "pass_pattern_ids": [result["pattern"]["pattern_id"] for result in eligible], "status": status}


def score_vector(frame, params):
    components = {}
    for name in FEATURES:
        lo, hi, width = params[name]
        values = frame[name].to_numpy(dtype="float64")
        components[name] = 100 * np.maximum(0, 1 - np.maximum(np.maximum(lo - values, 0), values - hi) / width)
    components["mode"] = np.where(frame["mode"].to_numpy() == params["preferred_mode"], 100.0, 0.0)
    score = params["ceiling"] * sum(params["weights"][name] * value for name, value in components.items()) / 10000
    return score, components


def speed(tempo, signature):
    value = Decimal(str(tempo))
    if int(signature) == 3:
        value /= Decimal("1.5")
    value = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return "slow" if value < 80 else "medium" if value < 110 else "fast" if value < 150 else "fastest"


def mapping():
    text = MAPPING_PATH.read_text(encoding="utf-8").split("### 3-1.", 1)[1].split("## 4.", 1)[0]
    groups = {}
    for line in text.splitlines():
        cells = [value.strip() for value in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"[A-Z][A-Z_-]*", cells[0]):
            groups[cells[0]] = [value.strip() for value in cells[2].split(",")]
    assert len(groups) == 18 and len(set(itertools.chain.from_iterable(groups.values()))) == 77
    return groups


def stats(frame):
    return {"track_count": len(frame), "duration_ms": int(frame.duration_ms.sum()), "duration_minutes": float(frame.duration_ms.sum()) / 60000}


def exact_subset(durations, target, block=32):
    bits, checkpoints = 1, {0: 1}
    mask = (1 << (target + 1)) - 1
    processed = 0
    for index, duration in enumerate(durations, 1):
        bits |= (bits << int(duration)) & mask
        processed = index
        if index % block == 0:
            checkpoints[index] = bits
        if (bits >> target) & 1:
            break
    if not ((bits >> target) & 1):
        return None, {"processed_count": processed, "checkpoint_count": len(checkpoints)}
    chosen, remainder, end = [], target, processed
    while end:
        start = ((end - 1) // block) * block
        states = [checkpoints[start]]
        for index in range(start, end):
            previous = states[-1]
            states.append(previous | ((previous << int(durations[index])) & mask))
        for index in range(end - 1, start - 1, -1):
            if (states[index - start] >> remainder) & 1:
                continue
            duration = int(durations[index])
            assert remainder >= duration and (states[index - start] >> (remainder - duration)) & 1
            chosen.append(index)
            remainder -= duration
        end = start
    assert remainder == 0
    return sorted(chosen), {"processed_count": processed, "checkpoint_count": len(checkpoints), "reconstruction_block_size": block}


def make_example(pool, weather, policy):
    allowed = pool.loc[pool.speed.isin(weather["example_allowed_speeds"])].copy()
    target = int(policy["target_duration_ms"])
    usable = allowed.loc[allowed.duration_ms.le(target)].copy()
    sizes, size = [], min(200, len(usable))
    while size:
        sizes.append(size)
        chosen, search = exact_subset(usable.duration_ms.iloc[:size].tolist(), target)
        if chosen is not None:
            result = usable.iloc[chosen].copy()
            exact_values = list(map(Fraction, result.weather_score_exact))
            all_max = all(value == 100 for value in exact_values)
            assert result.track_id.is_unique and int(result.duration_ms.sum()) == target
            quality = sum(int(duration) * score for duration, score in zip(result.duration_ms, exact_values)) / target
            return result, {"status": "ANALYSIS_FEASIBLE_NOT_PRODUCTION_ACCEPTANCE", "readiness_status": "ANALYSIS_ONLY_NOT_READY", "candidate_pool": stats(allowed), "searched_prefix_sizes": sizes, "search": search, "exact_target_achieved": True, "quality_time_weighted_mean": float(quality), "quality_exact": str(quality), "quality_upper_bound": 100, "all_selected_scores_exactly_100": all_max, "quality_optimality": "PROVEN_ALL_SELECTED_SCORES_AT_GLOBAL_UPPER_BOUND" if all_max else "NOT_PROVEN", "tie_optimality": "NOT_PROVEN", "play_order": "weather_score_desc_then_track_id_asc; transition quality not optimized", "instrumental_only": False, "selected": stats(result), "unique_track_ids": True}
        if size == len(usable):
            break
        size = min(size * 2, len(usable))
    return usable.iloc[:0].copy(), {"status": "EXACT_TARGET_NOT_FOUND", "exact_target_achieved": False, "quality_optimality": "NOT_PROVEN"}


def build_pattern(base, raw, weather, pattern, thresholds, core_min):
    params = pattern_params(weather, pattern)
    float_scores, float_components = score_vector(base, params)
    exact_components, weighted = {}, {}
    for name in FEATURES:
        strings = raw.loc[base.track_id, name].tolist()
        lookup = {value: component_exact(value, params[name]) for value in set(strings)}
        exact_components[name] = [lookup[value] for value in strings]
        weighted_lookup = {value: params["ceiling"] * params["weights"][name] * score / 10000 for value, score in lookup.items()}
        weighted[name] = [weighted_lookup[value] for value in strings]
    exact_components["mode"] = [Fraction(100 if int(value) == params["preferred_mode"] else 0) for value in base["mode"]]
    mode_weighted = [params["ceiling"] * params["weights"]["mode"] * value / 10000 for value in exact_components["mode"]]
    exact_scores = [energy + acousticness + valence + mode for energy, acousticness, valence, mode in zip(weighted["energy"], weighted["acousticness"], weighted["valence"], mode_weighted)]
    exact_gates = np.fromiter((energy >= core_min and acousticness >= core_min for energy, acousticness in zip(exact_components["energy"], exact_components["acousticness"])), dtype=bool, count=len(base))
    masks = {threshold: exact_gates & np.fromiter((score >= threshold for score in exact_scores), dtype=bool, count=len(base)) for threshold in thresholds}
    float_gates = (float_components["energy"] >= core_min) & (float_components["acousticness"] >= core_min)
    near = np.zeros(len(base), dtype=bool)
    for threshold in thresholds:
        near |= np.abs(float_scores - threshold) <= 1e-8
    for name in ["energy", "acousticness"]:
        near |= np.abs(float_components[name] - core_min) <= 1e-8
    changes = {str(threshold): int(((float_gates & (float_scores >= threshold)) != masks[threshold]).sum()) for threshold in thresholds}
    changed_indices = np.zeros(len(base), dtype=bool)
    for threshold in thresholds:
        changed_indices |= (float_gates & (float_scores >= threshold)) != masks[threshold]
    assert not (changed_indices & ~near).any()
    records = [{"track_id": base.iloc[index].track_id, "score_float_before": float(float_scores[index]), "score_exact": str(exact_scores[index]), "energy_exact": str(exact_components["energy"][index]), "acousticness_exact": str(exact_components["acousticness"][index]), "changed_thresholds": [threshold for threshold in thresholds if bool(float_gates[index] and float_scores[index] >= threshold) != bool(masks[threshold][index])]} for index in np.flatnonzero(changed_indices)]
    return {"pattern": pattern, "scores_exact": exact_scores, "scores": np.fromiter(map(float, exact_scores), dtype=float, count=len(base)), "components_exact": exact_components, "gates": exact_gates, "masks": masks, "float_masks": {threshold: float_gates & (float_scores >= threshold) for threshold in thresholds}, "boundary": {"near_boundary_count": int(near.sum()), "classification_changes": changes, "changed_records": records}}


def analytic_coverage_checks(policy):
    expected = {"CLEAR": ([.5, 1], [0, 1], [.5, 1]), "CLOUDY": ([.5, 1], [0, 1], [0, .5]), "OVERCAST": ([0, .5], [0, .5], [0, .5]), "RAIN": ([0, .5], [.5, 1], [0, .5]), "SNOW": ([0, .5], [0, 1], [.5, 1])}
    boxes = {}
    for code, ranges in expected.items():
        weather = policy["weather"][code]
        support = next(pattern for pattern in weather["patterns"] if pattern["kind"] == "SUPPORT")
        assert all(support[name][:2] == bounds for name, bounds in zip(FEATURES, ranges))
        assert sum(weather["weights"].values()) == 100
        minimum = fraction(support["ceiling"]) * sum(weather["weights"][name] for name in FEATURES) / 100
        assert minimum >= policy["score_threshold"] and policy["core_component_min"] <= 100
        boxes[code] = {"pattern_id": support["pattern_id"], "closed_box": dict(zip(FEATURES, ranges)), "minimum_inside_score_mode_mismatch_or_null": str(minimum), "inside_core_components": 100}
    boundary_records = []
    for energy, acousticness, valence in itertools.product([0, .5, 1], repeat=3):
        for mode in [0, 1, None]:
            row = {"energy": energy, "acousticness": acousticness, "valence": valence, "mode": mode}
            passed = [code for code, weather in policy["weather"].items() if select_exact(row, weather, policy["score_threshold"], policy["core_component_min"])["passes"]]
            assert passed
            boundary_records.append({**row, "passing_weathers": passed})
    cases = ["energy>=.5 and valence>=.5 -> CLEAR_SUPPORT; acousticness unrestricted", "energy>=.5 and valence<=.5 -> CLOUDY_SUPPORT; acousticness unrestricted", "energy<=.5 and valence>=.5 -> SNOW_SUPPORT; acousticness unrestricted", "energy<=.5 and valence<=.5 and acousticness<=.5 -> OVERCAST_SUPPORT", "energy<=.5 and valence<=.5 and acousticness>=.5 -> RAIN_SUPPORT"]
    return {"proof_type": "ANALYTIC_CLOSED_BOX_COVER_AND_INSIDE_SCORE_LOWER_BOUND", "domain": "energy/acousticness/valence in[0,1], mode0/1/null", "exhaustive_partition_argument": cases, "closed_boundaries_allow_overlap": True, "boxes": boxes, "boundary_sample_check_not_the_proof": {"tested_count": len(boundary_records), "all_have_a_passing_weather": True, "records": boundary_records}}


def fixed_anchor_checks(policy):
    anchors = {"CLEAR_ONLY_REQUIRE_RAIN_SNOW_FAIL": {"raw": [.8, .1, .8, 1], "must_pass": ["CLEAR"], "must_fail": ["RAIN", "SNOW"]}, "CLOUDY_ONLY": {"raw": [.9, .05, .1, 0], "must_pass": ["CLOUDY"], "must_fail": ["CLEAR", "OVERCAST", "RAIN", "SNOW"]}, "OVERCAST_ONLY": {"raw": [.2, .1, .2, 0], "must_pass": ["OVERCAST"], "must_fail": ["CLEAR", "CLOUDY", "RAIN", "SNOW"]}, "RAIN_ONLY": {"raw": [0, .95, 0, 0], "must_pass": ["RAIN"], "must_fail": ["CLEAR", "CLOUDY", "OVERCAST", "SNOW"]}, "SNOW_ONLY": {"raw": [.1, .9, .9, 1], "must_pass": ["SNOW"], "must_fail": ["CLEAR", "CLOUDY", "OVERCAST", "RAIN"]}, "PREVIOUS_QUIET_DARK_ACOUSTIC": {"raw": [.2, .9, .2, 0]}, "PREVIOUS_SOFT_BRIGHT_ACOUSTIC": {"raw": [.15, .9, .65, 1]}, "PREVIOUS_MODERATE": {"raw": [.5, .5, .5, 0]}}
    records = []
    for name, values in anchors.items():
        raw = dict(zip(FEATURES + ["mode"], values["raw"]))
        results = {}
        for code, weather in policy["weather"].items():
            decision = select_exact(raw, weather, policy["score_threshold"], policy["core_component_min"])
            selected = decision["selected"]
            results[code] = {"passes": decision["passes"], "score": float(selected["score"]), "score_exact": str(selected["score"]), "selected_pattern_id": selected["pattern"]["pattern_id"], "pass_pattern_ids": decision["pass_pattern_ids"]}
        assert all(results[code]["passes"] for code in values.get("must_pass", []))
        assert all(not results[code]["passes"] for code in values.get("must_fail", []))
        records.append({"label": name, "assumed_not_observed": True, "raw_features": raw, "expectations": {"must_pass": values.get("must_pass", []), "must_fail": values.get("must_fail", [])}, "weather": results})
    negative = {"energy": .843, "acousticness": .5, "valence": .53, "mode": 0}
    decision = select_exact(negative, policy["weather"]["CLOUDY"], policy["score_threshold"], policy["core_component_min"])
    primary = next(pattern for pattern in policy["weather"]["CLOUDY"]["patterns"] if pattern["kind"] == "PRIMARY")
    primary_score, primary_components = score_exact(negative, pattern_params(policy["weather"]["CLOUDY"], primary))
    assert primary_score > decision["selected"]["score"] and primary_components["energy"] < policy["core_component_min"]
    assert decision["passes"] and decision["selected"]["pattern"]["kind"] == "SUPPORT"
    below = {"energy": .843, "acousticness": .5, "valence": .65, "mode": 0}
    below_decision = select_exact(below, policy["weather"]["CLOUDY"], policy["score_threshold"], policy["core_component_min"])
    assert not below_decision["passes"] and below_decision["selected"]["pattern"]["pattern_id"] == "CLOUDY_SUPPORT"
    assert below_decision["selected"]["score"] == Fraction(56) and below_decision["status"] == "CORE_PASS_SCORE_BELOW_THRESHOLD"
    missing = select_exact({"energy": None, "acousticness": .5, "valence": .5, "mode": None}, policy["weather"]["CLEAR"], policy["score_threshold"], policy["core_component_min"])
    assert missing["status"] == "HOLD_WITH_NULL_SCORE" and missing["selected"] is None
    return records, {"raw_features": negative, "rejected_raw_max_primary_score": str(primary_score), "rejected_primary_energy_component": str(primary_components["energy"]), "selected_pattern_id": decision["selected"]["pattern"]["pattern_id"], "selected_score_exact": str(decision["selected"]["score"]), "test_passed": True, "core_pass_below_score_threshold_case": {"raw_features": below, "selected_pattern_id": below_decision["selected"]["pattern"]["pattern_id"], "selected_score_exact": str(below_decision["selected"]["score"]), "passes": below_decision["passes"], "status": below_decision["status"], "test_passed": True}, "missing_continuous_holds_null_score_test_passed": True}


def main():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    threshold, core_min = policy["score_threshold"], policy["core_component_min"]
    thresholds = sorted({70, threshold, 80})
    v1_path = HERE / "archive/v1/summary.json"
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    v1_policy = json.loads((HERE / "archive/v1/policy.json").read_text(encoding="utf-8"))
    d = pd.read_csv(SOURCE)
    raw = pd.read_csv(SOURCE, dtype=str).drop_duplicates("track_id").set_index("track_id")
    u = d.drop_duplicates("track_id").copy()
    genre_sets = d.groupby("track_id")["track_genre"].agg(lambda values: sorted(set(values)))
    groups, raw_to_codes = mapping(), {}
    for code, genres in groups.items():
        for genre in genres:
            raw_to_codes.setdefault(genre, set()).add(code)
    u["raw_track_genres"] = u.track_id.map(genre_sets).map(lambda values: ";".join(values))
    u["service_genre_codes"] = u.track_id.map(genre_sets).map(lambda values: ";".join(sorted(set().union(*(raw_to_codes.get(genre, set()) for genre in values)))))
    metadata = u[["artists", "album_name", "track_name"]].notna().all(axis=1) & u.duration_ms.gt(0)
    audio_valid = u[FEATURES].notna().all(axis=1) & u[FEATURES].ge(0).all(axis=1) & u[FEATURES].le(1).all(axis=1) & u["mode"].isin([0, 1])
    base = u.loc[metadata & audio_valid & u.tempo.gt(0) & np.isfinite(u.tempo) & u.service_genre_codes.ne("")].copy().reset_index(drop=True)
    assert len(base) == 61931
    base["speed"] = [speed(row.tempo, row.time_signature) for row in base.itertuples()]
    base["instrumental_auto"] = np.where(base.instrumentalness.ge(.8), "TRUE", np.where(base.instrumentalness.lt(.2), "FALSE", "UNKNOWN"))
    base["instrumental_source"] = "AUTO_UNREVIEWED"
    source_hash = sha256(SOURCE)
    summary = {"policy_version": policy["policy_version"], "score_formula_version": policy["policy_version"], "model_version": policy.get("model_version"), "status": "ANALYSIS_FEASIBLE_NOT_PRODUCTION_ACCEPTANCE", "readiness_status": "ANALYSIS_ONLY_NOT_READY", "weather_updates": policy["weather_updates"], "source": {"path": str(SOURCE), "sha256": source_hash, "bytes": SOURCE.stat().st_size, "data_rows": len(d), "columns": d.columns.tolist(), "unique_track_ids": len(u), "extra_duplicate_rows": int(d.track_id.duplicated().sum()), "missing_counts": d.isna().sum().to_dict(), "mapping_path": str(MAPPING_PATH.relative_to(ROOT)), "mapping_sha256": sha256(MAPPING_PATH), "policy_sha256": sha256(POLICY_PATH)}, "source_profile": v1["source_profile"], "eligibility": {**v1["eligibility"], "base": stats(base), "raw_unique_track_ids_are_a_separate_denominator": len(u)}, "numerics": {"screening": "NumPy float64 per pattern for error diagnostics", "decisions_and_scores": "Every pattern component, ceiling-scaled score and threshold is calculated from source decimal strings using exact Fraction", "sort": "exact values normalized before float conversion; exact score strings preserved", "production_numeric_contract": "not implemented; analysis arithmetic is not production publishing acceptance"}, "weather": {}, "sensitivity": {}, "boundary_checks": {}, "examples": {}}
    summary["domain_coverage_proof"] = analytic_coverage_checks(policy)
    summary["hypothetical_patterns"], summary["negative_selection_test"] = fixed_anchor_checks(policy)
    base_columns = ["track_id", "artists", "album_name", "track_name", "duration_ms", "explicit"] + AUDIO + ["raw_track_genres", "service_genre_codes", "speed", "instrumental_auto", "instrumental_source"]
    pool_dir, example_dir = HERE / "pools", HERE / "examples"
    pool_dir.mkdir(exist_ok=True)
    example_dir.mkdir(exist_ok=True)
    frames, passed_masks, v1_masks = {}, {}, {}
    for weather_code, weather in policy["weather"].items():
        patterns = sorted(weather["patterns"], key=lambda value: value["pattern_id"])
        results = [build_pattern(base, raw, weather, pattern, thresholds, core_min) for pattern in patterns]
        scores = np.column_stack([result["scores"] for result in results])
        diagnostic_index = scores.argmax(axis=1)
        core_matrix = np.column_stack([result["gates"] for result in results])
        has_core_pattern = core_matrix.any(axis=1)
        core_representative_index = np.where(has_core_pattern, np.where(core_matrix, scores, -np.inf).argmax(axis=1), diagnostic_index)
        qualified_by_threshold, selected_by_threshold, boundary = {}, {}, {}
        for limit in thresholds:
            pass_matrix = np.column_stack([result["masks"][limit] for result in results])
            qualified = pass_matrix.any(axis=1)
            selected = core_representative_index.copy()
            assert all(not has_core_pattern[index] or results[int(selected[index])]["gates"][index] for index in range(len(base)))
            qualified_by_threshold[limit], selected_by_threshold[limit] = qualified, selected
            float_qualified = np.column_stack([result["float_masks"][limit] for result in results]).any(axis=1)
            boundary[str(limit)] = int((qualified != float_qualified).sum())
        selected = selected_by_threshold[threshold]
        qualified = qualified_by_threshold[threshold]
        frame = base[base_columns].copy()
        frame["selected_pattern_id"] = [patterns[index]["pattern_id"] for index in selected]
        frame["selected_pattern_kind"] = [patterns[index]["kind"] for index in selected]
        frame["selected_pattern_ceiling"] = [patterns[index]["ceiling"] for index in selected]
        frame["pass_pattern_ids"] = [";".join(result["pattern"]["pattern_id"] for result in results if result["masks"][threshold][index]) for index in range(len(base))]
        frame["weather_score_exact"] = [str(results[int(pattern)]["scores_exact"][index]) for index, pattern in enumerate(selected)]
        frame["weather_score"] = list(map(float, map(Fraction, frame.weather_score_exact)))
        frame["diagnostic_raw_max_score"] = scores.max(axis=1)
        for name in FEATURES + ["mode"]:
            exact = [results[int(pattern)]["components_exact"][name][index] for index, pattern in enumerate(selected)]
            frame["component_" + name] = list(map(float, exact))
            frame["component_" + name + "_exact"] = list(map(str, exact))
        frame["weather"] = weather_code
        frame["policy_version"] = policy["policy_version"]
        frame["score_formula_version"] = policy["policy_version"]
        frame["model_version"] = policy.get("model_version")
        frame["model_fit_status"] = "INITIAL_PLANNING_NOT_FITTED"
        frame["source_dataset_sha256"] = source_hash
        frame["analysis_status"] = "ANALYSIS_ONLY_NOT_READY"
        frame["selection_status"] = np.where(qualified, "QUALIFIED_PATTERN", np.where(has_core_pattern, "CORE_PASS_SCORE_BELOW_THRESHOLD", "RAW_MAX_DIAGNOSTIC_ONLY"))
        frame["pass_reason"] = np.where(qualified, f"EXISTS_PATTERN_SCORE_GE{threshold}_ENERGY_GE{core_min}_ACOUSTICNESS_GE{core_min}", "NO_PATTERN_MEETS_SCORE_AND_CORE")
        pool = frame.loc[qualified].sort_values(["weather_score", "track_id"], ascending=[False, True]).reset_index(drop=True)
        assert pool.track_id.is_unique
        pool.to_csv(pool_dir / f"{weather_code}.csv", index=False, encoding="utf-8-sig", float_format="%.15g")
        frames[weather_code], passed_masks[weather_code] = frame, qualified
        primary_index = next(index for index, pattern in enumerate(patterns) if pattern["kind"] == "PRIMARY")
        primary = patterns[primary_index]
        old = v1_policy["weather"][weather_code]
        assert primary["ceiling"] == 100 and weather["weights"] == old["weights"]
        assert all(primary[key] == old[key] for key in FEATURES + ["preferred_mode"])
        v1_masks[weather_code] = results[primary_index]["masks"][threshold]
        assert int(v1_masks[weather_code].sum()) == v1["weather"][weather_code]["passing_pool"]["track_count"]
        assert not (v1_masks[weather_code] & ~qualified).any()
        filtered_speed = pool.loc[pool.speed.isin(weather["example_allowed_speeds"])]
        pass_matrix = np.column_stack([result["masks"][threshold] for result in results])
        pattern_counts = {result["pattern"]["pattern_id"]: {"kind": result["pattern"]["kind"], "ceiling": result["pattern"]["ceiling"], "passing_count": int(result["masks"][threshold].sum()), "representative_count": int(((selected == index) & qualified).sum()), "sensitivity_passing_count": {str(limit): int(result["masks"][limit].sum()) for limit in thresholds}} for index, result in enumerate(results)}
        for index in np.flatnonzero(qualified):
            chosen = results[int(selected[index])]
            assert chosen["masks"][threshold][index]
            recomposed = fraction(chosen["pattern"]["ceiling"]) * sum(weather["weights"][name] * chosen["components_exact"][name][index] for name in FEATURES + ["mode"]) / 10000
            assert recomposed == Fraction(frame.iloc[index].weather_score_exact)
        summary["weather"][weather_code] = {"label": weather["label"], "passing_pool": stats(pool), "pass_percent_of_base": 100 * len(pool) / len(base), "score_100_count": int(pool.weather_score.eq(100).sum()), "all_base_score": {"interpretation": "maximum among core-passing patterns even below score threshold; raw maximum diagnostic only when no pattern passes core", "mean": float(frame.weather_score.mean()), "median": float(frame.weather_score.median()), "min": float(frame.weather_score.min()), "max": float(frame.weather_score.max())}, "patterns": pattern_counts, "both_patterns_pass_count": int(pass_matrix.all(axis=1).sum()), "exactly_one_pattern_pass_count": int((pass_matrix.sum(axis=1) == 1).sum()), "representative_uses_one_consistent_pattern_all_features": True, "auto_instrumental_true_pool": stats(pool.loc[pool.instrumental_auto.eq("TRUE")]), "example_speed_codes": weather["example_allowed_speeds"], "example_speed_filtered_pool": stats(filtered_speed), "example_speed_and_auto_instrumental_true_pool": stats(filtered_speed.loc[filtered_speed.instrumental_auto.eq("TRUE")]), "clear_low_score_actual_tracks": frame.sort_values(["weather_score", "track_id"]).head(2)[["track_id", "artists", "track_name", "energy", "acousticness", "valence", "mode", "weather_score", "selected_pattern_id", "component_energy", "component_acousticness", "selection_status"]].to_dict(orient="records")}
        summary["sensitivity"][weather_code] = {str(limit): stats(frame.loc[qualified_by_threshold[limit]]) for limit in thresholds}
        summary["boundary_checks"][weather_code] = {"weather_union_classification_changes": boundary, "patterns": {result["pattern"]["pattern_id"]: result["boundary"] for result in results}}
        example, metadata = make_example(pool, weather, policy)
        for _, row in example.iterrows():
            decision = select_exact(raw.loc[row.track_id], weather, threshold, core_min)
            assert decision["passes"] and decision["selected"]["pattern"]["pattern_id"] == row.selected_pattern_id
            assert decision["selected"]["score"] == Fraction(row.weather_score_exact)
        example.insert(0, "position", range(1, len(example) + 1))
        example.to_csv(example_dir / f"{weather_code}_180min.csv", index=False, encoding="utf-8-sig", float_format="%.15g")
        metadata["exact_fraction_score_gate_checks_passed"] = True
        summary["examples"][weather_code] = metadata
        print(json.dumps({"weather_completed": weather_code, "passing": len(pool), "patterns": pattern_counts}, ensure_ascii=True), flush=True)
    matrix = np.column_stack(list(passed_masks.values()))
    union, old_union = matrix.any(axis=1), np.column_stack(list(v1_masks.values())).any(axis=1)
    assert union.all()
    assert int((~old_union).sum()) == v1["passing_weather_count_distribution"]["0"]
    summary["passing_weather_count_distribution"] = {str(count): int((matrix.sum(axis=1) == count).sum()) for count in range(6)}
    summary["coverage"] = {"denominator": len(base), "raw_unique_track_ids_separate": len(u), "passing_weather_union_count": int(union.sum()), "union_equals_base_ids": True, "unmatched_ids": base.loc[~union, "track_id"].tolist(), "every_base_track_matches_at_least_one_weather": True, "fallback_assignment_used": False}
    summary["v1_vs_v2"] = {"v1_policy_version": v1["policy_version"], "v1_summary_sha256": sha256(v1_path), "v1_base": v1["eligibility"]["base"], "v2_base": stats(base), "v1_unmatched_count": int((~old_union).sum()), "v2_unmatched_count": int((~union).sum()), "v1_unmatched_rescued_count": int((~old_union & union).sum()), "v1_qualified_tracks_lost_count": int((old_union & ~union).sum()), "v1_qualified_retained_per_weather": {weather: bool(not (v1_masks[weather] & ~passed_masks[weather]).any()) for weather in passed_masks}, "weather_counts": {weather: {"v1": int(v1_masks[weather].sum()), "v2": int(passed_masks[weather].sum()), "added": int((passed_masks[weather] & ~v1_masks[weather]).sum())} for weather in passed_masks}}
    summary["pairwise"] = {}
    for left, right in itertools.combinations(policy["weather"], 2):
        intersection = int((passed_masks[left] & passed_masks[right]).sum())
        either = int((passed_masks[left] | passed_masks[right]).sum())
        summary["pairwise"][left + "__" + right] = {"intersection": intersection, "union": either, "jaccard": intersection / either if either else None, "score_pearson_all_base": float(np.corrcoef(frames[left].weather_score, frames[right].weather_score)[0, 1])}
    mixed_mask = passed_masks["RAIN"] & passed_masks["SNOW"]
    mixed = base.loc[mixed_mask, base_columns].copy()
    for weather in ["RAIN", "SNOW"]:
        for name in ["weather_score", "weather_score_exact", "selected_pattern_id", "selected_pattern_kind", "selected_pattern_ceiling", "pass_pattern_ids"] + ["component_" + name for name in FEATURES + ["mode"]] + ["component_" + name + "_exact" for name in FEATURES + ["mode"]]:
            mixed[weather.lower() + "_" + name] = frames[weather].loc[mixed_mask, name].to_numpy()
    mixed["ranking_score_min_rain_snow"] = np.minimum(mixed.rain_weather_score, mixed.snow_weather_score)
    mixed["ranking_score_exact"] = [str(min(Fraction(rain), Fraction(snow))) for rain, snow in zip(mixed.rain_weather_score_exact, mixed.snow_weather_score_exact)]
    for name, value in {"adapter_code": "RAIN_SNOW_INTERSECTION", "source_pty": ";".join(map(str, policy["mixed_precipitation"]["source_pty"])), "separate_weather_model": False, "score_formula_version": policy["policy_version"], "model_version": policy.get("model_version"), "model_fit_status": "INITIAL_PLANNING_NOT_FITTED", "source_dataset_sha256": source_hash, "analysis_status": "ANALYSIS_ONLY_NOT_READY", "pass_reason": "IN_RAIN_POOL_AND_SNOW_POOL"}.items():
        mixed[name] = value
    mixed = mixed.sort_values(["ranking_score_min_rain_snow", "track_id"], ascending=[False, True]).reset_index(drop=True)
    mixed.to_csv(pool_dir / "RAIN_SNOW_INTERSECTION.csv", index=False, encoding="utf-8-sig", float_format="%.15g")
    slow = mixed.loc[mixed.speed.isin(["slow", "medium"])]
    summary["mixed_adapter"] = {"adapter_code": "RAIN_SNOW_INTERSECTION", "source_pty": policy["mixed_precipitation"]["source_pty"], "separate_weather_model": False, "definition": "Intersection of RAIN and SNOW qualified pools; preserves both independently selected pattern records; not a sixth independent weather model", "ranking": "MIN_RAIN_SNOW_INITIAL_PROPOSAL_THEN_TRACK_ID_ASC", "score_formula_version": policy["policy_version"], "model_version": policy.get("model_version"), "readiness_status": "ANALYSIS_ONLY_NOT_READY", "all_speed_pool": stats(mixed), "speed_counts": mixed.speed.value_counts().to_dict(), "auto_instrumental_true_pool": stats(mixed.loc[mixed.instrumental_auto.eq("TRUE")]), "slow_medium_pool": stats(slow), "slow_medium_auto_instrumental_true_pool": stats(slow.loc[slow.instrumental_auto.eq("TRUE")]), "csv": "pools/RAIN_SNOW_INTERSECTION.csv", "unique_track_ids": bool(mixed.track_id.is_unique)}
    # Re-read all saved CSVs. Check serialized scores, exact fractions, versions,
    # representative pattern components, pool inclusion, ordering and examples.
    pools = {}
    for code, weather in policy["weather"].items():
        pool = pd.read_csv(pool_dir / f"{code}.csv")
        example = pd.read_csv(example_dir / f"{code}_180min.csv")
        pools[code] = pool
        assert len(pool) == summary["weather"][code]["passing_pool"]["track_count"]
        assert pool.track_id.is_unique and example.track_id.is_unique
        assert pool.sort_values(["weather_score", "track_id"], ascending=[False, True]).track_id.tolist() == pool.track_id.tolist()
        pattern_lookup = {pattern["pattern_id"]: pattern for pattern in weather["patterns"]}
        for row in pool.itertuples():
            score = Fraction(str(row.weather_score_exact))
            components = {name: Fraction(str(getattr(row, "component_" + name + "_exact"))) for name in FEATURES + ["mode"]}
            pattern = pattern_lookup[row.selected_pattern_id]
            assert score >= threshold and components["energy"] >= core_min and components["acousticness"] >= core_min
            assert fraction(pattern["ceiling"]) * sum(weather["weights"][name] * components[name] for name in components) / 10000 == score
            assert row.selected_pattern_id in row.pass_pattern_ids.split(";")
            assert row.selected_pattern_ceiling == pattern["ceiling"] and row.selected_pattern_kind == pattern["kind"]
        assert example.track_id.isin(pool.track_id).all() and int(example.duration_ms.sum()) == policy["target_duration_ms"]
        assert example.speed.isin(weather["example_allowed_speeds"]).all()
        for frame in [pool, example]:
            assert frame.model_version.isna().all() and frame.score_formula_version.eq(policy["policy_version"]).all()
            assert frame.model_fit_status.eq("INITIAL_PLANNING_NOT_FITTED").all() and frame.source_dataset_sha256.eq(source_hash).all()
    saved_mixed = pd.read_csv(pool_dir / "RAIN_SNOW_INTERSECTION.csv")
    assert set(saved_mixed.track_id) == set(pools["RAIN"].track_id) & set(pools["SNOW"].track_id)
    assert saved_mixed.sort_values(["ranking_score_min_rain_snow", "track_id"], ascending=[False, True]).track_id.tolist() == saved_mixed.track_id.tolist()
    assert saved_mixed.model_version.isna().all() and saved_mixed.score_formula_version.eq(policy["policy_version"]).all()
    for weather in ["rain", "snow"]:
        joined = saved_mixed.set_index("track_id").join(pools[weather.upper()].set_index("track_id")[["selected_pattern_id", "weather_score_exact"]])
        assert joined[weather + "_selected_pattern_id"].eq(joined.selected_pattern_id).all()
        assert joined[weather + "_weather_score_exact"].astype(str).eq(joined.weather_score_exact.astype(str)).all()
    summary["checks"] = {"all_pools_unique": True, "all_examples_exact_180min": all(value["exact_target_achieved"] for value in summary["examples"].values()), "all_saved_csvs_reloaded_and_verified": True, "all_representative_components_from_same_selected_pattern": True, "thresholds_select_patterns_independently": thresholds, "coverage_zero_unmatched": True, "v1_qualified_all_retained": True, "v1_unmatched_all_rescued": True, "support_box_domain_proof_verified": True, "fixed_anchors_passed": True, "negative_raw_max_gate_failure_test_passed": True, "weather_models_independent_calculation": True, "weather_scores_statistically_independent": False, "coefficients_fitted_to_weather_labels": False}
    (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"base": stats(base), "coverage": summary["coverage"], "counts": {code: value["passing_pool"] for code, value in summary["weather"].items()}, "distribution": summary["passing_weather_count_distribution"], "v1_vs_v2": summary["v1_vs_v2"], "examples": {code: {key: value[key] for key in ["selected", "quality_exact", "quality_optimality", "tie_optimality"]} for code, value in summary["examples"].items()}, "mixed": summary["mixed_adapter"], "checks": summary["checks"]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
