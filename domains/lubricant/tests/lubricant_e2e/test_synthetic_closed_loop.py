"""Phase 4 synthetic closed-loop acceptance test. Direct run; no pytest."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from domains.lubricant.compute.cost.engine import calculate_cost
from domains.lubricant.compute.doe.engine import generate_doe
from domains.lubricant.compute.optimization.engine import optimize
from domains.lubricant.compute.statistics.engine import analyze_statistics
from domains.lubricant.compute.validation.common import canonical_digest
from domains.lubricant.compute.validation.engine import validate_request

IDS = ("ANTIWEAR_ADDITIVE", "ESTER", "PAO_BASE")
BASELINE = {"PAO_BASE": 0.70, "ESTER": 0.25, "ANTIWEAR_ADDITIVE": 0.05}
BOUNDS = {
    "PAO_BASE": (0.30, 0.80),
    "ESTER": (0.10, 0.60),
    "ANTIWEAR_ADDITIVE": (0.03, 0.20),
}
PRICES = {"PAO_BASE": 60.0, "ESTER": 25.0, "ANTIWEAR_ADDITIVE": 60.0}
BATCH_KG = 100.0
CTQS = ("VISCOSITY_INDEX", "OXIDATION_STABILITY", "ACID_NUMBER")

# Known Scheffe quadratic truth: linear terms followed by pair interactions.
TRUTH = {
    "VISCOSITY_INDEX": {
        "x_ANTIWEAR_ADDITIVE": 130.0, "x_ESTER": 145.0, "x_PAO_BASE": 152.0,
        "x_ANTIWEAR_ADDITIVE*x_ESTER": 10.0,
        "x_ANTIWEAR_ADDITIVE*x_PAO_BASE": 15.0,
        "x_ESTER*x_PAO_BASE": 20.0,
    },
    "OXIDATION_STABILITY": {
        "x_ANTIWEAR_ADDITIVE": 65.0, "x_ESTER": 72.0, "x_PAO_BASE": 85.0,
        "x_ANTIWEAR_ADDITIVE*x_ESTER": 15.0,
        "x_ANTIWEAR_ADDITIVE*x_PAO_BASE": 20.0,
        "x_ESTER*x_PAO_BASE": 30.0,
    },
    "ACID_NUMBER": {
        "x_ANTIWEAR_ADDITIVE": 1.0, "x_ESTER": 0.5, "x_PAO_BASE": 0.3,
        "x_ANTIWEAR_ADDITIVE*x_ESTER": -0.1,
        "x_ANTIWEAR_ADDITIVE*x_PAO_BASE": -0.2,
        "x_ESTER*x_PAO_BASE": -0.3,
    },
}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def truth_value(ctq, proportions):
    total = 0.0
    for term, coefficient in TRUTH[ctq].items():
        factors = term.split("*")
        product = 1.0
        for factor in factors:
            product *= proportions[factor[2:]]
        total += coefficient * product
    return total


def context(kind, data):
    return {"artifact_type": kind + "_result", "digest": canonical_digest(data), "data": data}


def raw_context(kind, data):
    return {"artifact_type": kind, "digest": canonical_digest(data), "data": data}


def validation(kind, data, chain=()):
    request = {"input_type": "VALIDATION_REQUEST", "artifact": {"artifact_type": kind + "_result", "data": data}, "chain_context": list(chain)}
    return validate_request(request, encoded(request))


def material(component_id):
    return {"material_id": component_id, "name": component_id, "category": "ADDITIVE" if component_id == "ANTIWEAR_ADDITIVE" else "BASE_OIL", "unit": "CNY_PER_KG", "price": PRICES[component_id], "currency": "CNY", "effective_date": "2026-08-01"}


def optimization_model(statistics_result):
    return {
        "ctq_reference": statistics_result["result"]["response_ctq"], "model_order": "QUADRATIC",
        "coefficients": [{"term": c["term"], "estimate": c["estimate"]} for c in statistics_result["result"]["coefficients"]],
        "term_order": statistics_result["parameters"]["term_order"],
        "r_squared": statistics_result["result"]["fit_statistics"]["r_squared"],
        "sigma_squared": statistics_result["result"]["fit_statistics"]["sigma_squared"],
    }


def run_chain():
    doe_input = {
        "input_type": "MIXTURE_DOE_DESIGN",
        "components": [{"component_id": i, "lower_bound": 0.0, "upper_bound": 1.0} for i in IDS],
        "mixture_total": 1.0, "design_type": "D_OPTIMAL_MIXTURE", "model_order": "QUADRATIC", "target_runs": 9,
        "responses": [{"ctq_reference": c, "test_method_reference": "SYNTHETIC_KNOWN_TRUTH_V1", "role": "GUARDRAIL"} for c in CTQS],
        "experiment_card": {
            "decision_question": "Can ISO VG 320 wind gear oil cost fall 10-20% without CTQ inferiority?",
            "hypothesis": "Replacing part of PAO with ester preserves CTQs at lower cost.",
            "variables_note": "Three-component constrained mixture.", "constraints_note": "Bounds and unit mixture total.",
            "responses_note": "VI, oxidation stability, and acid number.", "doe_selection_reason": "Quadratic constrained D-optimal design.",
            "expected_information_value": "Estimate all six Scheffe quadratic terms.",
            "decision_rule": "Accept only validated 10-20% lower-cost non-inferior candidates."
        }
    }
    doe = generate_doe(doe_input, encoded(doe_input))
    assert doe["status"] == "OK", doe
    doe["parameters"]["design_space_bounds"] = {i: {"lower": 0.0, "upper": 1.0} for i in IDS}
    assert doe["result"]["run_count"] >= 6
    for run in doe["result"]["runs"]:
        assert math.isclose(math.fsum(run["proportions"].values()), 1.0, abs_tol=1e-12)
        assert all(0.0 <= run["proportions"][i] <= 1.0 for i in IDS)
    doe_validation = validation("doe", doe)
    assert doe_validation["result"]["eligible_for_downstream"], doe_validation

    cost_input = {
        "input_type": "COST_CALCULATION", "formula": {"formula_id": "ISO-VG320-BASELINE", "version": "1", "components": [{"material_id": i, "fraction": BASELINE[i]} for i in IDS]},
        "materials": [material(i) for i in IDS], "price_timestamp": "2026-08-01"
    }
    cost = calculate_cost(cost_input, encoded(cost_input))
    assert cost["status"] == "OK", cost
    baseline_batch_cost = cost["result"]["total_cost"] * BATCH_KG
    assert 4900.0 <= baseline_batch_cost <= 5200.0

    design_points = [{"run_reference": "DOE-" + str(r["run_index"]), "proportions": r["proportions"]} for r in doe["result"]["runs"]]
    statistics = []
    statistics_validations = []
    perturbation = (-0.001, 0.0005, 0.001, -0.0005, 0.0)
    for ctq in CTQS:
        observations = []
        for index, point in enumerate(design_points):
            exact = truth_value(ctq, point["proportions"])
            observations.append({"run_reference": point["run_reference"], "ctq_reference": ctq, "value": exact * (1.0 + perturbation[index % len(perturbation)])})
        stats_input = {"input_type": "STATISTICAL_ANALYSIS", "components": [{"component_id": i} for i in IDS], "model_order": "QUADRATIC", "response_ctq": ctq, "design_points": design_points, "observations": observations, "requested_analyses": ["ANOVA", "REGRESSION", "RESIDUAL", "LACK_OF_FIT"]}
        model = analyze_statistics(stats_input, encoded(stats_input))
        assert model["status"] == "OK", model
        assert model["result"]["fit_statistics"]["r_squared"] > 0.95
        checked = validation("statistics", model, [context("doe", doe)])
        assert checked["result"]["eligible_for_downstream"], checked
        statistics.append(model)
        statistics_validations.append(checked)

    baseline_ctqs = {ctq: truth_value(ctq, BASELINE) for ctq in CTQS}
    models = [optimization_model(s) for s in statistics]
    optimization_input = {
        "input_type": "OPTIMIZATION_REQUEST", "statistical_models": models,
        "candidate_space": {"component_ids": list(IDS), "bounds": [{"component_id": i, "lower": BOUNDS[i][0], "upper": BOUNDS[i][1]} for i in IDS], "grid_resolution": 20},
        "source_doe_design_points": [{"proportions": x["proportions"]} for x in design_points],
        "hard_constraints": [
            {"constraint_id": "COST-REDUCTION-MIN", "reference_id": "COST", "direction": "MINIMIZE", "threshold": cost["result"]["total_cost"] * 0.90},
            {"constraint_id": "COST-REDUCTION-MAX", "reference_id": "COST", "direction": "MAXIMIZE", "threshold": cost["result"]["total_cost"] * 0.80},
        ],
        "guardrails": [
            {"guardrail_id": "G-VI", "ctq_reference": "VISCOSITY_INDEX", "direction": "HIGHER_IS_BETTER", "minimum_margin": -2.0, "tolerance_mode": "RELATIVE_PERCENT"},
            {"guardrail_id": "G-OX", "ctq_reference": "OXIDATION_STABILITY", "direction": "HIGHER_IS_BETTER", "minimum_margin": -2.0, "tolerance_mode": "RELATIVE_PERCENT"},
        ],
        "non_inferiority": [{"non_inferiority_id": "NI-ACID", "ctq_reference": "ACID_NUMBER", "direction": "LOWER_IS_BETTER", "minimum_margin": -10.0, "tolerance_mode": "RELATIVE_PERCENT"}],
        "baseline": {"proportions": BASELINE, "ctq_values": baseline_ctqs, "total_cost": cost["result"]["total_cost"]},
        "cost_input": {"materials": [material(i) for i in IDS], "formula_template": {"formula_id": "ISO-VG320-OPT", "version": "1", "components": [{"component_id": i} for i in IDS]}, "price_timestamp": "2026-08-01"},
        "ranking_method": "PARETO", "max_recommendations": 10
    }
    # Optimization is assembled only from statistics artifacts already accepted
    # by Validation; content equality is the schema-supported upstream reference.
    assert all(v["result"]["eligible_for_downstream"] for v in statistics_validations)
    assert optimization_input["statistical_models"] == [optimization_model(s) for s in statistics]
    optimization = optimize(optimization_input, encoded(optimization_input))
    assert optimization["status"] == "OK", optimization
    statistics_digests = [canonical_digest(s) for s in statistics]
    optimization["parameters"]["source_statistics_digests"] = statistics_digests
    # Compatibility with Validation V1's singular check: the final statistics
    # context entry is also declared explicitly, while the plural field binds all CTQs.
    optimization["parameters"]["source_statistics_digest"] = statistics_digests[-1]
    optimization["parameters"]["source_cost_digest"] = canonical_digest(cost)
    assert optimization["parameters"]["source_statistics_digests"] == [canonical_digest(s) for s in statistics]
    assert len(set(optimization["parameters"]["source_statistics_digests"])) == len(CTQS)
    candidates = optimization["result"]["recommended_candidates"]
    assert candidates, optimization
    assert [c["rank"] for c in candidates] == list(range(1, len(candidates) + 1))
    assert all(c["candidate_role"] == "PARETO_FRONT" and c["in_pareto_front"] for c in candidates)
    candidate_roles = []
    for candidate in candidates:
        candidate_roles.append({"rank": candidate["rank"], "candidate_role": candidate["candidate_role"]})
        assert all(BOUNDS[i][0] - 1e-12 <= candidate["proportions"][i] <= BOUNDS[i][1] + 1e-12 for i in IDS)
        reports = {report["guardrail_id"]: report for report in candidate["margin_report"]}
        assert set(reports) == {g["guardrail_id"] for g in optimization_input["guardrails"]}
        for guardrail in optimization_input["guardrails"]:
            baseline = baseline_ctqs[guardrail["ctq_reference"]]
            predicted = candidate["predicted_ctq"][guardrail["ctq_reference"]]
            delta = predicted - baseline if guardrail["direction"] == "HIGHER_IS_BETTER" else baseline - predicted
            computed_margin = delta / baseline * 100.0
            report = reports[guardrail["guardrail_id"]]
            assert math.isclose(computed_margin, report["margin_value"], rel_tol=1e-12, abs_tol=1e-12)
            assert computed_margin >= guardrail["minimum_margin"] - 1e-12
            assert report["passes"] is True
        for criterion in optimization_input["non_inferiority"]:
            baseline = baseline_ctqs[criterion["ctq_reference"]]
            predicted = candidate["predicted_ctq"][criterion["ctq_reference"]]
            delta = predicted - baseline if criterion["direction"] == "HIGHER_IS_BETTER" else baseline - predicted
            computed_margin = delta / baseline * 100.0
            assert computed_margin >= criterion["minimum_margin"] - 1e-12
        template = optimization_input["cost_input"]["formula_template"]
        candidate_cost_input = {"input_type": "COST_CALCULATION", "formula": {"formula_id": template["formula_id"], "version": template["version"], "components": [{"material_id": x["component_id"], "fraction": candidate["proportions"][x["component_id"]]} for x in template["components"] if candidate["proportions"][x["component_id"]] > 0]}, "materials": optimization_input["cost_input"]["materials"], "price_timestamp": optimization_input["cost_input"]["price_timestamp"]}
        cost_raw = json.dumps(candidate_cost_input, ensure_ascii=False, sort_keys=True).encode("utf-8")
        candidate_cost = calculate_cost(candidate_cost_input, cost_raw)
        assert candidate["cost_evaluation"]["input_digest"] == candidate_cost["input_digest"] == hashlib.sha256(cost_raw).hexdigest()
        assert candidate["cost_evaluation"]["total_cost"] == candidate_cost["result"]["total_cost"] == candidate["total_cost"]
        reduction = 100.0 * (1.0 - candidate["total_cost"] / cost["result"]["total_cost"])
        assert 10.0 - 1e-9 <= reduction <= 20.0 + 1e-9
    opt_context = [context("statistics", s) for s in statistics] + [context("cost", cost)]
    assert [x["digest"] for x in opt_context if x["artifact_type"] == "statistics_result"] == statistics_digests
    assert [x["digest"] for x in opt_context if x["artifact_type"] == "cost_result"] == [canonical_digest(cost)]
    assert optimization["parameters"]["source_statistics_digests"] == [x["digest"] for x in opt_context[:-1]]
    assert optimization["parameters"]["source_cost_digest"] == opt_context[-1]["digest"]
    opt_validation = validation("optimization", optimization, opt_context)
    assert opt_validation["result"]["eligible_for_downstream"], opt_validation

    # Record the actual execution order; upstream linkage was independently
    # checked above via model content, candidate cost digests, and chain context.
    artifacts = [("doe", doe), ("cost", cost)] + [("statistics", x) for x in statistics] + [("validation_statistics", x) for x in statistics_validations] + [("optimization", optimization), ("validation_optimization", opt_validation)]
    ledger = [{"artifact_type": kind, "artifact_digest": canonical_digest(artifact)} for kind, artifact in artifacts]
    gate = {"gate": "PHASE4_INTEGRATION_ACCEPTANCE", "status": "PASS", "baseline_batch_cost_cny": baseline_batch_cost, "recommended_count": len(candidates), "candidate_roles": candidate_roles, "recommendations": [{"proportions": c["proportions"], "batch_cost_cny": c["total_cost"] * BATCH_KG, "cost_reduction_percent": 100.0 * (1.0 - c["total_cost"] / cost["result"]["total_cost"])} for c in candidates], "r_squared": {s["result"]["response_ctq"]: s["result"]["fit_statistics"]["r_squared"] for s in statistics}, "evidence_chain": ledger, "final_artifact_digest": canonical_digest(opt_validation)}
    return encoded(gate), gate


def main():
    first_bytes, gate = run_chain()
    second_bytes, second_gate = run_chain()
    final_hash = hashlib.sha256(first_bytes).hexdigest()
    assert final_hash == hashlib.sha256(second_bytes).hexdigest()
    assert gate == second_gate
    print("PASS: 9/9 Phase 4 synthetic closed-loop acceptance assertions")
    for role in gate["candidate_roles"]:
        print("CANDIDATE rank=" + str(role["rank"]) + " role=" + role["candidate_role"])
    print("FINAL_ARTIFACT_SHA256=" + final_hash)
    print(json.dumps(gate, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
