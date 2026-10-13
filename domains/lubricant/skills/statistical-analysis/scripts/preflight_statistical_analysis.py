"""Reject incomplete statistical-analysis requests before a MODEL_BUILT artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from statistical_analysis_policy import grease_route as routes_as_grease_route, has_gap


ROOT = Path(__file__).resolve().parents[1]
# ADDITIVE (step 12, PRECISION_GREASE_DEV): the four upstream artifact types named by
# the plan (batch / screening / bench_test / variance) are appended AFTER the seven
# original entries. Nothing existing is removed or reordered, so every oil route keeps
# exactly the upstream list it had; the new entries are only ever required on the
# grease route (see UPSTREAM_GREASE and the project-type route gate below).
# TWO FIXES against the request shape deciding the validation (step 3 of the E2E chain):
#   1. the GO requirement is applied per artifact KIND (verdict vs record, RECORD_UPSTREAM),
#      because bench_test carries UNDECIDED by contract and no oil route uses it; and
#   2. the grease precondition is read from the charter's project_type, so a grease project
#      that omits the four inner-loop keys HOLDs instead of falling through to the oil path.
SCHEMAS = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "batch.schema.json", "screening.schema.json", "bench_test.schema.json", "variance.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"), ("experiment_artifact", "experiment.schema.json", "EXPERIMENT_RUNNING"), ("batch_artifact", "batch.schema.json", "BATCH_PRODUCED"), ("screening_artifact", "screening.schema.json", "SCREENING_PASSED"), ("bench_test_artifact", "bench_test.schema.json", "BENCH_TESTED"), ("variance_artifact", "variance.schema.json", "VARIANCE_ASSESSED"))
# Upstream entries the six oil routes use. Kept as the original seven, verbatim, so an
# oil request is validated against exactly the list it was validated against before.
UPSTREAM_OIL = UPSTREAM[:7]
# Upstream entries the precision-grease inner loop adds. Required only when the
# supplied project charter routes as PRECISION_GREASE_DEV; on any other route they are
# neither required nor read, which is what keeps the oil paths byte-for-byte unchanged.
UPSTREAM_GREASE = UPSTREAM[7:]
# Which upstream artifacts may be asked for ``decision: GO``, and which may not.
#
# ``decision: GO`` is a VERDICT requirement, so it is only meaningful for an artifact
# whose own contract derives a GO/HOLD verdict from the record it carries: for those,
# a non-GO value (HOLD) is a legitimate producer output that this gate must refuse.
# An artifact whose contract records an observation instead is exempt, because demanding
# GO from it refuses the very artifact its producer is required to write.
#
# The eleven upstream artifacts, judged by what their own producers do:
#
#   * bench_test_artifact - RECORD (exempt). Its contract fixes ``decision`` to
#     UNDECIDED: bench_test_policy.py:410-412 ("The decision is UNDECIDED on purpose: a
#     single bench run is a record, and whether the round's difference is real is decided
#     at Step 12 (variance-assessment)"), written at bench_test_policy.py:458, and its
#     module docstring (bench_test_policy.py:44-46) says the same. Requiring GO from it
#     made MODEL_BUILT unreachable on the one route that owns bench_test.
#   * test_method_artifact - VERDICT. qualification_policy.py:221: "GO" if qualified else "HOLD".
#   * design_space_artifact - VERDICT. design_space_policy.py:173: "GO" if ready else "HOLD".
#   * experiment_design_artifact - VERDICT. doe_design_policy.py:96 and :135: "GO" if ready else "HOLD".
#   * batch_artifact - VERDICT. grease_batch_policy.py:669: decision = "GO" if not blockers else "HOLD".
#   * screening_artifact - VERDICT. grease_screening_policy.py:446: decision = "GO" if not blockers else "HOLD".
#   * variance_artifact - VERDICT. variance_assessment_policy.py:742-746: GO exactly for the
#     releasing verdict, HOLD otherwise (a produced HOLD record is legitimate).
#   * project_artifact, challenge_artifact, failure_ctq_artifact, experiment_artifact -
#     their producers fix the decision to GO (build_duty_challenge_artifact.py:64,
#     build_failure_ctq_artifact.py:79, preflight_experiment_import.py:134; the charter is
#     caller-assembled per project-definition/SKILL.md Step 2 and its validator accepts
#     only the contract), so a non-GO value there can only be a hand-edited artifact. All
#     four sit on the six oil routes, and keeping the requirement on them is what leaves
#     those routes' validation exactly as it was; it stays.
#
# bench_test is also the only exempt artifact that sits on no oil route:
# contracts/state-machine.json declares BENCH_TESTED only under PRECISION_GREASE_DEV,
# which is why exempting it cannot move any oil path.
RECORD_UPSTREAM = frozenset({"bench_test_artifact"})
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"analysis"}
OIL_INPUT_FIELDS = {key for key, _, _ in UPSTREAM_OIL} | {"analysis"}
REQUEST_FIELDS = {"model_id", "requested_analyses", "response_references", "evidence"}


def schema_dir() -> Path:
    canonical = ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMAS) else ROOT / "references"


def read_path(value: object, input_path: Path) -> Path | None:
    return input_path.parent / value if isinstance(value, str) and value.strip() else None


def loaded_schemas() -> tuple[dict[str, dict], Registry]:
    directory = schema_dir()
    schemas = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMAS}
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def load_artifact(path: Path | None, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    if path is None:
        return [label], None
    try:
        schemas, registry = loaded_schemas()
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(schemas[schema_name], registry=registry).iter_errors(value)]
    return errors, value if not errors else None


def request_errors(request: object, project_id: str, evidence_scope: str | None = None) -> list[str]:
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        return ["analysis must contain only model_id, requested_analyses, response_references, and evidence"]
    candidate = {"schema_version": "0.1.0", "artifact_type": "model", "project_id": project_id or "input-project", "stage": "MODEL_BUILT", "evidence_scope": evidence_scope, "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": "GO", "next_action": "input", "experiment_reference": "input-experiment", "design_space_reference": "input-design-space", "test_method_references": ["input-method"], "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **request}
    schemas, registry = loaded_schemas()
    return [f"analysis: {error.message}" for error in Draft202012Validator(schemas["model.schema.json"], registry=registry).iter_errors(candidate)]


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    # The input key set is decided by the route, not by the widest list: an oil
    # request supplies exactly the seven original keys it always did, and the
    # grease route additionally supplies the four inner-loop artifacts. Requiring
    # the union on both routes would reject every oil request.
    supplied = set(data)
    if supplied not in (OIL_INPUT_FIELDS, INPUT_FIELDS):
        errors.append("input must contain only required upstream artifact paths and analysis")
    for key, schema, stage in UPSTREAM:
        if key not in supplied:
            continue
        item_errors, artifact = load_artifact(read_path(data.get(key), input_path), schema, key)
        errors.extend(item_errors)
        artifacts[key] = artifact
        if artifact and artifact.get("stage") != stage:
            errors.append(f"{key} must be stage {stage}")
        if artifact and key not in RECORD_UPSTREAM and artifact.get("decision") != "GO":
            errors.append(f"{key} must have decision GO")
    # The grease precondition is keyed on the supplied charter's OWN project_type, never
    # on the request's key shape: a PRECISION_GREASE_DEV project whose request omits the
    # four inner-loop keys (or supplies only some of them) must HOLD, because the four are
    # that route's modeling precondition. The old eleven-key shape test is kept as an
    # additional trigger, so it can only ever ADD enforcement; an eleven-key request is
    # validated at least as strictly as it was before.
    grease_route = supplied == INPUT_FIELDS or routes_as_grease_route(artifacts.get("project_artifact"))
    if grease_route:
        # The four inner-loop artifacts are the grease route's own precondition:
        # without a variance assessment there is nothing that says whether the
        # round's difference is real, and modeling it would fit noise.
        for key, schema, stage in UPSTREAM_GREASE:
            if artifacts.get(key) is None:
                errors.append(f"{key} is required on the PRECISION_GREASE_DEV route")
    # The seven original upstream artifacts are read BY NAME, not unpacked
    # positionally: UPSTREAM grew to eleven entries for the precision-grease
    # inner loop, and a positional unpack silently becomes a crash the moment a
    # list grows (it did, and this comment is why it will not again). The four
    # additions are read by name where they are needed.
    project = artifacts["project_artifact"]
    challenge = artifacts["challenge_artifact"]
    failure = artifacts["failure_ctq_artifact"]
    method = artifacts["test_method_artifact"]
    design_space = artifacts["design_space_artifact"]
    experiment_design = artifacts["experiment_design_artifact"]
    experiment = artifacts["experiment_artifact"]
    oil_upstream = (project, challenge, failure, method, design_space, experiment_design, experiment)
    available = [item for item in oil_upstream if item]
    scopes = {item.get("evidence_scope") for item in (method, experiment_design, experiment) if item is not None}
    if scopes - {"SYNTHETIC", "PHYSICAL"} or len(scopes) != 1:
        errors.append("test_method, experiment_design, and experiment evidence_scope values must exist and match")
    if project and project.get("status") != "ACTIVE": errors.append("project_artifact must have status ACTIVE")
    if len(available) == len(oil_upstream) and len({item.get("project_id") for item in available}) != 1: errors.append("all upstream artifact project_id values must match")
    if challenge and failure and failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if failure and method and method.get("target_failure_reference") != failure.get("failure_id"): errors.append("test_method_artifact failure link is invalid")
    if method and (method.get("qualification_status") != "QUALIFIED" or not ({"D", "P"} & set(method.get("role", [])))): errors.append("test_method_artifact must be qualified D or P")
    if design_space and method and method.get("method_id") not in (design_space.get("qualified_test_method_references") or []): errors.append("design_space_artifact method link is invalid")
    if experiment_design and design_space and experiment_design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    if experiment_design and method and method.get("method_id") not in (experiment_design.get("test_method_references") or []): errors.append("experiment_design_artifact method link is invalid")
    if experiment and experiment_design and experiment.get("experiment_design_reference") != experiment_design.get("experiment_design_id"): errors.append("experiment_artifact design link is invalid")
    if experiment and design_space and experiment.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_artifact design-space link is invalid")
    if experiment and method and method.get("method_id") not in (experiment.get("test_method_references") or []): errors.append("experiment_artifact method link is invalid")
    # WP-07: the modeling entry stays DOE-only. Non-DOE experiment records
    # (APPLICATION_FIELD / CONFIRMATORY_NON_DOE) are legitimate imports but are
    # explicitly excluded here, naming the record and the reason. A record
    # without an explicit evidence_class is DOE_POINT by contract default.
    if experiment and experiment.get("evidence_class", "DOE_POINT") != "DOE_POINT":
        errors.append(
            f"experiment_artifact {experiment.get('experiment_id')} has evidence_class "
            f"{experiment.get('evidence_class')} and is excluded from the modeling entry; "
            "only DOE_POINT records may be modeled (non-DOE evidence never enters statistical analysis)"
        )
    request = data.get("analysis")
    errors.extend(request_errors(request, project.get("project_id", "") if project else "", experiment.get("evidence_scope") if experiment else None))
    if not isinstance(request, dict): return errors
    if has_gap(request): errors.append("analysis.evidence contains GAP")
    ctqs = {item.get("ctq_id"): item for item in failure.get("ctqs", []) if isinstance(item, dict)} if failure else {}
    observed = {response.get("ctq_reference") for run in experiment.get("runs", []) for response in run.get("response_measurements", []) if isinstance(response, dict)} if experiment else set()
    for response in request.get("response_references", []):
        if not isinstance(response, dict): continue
        ctq_id = response.get("ctq_reference")
        if ctq_id not in ctqs or not design_space or ctq_id not in design_space.get("ctq_references", []) or ctq_id not in observed: errors.append(f"analysis response {ctq_id} is not a linked observed CTQ")
        if not method or response.get("test_method_reference") != method.get("method_id") or method.get("method_id") not in ctqs.get(ctq_id, {}).get("test_references", []): errors.append("analysis response must link the qualified method")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_statistical_analysis.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: input can form one MODEL_BUILT request only"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
