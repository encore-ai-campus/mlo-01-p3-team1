"""Reproduce the planning proposal; no source data or production systems are changed."""
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fraction(value) -> Fraction:
    return Fraction(str(value))


def component_exact(value, params) -> Fraction:
    x = fraction(value)
    lo, hi, width = map(fraction, params)
    distance = max(lo - x, Fraction(0), x - hi)
    return 100 * max(Fraction(0), 1 - distance / width)


def score_exact(row, params):
    components = {name: component_exact(row[name], params[name]) for name in FEATURES}
    components["mode"] = Fraction(100 if int(row["mode"]) == params["preferred_mode"] else 0)
    total = sum(fraction(params["weights"][name]) * value for name, value in components.items()) / 100
    return total, components


def score_vector(frame, params):
    components = {}
    for name in FEATURES:
        lo, hi, width = params[name]
        values = frame[name].to_numpy(dtype="float64")
        distance = np.maximum(np.maximum(lo - values, 0.0), values - hi)
        components[name] = 100.0 * np.maximum(0.0, 1.0 - distance / width)
    components["mode"] = np.where(frame["mode"].to_numpy() == params["preferred_mode"], 100.0, 0.0)
    total = sum(params["weights"][name] * value for name, value in components.items()) / 100.0
    return total, components


def speed(tempo, signature):
    value = Decimal(str(tempo))
    if int(signature) == 3:
        value /= Decimal("1.5")
    value = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return "slow" if value < 80 else "medium" if value < 110 else "fast" if value < 150 else "fastest"


def mapping():
    text = MAPPING_PATH.read_text(encoding="utf-8")
    section = text.split("### 3-1.", 1)[1].split("## 4.", 1)[0]
    groups = {}
    for line in section.splitlines():
        cells = [value.strip() for value in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"[A-Z][A-Z_-]*", cells[0]):
            groups[cells[0]] = [value.strip() for value in cells[2].split(",")]
    assert len(groups) == 18
    assert len(set(itertools.chain.from_iterable(groups.values()))) == 77
    return groups


def stats(frame):
    return {"track_count": len(frame), "duration_ms": int(frame.duration_ms.sum()), "duration_minutes": float(frame.duration_ms.sum()) / 60000}


def exact_subset(durations, target, block=32):
    """0/1 subset sum; checkpoint every 32 items, reconstruct one block at a time."""
    bits = 1
    mask = (1 << (target + 1)) - 1
    checkpoints = {0: bits}
    processed = 0
    for i, duration in enumerate(durations, 1):
        bits |= (bits << int(duration)) & mask
        processed = i
        if i % block == 0:
            checkpoints[i] = bits
        if (bits >> target) & 1:
            break
    if not ((bits >> target) & 1):
        return None, {"processed_count": processed, "checkpoint_count": len(checkpoints)}
    chosen = []
    remainder = target
    end = processed
    while end:
        start = ((end - 1) // block) * block
        states = [checkpoints[start]]
        for i in range(start, end):
            previous = states[-1]
            states.append(previous | ((previous << int(durations[i])) & mask))
        for i in range(end - 1, start - 1, -1):
            if (states[i - start] >> remainder) & 1:
                continue
            duration = int(durations[i])
            assert remainder >= duration
            assert (states[i - start] >> (remainder - duration)) & 1
            chosen.append(i)
            remainder -= duration
        end = start
    assert remainder == 0
    return sorted(chosen), {"processed_count": processed, "checkpoint_count": len(checkpoints), "reconstruction_block_size": block}


def example(pool, params, policy):
    allowed = pool.loc[pool.speed.isin(params["example_allowed_speeds"])].copy()
    target = int(policy["target_duration_ms"])
    usable = allowed.loc[allowed.duration_ms.le(target)].copy()
    sizes = []
    size = min(200, len(usable))
    while size:
        sizes.append(size)
        selected, search = exact_subset(usable.duration_ms.iloc[:size].tolist(), target)
        if selected is not None:
            result = usable.iloc[selected].copy()
            assert result.track_id.is_unique
            assert int(result.duration_ms.sum()) == target
            assert result.weather_score.ge(policy["score_threshold"] - 1e-10).all()
            assert result.component_energy.ge(policy["core_component_min"] - 1e-10).all()
            assert result.component_acousticness.ge(policy["core_component_min"] - 1e-10).all()
            all_maximum = bool(result.weather_score.eq(100.0).all())
            weighted_score = float((result.weather_score * result.duration_ms).sum() / target)
            return result, {"status": "ANALYSIS_FEASIBLE_NOT_PRODUCTION_ACCEPTANCE", "candidate_pool": stats(allowed), "searched_prefix_sizes": sizes, "search": search, "exact_target_achieved": True, "quality_time_weighted_mean": weighted_score, "quality_upper_bound": 100.0, "quality_optimality": "PROVEN_ALL_SELECTED_SCORES_AT_GLOBAL_UPPER_BOUND" if all_maximum else "NOT_PROVEN", "play_order": "weather_score_desc_then_track_id_asc; transition quality not optimized", "instrumental_only": False}
        if size == len(usable):
            break
        size = min(size * 2, len(usable))
    return usable.iloc[:0].copy(), {"status": "EXACT_TARGET_NOT_FOUND", "candidate_pool": stats(allowed), "searched_prefix_sizes": sizes, "exact_target_achieved": False, "quality_optimality": "NOT_PROVEN"}


def main():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    d = pd.read_csv(SOURCE)
    raw = pd.read_csv(SOURCE, dtype=str).drop_duplicates("track_id").set_index("track_id")
    u = d.drop_duplicates("track_id").copy()
    genre_sets = d.groupby("track_id")["track_genre"].agg(lambda values: sorted(set(values)))
    groups = mapping()
    raw_to_codes = {}
    for code, genres in groups.items():
        for genre in genres:
            raw_to_codes.setdefault(genre, set()).add(code)
    u["raw_track_genres"] = u.track_id.map(genre_sets).map(lambda values: ";".join(values))
    u["service_genre_codes"] = u.track_id.map(genre_sets).map(lambda values: ";".join(sorted(set().union(*(raw_to_codes.get(genre, set()) for genre in values)))))
    metadata = u[["artists", "album_name", "track_name"]].notna().all(axis=1) & u.duration_ms.gt(0)
    audio_valid = u[FEATURES].notna().all(axis=1) & u[FEATURES].ge(0).all(axis=1) & u[FEATURES].le(1).all(axis=1) & u["mode"].isin([0, 1])
    valid_tempo = u.tempo.gt(0) & np.isfinite(u.tempo)
    genre_valid = u.service_genre_codes.ne("")
    base = u.loc[metadata & audio_valid & valid_tempo & genre_valid].copy().reset_index(drop=True)
    base["speed"] = [speed(row.tempo, row.time_signature) for row in base.itertuples()]
    base["instrumental_auto"] = np.where(base.instrumentalness.ge(.8), "TRUE", np.where(base.instrumentalness.lt(.2), "FALSE", "UNKNOWN"))
    base["instrumental_source"] = "AUTO_UNREVIEWED"
    summary = {
        "policy_version": policy["policy_version"], "score_formula_version": policy["policy_version"], "model_version": policy.get("model_version"), "status": "ANALYSIS_FEASIBLE_NOT_PRODUCTION_ACCEPTANCE", "readiness_status": "ANALYSIS_ONLY_NOT_READY", "weather_updates": policy.get("weather_updates"),
        "source": {"path": str(SOURCE), "sha256": sha256(SOURCE), "bytes": SOURCE.stat().st_size, "data_rows": len(d), "columns": d.columns.tolist(), "unique_track_ids": len(u), "extra_duplicate_rows": int(d.track_id.duplicated().sum()), "missing_counts": d.isna().sum().to_dict(), "mapping_path": str(MAPPING_PATH.relative_to(ROOT)), "mapping_sha256": sha256(MAPPING_PATH), "policy_sha256": sha256(POLICY_PATH)},
        "eligibility": {"analysis_only": True, "ready_verified": False, "tag_approval_verified": False, "listening_review_verified": False, "database_or_playback_tested": False, "base_definition": "valid names, duration>0, finite raw features in[0,1], mode0/1, finite tempo>0, at least one mapped style; time_signature=3 correction only", "base": stats(base), "style_and_metadata_without_tempo_filter": stats(u.loc[metadata & audio_valid & genre_valid]), "speed_counts": base.speed.value_counts().to_dict(), "instrumental_auto_counts": base.instrumental_auto.value_counts().to_dict(), "no_instrumental_filter_in_weather_pools": True},
        "source_profile": {"repeated_id_count": int(d.track_id.value_counts().gt(1).sum()), "exact_duplicate_rows_excluding_index": int(d.drop(columns="Unnamed: 0").duplicated().sum()), "id_conflict_counts_by_column": d.groupby("track_id").nunique(dropna=False).gt(1).sum().to_dict(), "raw_genre_counts": d.track_genre.value_counts().to_dict(), "unique_id_numeric_quantiles": u[AUDIO + ["duration_ms", "popularity"]].quantile([0, .01, .05, .25, .5, .75, .95, .99, 1]).to_dict(), "unique_id_feature_pearson": u[AUDIO].corr().to_dict(), "weather_rating_label_available": False, "instrumental_auto_unique_id_counts": {"FALSE": int(u.instrumentalness.lt(.2).sum()), "UNKNOWN": int((u.instrumentalness.ge(.2) & u.instrumentalness.lt(.8)).sum()), "TRUE": int(u.instrumentalness.ge(.8).sum())}},
        "numerics": {"screening": "NumPy float64", "boundary_exact_check": "Fraction from original CSV decimal strings at score70/75/80 or core20 within1e-8; exact checks on all example selections", "full_score_normalization": "After recording boundary errors, exact Fraction component lookups normalize every score and confirm every threshold decision; float conversion occurs only after exact calculation to preserve mathematical ties in sorting", "production_numeric_contract": "not implemented; this reproducible analysis does not establish production arithmetic or publishing acceptance"},
        "weather": {}, "sensitivity": {}, "boundary_checks": {}, "hypothetical_patterns": [], "examples": {},
    }
    scored = {}
    passed_masks = {}
    base_columns = ["track_id", "artists", "album_name", "track_name", "duration_ms", "explicit"] + AUDIO + ["raw_track_genres", "service_genre_codes", "speed", "instrumental_auto", "instrumental_source"]
    pool_dir = HERE / "pools"
    example_dir = HERE / "examples"
    pool_dir.mkdir(exist_ok=True)
    example_dir.mkdir(exist_ok=True)
    for weather, params in policy["weather"].items():
        values, components = score_vector(base, params)
        gates = (components["energy"] >= policy["core_component_min"]) & (components["acousticness"] >= policy["core_component_min"])
        masks = {threshold: gates & (values >= threshold) for threshold in [70, 75, 80]}
        near = np.zeros(len(base), dtype=bool)
        for threshold in [70, 75, 80]:
            near |= np.abs(values - threshold) <= 1e-8
        for feature in ["energy", "acousticness"]:
            near |= np.abs(components[feature] - policy["core_component_min"]) <= 1e-8
        checks = []
        changes = {threshold: 0 for threshold in masks}
        for index in np.flatnonzero(near):
            track_id = base.iloc[index].track_id
            exact_total, exact_components = score_exact(raw.loc[track_id], params)
            exact_gate = exact_components["energy"] >= policy["core_component_min"] and exact_components["acousticness"] >= policy["core_component_min"]
            old_total = float(values[index])
            changed_thresholds = []
            for threshold in masks:
                decision = exact_gate and exact_total >= threshold
                changed = masks[threshold][index] != decision
                changes[threshold] += int(changed)
                if changed:
                    changed_thresholds.append(threshold)
                masks[threshold][index] = decision
            values[index] = float(exact_total)
            for name in components:
                components[name][index] = float(exact_components[name])
            checks.append({"track_id": track_id, "score_float_before": old_total, "score_exact": str(exact_total), "energy_exact": str(exact_components["energy"]), "acousticness_exact": str(exact_components["acousticness"]), "changed_thresholds": changed_thresholds, "pass75_exact": bool(masks[75][index])})
        # Normalize all mathematically identical scores before sorting. Otherwise
        # float64 can produce 94.99999999999999 and95 for the same exact value.
        exact_columns = {}
        weighted_columns = {}
        for name in FEATURES:
            raw_values = raw.loc[base.track_id, name].tolist()
            lookup = {value: component_exact(value, params[name]) for value in set(raw_values)}
            exact_columns[name] = [lookup[value] for value in raw_values]
            weighted_lookup = {value: params["weights"][name] * score / 100 for value, score in lookup.items()}
            weighted_columns[name] = [weighted_lookup[value] for value in raw_values]
            components[name] = np.fromiter((float(value) for value in exact_columns[name]), dtype="float64", count=len(base))
        mode_contribution = np.where(base["mode"].to_numpy() == params["preferred_mode"], params["weights"]["mode"], 0)
        exact_scores = [energy + acousticness + valence + int(mode) for energy, acousticness, valence, mode in zip(weighted_columns["energy"], weighted_columns["acousticness"], weighted_columns["valence"], mode_contribution)]
        values = np.fromiter(map(float, exact_scores), dtype="float64", count=len(base))
        exact_gates = np.fromiter((energy >= policy["core_component_min"] and acousticness >= policy["core_component_min"] for energy, acousticness in zip(exact_columns["energy"], exact_columns["acousticness"])), dtype=bool, count=len(base))
        for threshold in masks:
            exact_mask = exact_gates & np.fromiter((value >= threshold for value in exact_scores), dtype=bool, count=len(base))
            assert np.array_equal(masks[threshold], exact_mask), "Boundary screening missed an exact threshold difference"
            masks[threshold] = exact_mask
        frame = base[base_columns].copy()
        for name, feature_values in components.items():
            frame["component_" + name] = feature_values
        frame["weather_score"] = values
        frame["weather"] = weather
        frame["policy_version"] = policy["policy_version"]
        frame["score_formula_version"] = policy["policy_version"]
        frame["model_version"] = policy.get("model_version")
        frame["model_fit_status"] = "INITIAL_PLANNING_NOT_FITTED"
        frame["source_dataset_sha256"] = summary["source"]["sha256"]
        frame["analysis_status"] = "ANALYSIS_ONLY_NOT_READY"
        frame["pass_reason"] = np.where(masks[75], "SCORE_GE75_AND_ENERGY_GE20_AND_ACOUSTICNESS_GE20", "FAILED_SCORE_OR_CORE_GATE")
        pool = frame.loc[masks[75]].sort_values(["weather_score", "track_id"], ascending=[False, True]).reset_index(drop=True)
        pool.to_csv(pool_dir / f"{weather}.csv", index=False, encoding="utf-8-sig", float_format="%.15g")
        scored[weather] = frame
        passed_masks[weather] = masks[75]
        filtered_speed = pool.loc[pool.speed.isin(params["example_allowed_speeds"])]
        summary["weather"][weather] = {"label": params["label"], "all_base_score": {"mean": float(values.mean()), "median": float(np.median(values)), "min": float(values.min()), "max": float(values.max()), "quantiles": {str(q): float(np.quantile(values, q)) for q in [.01, .05, .25, .5, .75, .95, .99]}}, "passing_pool": stats(pool), "pass_percent_of_base": 100 * len(pool) / len(base), "score_100_count": int(pool.weather_score.eq(100).sum()), "auto_instrumental_true_pool": stats(pool.loc[pool.instrumental_auto.eq("TRUE")]), "example_speed_codes": params["example_allowed_speeds"], "example_speed_filtered_pool": stats(filtered_speed), "example_speed_and_auto_instrumental_true_pool": stats(filtered_speed.loc[filtered_speed.instrumental_auto.eq("TRUE")]), "clear_low_score_actual_tracks": frame.sort_values(["weather_score", "track_id"]).head(2)[["track_id", "artists", "track_name", "energy", "acousticness", "valence", "mode", "weather_score", "component_energy", "component_acousticness", "pass_reason"]].to_dict(orient="records")}
        summary["sensitivity"][weather] = {str(threshold): stats(frame.loc[mask]) for threshold, mask in masks.items()}
        summary["boundary_checks"][weather] = {"rechecked_count": len(checks), "classification_changes": changes, "records": checks}
        result, result_meta = example(pool, params, policy)
        selected_exact_values = []
        for _, row in result.iterrows():
            exact_total, exact_components = score_exact(raw.loc[row.track_id], params)
            selected_exact_values.append(exact_total)
            assert exact_total >= policy["score_threshold"]
            assert exact_components["energy"] >= policy["core_component_min"]
            assert exact_components["acousticness"] >= policy["core_component_min"]
        exact_all_maximum = bool(selected_exact_values) and all(value == 100 for value in selected_exact_values)
        result_meta["quality_optimality"] = "PROVEN_ALL_SELECTED_SCORES_AT_GLOBAL_UPPER_BOUND" if exact_all_maximum else "NOT_PROVEN"
        result_meta["all_selected_scores_exactly_100"] = exact_all_maximum
        result_meta["tie_optimality"] = "NOT_PROVEN"
        result_meta["readiness_status"] = "ANALYSIS_ONLY_NOT_READY"
        result.insert(0, "position", range(1, len(result) + 1))
        result.to_csv(example_dir / f"{weather}_180min.csv", index=False, encoding="utf-8-sig", float_format="%.15g")
        result_meta["selected"] = stats(result)
        result_meta["unique_track_ids"] = bool(result.track_id.is_unique)
        result_meta["exact_fraction_score_gate_checks_passed"] = True
        summary["examples"][weather] = result_meta
    matrix = np.column_stack(list(passed_masks.values()))
    summary["passing_weather_count_distribution"] = {str(count): int((matrix.sum(axis=1) == count).sum()) for count in range(6)}
    summary["pairwise"] = {}
    for left, right in itertools.combinations(policy["weather"], 2):
        lmask, rmask = passed_masks[left], passed_masks[right]
        intersection = int((lmask & rmask).sum())
        union = int((lmask | rmask).sum())
        summary["pairwise"][left + "__" + right] = {"intersection": intersection, "union": union, "jaccard": intersection / union if union else None, "score_pearson_all_base": float(np.corrcoef(scored[left].weather_score, scored[right].weather_score)[0, 1])}
    mixed_mask = passed_masks["RAIN"] & passed_masks["SNOW"]
    mixed = base.loc[mixed_mask, base_columns].copy()
    for weather in ["RAIN", "SNOW"]:
        mixed[weather.lower() + "_weather_score"] = scored[weather].loc[mixed_mask, "weather_score"].to_numpy()
        for name in FEATURES + ["mode"]:
            mixed[weather.lower() + "_component_" + name] = scored[weather].loc[mixed_mask, "component_" + name].to_numpy()
    mixed["ranking_score_min_rain_snow"] = np.minimum(mixed.rain_weather_score, mixed.snow_weather_score)
    mixed["adapter_code"] = "RAIN_SNOW_INTERSECTION"
    mixed["source_pty"] = ";".join(map(str, policy["mixed_precipitation"]["source_pty"]))
    mixed["separate_weather_model"] = False
    mixed["score_formula_version"] = policy["policy_version"]
    mixed["model_version"] = policy.get("model_version")
    mixed["model_fit_status"] = "INITIAL_PLANNING_NOT_FITTED"
    mixed["source_dataset_sha256"] = summary["source"]["sha256"]
    mixed["analysis_status"] = "ANALYSIS_ONLY_NOT_READY"
    mixed["pass_reason"] = "IN_RAIN_POOL_AND_SNOW_POOL"
    mixed = mixed.sort_values(["ranking_score_min_rain_snow", "track_id"], ascending=[False, True]).reset_index(drop=True)
    mixed.to_csv(pool_dir / "RAIN_SNOW_INTERSECTION.csv", index=False, encoding="utf-8-sig", float_format="%.15g")
    mixed_slow_medium = mixed.loc[mixed.speed.isin(["slow", "medium"])]
    summary["mixed_adapter"] = {"adapter_code": "RAIN_SNOW_INTERSECTION", "source_pty": policy["mixed_precipitation"]["source_pty"], "separate_weather_model": False, "definition": "Intersection of the existing RAIN and SNOW passing pools; not a sixth independent weather model", "ranking": "MIN_RAIN_SNOW_INITIAL_PROPOSAL_THEN_TRACK_ID_ASC", "score_formula_version": policy["policy_version"], "model_version": policy.get("model_version"), "readiness_status": "ANALYSIS_ONLY_NOT_READY", "all_speed_pool": stats(mixed), "speed_counts": mixed.speed.value_counts().to_dict(), "auto_instrumental_true_pool": stats(mixed.loc[mixed.instrumental_auto.eq("TRUE")]), "slow_medium_pool": stats(mixed_slow_medium), "slow_medium_auto_instrumental_true_pool": stats(mixed_slow_medium.loc[mixed_slow_medium.instrumental_auto.eq("TRUE")]), "csv": "pools/RAIN_SNOW_INTERSECTION.csv", "unique_track_ids": bool(mixed.track_id.is_unique)}
    for name, values in {"HYPOTHETICAL_ENERGETIC_BRIGHT": [.8, .1, .8, 1], "HYPOTHETICAL_QUIET_DARK_ACOUSTIC": [.2, .9, .2, 0], "HYPOTHETICAL_SOFT_BRIGHT_ACOUSTIC": [.15, .9, .65, 1], "HYPOTHETICAL_MODERATE": [.5, .5, .5, 0]}.items():
        raw_row = dict(zip(FEATURES + ["mode"], values))
        profile = {"label": name, "assumed_not_observed": True, "raw_features": raw_row, "weather": {}}
        for weather, params in policy["weather"].items():
            total, components = score_exact(raw_row, params)
            profile["weather"][weather] = {"score": float(total), "score_exact": str(total), "component_energy": float(components["energy"]), "component_acousticness": float(components["acousticness"]), "passes": bool(total >=75 and components["energy"] >=20 and components["acousticness"] >=20)}
        summary["hypothetical_patterns"].append(profile)
    summary["checks"] = {"all_pools_have_unique_track_ids": all(frame.loc[passed_masks[weather]].track_id.is_unique for weather, frame in scored.items()), "all_examples_exact_180min": all(value["exact_target_achieved"] for value in summary["examples"].values()), "weather_count_distribution_matches_base": sum(summary["passing_weather_count_distribution"].values()) == len(base), "weather_models_independent_calculation": True, "weather_scores_statistically_independent": False, "coefficients_fitted_to_weather_labels": False}
    (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"base": summary["eligibility"]["base"], "pools": {weather: values["passing_pool"] for weather, values in summary["weather"].items()}, "examples": {weather: {key: values[key] for key in ["selected", "quality_time_weighted_mean", "quality_optimality", "search"]} for weather, values in summary["examples"].items()}, "boundary_changes": {weather: values["classification_changes"] for weather, values in summary["boundary_checks"].items()}, "passing_weather_count_distribution": summary["passing_weather_count_distribution"], "checks": summary["checks"]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
