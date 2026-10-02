"""Direct-run DOE factorial-channel tests (no pytest) - WP-04a.

Covers the pure-process / split-plot channel added by WP-04a, and proves the
legacy constrained-mixture channel is untouched:

  1. FULL_FACTORIAL, pure process factors (no components) -> structure-determined
     run count, orthogonal coded columns, closed df identity.
  2. FRACTIONAL_FACTORIAL 2^(k-1): half the runs, aliasing reported per column.
  3. SPLIT_PLOT: whole/sub-plot error decomposition with whole_plot_index.
  4. MIXTURE_PROCESS: frozen formula + process factors, fixed_proportions carried.
  5. Determinism: same bytes -> byte-identical envelope.
  6. Mixture non-regression: the legacy gold envelope is reproduced exactly.
  7. Fail-closed rejections (TAGUCHI deferred, multi-level, held-only, inverted
     levels, missing whole/sub, too-few factors for a half fraction, target_runs).
  8. Every produced envelope satisfies doe_result_schema.json.
"""
from __future__ import annotations

import hashlib
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
    v = Draft202012Validator(schemas[schema_name], registry=registry)
    return list(v.iter_errors(doc))


def make_card():
    return {
        "decision_question": "Which process axis moves KV40 across vessels?",
        "hypothesis": "Vessel change alters the temperature/vacuum response.",
        "variables_note": "Process factors only.",
        "constraints_note": "Each factor holds its own independent bounds.",
        "responses_note": "KV40 OPTIMIZATION_RESPONSE.",
        "doe_selection_reason": "Two-level factorial resolves main effects and interactions.",
        "expected_information_value": "Orthogonal columns isolate each effect.",
        "decision_rule": "Pick the setting that reproduces KV40 across vessels.",
    }


def factor(factor_id, low, high, factor_type="CONTINUOUS", role="WHOLE_PLOT", unit=None):
    entry = {
        "factor_id": factor_id,
        "factor_type": factor_type,
        "role": role,
        "range": {"lower": low, "upper": high},
    }
    if unit is not None:
        entry["unit"] = unit
    return entry


def held_factor(factor_id, value, factor_type="CONTINUOUS", role="WHOLE_PLOT", unit=None):
    entry = {"factor_id": factor_id, "factor_type": factor_type, "role": role, "hold_at": value}
    if unit is not None:
        entry["unit"] = unit
    return entry


def make_factor_input(factors, design_type, model_order="LINEAR", target_runs=0,
                      input_type="FACTORIAL_DOE_DESIGN", extra=None):
    payload = {
        "input_type": input_type,
        "design_type": design_type,
        "model_order": model_order,
        "target_runs": target_runs,
        "design_space_reference": "DS-PROC-001",
        "factors": factors,
        "responses": [{"ctq_reference": "KV40", "test_method_reference": "ASTM D445",
                       "role": "OPTIMIZATION_RESPONSE"}],
        "experiment_card": make_card(),
    }
    if extra:
        payload.update(extra)
    return payload


def assert_df_identity(envelope):
    result = envelope["result"]
    degrees = result["degrees_of_freedom"]
    assert degrees["error"] == sum(t["degrees_of_freedom"] for t in result["error_terms"]), degrees
    assert degrees["total"] == degrees["replicate"] + degrees["model"] + degrees["error"], degrees


def main():
    sys.path.insert(0, str(ROOT))
    from domains.lubricant.compute.doe.engine import generate_doe

    # 1. FULL_FACTORIAL pure process: 2 varying + 1 held -> 4 runs, 3 columns.
    inp = make_factor_input(
        [factor("TEMP", 90, 110, unit="degC"), factor("VACUUM", 1, 10, unit="kPa"),
         held_factor("AGITATION", 300, unit="rpm")],
        "FULL_FACTORIAL",
    )
    env = generate_doe(inp)
    assert env["status"] == "OK", env.get("rejection_reasons")
    result = env["result"]
    assert result["run_count"] == 4, result["run_count"]
    assert len(result["runs"]) == 4
    assert result["degrees_of_freedom"] == {"total": 3, "replicate": 0, "model": 2, "error": 1}, result["degrees_of_freedom"]
    assert_df_identity(env)
    column_ids = [c["column_id"] for c in result["columns"]]
    assert column_ids == ["TEMP", "VACUUM", "TEMP*VACUUM"], column_ids
    # held factor is not a varying column but is carried in every run
    assert all("AGITATION" in r["settings"] for r in result["runs"])
    assert not validate("doe_result_schema.json", env), [e.message for e in validate("doe_result_schema.json", env)]
    print("PASS: pure-process full factorial 2^2 + 1 held factor")

    # 2. FULL_FACTORIAL all varying: 2^3 -> 8 runs, 7 orthogonal columns.
    inp = make_factor_input(
        [factor("TEMP", 90, 110), factor("VACUUM", 1, 10), factor("TIME", 10, 30)],
        "FULL_FACTORIAL", model_order="QUADRATIC",
    )
    env = generate_doe(inp)
    assert env["status"] == "OK", env.get("rejection_reasons")
    result = env["result"]
    assert result["run_count"] == 8, result["run_count"]
    assert len(result["columns"]) == 7, [c["column_id"] for c in result["columns"]]
    assert result["degrees_of_freedom"] == {"total": 7, "replicate": 0, "model": 7, "error": 0}
    assert_df_identity(env)
    # exact orthogonality: every coded column sums to zero and is pairwise orthogonal
    columns = result["columns"]
    for c in columns:
        assert sum(c["coded_levels"]) == 0, c
    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            dot = sum(a * b for a, b in zip(columns[i]["coded_levels"], columns[j]["coded_levels"]))
            assert dot == 0, (columns[i]["column_id"], columns[j]["column_id"], dot)
    print("PASS: pure-process full factorial 2^3 fully orthogonal")

    # 3. FRACTIONAL_FACTORIAL 2^(k-1): k=4 -> 8 runs, last factor aliased with a 3-way product.
    inp = make_factor_input(
        [factor("F0", 1, 2), factor("F1", 1, 2), factor("F2", 1, 2), factor("F3", 1, 2)],
        "FRACTIONAL_FACTORIAL", model_order="LINEAR",
    )
    env = generate_doe(inp)
    assert env["status"] == "OK", env.get("rejection_reasons")
    result = env["result"]
    assert result["run_count"] == 8, result["run_count"]
    assert env["method"] == "HALF_FRACTION_FACTORIAL_V1"
    aliased = [c for c in result["columns"] if "aliases" in c]
    assert aliased, "half fraction must report at least one aliasing group"
    # the generator makes the last sorted factor equal to the product of the others
    f3 = next(c for c in result["columns"] if c["column_id"] == "F3")
    assert "aliases" in f3 and any("F0*F1*F2" == name for name in f3["aliases"]), f3
    assert_df_identity(env)
    assert not validate("doe_result_schema.json", env)
    print("PASS: half fraction 2^(4-1) with per-column aliasing")

    # 4. SPLIT_PLOT: 1 whole x 2 sub, 2 replicates -> whole/sub error decomposition.
    inp = make_factor_input(
        [factor("KETTLE", 1, 2, role="WHOLE_PLOT"),
         factor("TEMP", 90, 110, role="SUB_PLOT"), factor("TIME", 10, 30, role="SUB_PLOT")],
        "SPLIT_PLOT", model_order="QUADRATIC",
        extra={"whole_plot_replicates": 2},
    )
    env = generate_doe(inp)
    assert env["status"] == "OK", env.get("rejection_reasons")
    result = env["result"]
    assert env["method"] == "SPLIT_PLOT_2LEVEL_V1"
    assert result["run_count"] == 2 ** 3 * 2, result["run_count"]
    assert all("whole_plot_index" in r for r in result["runs"])
    scopes = {term["scope"] for term in result["error_terms"]}
    assert "WHOLE_PLOT" in scopes and "SUB_PLOT" in scopes, scopes
    whole = next(t for t in result["error_terms"] if t["scope"] == "WHOLE_PLOT")
    assert whole["degrees_of_freedom"] == (2 - 1) * (2 - 1), whole  # (r-1)(W-1)
    assert_df_identity(env)
    assert not validate("doe_result_schema.json", env)
    print("PASS: split-plot whole/sub-plot error decomposition")

    # 5. MIXTURE_PROCESS: frozen formula sum == mixture_total, plus process factors.
    components = [
        {"component_id": "PAO6", "lower_bound": 0.7, "upper_bound": 0.7},
        {"component_id": "AN", "lower_bound": 0.2, "upper_bound": 0.2},
        {"component_id": "Additive", "lower_bound": 0.1, "upper_bound": 0.1},
    ]
    inp = make_factor_input(
        [factor("TEMP", 90, 110), factor("VACUUM", 1, 10)],
        "FULL_FACTORIAL", input_type="MIXTURE_PROCESS_DOE_DESIGN",
        extra={"components": components, "mixture_total": 1.0},
    )
    env = generate_doe(inp)
    assert env["status"] == "OK", env.get("rejection_reasons")
    assert env["method"] == "MIXTURE_PROCESS_FULL_FACTORIAL_2LEVEL_V1", env["method"]
    assert all(r.get("fixed_proportions") == {"AN": 0.2, "Additive": 0.1, "PAO6": 0.7}
               for r in env["result"]["runs"])
    assert env["parameters"]["design_space_reference"] == "DS-PROC-001"
    assert not validate("doe_result_schema.json", env)
    print("PASS: mixture+process combined channel with frozen proportions")

    # 6. Determinism: identical bytes -> byte-identical envelope (offline, no clock/random).
    raw = json.dumps(inp, ensure_ascii=False).encode("utf-8")
    first = generate_doe(json.loads(raw.decode("utf-8")), raw)
    second = generate_doe(json.loads(raw.decode("utf-8")), raw)
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)
    with tempfile.TemporaryDirectory() as td:
        p_in, p_out1, p_out2 = Path(td) / "in.json", Path(td) / "o1.json", Path(td) / "o2.json"
        p_in.write_bytes(raw)
        import subprocess
        for target in (p_out1, p_out2):
            r = subprocess.run([sys.executable, "-m", "domains.lubricant.compute.doe.engine", str(p_in), str(target)],
                               cwd=str(ROOT), capture_output=True)
            assert r.returncode == 0, r.stderr.decode()[:400]
        assert p_out1.read_bytes() == p_out2.read_bytes()
    print("PASS: factorial channel deterministic double run byte equal")

    # 7. Mixture non-regression: legacy gold envelope reproduced byte-for-byte under
    #    the same EOL convention the suite uses (CRLF checkout is a pre-existing
    #    environment artefact, so compare LF-normalised).
    gold_in = ROOT / "fixtures/compute/doe-gold-input.json"
    gold_out = ROOT / "fixtures/compute/doe-gold-output.json"
    raw_lf = gold_in.read_bytes().replace(b"\r\n", b"\n")
    legacy = generate_doe(json.loads(raw_lf.decode("utf-8")), raw_lf)
    assert legacy["status"] == "OK"
    mine = (json.dumps(legacy, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    assert mine.replace(b"\r\n", b"\n") == gold_out.read_bytes().replace(b"\r\n", b"\n"), "mixture envelope regressed"
    assert legacy["input_digest"] == "fcf5cd8a0c764f28ce7fbdbc8568fd3fd6b0a3229a0e7ef257a77572b672e9a8"
    print("PASS: legacy mixture envelope non-regression")

    # 8. Fail-closed rejections.
    def rejected(payload, needle):
        env = generate_doe(payload)
        assert env["status"] == "REJECTED", (needle, env["status"])
        assert any(needle in reason for reason in env["rejection_reasons"]), (needle, env["rejection_reasons"])
        return env

    rejected(make_factor_input([factor("A", 1, 2), factor("B", 1, 2)], "TAGUCHI_ROBUST"),
             "TAGUCHI_ROBUST")
    rejected(make_factor_input([factor("A", 1, 2), factor("B", 1, 2)], "FULL_FACTORIAL", target_runs=12),
             "target_runs")
    rejected(make_factor_input([factor("A", 1, 2)], "FULL_FACTORIAL"), "at least two")
    rejected(make_factor_input([factor("A", 5, 1), factor("B", 1, 2)], "FULL_FACTORIAL"),
             "strictly increasing")
    rejected(make_factor_input([factor("A", 1, 2, role="WHOLE_PLOT"), factor("B", 1, 2, role="WHOLE_PLOT")],
                               "SPLIT_PLOT"), "SUB_PLOT")
    rejected(make_factor_input([factor("A", 1, 2, role="SUB_PLOT"), factor("B", 1, 2, role="SUB_PLOT")],
                               "SPLIT_PLOT"), "WHOLE_PLOT")
    rejected(make_factor_input([factor("A", 1, 2), factor("B", 1, 2)], "FRACTIONAL_FACTORIAL"),
             "3..7")
    # 3-level factor is a contract-level rejection (levels maxItems 2)
    three_level = make_factor_input([factor("A", 1, 2), factor("B", 1, 2)], "FULL_FACTORIAL")
    three_level["factors"][0] = {"factor_id": "A", "factor_type": "CONTINUOUS",
                                 "role": "WHOLE_PLOT", "levels": [1, 2, 3]}
    rejected(three_level, "too long")
    print("PASS: fail-closed rejections")

    print("ALL PASS: WP-04a factorial channel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
