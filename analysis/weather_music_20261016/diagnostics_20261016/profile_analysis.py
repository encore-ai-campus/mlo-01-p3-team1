"""Read-only V2 source diagnostics; writes only profile_* files beside this script."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
SPEC = importlib.util.spec_from_file_location("weather_analysis_read_only", PARENT / "analyze.py")
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)
QUANTILES = [0, .01, .05, .25, .5, .75, .95, .99, 1]
CORE = ["energy", "acousticness", "valence", "mode"]
CORRELATION_FEATURES = CORE + ["danceability", "tempo", "loudness", "instrumentalness", "speechiness", "liveness"]
CONTINUOUS_FEATURES = [name for name in CORRELATION_FEATURES if name != "mode"] + ["duration_ms"]
UNIT_FEATURES = {"energy", "acousticness", "valence", "danceability", "instrumentalness", "speechiness", "liveness"}
ROBUST_Z_FACTOR = .6744897501960817
ROBUST_Z_LIMIT = 3.5


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump_csv(name, frame):
    frame.to_csv(HERE / name, index=False, encoding="utf-8-sig", float_format="%.12g")


def describe(cohort, name, values, categorical=False):
    values = pd.to_numeric(values, errors="coerce").dropna()
    quantiles = values.quantile(QUANTILES)
    record = {"cohort": cohort, "feature": name, "n": len(values), "mean": float(values.mean()), "std_population_ddof0": float(values.std(ddof=0)), "skew_fisher_pearson_unbiased": None if categorical else float(values.skew()), "zero_ratio": float(values.eq(0).mean()), "one_ratio": float(values.eq(1).mean()), "ratio_le_0_01": float(values.le(.01).mean()) if name in UNIT_FEATURES else None, "ratio_ge_0_99": float(values.ge(.99).mean()) if name in UNIT_FEATURES else None, "unit_interval_thresholds_applicable": name in UNIT_FEATURES, "categorical_indicator": categorical}
    for q, value in quantiles.items():
        record[f"p{round(q * 100):02d}"] = float(value)
    return record


def collinearity(cohort, frame):
    raw = frame[CORE].to_numpy(dtype=float)
    means, stds = raw.mean(axis=0), raw.std(axis=0, ddof=0)
    assert (stds > 0).all()
    standardized = (raw - means) / stds
    design = np.column_stack([np.ones(len(frame)), standardized])
    records, regressions = [], []
    for target, name in enumerate(CORE):
        other = [index for index in range(len(CORE)) if index != target]
        x = np.column_stack([np.ones(len(frame)), standardized[:, other]])
        y = standardized[:, target]
        coefficients, residuals, rank, singular = np.linalg.lstsq(x, y, rcond=None)
        errors = y - x @ coefficients
        sse, sst = float(errors @ errors), float((y - y.mean()) @ (y - y.mean()))
        r_squared = 1 - sse / sst
        vif = 1 / (1 - r_squared) if r_squared < 1 else None
        records.append({"cohort": cohort, "feature": name, "n": len(frame), "vif": vif, "auxiliary_r_squared": r_squared, "rank_with_intercept": int(rank), "constant_feature": False})
        regressions.append({"target_feature_for_redundancy_only": name, "predictor_features": [CORE[index] for index in other], "intercept_standardized": float(coefficients[0]), "standardized_predictor_coefficients": {CORE[index]: float(value) for index, value in zip(other, coefficients[1:])}, "sse": sse, "sst": sst, "r_squared": r_squared, "rank": int(rank), "singular_values": singular.tolist()})
    condition = {"cohort": cohort, "n": len(frame), "features": CORE, "mode_coding": "0/1 categorical indicator, standardized as a single design column; not an ordinal music scale", "standardization": "(x-mean)/population_std(ddof=0)", "means": dict(zip(CORE, means.tolist())), "std_population": dict(zip(CORE, stds.tolist())), "condition_number_standardized_predictors": float(np.linalg.cond(standardized)), "condition_number_standardized_with_intercept": float(np.linalg.cond(design)), "rank_standardized_with_intercept": int(np.linalg.matrix_rank(design)), "lstsq_auxiliary_regressions_not_weather_models": regressions}
    return records, condition


def review_flags(base):
    criteria, flagged = [], []
    for name in CONTINUOUS_FEATURES:
        values = base[name].to_numpy(dtype=float)
        q1, median, q3 = np.quantile(values, [.25, .5, .75])
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        iqr_flags = (values < lower) | (values > upper) if iqr > 0 else np.zeros(len(base), dtype=bool)
        mad = float(np.median(np.abs(values - median)))
        mad_flags = np.abs(ROBUST_Z_FACTOR * (values - median) / mad) > ROBUST_Z_LIMIT if mad > 0 else np.zeros(len(base), dtype=bool)
        either = iqr_flags | mad_flags
        criteria.append({"feature": name, "n": len(base), "q1": float(q1), "median": float(median), "q3": float(q3), "iqr": float(iqr), "iqr_lower": float(lower), "iqr_upper": float(upper), "iqr_factor": 1.5, "iqr_flag_count": int(iqr_flags.sum()), "iqr_flag_ratio": float(iqr_flags.mean()), "iqr_status": "REVIEW_ONLY" if iqr > 0 else "ZERO_IQR_NO_IQR_FLAG", "mad": mad, "mad_status": "REVIEW_ONLY" if mad > 0 else "ZERO_MAD_NO_ROBUST_Z_FLAG", "mad_abs_robust_z_threshold": ROBUST_Z_LIMIT, "mad_flag_count": int(mad_flags.sum()), "mad_flag_ratio": float(mad_flags.mean()), "nonmedian_count_if_mad_zero": int((values != median).sum()) if mad == 0 else None, "either_count": int(either.sum()), "either_ratio": float(either.mean()), "deleted_count": 0})
        if either.any():
            flagged.append(pd.DataFrame({"track_id": base.loc[either, "track_id"].to_numpy(), "feature": name, "iqr_flag": iqr_flags[either], "mad_flag": mad_flags[either]}))
    compact = pd.concat(flagged, ignore_index=True) if flagged else pd.DataFrame(columns=["track_id", "feature", "iqr_flag", "mad_flag"])
    compact = compact.sort_values(["track_id", "feature"]).reset_index(drop=True)
    assert not compact.duplicated(["track_id", "feature"]).any()
    assert (compact.iqr_flag | compact.mad_flag).all()
    return criteria, compact


def main():
    policy_path, existing_path = PARENT / "policy.json", PARENT / "summary.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    existing = json.loads(existing_path.read_text(encoding="utf-8"))
    source = Path(existing["source"]["path"])
    hashes_before = {"source_sha256": digest(source), "policy_sha256": digest(policy_path), "existing_summary_sha256": digest(existing_path), "mapping_sha256": digest(ANALYSIS.MAPPING_PATH), "analysis_code_sha256": digest(PARENT / "analyze.py")}
    assert hashes_before["source_sha256"] == existing["source"]["sha256"]
    assert hashes_before["policy_sha256"] == existing["source"]["policy_sha256"]
    assert hashes_before["mapping_sha256"] == existing["source"]["mapping_sha256"]
    assert policy["policy_version"] == "WEATHER_SCORE_PROPOSAL_20261016_V2"
    d = pd.read_csv(source)
    u = d.drop_duplicates("track_id").copy()
    genre_sets = d.groupby("track_id")["track_genre"].agg(lambda values: sorted(set(values)))
    groups, raw_to_codes = ANALYSIS.mapping(), {}
    for code, labels in groups.items():
        for label in labels:
            raw_to_codes.setdefault(label, set()).add(code)
    u["service_genre_codes"] = u.track_id.map(genre_sets).map(lambda labels: ";".join(sorted(set().union(*(raw_to_codes.get(label, set()) for label in labels)))))
    metadata = u[["artists", "album_name", "track_name"]].notna().all(axis=1) & u.duration_ms.gt(0)
    features = u[ANALYSIS.FEATURES].notna().all(axis=1) & u[ANALYSIS.FEATURES].ge(0).all(axis=1) & u[ANALYSIS.FEATURES].le(1).all(axis=1) & u["mode"].isin([0, 1])
    base = u.loc[metadata & features & u.tempo.gt(0) & np.isfinite(u.tempo) & u.service_genre_codes.ne("")].copy().reset_index(drop=True)
    base["speed"] = [ANALYSIS.speed(row.tempo, row.time_signature) for row in base.itertuples()]
    assert len(u) == 89741 and len(base) == 61931 and base.track_id.is_unique
    assert int(base.duration_ms.sum()) == existing["eligibility"]["base"]["duration_ms"]
    distribution, pearson, spearman, mode_counts, vif_records, conditions = [], [], [], [], [], []
    for cohort, frame in [("SOURCE_UNIQUE_89741", u), ("BASE_ELIGIBLE_61931", base)]:
        for name in CONTINUOUS_FEATURES + ["mode"]:
            distribution.append(describe(cohort, name, frame[name], categorical=name == "mode"))
        for name in ["mode", "key", "time_signature"]:
            for value, count in frame[name].value_counts(dropna=False).sort_index().items():
                mode_counts.append({"cohort": cohort, "categorical_feature": name, "value": int(value), "count": int(count), "ratio": int(count) / len(frame)})
        numeric = frame[CORRELATION_FEATURES]
        p = numeric.corr(method="pearson")
        rank_correlation = numeric.rank(method="average").corr(method="pearson")
        for left in CORRELATION_FEATURES:
            for right in CORRELATION_FEATURES:
                pearson.append({"cohort": cohort, "feature_x": left, "feature_y": right, "n": len(frame), "r": float(p.loc[left, right])})
                spearman.append({"cohort": cohort, "feature_x": left, "feature_y": right, "n": len(frame), "rho": float(rank_correlation.loc[left, right])})
        rows, condition = collinearity(cohort, frame)
        vif_records.extend(rows)
        conditions.append(condition)
    dump_csv("profile_feature_distribution.csv", pd.DataFrame(distribution))
    dump_csv("profile_pearson.csv", pd.DataFrame(pearson))
    dump_csv("profile_spearman.csv", pd.DataFrame(spearman))
    dump_csv("profile_category_counts.csv", pd.DataFrame(mode_counts))
    dump_csv("profile_vif.csv", pd.DataFrame(vif_records))
    criteria, flags = review_flags(base)
    dump_csv("profile_review_criteria.csv", pd.DataFrame(criteria))
    dump_csv("profile_review_flags.csv", flags)
    genre_memberships = base[["track_id", "service_genre_codes"]].copy()
    genre_memberships["genre_code"] = genre_memberships.service_genre_codes.str.split(";")
    genre_memberships = genre_memberships.explode("genre_code")[["track_id", "genre_code"]]
    genre_denominators = genre_memberships.groupby("genre_code").track_id.nunique()
    flagged_by_genre = flags.merge(genre_memberships, on="track_id", how="left").groupby(["feature", "genre_code"]).agg(flagged_track_count=("track_id", "nunique"), iqr_flag_count=("iqr_flag", "sum"), mad_flag_count=("mad_flag", "sum")).reset_index()
    flagged_by_genre["genre_base_track_count"] = flagged_by_genre.genre_code.map(genre_denominators)
    flagged_by_genre["flag_ratio_within_genre"] = flagged_by_genre.flagged_track_count / flagged_by_genre.genre_base_track_count
    flagged_by_genre = flagged_by_genre.sort_values(["feature", "flag_ratio_within_genre", "genre_code"], ascending=[True, False, True]).reset_index(drop=True)
    dump_csv("profile_review_flags_by_genre.csv", flagged_by_genre)
    pool_features, pattern_rows, tie_rows, genre_rows, speed_rows = [], [], [], [], []
    all_ids = set()
    pool_summaries = {}
    required = ["track_id", "weather_score", "weather_score_exact", "selected_pattern_id", "selected_pattern_kind", "selected_pattern_ceiling", "pass_pattern_ids", "speed", "service_genre_codes", "score_formula_version", "source_dataset_sha256"]
    pool_hashes = {}
    for code, weather in policy["weather"].items():
        path = PARENT / "pools" / f"{code}.csv"
        pool_hashes[code] = digest(path)
        pool = pd.read_csv(path, usecols=required, dtype={"weather_score_exact": str})
        assert pool.track_id.is_unique and len(pool) == existing["weather"][code]["passing_pool"]["track_count"]
        assert pool.source_dataset_sha256.eq(hashes_before["source_sha256"]).all()
        assert pool.score_formula_version.eq(policy["policy_version"]).all()
        all_ids.update(pool.track_id)
        source_rows = base.set_index("track_id").loc[pool.track_id]
        for feature in ANALYSIS.FEATURES:
            pool_features.append(describe(code, feature, source_rows[feature]))
        for kind, group in pool.groupby("selected_pattern_kind"):
            pattern_rows.append({"weather": code, "kind": kind, "selected_count": len(group), "ratio_of_pool": len(group) / len(pool), "pool_n": len(pool)})
        for subgroup, group in [("ALL", pool)] + list(pool.groupby("selected_pattern_kind")):
            exact = group.weather_score_exact.map(Fraction)
            counts = {score: int(exact.eq(Fraction(score)).sum()) for score in [76, 80, 100]}
            for score, count in counts.items():
                tie_rows.append({"weather": code, "selected_kind": subgroup, "score_exact": score, "count": count, "ratio_within_subgroup": count / len(group) if len(group) else None, "subgroup_n": len(group)})
        counts = pool.service_genre_codes.str.split(";").explode().value_counts()
        for genre, count in counts.items():
            genre_rows.append({"weather": code, "genre_code": genre, "track_count": int(count), "ratio_of_pool_nonexclusive": int(count) / len(pool), "pool_n": len(pool)})
        for speed_code, count in pool.speed.value_counts().items():
            speed_rows.append({"weather": code, "speed": speed_code, "track_count": int(count), "ratio_of_pool_exclusive": int(count) / len(pool), "pool_n": len(pool)})
        all_exact = pool.weather_score_exact.map(Fraction)
        pools_ties = {str(score): int(all_exact.eq(Fraction(score)).sum()) for score in [76, 80, 100]}
        pool_summaries[code] = {"n": len(pool), "feature_distribution": [row for row in pool_features if row["cohort"] == code], "selected_pattern_kind_counts": pool.selected_pattern_kind.value_counts().to_dict(), "exact_score_mass": pools_ties, "exact_score_mass_ratio": {score: count / len(pool) for score, count in pools_ties.items()}, "genre_membership_count": int(counts.sum()), "genre_ratios_sum_nonexclusive": float(counts.sum()) / len(pool), "speed_partition_verified": int(pool.speed.value_counts().sum()) == len(pool)}
    assert all_ids == set(base.track_id)
    dump_csv("profile_pool_features.csv", pd.DataFrame(pool_features))
    dump_csv("profile_pattern_selection.csv", pd.DataFrame(pattern_rows))
    dump_csv("profile_pool_score_ties.csv", pd.DataFrame(tie_rows))
    dump_csv("profile_pool_genres.csv", pd.DataFrame(genre_rows))
    dump_csv("profile_pool_speeds.csv", pd.DataFrame(speed_rows))
    weather_pairs = [{"weather_x": pair.split("__")[0], "weather_y": pair.split("__")[1], **values} for pair, values in existing["pairwise"].items()]
    dump_csv("profile_weather_score_correlations.csv", pd.DataFrame(weather_pairs))
    summary = {"status": "DESCRIPTIVE_DIAGNOSTICS_NOT_LISTENING_VALIDATION", "policy_version": policy["policy_version"], "model_version": None, "hashes": hashes_before, "pool_hashes": pool_hashes, "denominators": {"source_rows_not_independent_tracks": len(d), "source_unique_track_ids": len(u), "base_eligible_unique_track_ids": len(base), "base_source_id_union_reproduced": True}, "methods": {"quantiles": QUANTILES, "std": "population ddof=0", "skew": "pandas adjusted Fisher-Pearson sample skewness; descriptive only", "spearman": "average-tie ranks then Pearson; no SciPy dependency", "mode": "binary categorical indicator; Pearson with continuous features is point-biserial interpretation", "excluded_from_continuous_regression": {"key": "pitch class/circular category; numeric labels are not a linear scale", "time_signature": "categorical meter, not continuous weather evidence"}, "zero_one_unit_interval_tail_ratios": "<=.01 and>=.99 ratios apply only to declared0..1 continuous features", "source_tempo_zero_values": "157 unique source records have tempo0; retained in source descriptive cohort and excluded from eligible base; do not interpret0 as a measured slow BPM"}, "distribution": distribution, "collinearity": conditions, "vif": vif_records, "correlation_pearson": pearson, "correlation_spearman": spearman, "review_flags": {"interpretation": "Statistical rarity for human/domain review, not errors; no automatic deletion or imputation", "automatic_deleted_count": 0, "flagged_feature_track_pairs": len(flags), "unique_flagged_tracks": int(flags.track_id.nunique()), "base_n": len(base), "criteria": criteria, "mad_zero_handling": "Do not divide by0; no robust-z flags; report nonmedian count separately", "iqr_zero_handling": "No IQR flags if IQR0; report zero-IQR status", "genre_exception_note": "Global fences can flag normal genre-specific characteristics; inspect genre-level context before any change", "many_flags_note": "Zero-inflated instrumentalness/speechiness and long-tailed liveness/duration can create many valid review flags; flags are not evidence of corruption", "compact_flags_file": "profile_review_flags.csv", "genre_context_file": "profile_review_flags_by_genre.csv", "genre_context": flagged_by_genre.to_dict(orient="records")}, "pools": pool_summaries, "weather_score_correlations": {"source": "Imported without modification from V2 summary calculated over the same base61931; core-passing representative rules", "mathematically_dependent_inputs": True, "not_independent_weather_observations_or_preference_labels": True, "pairs": weather_pairs}, "limitations": ["No weather-suitability or listening-rating y exists", "Feature-to-feature auxiliary least squares is redundancy diagnostics, not weather regression fitting", "No weather suitability, causality or population preference is inferred", "Genre labels are multiple memberships; ratios can sum above100percent", "Original genre rows were balanced at1000per label and are not market prevalence", "No production changes or external/LLM API calls"], "files": sorted(set(path.name for path in HERE.glob("profile_*") if path.is_file()) | {"profile_summary.json"})}
    assert hashes_before["source_sha256"] == digest(source)
    assert hashes_before["policy_sha256"] == digest(policy_path)
    assert hashes_before["existing_summary_sha256"] == digest(existing_path)
    assert hashes_before["mapping_sha256"] == digest(ANALYSIS.MAPPING_PATH)
    assert hashes_before["analysis_code_sha256"] == digest(PARENT / "analyze.py")
    assert all(pool_hashes[code] == digest(PARENT / "pools" / f"{code}.csv") for code in pool_hashes)
    summary["existing_sources_unchanged_after_analysis"] = True
    (HERE / "profile_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"denominators": summary["denominators"], "vif": vif_records, "condition_numbers": [{"cohort": value["cohort"], "condition_number": value["condition_number_standardized_with_intercept"]} for value in conditions], "flags": {key: summary["review_flags"][key] for key in ["flagged_feature_track_pairs", "unique_flagged_tracks", "automatic_deleted_count"]}, "flag_density": [{"feature": row["feature"], "iqr": row["iqr_flag_count"], "mad": row["mad_flag_count"], "either": row["either_count"], "either_ratio": row["either_ratio"]} for row in criteria], "pool_ties": {code: {"n": value["n"], "mass": value["exact_score_mass"], "mass_ratio": value["exact_score_mass_ratio"]} for code, value in pool_summaries.items()}, "unchanged": True}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
