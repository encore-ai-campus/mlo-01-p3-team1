"""Read-only V2 sensitivity diagnostics; writes only sibling diagnostic artifacts.

No listening labels are available. These are stability/coverage checks, not
recommendation quality estimates or fitted model coefficients.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.dont_write_bytecode = True  # Importing the V2 reference must not create its __pycache__.

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
EPS = 1e-8
FEATURES = ["energy", "acousticness", "valence"]
WEIGHTS = FEATURES + ["mode"]
LIMITS = [74, 75, 76, 77, 80]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frac(value):
    return Fraction(str(value))


def snapshot():
    paths = [V2 / "policy.json", V2 / "analyze.py", V2 / "summary.json"]
    paths += sorted((V2 / "pools").glob("*.csv"))
    paths += sorted((V2 / "examples").glob("*.csv"))
    return {str(p.relative_to(V2)): digest(p) for p in paths}


def load():
    spec = importlib.util.spec_from_file_location("v2_readonly_reference", V2 / "analyze.py")
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    policy = json.loads((V2 / "policy.json").read_text(encoding="utf-8"))
    summary = json.loads((V2 / "summary.json").read_text(encoding="utf-8"))
    source = Path(summary["source"]["path"])
    assert digest(source) == summary["source"]["sha256"]
    assert digest(V2 / "policy.json") == summary["source"]["policy_sha256"]
    data = pd.read_csv(source)
    raw = pd.read_csv(source, dtype=str).drop_duplicates("track_id").set_index("track_id")
    unique = data.drop_duplicates("track_id").copy()
    mapping = ref.mapping()
    mapped = set(label for labels in mapping.values() for label in labels)
    has_style = data.groupby("track_id").track_genre.agg(lambda values: any(value in mapped for value in values))
    meta = unique[["artists", "album_name", "track_name"]].notna().all(axis=1) & unique.duration_ms.gt(0)
    audio = unique[FEATURES].notna().all(axis=1) & unique[FEATURES].ge(0).all(axis=1) & unique[FEATURES].le(1).all(axis=1) & unique["mode"].isin([0, 1])
    base = unique.loc[meta & audio & unique.tempo.gt(0) & np.isfinite(unique.tempo) & unique.track_id.map(has_style)].copy().reset_index(drop=True)
    assert len(base) == 61931 == summary["eligibility"]["base"]["track_count"]
    raw = raw.loc[base.track_id]
    return ref, policy, summary, source, base, raw


def curve_component(q, curve, parameter):
    if curve == "linear":
        return 100 * (1 - q)
    if curve == "power":
        return 100 * np.power(1 - q, parameter)
    if curve == "exp":
        return 100 * (np.exp(-parameter * q) - np.exp(-parameter)) / (1 - np.exp(-parameter))
    raise ValueError(curve)


def rank_top(ids, scores, mask, k=200):
    eligible = np.flatnonzero(mask)
    ordered = eligible[np.lexsort((ids[eligible], -scores[eligible]))]
    top = ordered[:k]
    if not len(top):
        return top, {"top_k_size": 0, "cutoff_score": None, "cutoff_tie_pool_count": 0, "selected_at_cutoff_count": 0}
    cutoff = scores[top[-1]]
    return top, {"top_k_size": len(top), "cutoff_score": float(cutoff), "cutoff_tie_pool_count": int((scores[eligible] == cutoff).sum()), "selected_at_cutoff_count": int((scores[top] == cutoff).sum())}


def run():
    before = snapshot()
    ref, policy, baseline_summary, source, base, raw = load()
    codes = list(policy["weather"])
    ids = base.track_id.to_numpy()
    n = len(base)
    examples = {code: pd.read_csv(V2 / "examples" / f"{code}_180min.csv") for code in codes}
    example_positions = {code: np.flatnonzero(base.track_id.isin(examples[code].track_id)) for code in codes}
    pattern_data, q_cache = {}, {}
    for code in codes:
        weather = policy["weather"][code]
        records = []
        for pattern in sorted(weather["patterns"], key=lambda p: p["pattern_id"]):
            exact = ref.build_pattern(base, raw, weather, pattern, LIMITS, policy["core_component_min"])
            records.append(exact)
            for name in FEATURES:
                q_cache[(code, pattern["pattern_id"], name, "1")] = 1 - np.fromiter((float(x) for x in exact["components_exact"][name]), dtype=float) / 100
        pattern_data[code] = records
    print("Exact V2 component/score baseline reconstructed", flush=True)

    def evaluate_weather(code, scenario):
        records = pattern_data[code]
        weather = policy["weather"][code]
        changed = scenario.get("weather") == code
        curve = scenario.get("curve", "linear")
        curve_parameter = scenario.get("curve_parameter", 1)
        linear = curve == "linear"
        weights = {name: frac(value) for name, value in weather["weights"].items()}
        if scenario["family"] == "weight" and changed:
            weights[scenario["feature"]] *= frac(scenario["factor"])
            total = sum(weights.values())
            weights = {name: 100 * value / total for name, value in weights.items()}
        threshold = frac(scenario.get("threshold", 75))
        core_min = frac(scenario.get("core_min", 20))
        matrix_scores, matrix_core, matrix_near, matrix_lower, matrix_upper, matrix_nominal = [], [], [], [], [], []
        exact_resolved = 0
        for rec in records:
            pattern = rec["pattern"]
            if linear and scenario["family"] in {"baseline", "threshold", "core"} or (linear and not changed):
                score = rec["scores"].copy()
                comp = {name: np.fromiter(map(float, rec["components_exact"][name]), dtype=float) for name in WEIGHTS}
                core = np.fromiter((e >= core_min and a >= core_min for e, a in zip(rec["components_exact"]["energy"], rec["components_exact"]["acousticness"])), dtype=bool, count=n)
                passing = core & np.fromiter((s >= threshold for s in rec["scores_exact"]), dtype=bool, count=n)
                matrix_scores.append(score)
                matrix_core.append(core)
                matrix_near.append(np.zeros(n, bool))
                matrix_lower.append(passing)
                matrix_upper.append(passing)
                matrix_nominal.append(passing)
                continue
            comp = {}
            params = copy.deepcopy(pattern)
            for name in FEATURES:
                factor = frac(scenario["factor"]) if changed and scenario["family"] == "width" and name == scenario["feature"] else Fraction(1)
                key = (code, pattern["pattern_id"], name, str(factor))
                if key not in q_cache:
                    width = frac(pattern[name][2]) * factor
                    params[name][2] = width
                    values = raw[name].tolist()
                    look = {v: 1 - float(ref.component_exact(v, [pattern[name][0], pattern[name][1], width])) / 100 for v in set(values)}
                    q_cache[key] = np.fromiter((look[v] for v in values), dtype=float)
                if factor != 1:
                    params[name][2] = frac(pattern[name][2]) * factor
                comp[name] = curve_component(q_cache[key], curve, curve_parameter)
            comp["mode"] = np.fromiter(map(float, rec["components_exact"]["mode"]), dtype=float)
            score = float(pattern["ceiling"]) * sum(float(weights[name]) * comp[name] for name in WEIGHTS) / 10000
            core = (comp["energy"] >= float(core_min)) & (comp["acousticness"] >= float(core_min))
            near = (np.abs(score - float(threshold)) <= EPS) | (np.abs(comp["energy"] - float(core_min)) <= EPS) | (np.abs(comp["acousticness"] - float(core_min)) <= EPS)
            passing = core & (score >= float(threshold))
            if linear:
                params["weights"] = weights
                for index in np.flatnonzero(near):
                    total, exact_comp = ref.score_exact(raw.iloc[index], params)
                    score[index] = float(total)
                    core[index] = exact_comp["energy"] >= core_min and exact_comp["acousticness"] >= core_min
                    passing[index] = core[index] and total >= threshold
                    exact_resolved += 1
                unresolved = np.zeros(n, bool)
                lower = upper = passing
            else:
                unresolved = near.copy()
                lower = (score - EPS >= float(threshold)) & (comp["energy"] - EPS >= float(core_min)) & (comp["acousticness"] - EPS >= float(core_min))
                upper = (score + EPS >= float(threshold)) & (comp["energy"] + EPS >= float(core_min)) & (comp["acousticness"] + EPS >= float(core_min))
                for index in np.flatnonzero(near):
                    exact_comp = None
                    if all(comp[name][index] in (0, 100) for name in FEATURES):
                        exact_comp = {name: frac(comp[name][index]) for name in FEATURES}
                    elif curve == "power":
                        candidate = {}
                        for name in FEATURES:
                            linear_fit = ref.component_exact(raw.iloc[index][name], params[name]) / 100
                            if curve_parameter == 2:
                                candidate[name] = 100 * linear_fit ** 2
                            elif curve_parameter == .5:
                                numerator, denominator = math.isqrt(linear_fit.numerator), math.isqrt(linear_fit.denominator)
                                if numerator ** 2 != linear_fit.numerator or denominator ** 2 != linear_fit.denominator:
                                    break
                                candidate[name] = 100 * Fraction(numerator, denominator)
                        if len(candidate) == len(FEATURES):
                            exact_comp = candidate
                    if exact_comp is not None:
                        exact_comp["mode"] = rec["components_exact"]["mode"][index]
                        total = frac(pattern["ceiling"]) * sum(weights[name] * exact_comp[name] for name in WEIGHTS) / 10000
                        score[index] = float(total)
                        core[index] = exact_comp["energy"] >= core_min and exact_comp["acousticness"] >= core_min
                        passing[index] = core[index] and total >= threshold
                        lower[index] = upper[index] = passing[index]
                        unresolved[index] = False
                        exact_resolved += 1
            # Ranking-only rounding removes sub-ULP mathematical tie noise.
            # Qualification uses the unrounded computation/exact boundary result.
            matrix_scores.append(np.round(np.clip(score, 0, pattern["ceiling"]), 10))
            matrix_core.append(core)
            matrix_near.append(unresolved)
            matrix_lower.append(lower)
            matrix_upper.append(upper)
            matrix_nominal.append(passing)
        scores = np.column_stack(matrix_scores)
        gates = np.column_stack(matrix_core)
        # Exact rational pass flags are retained through lower==upper for linear variants.
        lower = np.column_stack(matrix_lower).any(axis=1)
        upper = np.column_stack(matrix_upper).any(axis=1)
        passed = np.column_stack(matrix_nominal).any(axis=1)
        any_core = gates.any(axis=1)
        selected = np.where(any_core, np.where(gates, scores, -np.inf).argmax(axis=1), scores.argmax(axis=1))
        representative = scores[np.arange(n), selected]
        support = next(p for p in weather["patterns"] if p["kind"] == "SUPPORT")
        floor = frac(support["ceiling"]) * (100 - weights["mode"]) / 100
        return {"passed": passed, "scores": representative, "has_core": any_core, "lower": lower, "upper": upper, "boundary_near_count": int(np.column_stack(matrix_near).any(axis=1).sum()), "unresolved_decision_count": int((lower != upper).sum()), "exact_boundary_rechecks": exact_resolved, "support_inside_min": floor, "weights": weights}

    scenarios = [{"id": "V2_BASELINE", "family": "baseline", "label": "V2 baseline"}]
    scenarios += [{"id": f"THRESHOLD_{t}", "family": "threshold", "threshold": t, "label": f"score threshold {t}"} for t in LIMITS if t != 75]
    scenarios += [{"id": f"CORE_{g}", "family": "core", "core_min": g, "label": f"core minimum {g}"} for g in [15, 25]]
    for code in codes:
        for name in WEIGHTS:
            for factor in ["0.9", "1.1"]:
                scenarios.append({"id": f"WEIGHT_{code}_{name}_{factor}", "family": "weight", "weather": code, "feature": name, "factor": factor, "label": f"{code} {name} relative weight x{factor}; normalize to100"})
        for name in FEATURES:
            for factor in ["0.9", "1.1"]:
                scenarios.append({"id": f"WIDTH_{code}_{name}_{factor}", "family": "width", "weather": code, "feature": name, "factor": factor, "label": f"{code} {name} both pattern widths x{factor}"})
    scenarios += [{"id": f"POWER_{p}", "family": "curve", "curve": "power", "curve_parameter": p, "label": f"F=100*(1-q)^{p}"} for p in [.5, 2]]
    scenarios += [{"id": f"EXP_{k}", "family": "curve", "curve": "exp", "curve_parameter": k, "label": f"normalized exp k={k}"} for k in [1, 2]]
    baseline = {code: evaluate_weather(code, scenarios[0]) for code in codes}
    base_top, baseline_checks = {}, {}
    for code in codes:
        stored = pd.read_csv(V2 / "pools" / f"{code}.csv")
        assert set(ids[baseline[code]["passed"]]) == set(stored.track_id)
        top, tie = rank_top(ids, baseline[code]["scores"], baseline[code]["passed"])
        assert ids[top].tolist() == stored.track_id.head(200).tolist()
        base_top[code] = set(ids[top])
        pos = pd.Index(ids).get_indexer(stored.track_id)
        assert np.allclose(baseline[code]["scores"][pos], stored.weather_score, atol=1e-10, rtol=0)
        assert int(examples[code].duration_ms.sum()) == 10800000 and examples[code].track_id.is_unique
        baseline_checks[code] = {"pool_ids_exact_match": True, "pool_count": len(stored), "top200_id_order_exact_match": True, "scores_match_saved_v2": True, "example_exact_180min_unique_and_in_baseline_pool": bool(examples[code].track_id.isin(stored.track_id).all()), "top200_ties": tie}
    rows, overview, detailed = [], [], []
    baseline_matrix = np.column_stack([baseline[c]["passed"] for c in codes])
    flip_count, any_changed_count = np.zeros(n, int), np.zeros(n, int)
    for number, scenario in enumerate(scenarios):
        outputs = baseline if number == 0 else {code: evaluate_weather(code, scenario) for code in codes}
        mat = np.column_stack([outputs[c]["passed"] for c in codes])
        lower_mat = np.column_stack([outputs[c]["lower"] for c in codes])
        upper_mat = np.column_stack([outputs[c]["upper"] for c in codes])
        changed = mat != baseline_matrix
        if number:
            flip_count += changed.sum(axis=1)
            any_changed_count += changed.any(axis=1)
        distribution = {str(k): int((mat.sum(axis=1) == k).sum()) for k in range(6)}
        domain_ok = all(out["support_inside_min"] >= scenario.get("threshold", 75) and scenario.get("core_min", 20) <= 100 for out in outputs.values())
        floor = min(out["support_inside_min"] for out in outputs.values())
        overall = {"scenario_id": scenario["id"], "family": scenario["family"], "description": scenario["label"], "union_count": int(mat.any(axis=1).sum()), "unmatched_count": distribution["0"], "union_count_lower_numeric_bound": int(lower_mat.any(axis=1).sum()), "union_count_upper_numeric_bound": int(upper_mat.any(axis=1).sum()), "passing_weather_count_distribution": distribution, "support_domain_min_score": float(floor), "support_domain_min_score_exact": str(floor), "full_cube_coverage_proved": domain_ok, "automatic_assignment_or_flooring": False, "weather_pass_flips": int(changed.sum()), "tracks_any_weather_changed": int(changed.any(axis=1).sum()), "numeric_method": "FLOAT_NONLINEAR_WITH_BOUNDARY_INTERVAL" if scenario["family"] == "curve" else "FRACTION_BASELINE_AND_RATIONAL_BOUNDARY_RECHECK", "unresolved_boundary_decisions_weather_sum": sum(o["unresolved_decision_count"] for o in outputs.values())}
        overview.append(overall)
        weather_results = {}
        for code in codes:
            out, old = outputs[code], baseline[code]
            new_mask, old_mask = out["passed"], old["passed"]
            either = new_mask | old_mask
            top, ties = rank_top(ids, out["scores"], new_mask)
            top_set = set(ids[top])
            ex_pos = example_positions[code]
            item = {"scenario_id": scenario["id"], "family": scenario["family"], "weather": code, "pool_count": int(new_mask.sum()), "baseline_count": int(old_mask.sum()), "added": int((new_mask & ~old_mask).sum()), "removed": int((old_mask & ~new_mask).sum()), "jaccard_vs_v2": float((new_mask & old_mask).sum() / either.sum()) if either.any() else 1, "top200_retained_count": len(top_set & base_top[code]), "top200_retention": len(top_set & base_top[code]) / len(base_top[code]) if base_top[code] else 1, **ties, "near_boundary_unresolved_count": out["boundary_near_count"], "ambiguous_pass_decision_count": out["unresolved_decision_count"], "exact_boundary_rechecks": out["exact_boundary_rechecks"], "existing_180min_example_tracks": len(ex_pos), "existing_example_still_eligible": int(new_mask[ex_pos].sum()), "existing_example_all_tracks_still_eligible": bool(new_mask[ex_pos].all()), "pool_count_lower_numeric_bound": int(out["lower"].sum()), "pool_count_upper_numeric_bound": int(out["upper"].sum()), "support_inside_min_score": float(out["support_inside_min"])}
            rows.append(item)
            weather_results[code] = item
        detailed.append({"configuration": scenario, "overview": overall, "weather": weather_results})
        if number % 10 == 0:
            print(json.dumps({"scenario": number + 1, "total": len(scenarios), "id": scenario["id"], "unmatched": distribution["0"]}), flush=True)
    margin = np.min(np.column_stack([np.where(baseline[c]["has_core"], np.abs(baseline[c]["scores"] - 75), np.inf) for c in codes]), axis=1)
    flags = pd.DataFrame({"track_id": ids, "scenario_pass_flip_count": flip_count, "any_weather_changed_count": any_changed_count, "baseline_min_abs_score_margin_to75": margin})
    flags.sort_values(["any_weather_changed_count", "scenario_pass_flip_count", "baseline_min_abs_score_margin_to75", "track_id"], ascending=[False, False, True, True]).to_csv(HERE / "pertrack_sensitivity_flags.csv", index=False, encoding="utf-8-sig", float_format="%.12g")
    frame = pd.DataFrame(rows)
    frame.to_csv(HERE / "sensitivity_scenarios.csv", index=False, encoding="utf-8-sig", float_format="%.12g")
    pd.DataFrame([{k: v for k, v in r.items() if k != "passing_weather_count_distribution"} for r in overview]).to_csv(HERE / "sensitivity_scenario_overview.csv", index=False, encoding="utf-8-sig", float_format="%.12g")
    after = snapshot()
    assert before == after, "Baseline V2 inputs/outputs changed during diagnostics"
    result = {"analysis_version": "SENSITIVITY_DIAGNOSTICS_20261016_V1", "status": "PARAMETER_STABILITY_NOT_LISTENING_QUALITY", "source": {"path": str(source), "sha256": digest(source), "base_count": n, "raw_unique_count": baseline_summary["source"]["unique_track_ids"], "baseline_policy_version": policy["policy_version"], "baseline_artifact_hashes": before}, "assumptions": {"one_at_a_time": True, "full_factorial": False, "weight_change": "One weather and one weight multiplied relatively by0.9/1.1; all4 weights then normalized to100; applies to both patterns", "width_change": "One weather and one continuous feature width multiplied by0.9/1.1 in both patterns", "power_formula": "F=100*(1-q)^p; p0.5 gentler, p2 steeper; q=min(1,d/h)", "exp_formula": "F=100*(exp(-k*q)-exp(-k))/(1-exp(-k))", "mode_curve": "Binary mode match100 else0 unchanged", "nonlinear_numeric_tolerance": EPS, "nonlinear_ambiguity": "Boundary interval lower/upper results are reported; terminal0/100 components, integer power and rational square-root identities are exactly rechecked where available; remaining transcendental/irrational comparisons are float diagnostics", "rational_numeric_method": "Exact Fraction V2 baseline and exact recomposition of every threshold/core-near rational scenario row; non-boundary rows use float with1e-8 diagnostic margin", "ranking": "For perturbed float calculations scores rounded to10 decimals for ranking only, ID asc tie; qualification is evaluated before ranking rounding; top200 retention depends on deterministic ID tie order, not unique optimum", "no_listening_labels": True, "no_quality_or_causal_inference": True, "no_new_scenario_3h_csv": True}, "baseline_checks": baseline_checks, "baseline_artifacts_unchanged": before == after, "scenario_count_including_baseline": len(scenarios), "scenarios": detailed, "pertrack_flags": {"path": "pertrack_sensitivity_flags.csv", "row_count": n, "scenario_pass_flip_count": "Sum of weather-level pass/fail flips across all nonbaseline scenarios; may exceed scenario count", "any_weather_changed_count": "Number of nonbaseline scenarios changing at least1 weather decision", "baseline_min_abs_score_margin_to75": "Minimum over weather representatives with a core-passing pattern; diagnostic raw maxima without core are excluded", "interpretation": "Review prioritization only; not an error label, recommendation failure label or listening ground truth", "tracks_with_any_flip": int((any_changed_count > 0).sum()), "maximum_any_changed_count": int(any_changed_count.max())}}
    (HERE / "sensitivity_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    plot(frame, overview)
    print(json.dumps({"completed": True, "scenarios": len(scenarios), "baseline": baseline_checks, "coverage_failures": [r for r in overview if r["unmatched_count"]], "pertrack": result["pertrack_flags"]}, ensure_ascii=False), flush=True)


def plot(frame, overview):
    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "figure.dpi": 150})
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4), layout="constrained")
    selected = [r for r in overview if r["family"] in {"baseline", "threshold"}]
    selected.sort(key=lambda r: 75 if r["family"] == "baseline" else int(r["scenario_id"].split("_")[-1]))
    ax[0].bar([75 if r["family"] == "baseline" else int(r["scenario_id"].split("_")[-1]) for r in selected], [r["unmatched_count"] for r in selected], color="#176B87", width=.65)
    ax[0].set(title="점수 하한 변화와 미매칭 곡", xlabel="점수 하한", ylabel="5개 날씨 모두 미통과 곡 수", xticks=[74,75,76,77,80])
    curves = frame.loc[frame.family.eq("curve")].pivot(index="scenario_id", columns="weather", values="jaccard_vs_v2").reindex(columns=["CLEAR","CLOUDY","OVERCAST","RAIN","SNOW"])
    im = ax[1].imshow(curves, vmin=0, vmax=1, cmap="YlGnBu", aspect="auto")
    ax[1].set(title="감점 곡선 변경: V2 후보와의 Jaccard", xticks=range(5), xticklabels=["맑음","구름낌","흐림","비","눈"], yticks=range(len(curves)), yticklabels=curves.index)
    for i in range(len(curves)):
        for j in range(5):
            ax[1].text(j,i,f"{curves.iloc[i,j]:.3f}",ha="center",va="center",color="white" if curves.iloc[i,j]>.6 else "black",fontsize=9)
    fig.colorbar(im, ax=ax[1], shrink=.8)
    fig.suptitle("V2 민감도 진단 · 기본 유효곡 61,931개 · 청취 품질 검증 아님", fontsize=12)
    fig.savefig(HERE / "sensitivity_overview.png")
    plt.close(fig)


if __name__ == "__main__":
    run()
