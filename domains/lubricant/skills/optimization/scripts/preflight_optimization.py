"""Reject incomplete optimization requests before an OPTIMIZED artifact is written.

ADDITIVE (precision-grease step 14, plan section 4.4.3 items 3-3/3-4): the grease
route appends the variance artifact to SCHEMAS/UPSTREAM and reads the model's
applicability boundary (trust region) from the request, because the frozen model
artifact contract has no slot for it. Nothing existing is removed or reordered, so
every oil request is validated against exactly the list it was validated against
before; the appended entry and the trust-region key are only ever required when the
supplied charter routes as PRECISION_GREASE_DEV.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from optimization_policy import (
    ADMISSIBLE_VARIANCE_VERDICTS,
    BLOCKING_VARIANCE_VERDICTS,
    MODEL_TRUST_REGION_INPUT_FIELD,
    default_note,
    grease_route,
    has_gap,
    resolve_objective_type,
    stage_for,
    trust_region_errors,
    trust_region_from_boundary,
    trust_region_summary,
)


ROOT = Path(__file__).resolve().parents[1]
# The appended schema and upstream entry are the grease route's own references: the
# variance assessment that says whether the round's difference is real. The model's
# applicability boundary (trust region) travels input-side (see MODULE docstring).
SCHEMAS = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json", "variance.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"), ("experiment_artifact", "experiment.schema.json", "EXPERIMENT_RUNNING"), ("model_artifact", "model.schema.json", "MODEL_BUILT"), ("variance_artifact", "variance.schema.json", "VARIANCE_ASSESSED"))
# Upstream entries the six oil routes use. Kept as the original eight, verbatim.
UPSTREAM_OIL = UPSTREAM[:8]
# The entry the precision-grease inner loop appends. Required only on that route.
UPSTREAM_GREASE = UPSTREAM[8:]
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"optimization"}
OIL_INPUT_FIELDS = {key for key, _, _ in UPSTREAM_OIL} | {"optimization"}
# The grease route additionally carries the model's applicability boundary. It is an
# INPUT-side field: schemas/model.schema.json is closed (unevaluatedProperties false)
# and the batch-3 scope does not permit changing it.
GREASE_INPUT_FIELDS = INPUT_FIELDS | {MODEL_TRUST_REGION_INPUT_FIELD}
OIL_INPUT_FIELDS_WITH_REGION = OIL_INPUT_FIELDS | {MODEL_TRUST_REGION_INPUT_FIELD}
# The one upstream key the grease route may legally omit: CHALLENGES_DEFINED is on no
# type_route, so that route records the Challenge Map link as UNROUTED:<project_id> on
# the failure record instead of producing an out-of-route artifact. (The request field
# the policy module names is MODEL_TRUST_REGION_INPUT_FIELD; the constant the plan called
# GREASE_INPUT_FIELDS_WITH_REGION does not exist here and is not introduced -- the two
# grease shapes are derived instead, so a typo cannot silently add a shape.)
CHALLENGE_KEY = "challenge_artifact"
GREASE_NO_CHALLENGE_FIELDS = GREASE_INPUT_FIELDS - {CHALLENGE_KEY}
GREASE_NO_CHALLENGE_FIELDS_WITH_REGION = GREASE_NO_CHALLENGE_FIELDS | {MODEL_TRUST_REGION_INPUT_FIELD}
# Provenance of the recorded gap: the route contract is what says the stage is on no
# type_route, so it is what the recorded evidence cites.
ROUTE_CONTRACT_SOURCE = "contracts/state-machine.json"
REQUEST_FIELDS = {"optimization_id", "objective_type", "objectives", "methods", "evidence"}


def schema_dir() -> Path:
    canonical = ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMAS) else ROOT / "references"


def load_schemas() -> tuple[dict[str, dict], Registry]:
    directory = schema_dir(); schemas = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMAS}; registry = Registry()
    for schema in schemas.values(): registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


# E-1 (E6=A): the variance artifact is judged by its VERDICT, not by ``decision == GO``.
# The releasing verdict is the only one ``variance_assessment_policy.decision_for`` gives
# GO; a NO_DETECTABLE_DIFFERENCE round ("a capable design found nothing") is admissible to
# the optimization and its producer correctly writes HOLD, so a blanket GO demand would
# refuse a legitimate record. The two blocking verdicts stay refused by
# ``grease_reference_errors`` (its first-line branch below), which is why this dispatch
# only has to keep the decision honest for the admissible verdicts -- without it the two
# consumers could disagree about the same record.
RELEASING_VARIANCE_VERDICT = "CONSISTENT_DIFFERENCE"
NO_DIFFERENCE_VERDICT = "NO_DETECTABLE_DIFFERENCE"


def variance_gate_errors(artifact: dict) -> list[str]:
    """Verdict-level decision honesty for a variance record (E-1 / E6=A)."""
    verdict = artifact.get("verdict")
    decision = artifact.get("decision")
    if verdict == RELEASING_VARIANCE_VERDICT and decision != "GO":
        return ["variance_artifact must have decision GO"]
    if verdict == NO_DIFFERENCE_VERDICT and decision == "GO":
        return [
            "variance_artifact must not carry decision GO: NO_DETECTABLE_DIFFERENCE releases no "
            "model update (it is admissible to the optimization but is not a difference); only "
            "CONSISTENT_DIFFERENCE carries GO"
        ]
    return []


def read_artifact(value: object, input_path: Path, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    if not isinstance(value, str) or not value.strip(): return [label], None
    try:
        schemas, registry = load_schemas(); artifact = json.loads((input_path.parent / value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(schemas[schema_name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def charter_project_type(data: object, input_path: Path) -> object:
    """The route marker off the request's own charter, or None when it cannot be read.

    Read before the key-set verdict because whether the challenge key may be absent at
    all is a property of the route. An unreadable or absent charter yields None, which
    ``grease_route`` reads as "not the grease route": the request then gets exactly the
    pre-change key-set verdict.
    """
    if not isinstance(data, dict):
        return None
    value = data.get("project_artifact")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        project = json.loads((input_path.parent / value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return project.get("project_type") if isinstance(project, dict) else None


def unrouted_statement(project_id: object) -> str:
    """The recorded-gap sentence. The preflight prints it, the artifact's evidence carries it."""
    return (
        "challenge_artifact not supplied on the PRECISION_GREASE_DEV route "
        f"(CHALLENGES_DEFINED is on no type_route); the Challenge Map link is recorded as "
        f"UNROUTED:{project_id}"
    )


def challenge_note(project_id: object) -> str:
    """The one audible line a grease run without a challenge artifact prints."""
    return "NOTE: " + unrouted_statement(project_id)


def unrouted_evidence(project_id: object) -> dict:
    """The ASSUMED evidence item that records the missing challenge as a route property.

    Never GAP: several preflights refuse a GAP-status item outright, and this is not an
    unresolved gap in the record - it is a recorded property of the route.
    """
    return {
        "evidence_id": f"EV-UNROUTED-{project_id}",
        "statement": unrouted_statement(project_id),
        "source": ROUTE_CONTRACT_SOURCE,
        "status": "ASSUMED",
    }


def grease_without_challenge(data: object, project: object) -> bool:
    """True for the grease route's legal no-challenge shape, and nothing else.

    Strictly gated: a non-grease charter, or a grease request that did supply a challenge
    artifact, returns False and every caller keeps the output it had.
    """
    return (
        isinstance(data, dict)
        and CHALLENGE_KEY not in data
        and grease_route(project)
    )


def request_errors(request: object, project_id: str, evidence_scope: str | None = None, stage: str = "OPTIMIZED", grease: bool = False) -> list[str]:
    # The grease route may OMIT objective_type: the policy layer fills the
    # CONSTRAINT_SATISFACTION default (cost is a constraint, never an objective weighed
    # against performance). The oil routes keep demanding it explicitly, unchanged.
    allowed = (REQUEST_FIELDS, REQUEST_FIELDS - {"objective_type"}) if grease else (REQUEST_FIELDS,)
    if not isinstance(request, dict) or set(request) not in allowed:
        return ["optimization must contain only optimization_id, objective_type, objectives, methods, and evidence"]
    candidate = {"schema_version": "0.1.0", "artifact_type": "optimization", "project_id": project_id or "input-project", "stage": stage, "evidence_scope": evidence_scope, "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": "GO", "next_action": "input", "model_reference": "input-model", "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **request}
    resolved = resolve_objective_type(request, grease)
    if resolved is not None:
        candidate["objective_type"] = resolved
    schemas, registry = load_schemas()
    return [f"optimization: {error.message}" for error in Draft202012Validator(schemas["optimization.schema.json"], registry=registry).iter_errors(candidate)]


def grease_reference_errors(variance: dict | None, boundary: object) -> list[str]:
    """The two references the grease route adds: the variance gate and the trust region.

    A round whose variance verdict is UNDERPOWERED or REPLICATE_INCONSISTENT must not be
    optimized: the design could not resolve the question, so optimizing it optimizes
    noise. And the model's applicability boundary must be declared and numerically
    enforceable, because a recommendation outside it is an extrapolation.
    """
    errors: list[str] = []
    verdict = variance.get("verdict") if isinstance(variance, dict) else None
    if variance is None:
        errors.append("variance_artifact is required on the PRECISION_GREASE_DEV route: without a variance assessment there is no record of whether the round's difference is real")
    elif verdict in BLOCKING_VARIANCE_VERDICTS:
        errors.append(
            f"variance_artifact verdict {verdict} blocks the optimization: "
            + ("the design could not resolve the pre-registered difference, so optimizing it optimizes noise; "
               "UNDERPOWERED is never a synonym for NO_DETECTABLE_DIFFERENCE" if verdict == "UNDERPOWERED"
               else "same-arm replicates contradict, so there is no mean worth optimizing")
        )
    elif verdict not in ADMISSIBLE_VARIANCE_VERDICTS:
        errors.append(f"variance_artifact verdict {verdict!r} is not one of the four frozen values")
    if boundary is None:
        errors.append(f"{MODEL_TRUST_REGION_INPUT_FIELD} is required on the PRECISION_GREASE_DEV route: the model's applicability boundary (trust region) must accompany the request, because a recommendation outside the region the model was fitted on is an extrapolation and may never be recommended silently")
    else:
        boundary_errors = trust_region_errors(boundary)
        errors.extend(f"{MODEL_TRUST_REGION_INPUT_FIELD}: {message}" for message in boundary_errors)
        if not boundary_errors and trust_region_from_boundary(boundary) is None:
            errors.append(f"{MODEL_TRUST_REGION_INPUT_FIELD} must declare numeric lower_bounds and upper_bounds for its variables: a boundary with no enforceable box cannot be passed to the engine, and optimizing without one is refused rather than done silently")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict): return ["input must be a JSON object"]
    errors, artifacts = [], {}
    # The input key set is decided by the route, not by the widest list: an oil request
    # supplies exactly the eight original keys it always did; the grease route supplies
    # the variance assessment and the model's applicability boundary. Requiring the
    # union on both routes would reject every oil request. The grease route may also omit
    # the challenge path, because CHALLENGES_DEFINED is on no type_route.
    supplied = set(data)
    charter_type = charter_project_type(data, input_path)
    if charter_grease := grease_route({"project_type": charter_type}):
        allowed_shapes = (
            OIL_INPUT_FIELDS, OIL_INPUT_FIELDS_WITH_REGION, INPUT_FIELDS, GREASE_INPUT_FIELDS,
            GREASE_NO_CHALLENGE_FIELDS, GREASE_NO_CHALLENGE_FIELDS_WITH_REGION,
        )
    else:
        allowed_shapes = (OIL_INPUT_FIELDS, OIL_INPUT_FIELDS_WITH_REGION, INPUT_FIELDS, GREASE_INPUT_FIELDS)
    if supplied not in allowed_shapes:
        errors.append("input must contain only required upstream artifact paths and optimization")
    for key, schema, stage in UPSTREAM:
        if key not in supplied:
            continue
        item_errors, artifact = read_artifact(data.get(key), input_path, schema, key); errors.extend(item_errors); artifacts[key] = artifact
        if artifact and artifact.get("stage") != stage: errors.append(f"{key} must be stage {stage}")
        if artifact and key == "variance_artifact":
            # E-1: dispatched by verdict (see variance_gate_errors); the blocking verdicts
            # are already refused by grease_reference_errors above, so the old blanket
            # ``!= GO`` branch is skipped for this key to avoid reporting the same record
            # twice.
            errors.extend(variance_gate_errors(artifact))
        elif artifact and artifact.get("decision") != "GO": errors.append(f"{key} must have decision GO")
    # Read BY NAME, never unpacked positionally: UPSTREAM grew to nine entries for the
    # precision-grease inner loop, and a positional unpack silently becomes a crash the
    # moment a list grows.
    project = artifacts.get("project_artifact"); challenge = artifacts.get(CHALLENGE_KEY)
    failure = artifacts.get("failure_ctq_artifact"); method = artifacts.get("test_method_artifact")
    design_space = artifacts.get("design_space_artifact"); experiment_design = artifacts.get("experiment_design_artifact")
    experiment = artifacts.get("experiment_artifact"); model = artifacts.get("model_artifact")
    variance = artifacts.get("variance_artifact")
    grease = grease_route(project)
    grease_without_challenge = grease and CHALLENGE_KEY not in supplied
    if grease and variance is None:
        errors.append("variance_artifact is required on the PRECISION_GREASE_DEV route")
    if grease:
        errors.extend(grease_reference_errors(variance, data.get(MODEL_TRUST_REGION_INPUT_FIELD)))
    available = [value for value in (project, challenge, failure, method, design_space, experiment_design, experiment, model) if value]
    scopes = {value.get("evidence_scope") for value in (method, experiment_design, experiment, model) if value is not None}
    if scopes - {"SYNTHETIC", "PHYSICAL"} or len(scopes) != 1:
        errors.append("test_method, experiment_design, experiment, and model evidence_scope values must exist and match")
    if project and project.get("status") != "ACTIVE": errors.append("project_artifact must have status ACTIVE")
    if len(available) == 8 and len({value.get("project_id") for value in available}) != 1: errors.append("all upstream artifact project_id values must match")
    elif grease_without_challenge and len(available) == 7 and len({value.get("project_id") for value in available}) != 1:
        # The grease route's no-challenge shape: the same uniformity rule, over the seven
        # upstreams that do exist. Unreachable on any route that requires a challenge, so
        # the eight-key threshold above stays exactly what it was.
        errors.append("all upstream artifact project_id values must match")
    if failure and challenge and failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if method and failure and (method.get("target_failure_reference") != failure.get("failure_id") or method.get("qualification_status") != "QUALIFIED" or not ({"D", "P"} & set(method.get("role", [])))): errors.append("test_method_artifact must be linked qualified D or P")
    if design_space and method and method.get("method_id") not in (design_space.get("qualified_test_method_references") or []): errors.append("design_space_artifact method link is invalid")
    if experiment_design and design_space and experiment_design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    if experiment and experiment_design and experiment.get("experiment_design_reference") != experiment_design.get("experiment_design_id"): errors.append("experiment_artifact design link is invalid")
    if experiment and design_space and experiment.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_artifact design-space link is invalid")
    if model and experiment and model.get("experiment_reference") != experiment.get("experiment_id"): errors.append("model_artifact experiment link is invalid")
    if model and design_space and model.get("design_space_reference") != design_space.get("design_space_id"): errors.append("model_artifact design-space link is invalid")
    if model and method and method.get("method_id") not in (model.get("test_method_references") or []): errors.append("model_artifact method link is invalid")
    request = data.get("optimization"); errors.extend(request_errors(request, project.get("project_id", "") if project else "", model.get("evidence_scope") if model else None, stage_for(grease), grease))
    if not isinstance(request, dict): return errors
    if has_gap(request): errors.append("optimization.evidence contains GAP")
    if "BAYESIAN_OPTIMIZATION" in request.get("methods", []): errors.append("BAYESIAN_OPTIMIZATION is unsupported in Phase 3")
    model_responses = {item.get("ctq_reference") for item in model.get("response_references", []) if isinstance(item, dict)} if model else set()
    for objective in request.get("objectives", []):
        if isinstance(objective, dict) and objective.get("response_reference") not in model_responses: errors.append(f"optimization objective {objective.get('response_reference')} is not present in model_artifact")
    return errors


def route_notes(data: object, input_path: Path) -> list[str]:
    """Audible NOTE lines for the grease route, so a run is never silent about what it judged."""
    if not isinstance(data, dict):
        return []
    project = None
    project_reference = data.get("project_artifact")
    if isinstance(project_reference, str) and project_reference.strip():
        try:
            project = json.loads((input_path.parent / project_reference).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            project = None
    grease = grease_route(project)
    request = data.get("optimization")
    notes: list[str] = []
    if grease:
        notes.append(f"NOTE: PRECISION_GREASE_DEV route: this request will land at {stage_for(True)}")
        if CHALLENGE_KEY not in data:
            notes.append(challenge_note(project.get("project_id")) if isinstance(project, dict) else challenge_note(None))
        summary = trust_region_summary(trust_region_from_boundary(data.get(MODEL_TRUST_REGION_INPUT_FIELD)))
        if summary:
            notes.append(f"NOTE: trust region carried to the engine: {summary}")
        variance = data.get("variance_artifact")
        if isinstance(variance, str) and variance.strip():
            notes.append(f"NOTE: variance gate {variance} admits this round to the optimization")
    notes.extend(default_note(grease, request.get("objective_type") if isinstance(request, dict) else None))
    return notes


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python preflight_optimization.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: input can form one OPTIMIZED request only")
    for line in route_notes(data, path): print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
