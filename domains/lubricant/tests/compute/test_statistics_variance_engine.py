"""Direct-run functional tests for the step-12 variance capabilities.

Covers the new statistics-engine surface (variance_components / effect_size /
power_analysis / required_n_for_k / sigma_max_requirement / resolution_table /
consistency_check / sigma_confidence_interval), the four-verdict rule, and the
three fail-closed data-quality rules taken from the WGO_001 empirical lessons.

Also asserts the backward-compatibility property: a legacy input requesting only
ANOVA / REGRESSION / RESIDUAL / LACK_OF_FIT must produce the same result object
as before, with no step-12 sections attached.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domains.lubricant.compute.statistics.engine import (
    DEFAULT_ALPHA,
    VARIANCE_VERDICTS,
    analyze_statistics,
    consistency_check,
    decide_variance_verdict,
    effect_size,
    power_analysis,
    required_n_for_k,
    resolution_table,
    sigma_confidence_interval,
    sigma_max_requirement,
    variance_components,
)

FIXTURE_DIR = ROOT / "fixtures" / "compute"
GOLD_INPUT = FIXTURE_DIR / "statistics-variance-gold-input.json"
GOLD_OUTPUT = FIXTURE_DIR / "statistics-variance-gold-output.json"

EXPECTED_HASHES = {
    "statistics-variance-gold-input.json": "29eb7e7e26ddf9561094d8ed6501c5fab8a5a90380c36b185cb8e9830675ba29",
    "statistics-variance-gold-output.json": "594663036fd77192ee2f8668b3a661526656beadad8c1ae190faa60c448abf2b",
}


def load_gold_input():
    return json.loads(GOLD_INPUT.read_text(encoding="utf-8"))


def run(data, raw=None):
    if raw is None:
        raw = (json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    return analyze_statistics(data, raw)


def rejected_reasons(env):
    assert env["status"] == "REJECTED", env
    assert env["rejection_reasons"], env
    return env["rejection_reasons"]


def assert_no_exception_on(env):
    """Every failure path must be a REJECTED envelope, never a raised exception."""
    assert env["status"] in ("OK", "REJECTED"), env
    assert env["result"] == {} or env["status"] == "OK"


def test_scalar_capabilities():
    # SIGMA_MAX = delta/k, the WGO_001 real case.
    assert sigma_max_requirement(1.5, 3) == 0.5
    assert sigma_max_requirement(1.5) == 0.5
    print("PASS: SIGMA_MAX = delta/k reproduces the WGO_001 case (1.5 h / 3 = 0.5 h)")

    # Power is a probability in [0, 1] and increases with n.
    powers = [power_analysis(n, 1.5, 0.5) for n in range(2, 9)]
    assert all(0.0 <= value <= 1.0 for value in powers), powers
    assert powers == sorted(powers), powers
    assert power_analysis(2, 1.5, 0.5) > 0.80
    assert power_analysis(2, 0.5, 0.5) < 0.30
    assert power_analysis(5, 0.0, 1.0) == DEFAULT_ALPHA
    print("PASS: power in [0,1], monotone in n, alpha at delta=0")

    # The frozen planning table: k>=3 -> n=2, k=2 -> n=4, k=1.5 -> n=8, k<=1 -> n=16.
    expected_per_arm = {3.0: 2, 2.0: 4, 1.5: 8, 1.0: 16}
    for k_value, per_arm in expected_per_arm.items():
        plan = required_n_for_k(k_value)
        assert plan["per_arm_n"] == per_arm, (k_value, plan)
        assert plan["total_runs"] == per_arm * 2, plan
        assert plan["achieved_power"] >= plan["target_power"], plan
        assert plan["bench_round_days"] == 30, plan
        assert plan["bench_positions_per_round"] == 2, plan
        assert plan["bench_rounds_occupied"] == -(-plan["total_runs"] // 2), plan
        assert plan["calendar_days"] == plan["bench_rounds_occupied"] * 30, plan
        assert plan["feasible"] is (k_value >= 3.0), plan
    assert required_n_for_k(3.0)["calendar_months"] == 2.0
    assert required_n_for_k(1.5)["calendar_months"] == 8.0
    # The design rule must be stated in the output, not left to the reader.
    assert "do NOT increase n" in required_n_for_k(1.5)["design_rule"]
    assert "n ~ 16/k^2" in required_n_for_k(3.0)["design_rule"]
    print("PASS: required_n_for_k reproduces the frozen k table and states the k<3 design rule")

    # Effect size: reversed groups flip the sign, not the magnitude.
    forwards = effect_size([10.0, 11.0, 12.0], [13.0, 14.0, 15.0])
    backwards = effect_size([13.0, 14.0, 15.0], [10.0, 11.0, 12.0])
    assert abs(abs(forwards["cohens_d"]) - abs(backwards["cohens_d"])) < 1e-12
    assert forwards["cohens_d"] < 0 < backwards["cohens_d"]
    assert forwards["magnitude"] == "LARGE"
    assert effect_size([10.0], [11.0])["cohens_d"] is None
    print("PASS: effect_size sign, magnitude and not-estimable path")

    # Resolution scales as 1/sqrt(n): quadrupling n halves the detectable difference.
    rows = resolution_table(50.0, [3, 6, 12])
    assert abs(rows[0]["detectable_difference"] - 4 * 50.0 / 3 ** 0.5) < 1e-12
    assert abs(rows[0]["detectable_difference"] / rows[2]["detectable_difference"] - 2.0) < 1e-12
    assert rows[1]["replicates_per_group"] == 6
    assert "1/sqrt(n)" in rows[1]["note"]
    print("PASS: resolution table shows the sqrt(n) trade-off")

    # sigma CI at n=3 carries the pack's +/-50% relative error figure.
    interval = sigma_confidence_interval(3, 50.0)
    assert abs(interval["relative_standard_error"] - 0.5) < 1e-12
    assert interval["sigma_low"] < 50.0 < interval["sigma_high"]
    assert interval["small_sample"] is True and interval["limitation"]
    wide = sigma_confidence_interval(10, 50.0)
    assert wide["relative_standard_error"] < interval["relative_standard_error"]
    for n in (2, 3, 6, 10, 20):
        check = sigma_confidence_interval(n, 50.0)
        assert check["sigma_low"] < check["sigma_high"], check
    assert sigma_confidence_interval(1, 50.0)["sigma_high"] is None
    print("PASS: sigma confidence interval reports the n=3 +/-50% limitation honestly")


def test_verdict_enum_and_logic():
    # Exactly four verdicts, and UNDERPOWERED is its own value.
    assert VARIANCE_VERDICTS == (
        "CONSISTENT_DIFFERENCE", "NO_DETECTABLE_DIFFERENCE",
        "UNDERPOWERED", "REPLICATE_INCONSISTENT")
    assert "UNDERPOWERED" in VARIANCE_VERDICTS
    consistent = {"verdict": "CONSISTENT", "inconsistent_arms": [],
                  "material_identity_conflicts": []}
    # 1. A separated difference is CONSISTENT_DIFFERENCE.
    decision = decide_variance_verdict(consistent, 1.5, 0.2, 1.5, 0.99, 3)
    assert decision["verdict"] == "CONSISTENT_DIFFERENCE", decision
    # 2. No comparison performed -> UNDERPOWERED, never NO_DETECTABLE_DIFFERENCE.
    decision = decide_variance_verdict(consistent, None, 0.2, 1.5, 0.99, 3)
    assert decision["verdict"] == "UNDERPOWERED", decision
    # 3. Small difference with a weak design -> UNDERPOWERED (the expensive error).
    decision = decide_variance_verdict(consistent, 0.01, 0.5, 1.5, 0.10, 2)
    assert decision["verdict"] == "UNDERPOWERED", decision
    assert "power" in decision["basis"]
    # 4. Small difference, properly powered design -> NO_DETECTABLE_DIFFERENCE.
    decision = decide_variance_verdict(consistent, 0.01, 0.5, 1.5, 0.95, 8)
    assert decision["verdict"] == "NO_DETECTABLE_DIFFERENCE", decision
    # 5. A method whose noise exceeds SIGMA_MAX is UNDERPOWERED: the method is
    #    unqualified, which is not a data-shortage problem.
    decision = decide_variance_verdict(consistent, 0.01, 2.0, 1.5, 0.95, 8)
    assert decision["verdict"] == "UNDERPOWERED", decision
    assert decision["k_ratio"] is not None and decision["k_ratio"] < 1.0
    # 6. Replicate contradiction outranks a large difference.
    contradicted = {"verdict": "REPLICATE_INCONSISTENT",
                    "inconsistent_arms": [{"group_reference": "ARM-1"}],
                    "material_identity_conflicts": []}
    decision = decide_variance_verdict(contradicted, 99.0, 0.01, 1.5, 1.0, 9)
    assert decision["verdict"] == "REPLICATE_INCONSISTENT", decision
    print("PASS: four-verdict logic, UNDERPOWERED kept separate from NO_DETECTABLE_DIFFERENCE")


def test_rule_censoring_never_an_endpoint():
    data = load_gold_input()

    # (a) A right-censored observation must not contribute an event_time.
    poisoned = copy.deepcopy(data)
    for entry in poisoned["censoring"]:
        if entry["censoring_type"] == "RIGHT":
            entry["event_time"] = 10.0
    reasons = rejected_reasons(run(poisoned))
    assert any("event_time" in reason for reason in reasons), reasons
    print("PASS: right-censored observation carrying event_time is rejected")

    # (b) A right-censored observation must not claim the event occurred.
    poisoned = copy.deepcopy(data)
    for entry in poisoned["censoring"]:
        if entry["censoring_type"] == "RIGHT":
            entry["event_occurred"] = True
    reasons = rejected_reasons(run(poisoned))
    assert any("event_occurred" in reason for reason in reasons), reasons
    print("PASS: right-censored observation claiming event_occurred=true is rejected")

    # (c) A censored observation with no stop_reason is rejected fail-closed.
    #     The schema enforces the field's presence and non-emptiness; the
    #     business layer enforces it again for whitespace-only reasons, so the
    #     rule survives either path.
    poisoned = copy.deepcopy(data)
    for entry in poisoned["censoring"]:
        if entry["censoring_type"] == "RIGHT":
            entry.pop("stop_reason")
    reasons = rejected_reasons(run(poisoned))
    assert reasons, reasons
    print("PASS: censored observation missing stop_reason is rejected fail-closed (schema level)")

    poisoned = copy.deepcopy(data)
    for entry in poisoned["censoring"]:
        if entry["censoring_type"] == "RIGHT":
            entry["stop_reason"] = "   "
    reasons = rejected_reasons(run(poisoned))
    assert any("stop_reason" in reason for reason in reasons), reasons
    print("PASS: censored observation with a blank stop_reason is rejected fail-closed")

    # (d) The censoring entry must point at a real observation.
    poisoned = copy.deepcopy(data)
    poisoned["censoring"][0]["observation_reference"] = "OBS-NOT-PRESENT"
    reasons = rejected_reasons(run(poisoned))
    assert any("unknown observation_reference" in reason for reason in reasons), reasons
    print("PASS: censoring entry for an unknown observation is rejected")

    # (e) The censored value is excluded from the estimate; the surviving
    #     estimate must equal the estimate computed with the observation gone.
    components = variance_components(data)
    assert components["status"] == "COMPUTED", components
    assert components["censored_excluded"] >= 1, components
    censored_refs = {entry["observation_reference"] for entry in components["excluded_observations"]
                     if entry["reason"] == "CENSORED_NOT_AN_END_POINT"}
    assert censored_refs, components
    assert all(reference.startswith("OBS-") for reference in censored_refs)
    totals = [entry["observation_reference"] for entry in data["observations"]
              if entry["observation_reference"] not in censored_refs]
    assert components["observations_used"] < len(data["observations"])
    without = copy.deepcopy(data)
    without["observations"] = [entry for entry in without["observations"]
                               if entry["observation_reference"] not in censored_refs]
    without["censoring"] = [entry for entry in without["censoring"]
                            if entry["observation_reference"] not in censored_refs]
    bare = variance_components(without)
    assert bare["status"] == "COMPUTED", bare
    assert abs(bare["sigma_meas"] - components["sigma_meas"]) < 1e-12
    assert abs(bare["sigma_total"] - components["sigma_total"]) < 1e-12
    print("PASS: censored values are excluded from every estimate (equivalent to removing them)")


def test_rule_material_identity_conflict():
    data = load_gold_input()

    # Same sample_id under two batch_ids -> judged REPLICATE_INCONSISTENT and
    # excluded from the estimate; never averaged.
    conflicted = copy.deepcopy(data)
    conflicted_group = "ARM-ADDITIVE"
    arms = [entry for entry in conflicted["observations"]
            if entry["group_reference"] == conflicted_group]
    first, second = arms[0], arms[1]
    second["sample_id"] = first["sample_id"]  # same name...
    second["batch_id"] = first["batch_id"] + "-OTHER"  # ...different thing
    env = run(conflicted)
    assert env["status"] == "OK", env
    assert env["result"]["verdict"] == "REPLICATE_INCONSISTENT", env["result"]["verdict"]
    conflicts = env["result"]["consistency"]["material_identity_conflicts"]
    assert conflicts, env["result"]["consistency"]
    assert conflicts[0]["sample_id"] == first["sample_id"], conflicts
    assert len(conflicts[0]["batch_ids"]) > 1, conflicts
    assert env["result"]["data_quality"]["identity_conflicts_excluded"] >= 1, env["result"]
    excluded = env["result"]["data_quality"]["excluded_observations"]
    assert any(entry["reason"] == "MATERIAL_IDENTITY_CONFLICT" for entry in excluded), excluded
    print("PASS: same sample_id across different batch_ids -> REPLICATE_INCONSISTENT + excluded")

    # consistency_check alone reports the same conflict on the canonical shape.
    direct = consistency_check([
        {"observation_reference": "A", "group_reference": "ARM-X", "sample_id": "S-1",
         "batch_id": "B-1", "event_occurred": True, "_censored": False},
        {"observation_reference": "B", "group_reference": "ARM-X", "sample_id": "S-1",
         "batch_id": "B-2", "event_occurred": True, "_censored": False},
    ])
    assert direct["verdict"] == "REPLICATE_INCONSISTENT", direct
    assert direct["material_identity_conflicts"], direct
    print("PASS: consistency_check flags the material-identity conflict directly")

    # A legitimate pair (same sample, same batch) stays CONSISTENT.
    clean = consistency_check([
        {"observation_reference": "A", "group_reference": "ARM-X", "sample_id": "S-1",
         "batch_id": "B-1", "event_occurred": True, "_censored": False},
        {"observation_reference": "B", "group_reference": "ARM-X", "sample_id": "S-1",
         "batch_id": "B-1", "event_occurred": True, "_censored": False},
    ])
    assert clean["verdict"] == "CONSISTENT", clean
    print("PASS: a genuinely clean replicate pair is judged CONSISTENT")


def test_rule_replicate_outcome_contradiction():
    # One replicate has the event, the other runs to completion: FAIL on the
    # outcome flags alone, whatever the numbers say.
    contradicted = consistency_check([
        {"observation_reference": "A", "group_reference": "ARM-X", "sample_id": "S-1",
         "batch_id": "B-1", "event_occurred": True, "_censored": False},
        {"observation_reference": "B", "group_reference": "ARM-X", "sample_id": "S-2",
         "batch_id": "B-1", "event_occurred": False, "_censored": False},
    ])
    assert contradicted["verdict"] == "REPLICATE_INCONSISTENT", contradicted
    arms = contradicted["inconsistent_arms"]
    assert arms and arms[0]["with_event"] == ["A"] and arms[0]["without_event"] == ["B"], arms
    assert contradicted["basis"] == "OUTCOME_ONLY_NO_NUMBERS_USED", contradicted
    print("PASS: outcome contradiction within one arm -> REPLICATE_INCONSISTENT, numbers unused")

    # A censored replicate has an UNKNOWN outcome, so it is not a contradiction.
    censored_arm = consistency_check([
        {"observation_reference": "A", "group_reference": "ARM-X", "sample_id": "S-1",
         "batch_id": "B-1", "event_occurred": True, "_censored": False},
        {"observation_reference": "B", "group_reference": "ARM-X", "sample_id": "S-2",
         "batch_id": "B-1", "event_occurred": False, "_censored": True},
    ])
    assert censored_arm["verdict"] == "CONSISTENT", censored_arm
    print("PASS: a censored replicate is an unknown outcome, not a contradiction")


def test_rule_confounding_excluded():
    data = load_gold_input()
    env = run(data)
    assert env["status"] == "OK", env
    quality = env["result"]["data_quality"]
    assert quality["confounded_excluded"] >= 1, quality
    excluded = quality["excluded_observations"]
    assert any(entry["reason"] == "CONFOUNDED_OBSERVATION" for entry in excluded), excluded

    # The confounded observation must be inside the declared window and its
    # removal must not change the estimate (i.e. it never entered it).
    window_start, window_end = "2026-03-12T09:00:00Z", "2026-03-13T18:00:00Z"
    confounded_refs = {entry["observation_reference"] for entry in excluded
                       if entry["reason"] == "CONFOUNDED_OBSERVATION"}
    by_reference = {entry["observation_reference"]: entry for entry in data["observations"]}
    for reference in confounded_refs:
        moment = by_reference[reference]["at"]
        assert window_start <= moment <= window_end, (reference, moment)
    without = copy.deepcopy(data)
    without["observations"] = [entry for entry in without["observations"]
                               if entry["observation_reference"] not in confounded_refs]
    without["censoring"] = [entry for entry in without["censoring"]
                            if entry["observation_reference"] not in confounded_refs]
    # Both sides scoped to the same arm: removing an already-excluded
    # observation must not move the estimate at all.
    bare = variance_components(without, "ARM-BLANK")
    scoped = variance_components(data, "ARM-BLANK")
    assert bare["status"] == scoped["status"] == "COMPUTED", (bare, scoped)
    assert abs(bare["sigma_total"] - scoped["sigma_total"]) < 1e-12, (bare, scoped)
    assert bare["observations_used"] == scoped["observations_used"], (bare, scoped)
    print("PASS: confounded observation is excluded from the variance estimate")

    # Leaving the confounded observation in the pool would inflate the noise:
    # an unscoped decomposition folds the between-formulation difference into
    # sigma_batch, which is why the decomposition is arm-scoped.
    unscoped = variance_components(data)
    assert unscoped["sigma_batch"] > scoped["sigma_batch"], (unscoped, scoped)
    assert any("pooling formulations" in limitation for limitation in scoped["limitations"])
    print("PASS: unscoped pooling inflates sigma_batch, confirming the noise scope matters")

    # A confounds=true window with no parseable start is a rejection: an
    # unreadable window would silently hide a confounder.
    poisoned = copy.deepcopy(data)
    poisoned["intervention_events"][1]["at"] = "not-a-timestamp"
    reasons = rejected_reasons(run(poisoned))
    assert any("unparseable" in reason for reason in reasons), reasons
    print("PASS: unparseable intervention window is rejected, not silently ignored")

    # When a confounder exists but an observation has no timestamp, the engine
    # cannot prove it is outside the window -> reject instead of assuming.
    poisoned = copy.deepcopy(data)
    for entry in poisoned["observations"]:
        entry.pop("at", None)
    reasons = rejected_reasons(run(poisoned))
    assert any("cannot prove" in reason for reason in reasons), reasons
    print("PASS: observation without a timestamp under an active confounder is rejected")


def test_rejected_not_raised():
    # Unknown analysis name -> REJECTED envelope (this is also the schema path).
    bad = load_gold_input()
    bad["analyses"] = ["SOMETHING_ELSE"]
    reasons = rejected_reasons(run(bad))
    assert any("SOMETHING_ELSE" in reason for reason in reasons), reasons

    # Missing a required field -> REJECTED envelope, not an exception.
    bad = load_gold_input()
    bad.pop("replicate_structure")
    rejected_reasons(run(bad))

    # A comparison arm naming an unknown group is a business rejection.
    bad = load_gold_input()
    bad["comparison_arms"]["arm_a_group_reference"] = "ARM-NOT-PRESENT"
    reasons = rejected_reasons(run(bad))
    assert any("does not match any observation group_reference" in reason for reason in reasons), reasons

    # Both arms naming the same group means there is nothing to compare.
    bad = load_gold_input()
    bad["comparison_arms"]["arm_b_group_reference"] = bad["comparison_arms"]["arm_a_group_reference"]
    reasons = rejected_reasons(run(bad))
    assert any("same group twice" in reason for reason in reasons), reasons

    # No usable observation at all after exclusions.
    empty = load_gold_input()
    empty["observations"] = []
    empty["censoring"] = []
    env = analyze_statistics(empty, b"{}")
    assert env["status"] == "REJECTED", env
    assert env["rejection_reasons"], env
    print("PASS: every failure path is a REJECTED envelope, never a raised exception")


def build_underpowered_input():
    """A real UNDERPOWERED design: k = delta/sigma well below 3.

    Two arms whose observed difference (about 0.05 h) is far inside the noise
    scale (sigma about 0.2 h), against a pre-registered delta of 0.1 h at two
    replicates per arm. Power is near alpha, so the question is unanswerable at
    this resolution -- the pack's k <= 1 row, where the required n is 16 per arm
    and the right move is to change the method or the criterion.
    """
    blank_values = [4.00, 4.20, 4.10, 4.30, 3.90, 4.10, 4.00, 4.20]
    additive_values = [4.05, 4.25, 4.15, 4.35, 3.95, 4.15, 4.05, 4.25]
    observations = []
    censoring = []
    for index, value in enumerate(blank_values):
        reference = "OBS-B%02d" % (index + 1)
        observations.append({
            "observation_reference": reference, "level": "MEASUREMENT",
            "group_reference": "ARM-BLANK",
            "sample_id": "S-B%02d" % (index // 2 + 1),
            "batch_id": "BATCH-B%02d" % (index // 2 + 1),
            "run_reference": "RUN-B%02d" % (index // 2 + 1),
            "value": value, "at": "2026-02-%02dT09:00:00Z" % (10 + index),
            "event_occurred": True, "event_time": value,
        })
        censoring.append({"observation_reference": reference, "event_occurred": True,
                          "event_time": value, "censoring_type": "NONE",
                          "stop_reason": "event observed"})
    for index, value in enumerate(additive_values):
        reference = "OBS-A%02d" % (index + 1)
        observations.append({
            "observation_reference": reference, "level": "MEASUREMENT",
            "group_reference": "ARM-ADDITIVE",
            "sample_id": "S-A%02d" % (index // 2 + 1),
            "batch_id": "BATCH-A%02d" % (index // 2 + 1),
            "run_reference": "RUN-A%02d" % (index // 2 + 1),
            "value": value, "at": "2026-02-%02dT09:00:00Z" % (10 + index),
            "event_occurred": True, "event_time": value,
        })
        censoring.append({"observation_reference": reference, "event_occurred": True,
                          "event_time": value, "censoring_type": "NONE",
                          "stop_reason": "event observed"})
    return {
        "input_type": "VARIANCE_ANALYSIS",
        "analyses": ["VARIANCE_COMPONENTS", "POWER_ANALYSIS", "CONSISTENCY_CHECK"],
        "replicate_structure": [
            {"level": "BATCH", "n": 4, "group_reference": "ARM-BLANK"},
            {"level": "BENCH", "n": 2, "group_reference": "RUN-B01"},
            {"level": "MEASUREMENT", "n": 2, "group_reference": "RUN-B01"},
        ],
        "observations": observations,
        "censoring": censoring,
        "intervention_events": [],
        "comparison_arms": {"arm_a_group_reference": "ARM-ADDITIVE",
                            "arm_b_group_reference": "ARM-BLANK"},
        "preregistered_delta": 0.1,
        "k_required": 3,
        "alpha": 0.05,
        "target_power": 0.8,
        "resolution_n_values": [2, 3, 6, 12, 16],
    }


def test_underpowered_end_to_end():
    # A design that cannot resolve the pre-registered difference must be
    # UNDERPOWERED, and must NOT be reported as NO_DETECTABLE_DIFFERENCE.
    data = build_underpowered_input()
    env = run(data)
    assert env["status"] == "OK", env
    result = env["result"]
    assert result["verdict"] == "UNDERPOWERED", result["verdict"]
    assert result["verdict"] != "NO_DETECTABLE_DIFFERENCE"
    assert "UNDERPOWERED" in result["verdict_values_available"]
    assert result["power"]["status"] == "COMPUTED", result["power"]
    assert result["power"]["power"] < result["power"]["target_power"], result["power"]
    # The observed difference is inside the noise scale, so step 2 must not fire.
    comparison = result["comparison"]
    assert abs(comparison["difference"]) < comparison["k_required"] * result["variance_components"]["sigma_total"], comparison
    # k = delta/sigma is below the frozen viability threshold: the pack rule is
    # to change the method or the criterion, not to buy more replicates.
    assert result["power"]["k_ratio"] < 3.0, result["power"]
    assert "do NOT increase n" in result["power"]["note"], result["power"]["note"]
    required = result["power"]["required_n"]
    assert required["feasible"] is False, required
    print("PASS: an unresolvable question is UNDERPOWERED, not NO_DETECTABLE_DIFFERENCE")

    # The same design with a resolvable delta is NO_DETECTABLE_DIFFERENCE: proof
    # that the verdict tracks the design's capability, not the observed number.
    resolvable = copy.deepcopy(data)
    resolvable["preregistered_delta"] = 1.2
    env_resolvable = run(resolvable)
    assert env_resolvable["status"] == "OK", env_resolvable
    assert env_resolvable["result"]["power"]["power"] >= 0.8, env_resolvable["result"]["power"]
    assert env_resolvable["result"]["verdict"] == "NO_DETECTABLE_DIFFERENCE", \
        env_resolvable["result"]["verdict"]
    print("PASS: the same data with a resolvable delta is NO_DETECTABLE_DIFFERENCE")


def test_not_requested_no_change():
    # Backward compatibility: a legacy request must not gain step-12 sections.
    legacy = load_gold_input()
    legacy["requested_analyses"] = ["ANOVA", "REGRESSION", "RESIDUAL", "LACK_OF_FIT"]
    legacy.pop("analyses")
    for key in ("replicate_structure", "censoring", "intervention_events",
                "comparison_arms", "frozen_sigma", "frozen_sigma_reference",
                "control_band", "preregistered_delta", "k_required", "alpha",
                "target_power", "resolution_n_values"):
        legacy.pop(key, None)
    stats_input = {
        "input_type": "STATISTICAL_ANALYSIS",
        "components": [{"component_id": "A"}, {"component_id": "B"}, {"component_id": "C"}],
        "model_order": "QUADRATIC",
        "response_ctq": "KV40",
        "design_points": [
            {"run_reference": "R01", "proportions": {"A": 1, "B": 0, "C": 0}},
            {"run_reference": "R02", "proportions": {"A": 0, "B": 1, "C": 0}},
            {"run_reference": "R03", "proportions": {"A": 0, "B": 0, "C": 1}},
            {"run_reference": "R04", "proportions": {"A": 0.5, "B": 0.5, "C": 0}},
            {"run_reference": "R05", "proportions": {"A": 0.5, "B": 0, "C": 0.5}},
            {"run_reference": "R06", "proportions": {"A": 0, "B": 0.5, "C": 0.5}},
        ],
        "observations": [
            {"run_reference": "R01", "ctq_reference": "KV40", "value": 10},
            {"run_reference": "R02", "ctq_reference": "KV40", "value": 20},
            {"run_reference": "R03", "ctq_reference": "KV40", "value": 30},
            {"run_reference": "R04", "ctq_reference": "KV40", "value": 16},
            {"run_reference": "R05", "ctq_reference": "KV40", "value": 18.5},
            {"run_reference": "R06", "ctq_reference": "KV40", "value": 27},
        ],
        "requested_analyses": ["ANOVA", "REGRESSION", "RESIDUAL", "LACK_OF_FIT"],
    }
    raw = (json.dumps(stats_input, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    env = analyze_statistics(stats_input, raw)
    assert env["status"] == "OK", env
    assert env["method"] == "OLS_ANOVA_V1", env["method"]
    expected_keys = {"response_ctq", "coefficients", "anova_table", "fit_statistics",
                     "residual_analysis", "lack_of_fit"}
    assert set(env["result"].keys()) == expected_keys, sorted(env["result"].keys())

    # The legacy gold pair still hashes to its frozen value.
    for name, expected in {
        "statistics-gold-input.json": "d17cba69c8f1c61e04a7ec755d23b8da7559d6633b50e18118accae13e0b1512",
        "statistics-gold-output.json": "4bab7b2c494a08dca061daef916cc04730851606ab2cfa63e5c8e46d9ba62bf4",
    }.items():
        assert hashlib.sha256((FIXTURE_DIR / name).read_bytes()).hexdigest() == expected, name

    # Requesting a step-12 name DOES add its section (and only its section).
    extended = copy.deepcopy(stats_input)
    extended["requested_analyses"] = ["ANOVA", "VARIANCE_COMPONENTS"]
    env_extended = analyze_statistics(extended, raw)
    assert env_extended["status"] == "OK", env_extended
    assert set(env_extended["result"].keys()) - expected_keys == {"variance_components"}, \
        sorted(env_extended["result"].keys())
    assert env_extended["result"]["variance_components"]["scope"] == "DESIGN_POINT_LEVEL_SPLIT"

    power_only = copy.deepcopy(stats_input)
    power_only["requested_analyses"] = ["POWER_ANALYSIS"]
    env_power = analyze_statistics(power_only, raw)
    assert env_power["result"]["power_analysis"]["status"] == "NOT_COMPUTABLE"
    assert "pre-registered delta" in env_power["result"]["power_analysis"]["reason"]

    consistency_only = copy.deepcopy(stats_input)
    consistency_only["requested_analyses"] = ["CONSISTENCY_CHECK"]
    env_consistency = analyze_statistics(consistency_only, raw)
    assert env_consistency["result"]["consistency_check"]["verdict"] == "NOT_APPLICABLE"
    print("PASS: new sections appear only when requested; legacy result keys unchanged")


def test_gold_fixture_and_determinism():
    raw = GOLD_INPUT.read_bytes()
    expected = GOLD_OUTPUT.read_bytes()
    env = analyze_statistics(json.loads(raw.decode("utf-8")), raw)
    payload = (json.dumps(env, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    assert payload == expected, "statistics-variance gold output drifted"

    for name, digest in EXPECTED_HASHES.items():
        actual = hashlib.sha256((FIXTURE_DIR / name).read_bytes()).hexdigest()
        assert actual == digest, (name, actual)
    assert b"\r" not in raw and b"\r" not in expected, "gold fixtures must stay LF"

    # The verdict must be the positive case in the gold pair, and every
    # data-quality rule must be exercised by it.
    assert env["result"]["verdict"] == "CONSISTENT_DIFFERENCE", env["result"]["verdict"]
    quality = env["result"]["data_quality"]
    assert quality["censored_excluded"] >= 1, quality
    assert quality["confounded_excluded"] >= 1, quality
    assert env["result"]["consistency"]["verdict"] == "CONSISTENT"
    structure = env["result"]["replicate_structure"]
    assert structure["shortfalls"] == [], structure
    assert structure["declared_groups_by_level"]["BATCH"] == 6, structure
    assert structure["observed_groups_by_level"]["BATCH"] == 6, structure
    components = env["result"]["variance_components"]
    for key in ("sigma_meas", "sigma_bench", "sigma_batch", "sigma_total",
                "sigma_total_ci_low", "sigma_total_ci_high"):
        assert components[key] is not None, (key, components)
    assert components["sigma_total_ci_low"] <= components["sigma_total"] <= components["sigma_total_ci_high"]

    # Determinism: byte-identical envelopes for identical input.
    second = analyze_statistics(json.loads(raw.decode("utf-8")), raw)
    assert (json.dumps(second, ensure_ascii=False, indent=2) + "\n").encode("utf-8") == expected

    # input_digest must be the SHA256 of the canonical input bytes.
    assert env["input_digest"] == hashlib.sha256(raw).hexdigest()

    # The CLI writes the same bytes.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        inp = td / "in.json"
        inp.write_bytes(raw)
        outputs = []
        for name in ("a.json", "b.json"):
            target = td / name
            subprocess.run(
                [sys.executable, "-B", "-m", "domains.lubricant.compute.statistics.engine",
                 str(inp), str(target)],
                cwd=ROOT, check=True)
            outputs.append(target.read_bytes())
        assert outputs[0] == outputs[1] == expected
    print("PASS: variance gold bytes, SHA256 freeze, LF and determinism")


def main():
    test_scalar_capabilities()
    test_verdict_enum_and_logic()
    test_rule_censoring_never_an_endpoint()
    test_rule_material_identity_conflict()
    test_rule_replicate_outcome_contradiction()
    test_rule_confounding_excluded()
    test_rejected_not_raised()
    test_underpowered_end_to_end()
    test_not_requested_no_change()
    test_gold_fixture_and_determinism()
    print("PASS: statistics variance engine (capabilities, verdicts, data-quality rules, gold)")


if __name__ == "__main__":
    main()
