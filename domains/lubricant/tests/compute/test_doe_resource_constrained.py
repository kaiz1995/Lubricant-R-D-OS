"""Direct-run DOE resource-constrained tests (no pytest) - WP-04b.

Covers the resource envelope and the sequential channel added by WP-04b:

  1. bench_slots=2 -> exactly 2 recommended runs, each with a hypothesis id and a
     discriminative-power reason, consistent with the design matrix and the envelope.
  2. bench_slots=1 -> exactly 1 recommended run.
  3. Pure process-factor scenarios (FULL_FACTORIAL and SPLIT_PLOT) also recommend.
  4. The legacy mixture channel is untouched: gold envelope byte-identical and the
     resource envelope is a contract error on the mixture channel.
  5. Fail-closed resource rejections (bench_slots/lot_capacity/cycle_days/cost_cap/
     external_test_lead_time, malformed envelope, SEQUENTIAL without an envelope).
  6. BAYESIAN_SEQUENTIAL is a runnable deterministic path bounded by bench_slots. An
     effect that no run in the batch isolates becomes an explicit extra run at its
     all-high corner instead of silently borrowing another run's settings.
  7. The split-plot direction comes from data (explicit role, else process_factor_role)
     and is never hardcoded.
  8. Every produced factor envelope satisfies doe_result_schema.json.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "domains" / "lubricant" / "schemas"


def load_schemas():
    schemas = {}
    for p in SCHEMA_DIR.glob("*.json"):
        schemas[p.name] = json.loads(p.read_text(encoding="utf-8"))
    registry = Registry()
    for s in schemas.values():
        if "$id" in s:
            registry = registry.with_resource(s["$id"], Resource.from_contents(s))
    return schemas, registry


def validate(schema_name, doc):
    schemas, registry = load_schemas()
    return list(Draft202012Validator(schemas[schema_name], registry=registry).iter_errors(doc))


def assert_valid(env):
    errors = validate("doe_result_schema.json", env)
    assert not errors, [e.message for e in errors]


def make_card():
    return {
        "decision_question": "Which process hypothesis gets the next two bench slots?",
        "hypothesis": "Vessel change shifts the temperature/vacuum response.",
        "variables_note": "Process factors only.",
        "constraints_note": "Independent process bounds, no mixture closure.",
        "responses_note": "KV40 OPTIMIZATION_RESPONSE.",
        "doe_selection_reason": "Two-level factorials resolve the main effects first.",
        "expected_information_value": "Orthogonal columns isolate each effect.",
        "decision_rule": "Spend the next bench slots on the least-resolved hypothesis.",
    }


def envelope(bench_slots=2, lot_capacity=16, cycle_days=3.0, cost_cap=0.0, external_test_lead_time=0.0):
    return {
        "bench_slots": bench_slots, "lot_capacity": lot_capacity, "cycle_days": cycle_days,
        "cost_cap": cost_cap, "external_test_lead_time": external_test_lead_time,
    }


def factor_input(design_type="FULL_FACTORIAL", model_order="LINEAR", res=None, extra=None):
    payload = {
        "input_type": "FACTORIAL_DOE_DESIGN",
        "design_type": design_type,
        "model_order": model_order,
        "target_runs": 0,
        "design_space_reference": "DS-PROC-001",
        "process_factor_role": "WHOLE_PLOT",
        "factors": [
            {"factor_id": "PROC-TEMP", "factor_type": "CONTINUOUS", "range": {"lower": 90, "upper": 110}, "unit": "degC"},
            {"factor_id": "PROC-VACUUM", "factor_type": "CONTINUOUS", "range": {"lower": 1, "upper": 10}, "unit": "kPa"},
        ],
        "responses": [{"ctq_reference": "KV40", "test_method_reference": "ASTM D445", "role": "OPTIMIZATION_RESPONSE"}],
        "experiment_card": make_card(),
    }
    if res is not None:
        payload["resource_envelope"] = res
    if extra:
        payload.update(extra)
    return payload


def split_plot_input(res, roles=("WHOLE_PLOT", "SUB_PLOT", "SUB_PLOT"), model_order="QUADRATIC"):
    # The default mix is a valid split plot: one whole-plot (kettle) factor and two
    # sub-plot (temperature/vacuum) factors. The process-level default is deliberately
    # NOT relied on here so the direction is explicit and the scenario is readable.
    factors = [
        {"factor_id": "PROC-KETTLE", "factor_type": "DISCRETE", "levels": [1, 2]},
        {"factor_id": "PROC-TEMP", "factor_type": "CONTINUOUS", "range": {"lower": 90, "upper": 110}},
        {"factor_id": "PROC-VACUUM", "factor_type": "CONTINUOUS", "range": {"lower": 1, "upper": 10}},
    ]
    if roles is not None:
        for factor, role in zip(factors, roles):
            if role is not None:
                factor["role"] = role
    return factor_input("SPLIT_PLOT", model_order, res, extra={"factors": factors, "whole_plot_replicates": 2})


def main():
    sys.path.insert(0, str(ROOT))
    from domains.lubricant.compute.doe.engine import generate_doe

    # 1. bench_slots=2 -> exactly two recommended runs with hypothesis ids and reasons.
    env = generate_doe(factor_input(res=envelope(bench_slots=2)))
    assert env["status"] == "OK", env.get("rejection_reasons")
    result = env["result"]
    assert_valid(env)
    assert result["resource_feasible"] is True
    assert len(result["recommended_next_runs"]) == 2, result["recommended_next_runs"]
    by_index = {run["run_index"]: run for run in result["runs"]}
    seen_ids = set()
    for rank, entry in enumerate(result["recommended_next_runs"], start=1):
        assert entry["rank"] == rank
        assert entry["hypothesis_reference"].startswith("H")
        assert entry["hypothesis_statement"]
        assert entry["effect_reference"]
        assert entry["discriminative_power_reason"]
        assert entry["slots_used"] == 1
        assert entry["information_gain_per_slot"] > 0
        seen_ids.add(entry["hypothesis_reference"])
    assert len(seen_ids) == 2, "each recommended run must carry a distinct hypothesis"
    for entry in result["recommended_next_runs"]:
        # a full factorial contains the all-high corner of every main effect, so each
        # recommendation points at a real run of the matrix
        assert entry["run_index"] is not None
        assert entry["settings"] == by_index[entry["run_index"]]["settings"]
    assert result["information_gain_per_slot"] == sum(
        entry["information_gain_per_slot"] for entry in result["recommended_next_runs"]) / 2
    print("PASS: bench_slots=2 -> two recommended runs with hypothesis id + reason")

    # 2. bench_slots=1 -> exactly one.
    env = generate_doe(factor_input(res=envelope(bench_slots=1)))
    assert env["status"] == "OK"
    assert len(env["result"]["recommended_next_runs"]) == 1
    assert env["result"]["recommended_next_runs"][0]["rank"] == 1
    print("PASS: bench_slots=1 -> one recommended run")

    # 3. Pure process-factor scenarios (FACTORIAL and SPLIT_PLOT) also recommend.
    for design_type in ("FULL_FACTORIAL", "FRACTIONAL_FACTORIAL"):
        payload = factor_input(design_type, res=envelope(bench_slots=2))
        if design_type == "FRACTIONAL_FACTORIAL":
            payload["factors"] = payload["factors"] + [
                {"factor_id": "PROC-TIME", "factor_type": "CONTINUOUS", "range": {"lower": 10, "upper": 30}}]
        env = generate_doe(payload)
        assert env["status"] == "OK", (design_type, env.get("rejection_reasons"))
        assert len(env["result"]["recommended_next_runs"]) == 2, design_type
        assert_valid(env)
    env = generate_doe(split_plot_input(envelope(bench_slots=2)))
    assert env["status"] == "OK", env.get("rejection_reasons")
    split_result = env["result"]
    assert_valid(env)
    assert len(split_result["recommended_next_runs"]) == 2
    assert all("whole_plot_index" in entry for entry in split_result["recommended_next_runs"])
    assert all("whole plot" in entry["discriminative_power_reason"]
               for entry in split_result["recommended_next_runs"])
    print("PASS: pure process-factor designs (factorial + split-plot) recommend")

    # 4. Mixture channel non-regression: byte-identical gold, and an envelope is refused.
    gold_in = ROOT / "fixtures/compute/doe-gold-input.json"
    gold_out = ROOT / "fixtures/compute/doe-gold-output.json"
    raw = gold_in.read_bytes().replace(b"\r\n", b"\n")
    legacy = generate_doe(json.loads(raw.decode("utf-8")), raw)
    mine = (json.dumps(legacy, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    assert mine.replace(b"\r\n", b"\n") == gold_out.read_bytes().replace(b"\r\n", b"\n"), "mixture gold regressed"
    assert "resource_feasible" not in legacy["result"], "mixture channel must not emit resource annotations"
    mixture_with_envelope = json.loads(raw.decode("utf-8"))
    mixture_with_envelope["resource_envelope"] = envelope()
    assert generate_doe(mixture_with_envelope)["status"] == "REJECTED", "mixture must reject a resource envelope"
    print("PASS: mixture channel untouched and refuses a resource envelope")

    # 5. Fail-closed resource rejections.
    def rejected(payload, needle):
        env = generate_doe(payload)
        assert env["status"] == "REJECTED", (needle, env["status"])
        assert any(needle in reason for reason in env["rejection_reasons"]), (needle, env["rejection_reasons"])

    rejected(factor_input(res=envelope(bench_slots=0)), "bench_slots must be >= 1")
    rejected(factor_input(res=envelope(bench_slots=-2)), "bench_slots must be >= 1")
    rejected(factor_input(res=envelope(lot_capacity=0)), "lot_capacity must be >= 1")
    rejected(factor_input(res=envelope(cycle_days=0)), "cycle_days must be > 0")
    rejected(factor_input(res=envelope(cost_cap=-1.0)), "cost_cap must be >= 0")
    rejected(factor_input(res=envelope(external_test_lead_time=-1.0)), "external_test_lead_time must be >= 0")
    # A malformed envelope is refused fail-closed and the reason names the offending field.
    # The input schema catches a missing/extra key first; the engine keeps a structural
    # guard (see _resource_reasons) as a backstop for callers that skip schema validation.
    rejected(factor_input(res={"bench_slots": 2}), "lot_capacity")
    rejected(factor_input(res=dict(envelope(), unknown=1)), "unknown")
    rejected(factor_input(design_type="BAYESIAN_SEQUENTIAL", res=None),
             "BAYESIAN_SEQUENTIAL requires resource_envelope")
    print("PASS: fail-closed resource rejections")

    # 6. BAYESIAN_SEQUENTIAL is a runnable deterministic path bounded by bench_slots.
    seq = factor_input(design_type="BAYESIAN_SEQUENTIAL", res=envelope(bench_slots=3))
    first = generate_doe(seq)
    assert first["status"] == "OK", first.get("rejection_reasons")
    assert first["method"] == "BAYESIAN_SEQUENTIAL_GREEDY_V1"
    assert first["result"]["run_count"] == 3, first["result"]["run_count"]
    recs = first["result"]["recommended_next_runs"]
    assert len(recs) == 3
    # the greedy batch is 3 of the 4 corners of the 2^2 lattice, so the interaction cannot
    # be isolated by any run in it: that recommendation is an explicit extra run at the
    # all-high corner, never a silent reuse of another run's settings
    extra = [entry for entry in recs if entry["run_index"] is None]
    assert len(extra) == 1, recs
    assert extra[0]["effect_reference"] == "PROC-TEMP*PROC-VACUUM"
    assert extra[0]["settings"] == {"PROC-TEMP": 110.0, "PROC-VACUUM": 10.0}
    assert "extra run" in extra[0]["discriminative_power_reason"]
    assert_valid(first)
    with tempfile.TemporaryDirectory() as td:
        p_in, p_out1, p_out2 = Path(td) / "in.json", Path(td) / "o1.json", Path(td) / "o2.json"
        p_in.write_bytes(json.dumps(seq, ensure_ascii=False).encode("utf-8"))
        import subprocess
        for target in (p_out1, p_out2):
            r = subprocess.run([sys.executable, "-m", "domains.lubricant.compute.doe.engine", str(p_in), str(target)],
                               cwd=str(ROOT), capture_output=True)
            assert r.returncode == 0, r.stderr.decode()[:400]
        assert p_out1.read_bytes() == p_out2.read_bytes()
    print("PASS: BAYESIAN_SEQUENTIAL runnable, bounded by bench_slots, deterministic")

    # 7. Split-plot direction is data-driven: an explicit per-factor role wins, otherwise
    #    the process-level process_factor_role (the mirror of process.factor_role) applies.
    def counts(payload):
        env = generate_doe(payload)
        assert env["status"] == "OK", env.get("rejection_reasons")
        return env["parameters"]["whole_plot_factor_count"], env["parameters"]["sub_plot_factor_count"]

    inherit_whole = factor_input(res=envelope(), extra={"process_factor_role": "WHOLE_PLOT"})
    for factor in inherit_whole["factors"]:
        factor.pop("role", None)
    assert counts(inherit_whole) == (2, 0), "process_factor_role must supply the missing roles"
    inherit_sub = factor_input(res=envelope(), extra={"process_factor_role": "SUB_PLOT"})
    for factor in inherit_sub["factors"]:
        factor.pop("role", None)
    assert counts(inherit_sub) == (0, 2), "the resolved direction must follow the data, not a hardcoded list"
    override = factor_input(res=envelope(), extra={"process_factor_role": "WHOLE_PLOT"})
    override["factors"][0]["role"] = "SUB_PLOT"
    override["factors"][1]["role"] = "WHOLE_PLOT"
    assert counts(override) == (1, 1), "an explicit factors[].role must win over the default"
    # a valid split-plot mix built from the default role
    mixed = split_plot_input(envelope(), roles=["WHOLE_PLOT", None, None])
    mixed["process_factor_role"] = "SUB_PLOT"
    env = generate_doe(mixed)
    assert env["status"] == "OK", env.get("rejection_reasons")
    assert (env["parameters"]["whole_plot_factor_count"], env["parameters"]["sub_plot_factor_count"]) == (1, 2)
    assert_valid(env)
    # a varying factor with no role anywhere is rejected by name
    unresolved = factor_input("SPLIT_PLOT", "QUADRATIC", envelope(), extra={"whole_plot_replicates": 2})
    unresolved.pop("process_factor_role")
    env = generate_doe(unresolved)
    assert env["status"] == "REJECTED"
    assert any("has no split-plot role" in reason for reason in env["rejection_reasons"]), env["rejection_reasons"]
    print("PASS: split-plot direction resolved from data, never hardcoded")

    # 8. resource_feasible is false when the design cannot fit the lot capacity.
    env = generate_doe(factor_input(res=envelope(bench_slots=2, lot_capacity=1)))
    assert env["status"] == "OK"
    assert env["result"]["resource_feasible"] is False
    assert len(env["result"]["recommended_next_runs"]) == 2, "recommendations still respect bench_slots"
    assert_valid(env)
    print("PASS: resource_feasible reports a design that overflows lot_capacity")

    print("ALL PASS: WP-04b resource-constrained DOE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
