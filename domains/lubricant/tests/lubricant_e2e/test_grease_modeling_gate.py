"""Focused end-to-end gate test for the statistical-analysis MODEL_BUILT precondition.

Two product-code defects recorded by ``tests/lubricant_e2e/test_precision_grease_chain.py``
(and by ``test_inner_loop_iteration.py``'s MODEL_BUILT probe) are fixed inside
``skills/statistical-analysis/scripts/preflight_statistical_analysis.py``. This file pins
both fixes and the boundary of each:

1. **The GO requirement is a VERDICT requirement, so it now applies per artifact kind.**
   The generic upstream loop used to demand ``decision: GO`` from every supplied artifact,
   including the precision-grease ``bench_test`` record. That record's own contract fixes
   its decision to UNDECIDED ("a single bench run is a record, not a verdict",
   ``skills/experiment-import/scripts/bench_test_policy.py``:44-46 and :410-412, written at
   :458), so MODEL_BUILT was unreachable on the very route that owns bench_test. The
   preflight now exempts exactly the record artifacts (``RECORD_UPSTREAM``) and keeps the
   requirement on every verdict-carrying artifact.

2. **The grease precondition is read from the charter's project_type, not from the request
   shape.** A ``PRECISION_GREASE_DEV`` project whose request omitted the four inner-loop
   keys used to fall through to the oil path and be accepted (fail-open). It now HOLDs,
   naming every missing inner-loop artifact; a mixed request (only some of the four) HOLDs
   too. The old eleven-key shape test is kept as an additional trigger, so it can only ever
   add enforcement.

Fixture provenance: ``fixtures/statistical-analysis/grease-modeling-gate/`` is a chain for
project PGD-B1-001 produced by the pack's own producers, not hand-written JSON:
``project/challenge/failure_ctq/test_method/design_space`` are the recorded
``fixtures/precision-grease`` artifacts, ``experiment_design`` is a doe-design output,
``experiment`` and ``bench_test`` are experiment-import outputs, ``batch``/``sample`` come
from grease-batch, ``screening`` from grease-screening and ``variance`` from
variance-assessment. Because ``bench_test.json`` is the producer's own output, its
UNDECIDED decision is the contract's value, not this test's choice.

Cases (numbered as in the fix request):

  (a) grease project + all eleven keys + bench_test UNDECIDED -> READY, and the record is
      then built and validated end to end (pre-fix this HOLDed with
      "bench_test_artifact must have decision GO");
  (b) the same grease project with the four inner-loop keys omitted -> HOLD naming all
      four; a partial (mixed) request -> HOLD as well;
  (c) a verdict-carrying grease upstream (variance) at HOLD -> still HOLD; a
      verdict-carrying oil upstream (test_method) at HOLD -> still HOLD, so the fix did
      not loosen the requirement anywhere it applies;
  (d) the oil route's seven-key request -> READY, byte-for-byte the pre-fix output for the
      same input, and its HOLD output with a HOLD method is byte-for-byte the pre-fix
      output too (frozen below; captured from the pre-fix preflight in the fixing session
      and re-verified against a faithful reconstruction of it).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "statistical-analysis" / "scripts"
PREFLIGHT = SCRIPTS / "preflight_statistical_analysis.py"
BUILDER = SCRIPTS / "build_model_artifact.py"
VALIDATOR = SCRIPTS / "validate_model_artifact.py"
SCHEMAS = ROOT / "schemas"
GREASE_FIXTURES = ROOT / "fixtures" / "statistical-analysis" / "grease-modeling-gate"
OIL_FIXTURES = ROOT / "fixtures" / "statistical-analysis"
PROJECT_ID = "PGD-B1-001"
CTQ_ID = "CTQ-PG-B1-001"
METHOD_ID = "TM-PG-B1-001"
MARKER = "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE"

GREASE_INNER_KEYS = ("batch_artifact", "screening_artifact", "bench_test_artifact", "variance_artifact")
GREASE_UPSTREAM = (
    ("project_artifact", "project.json", "project"),
    ("challenge_artifact", "challenge.json", "challenge"),
    ("failure_ctq_artifact", "failure_ctq.json", "failure_ctq"),
    ("test_method_artifact", "test_method.json", "test_method"),
    ("design_space_artifact", "design_space.json", "design_space"),
    ("experiment_design_artifact", "experiment_design.json", "experiment_design"),
    ("experiment_artifact", "experiment.json", "experiment"),
    ("batch_artifact", "batch.json", "batch"),
    ("screening_artifact", "screening.json", "screening"),
    ("bench_test_artifact", "bench_test.json", "bench_test"),
    ("variance_artifact", "variance.json", "variance"),
)
OIL_FIXTURE_NAMES = {
    "project_artifact": "project-active.json",
    "challenge_artifact": "challenge-defined.json",
    "failure_ctq_artifact": "failure-ctq-defined.json",
    "test_method_artifact": "test-method-qualified.json",
    "design_space_artifact": "design-space-defined.json",
    "experiment_design_artifact": "experiment-design.json",
    "experiment_artifact": "experiment-running.json",
}

# Frozen pre-fix outputs for the oil route (same input, pre-fix revision). The oil path is
# required to stay byte-for-byte identical, so these are compared verbatim.
OIL_READY_OUTPUT = "READY: input can form one MODEL_BUILT request only"
# This HOLD output is produced under a state this test manufactures, not by the
# fixtures as stored. oil_workspace() overwrites the three stored HOLD upstreams
# (test_method.json, experiment_design.json, experiment.json) to decision GO -- the
# same simulation test_phase3_chain performs -- while the other four are already GO in
# the fixtures, so the manufactured baseline is GO throughout and READY. case_a_and_d
# then flips only the copied test_method back to HOLD and expects exactly this string.
# It therefore describes the test-simulated GO baseline with one record held, and
# deliberately does NOT represent the fixtures' real recorded state, in which
# test_method.json is itself decision=HOLD.
OIL_HOLD_METHOD_OUTPUT = (
    "HOLD: missing or invalid: test_method_artifact must have decision GO; no artifact generated"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(script), *map(str, arguments)],
        cwd=SCRIPTS, capture_output=True, text=True,
    )


def output(result: subprocess.CompletedProcess) -> str:
    return (result.stdout + result.stderr).strip()


def schema_errors(kind: str, instance: object) -> list[str]:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = read_json(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = read_json(SCHEMAS / f"{kind}.schema.json")
    return [error.message for error in Draft202012Validator(schema, registry=registry).iter_errors(instance)]


def stage_grease_workspace(workspace: Path) -> dict[str, str]:
    """Copy the producer-built PGD-B1-001 chain into the workspace, canonical names."""
    paths = {}
    for key, name, _kind in GREASE_UPSTREAM:
        shutil.copyfile(GREASE_FIXTURES / name, workspace / name)
        paths[key] = name
    return paths


def grease_request() -> dict:
    return {
        "project_artifact": "project.json",
        "challenge_artifact": "challenge.json",
        "failure_ctq_artifact": "failure_ctq.json",
        "test_method_artifact": "test_method.json",
        "design_space_artifact": "design_space.json",
        "experiment_design_artifact": "experiment_design.json",
        "experiment_artifact": "experiment.json",
        "batch_artifact": "batch.json",
        "screening_artifact": "screening.json",
        "bench_test_artifact": "bench_test.json",
        "variance_artifact": "variance.json",
        "analysis": {
            "model_id": "MODEL-PG-B1-001",
            "requested_analyses": ["ANOVA", "REGRESSION", "RESIDUAL"],
            "response_references": [{"ctq_reference": CTQ_ID, "test_method_reference": METHOD_ID}],
            "evidence": [
                {
                    "evidence_id": "E-M-PG-B1-001",
                    "statement": f"Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: analysis scope "
                                 "supplied for contract validation only.",
                    "source": "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION",
                    "status": "ASSUMED",
                }
            ],
        },
    }


def oil_workspace(workspace: Path) -> dict:
    """The oil route's seven upstreams, simulated to GO exactly as test_phase3_chain does."""
    request: dict = {}
    for key, name in OIL_FIXTURE_NAMES.items():
        value = read_json(OIL_FIXTURES / name)
        if key in ("test_method_artifact", "experiment_design_artifact", "experiment_artifact"):
            value.update({"evidence_scope": "PHYSICAL", "decision": "GO"})
            value["evidence"][0].update({"statement": MARKER, "source": MARKER})
            if key == "test_method_artifact":
                value["qualification_status"] = "QUALIFIED"
            if key == "experiment_artifact":
                value["doe_output_reference"] = {
                    "engine_name": "doe",
                    "engine_version": "simulated-contract-v1",
                    "input_digest": "a" * 64,
                    "output_digest": "a" * 64,
                }
                for entry in value["runs"]:
                    entry["formula_reference"] = "SIMULATED-FORMULA-001"
                    entry["doe_point_reference"] = {"run_index": 1}
                    entry["execution_provenance"] = {
                        "executed_at": "2026-08-25T09:30:00+08:00",
                        "operator_reference": MARKER,
                        "instrument_reference": MARKER,
                        "calibration_reference": MARKER,
                        "raw_record_reference": MARKER,
                    }
                    for response in entry["response_measurements"]:
                        response["method_reference"] = {"method_id": "TM-DOE-001", "qualification_reference": MARKER}
        else:
            value["evidence"][0].update({"statement": MARKER, "source": MARKER})
        write_json(workspace / name, value)
        request[key] = name
    # hold-input.synthetic.json is the honest name: the three HOLD upstreams it names
    # (test-method, experiment-design, experiment) are why its own preflight result is
    # HOLD. oil_workspace() uses it only for its analysis block; the three HOLD upstream
    # fixtures are read and rewritten to GO just above.
    request["analysis"] = read_json(OIL_FIXTURES / "hold-input.synthetic.json")["analysis"]
    return request


def fixture_set_is_contract_conform() -> None:
    """Every frozen upstream is schema-valid, and the record keeps its contract decision."""
    for _key, name, kind in GREASE_UPSTREAM:
        instance = read_json(GREASE_FIXTURES / name)
        errors = schema_errors(kind, instance)
        assert errors == [], f"{name} fails {kind}.schema.json: {errors}"
        assert instance.get("project_id") == PROJECT_ID, (name, instance.get("project_id"))
    decisions = {name: read_json(GREASE_FIXTURES / name).get("decision") for _key, name, _kind in GREASE_UPSTREAM}
    assert decisions["bench_test.json"] == "UNDECIDED", decisions
    for name in ("batch.json", "screening.json", "variance.json"):
        assert decisions[name] == "GO", decisions
    print("ok fixtures: 11 producer-built upstreams are schema-valid for " + PROJECT_ID
          + "; bench_test decision=UNDECIDED, batch/screening/variance decision=GO")


def case_a_and_d(workspace: Path) -> None:
    """(a) grease 11-key -> READY -> MODEL_BUILT record; (d) oil 7-key output is frozen."""
    grease_dir = workspace / "grease"
    grease_dir.mkdir(parents=True)
    stage_grease_workspace(grease_dir)
    request_path = grease_dir / "input-model.json"
    write_json(request_path, grease_request())

    ready = run(PREFLIGHT, request_path)
    assert ready.returncode == 0, output(ready)
    assert output(ready) == "READY: input can form one MODEL_BUILT request only", output(ready)
    print("(a) grease 11-key request with bench_test UNDECIDED -> " + output(ready))

    model_path = grease_dir / "model.json"
    built = run(BUILDER, request_path, model_path)
    assert built.returncode == 0, output(built)
    validated = run(VALIDATOR, model_path)
    assert validated.returncode == 0, output(validated)
    model = read_json(model_path)
    errors = schema_errors("model", model)
    assert errors == [], errors
    assert model["stage"] == "MODEL_BUILT" and model["project_id"] == PROJECT_ID, model
    print("(a) the record is then built and validated: " + output(validated))

    oil_dir = workspace / "oil"
    oil_dir.mkdir(parents=True)
    oil_request = oil_workspace(oil_dir)
    oil_path = oil_dir / "input-model.json"
    write_json(oil_path, oil_request)
    oil_ready = run(PREFLIGHT, oil_path)
    assert oil_ready.returncode == 0, output(oil_ready)
    assert output(oil_ready) == OIL_READY_OUTPUT, output(oil_ready)

    method_path = oil_dir / OIL_FIXTURE_NAMES["test_method_artifact"]
    method = read_json(method_path)
    method["decision"] = "HOLD"
    write_json(method_path, method)
    oil_hold = run(PREFLIGHT, oil_path)
    assert oil_hold.returncode != 0, output(oil_hold)
    assert output(oil_hold) == OIL_HOLD_METHOD_OUTPUT, output(oil_hold)
    print("(d) oil 7-key request: READY output and HOLD output are byte-for-byte the frozen "
          "pre-fix outputs")


def case_b(workspace: Path) -> None:
    """(b) grease project missing the four inner-loop keys (and a mixed request) -> HOLD."""
    grease_dir = workspace / "grease"
    grease_dir.mkdir(parents=True)
    stage_grease_workspace(grease_dir)
    full = grease_request()

    seven = {key: value for key, value in full.items() if key not in GREASE_INNER_KEYS}
    assert len(seven) == 8  # seven upstream keys + analysis
    seven_path = grease_dir / "input-model-seven.json"
    write_json(seven_path, seven)
    result = run(PREFLIGHT, seven_path)
    assert result.returncode != 0, output(result)
    text = output(result)
    for key in GREASE_INNER_KEYS:
        assert f"{key} is required on the PRECISION_GREASE_DEV route" in text, text
    assert text.startswith("HOLD:") and "no artifact generated" in text, text
    print("(b) grease 7-key request -> " + text)

    mixed = {key: value for key, value in full.items()
             if key not in ("screening_artifact", "bench_test_artifact")}
    mixed_path = grease_dir / "input-model-mixed.json"
    write_json(mixed_path, mixed)
    result = run(PREFLIGHT, mixed_path)
    assert result.returncode != 0, output(result)
    text = output(result)
    assert "input must contain only required upstream artifact paths and analysis" in text, text
    assert "screening_artifact is required on the PRECISION_GREASE_DEV route" in text, text
    assert "bench_test_artifact is required on the PRECISION_GREASE_DEV route" in text, text
    print("(b) grease mixed request (batch+variance only) -> " + text)


def case_c(workspace: Path) -> None:
    """(c) a verdict-carrying grease upstream at HOLD still HOLDs (nothing was loosened)."""
    grease_dir = workspace / "grease"
    grease_dir.mkdir(parents=True)
    stage_grease_workspace(grease_dir)
    request_path = grease_dir / "input-model.json"
    write_json(request_path, grease_request())

    variance_path = grease_dir / "variance.json"
    variance = read_json(variance_path)
    variance["decision"] = "HOLD"
    variance["next_action"] = "Hold: the round's difference is not released."
    write_json(variance_path, variance)
    result = run(PREFLIGHT, request_path)
    assert result.returncode != 0, output(result)
    text = output(result)
    assert "variance_artifact must have decision GO" in text, text
    assert "bench_test_artifact must have decision GO" not in text, text
    print("(c) grease 11-key with variance decision=HOLD -> " + text)


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        fixture_set_is_contract_conform()
        case_a_and_d(workspace / "a-d")
        case_b(workspace / "b")
        case_c(workspace / "c")
    print("PASS: statistical-analysis MODEL_BUILT gate — bench_test UNDECIDED admits the grease "
          "chain, the four inner-loop keys are required by project_type (fail-closed), verdict "
          "upstreams still require GO, and the oil route's outputs are byte-for-byte unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
