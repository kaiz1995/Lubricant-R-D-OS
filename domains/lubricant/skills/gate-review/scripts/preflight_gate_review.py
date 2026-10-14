"""Reject incomplete Gate-review requests before a VERIFIED artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from gate_review_policy import aggregate_scope, has_gap, process_window_synthetic


ROOT = Path(__file__).resolve().parents[1]


def _ensure_naming_checker_importable() -> bool:
    """Probe the shared naming checker in both layouts (knowledge_retrieval precedent).

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside this skill's scripts
    (install_domain_skill.py maps gate-review -> check_artifact_naming.py).
    If neither candidate holds the file the preflight still runs; the naming
    contract is then unenforced here, exactly like knowledge_retrieval.
    """
    for candidate in (ROOT / "scripts", ROOT.parents[1] / "scripts"):
        if (candidate / "check_artifact_naming.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return True
    return False


_NAMING_AVAILABLE = _ensure_naming_checker_importable()

if _NAMING_AVAILABLE:
    import check_artifact_naming  # noqa: E402


def workspace_naming_errors(input_path: Path) -> list[str]:
    """Enforce the canonical-name contract on the workspace holding the input.

    The input request file lives in the workspace root, so ``input_path.parent``
    is the workspace. A bare staging directory without ``project.json`` is not
    treated as a workspace (keeps ad-hoc preflight invocations working). Every
    violation here is a HOLD: a mangled artifact name is invisible to the
    stage-gate panel, so a GO must not be issued over it.
    """
    if not _NAMING_AVAILABLE:
        return []
    workspace = input_path.parent
    if not (workspace / "project.json").is_file():
        return []
    try:
        _, violations = check_artifact_naming.check_workspace(str(workspace))
    except OSError:
        return []
    return [f"workspace naming: {violation}" for violation in violations]
SCHEMAS = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json", "gate.schema.json", "process.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"), ("experiment_artifact", "experiment.schema.json", "EXPERIMENT_RUNNING"), ("model_artifact", "model.schema.json", "MODEL_BUILT"), ("optimization_artifact", "optimization.schema.json", "OPTIMIZED"))
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"gate"}
# Defect 4 (2026-10-03): the process pair used to be structurally unreachable
# from this gate. They are OPTIONAL here (a gate may review a non-process
# project), but when submitted they are validated and their evidence_scope is
# aggregated with the rest, so a SYNTHETIC process window can no longer slip
# through on an optimization artifact's PHYSICAL label.
#
# H7/consumer (2026-10-14): the window's PROCESS-WINDOW:<window_id> reference has
# no producer-side consumer yet: design_freeze ships a schema and fixtures but no
# builder, so this gate enforces the reference's presence and format rather than
# its consumption.
PROCESS_UPSTREAM = (("process_artifact", "process.schema.json", "DESIGN_SPACE_DEFINED"), ("process_window_artifact", "process.schema.json", "PROCESS_WINDOW_DEFINED"))
OPTIONAL_INPUT_FIELDS = {key for key, _, _ in PROCESS_UPSTREAM}
# WP-14 (2026-10-13): the precision-grease route's step-14 optimization artifact
# legally lands at NON_INFERIORITY_PASSED instead of OPTIMIZED
# (schemas/optimization.schema.json enumerates both). The expected stage of that
# key is therefore dispatched on the project artifact's project_type, the charter
# being the authority.
#
# E5=A / H7 (2026-10-14): the route's step-17 fixed window likewise lands at
# PROCESS_SCALE_VALIDATED (the producing skill's GREASE_STAGE), where the oil
# routes' window keeps PROCESS_WINDOW_DEFINED -- the same constant is duplicated
# here rather than imported so this gate never reaches into another skill's tree.
# Every other key, every other project_type and an absent or unreadable project
# artifact keep the original constant, so the six oil routes and the undecidable
# case behave exactly as before.
GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"
GREASE_OPTIMIZATION_STAGE = "NON_INFERIORITY_PASSED"
GREASE_PROCESS_WINDOW_STAGE = "PROCESS_SCALE_VALIDATED"
# The one upstream key the grease route may legally omit: CHALLENGES_DEFINED is on no
# type_route, so that route records the Challenge Map link as UNROUTED:<project_id> on
# the failure record instead of producing an out-of-route artifact. Named once and used
# by the key-set verdict, the take-item loop and the project_id threshold below.
CHALLENGE_KEY = "challenge_artifact"
GREASE_NO_CHALLENGE_FIELDS = INPUT_FIELDS - {CHALLENGE_KEY}
# Provenance of the recorded gap: the route contract is what says the stage is on no
# type_route, so it is what the recorded evidence cites.
ROUTE_CONTRACT_SOURCE = "contracts/state-machine.json"


def expected_stage(key: str, stage: str, project: object) -> str:
    """Stage constant the named upstream input must carry (oil behaviour by default).

    Two keys dispatch on the charter's project_type: the step-14 optimization
    artifact (WP-14) and the step-17 process window (E5=A / H7). Every other key,
    every other project_type and an absent or unreadable project artifact keep
    the constant the caller passed in.
    """
    if isinstance(project, dict) and project.get("project_type") == GREASE_PROJECT_TYPE:
        if key == "optimization_artifact":
            return GREASE_OPTIMIZATION_STAGE
        if key == "process_window_artifact":
            return GREASE_PROCESS_WINDOW_STAGE
    return stage
REQUEST_FIELDS = {"gate_id", "scope", "gate_status", "satisfied_conditions", "unsatisfied_conditions", "evidence_gaps", "risks", "reason", "evidence"}
# WP-08: the request may also carry the optional signoff record. It stays a
# record only — no authority check happens here or downstream.
OPTIONAL_REQUEST_FIELDS = {"technical_reviewer", "reviewed_at", "approver", "approved_at", "dissent"}


def schema_dir() -> Path:
    canonical = ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMAS) else ROOT / "references"


def schemas() -> tuple[dict[str, dict], Registry]:
    directory = schema_dir(); loaded = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMAS}; registry = Registry()
    for schema in loaded.values(): registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return loaded, registry


def artifact(value: object, input_path: Path, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    if not isinstance(value, str) or not value.strip(): return [label], None
    try:
        loaded, registry = schemas(); item = json.loads((input_path.parent / value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[schema_name], registry=registry).iter_errors(item)]
    return errors, item if not errors else None


def read_charter(value: object, input_path: Path) -> dict | None:
    """The charter beside the request, or None when it is absent or unreadable.

    Read structurally rather than schema-validated: this is the pre-check that decides
    which key shape is legal, and the ``artifact`` call below still validates it against
    the contract and reports whatever it finds. An unreadable charter yields None, which
    every caller reads as "not the grease route" - the pre-change behaviour.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        charter = json.loads((input_path.parent / value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return charter if isinstance(charter, dict) else None


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
        and isinstance(project, dict)
        and project.get("project_type") == GREASE_PROJECT_TYPE
    )


# L11 follow-up (2026-10-14): the reference-material side of the route's tie. The
# original finding asked for a required reference input key plus the record in
# GREASE_CHAIN; both were refused (no reference.schema.json in SCHEMAS, the deploy
# list lacks it, and the chain fixture count is pinned). The lightweight form the
# review settled on: when the SUBMITTED test_method names the reference set it was
# qualified against, and a readable record for that id sits beside the input, the
# recorded discrimination state must not be DISCRIMINATION_EVIDENCE_INCOMPLETE.
# Zero new dependency by construction -- no new input key, no schema, no deploy-list
# entry -- because an absent record is NOT an error here: the step-5 gate hard-refuses
# the incomplete case, and this is the review gate's carry-over of that promise.
REFERENCE_ARTIFACT_TYPE = "reference"
INCOMPLETE_DISCRIMINATION_FLAG = "DISCRIMINATION_EVIDENCE_INCOMPLETE"


def reference_ruler_errors(method: object, input_path: Path) -> list[str]:
    """Reject a submitted method whose recorded reference set is incomplete."""
    if not isinstance(method, dict):
        return []
    reference_id = method.get("reference_material_reference")
    if not isinstance(reference_id, str) or not reference_id.strip():
        return []
    for path in sorted(input_path.parent.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("artifact_type") != REFERENCE_ARTIFACT_TYPE:
            continue
        if record.get("reference_id") != reference_id:
            continue
        if record.get("downstream_flag") == INCOMPLETE_DISCRIMINATION_FLAG:
            return [
                f"test_method_artifact was qualified against reference set {reference_id}, whose recorded "
                f"downstream_flag is {INCOMPLETE_DISCRIMINATION_FLAG}: a reference set that cannot resolve "
                "its Known Bad cannot serve as the discrimination ruler this gate reviews over"
            ]
        return []
    return []


def gate_request_errors(request: object, project_id: str, experiment_id: str, evidence_scope: str | None = None) -> list[str]:
    if not isinstance(request, dict) or not REQUEST_FIELDS <= set(request) or set(request) - REQUEST_FIELDS - OPTIONAL_REQUEST_FIELDS: return ["gate must contain only the required review fields"]
    candidate = {"schema_version": "0.1.0", "artifact_type": "gate", "project_id": project_id or "input-project", "stage": "VERIFIED", "evidence_scope": evidence_scope, "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": request.get("gate_status"), "next_action": "input", "experiment_reference": experiment_id or "input-experiment", **{key: value for key, value in request.items() if key != "reason"}}
    loaded, registry = schemas()
    return [f"gate: {error.message}" for error in Draft202012Validator(loaded["gate.schema.json"], registry=registry).iter_errors(candidate)]


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict): return ["input must be a JSON object"]
    errors, items = [], {}
    unexpected = set(data) - INPUT_FIELDS - OPTIONAL_INPUT_FIELDS
    # The charter is read before the key-set verdict: whether the challenge path may be
    # absent at all is a property of the route (CHALLENGES_DEFINED is on no type_route),
    # and the charter's own project_type is what decides that. Any other route, and a
    # grease request that does supply a challenge, sees the pre-existing verdict verbatim.
    charter = read_charter(data.get("project_artifact"), input_path)
    grease = isinstance(charter, dict) and charter.get("project_type") == GREASE_PROJECT_TYPE
    no_challenge_shape = grease and CHALLENGE_KEY not in data
    missing = (GREASE_NO_CHALLENGE_FIELDS if no_challenge_shape else INPUT_FIELDS) - set(data)
    if unexpected or missing:
        errors.append("input must contain only required upstream artifact paths and gate (process artifacts optional but permitted)")
    project_value = None
    for key, schema, stage in UPSTREAM:
        # The grease route's legal no-challenge state: CHALLENGES_DEFINED is on no
        # type_route, so the absent key is not reported as a missing input. The take-item
        # loop still runs for every other key, and for every other route, unchanged.
        if key == CHALLENGE_KEY and no_challenge_shape and data.get(key) is None:
            items[key] = None
            continue
        item_errors, value = artifact(data.get(key), input_path, schema, key); errors.extend(item_errors); items[key] = value
        if key == "project_artifact": project_value = value
        expected = expected_stage(key, stage, project_value)
        if value and value.get("stage") != expected: errors.append(f"{key} must be stage {expected}")
        if value and value.get("decision") != "GO": errors.append(f"{key} must have decision GO")
    for key, schema, stage in PROCESS_UPSTREAM:
        if key not in data: continue
        item_errors, value = artifact(data.get(key), input_path, schema, key); errors.extend(item_errors); items[key] = value
        expected = expected_stage(key, stage, project_value)
        if value and value.get("stage") != expected: errors.append(f"{key} must be stage {expected}")
        if value and value.get("decision") != "GO": errors.append(f"{key} must have decision GO")
    if ("process_artifact" in data) != ("process_window_artifact" in data):
        errors.append("process_artifact and process_window_artifact must be submitted together")
    project, challenge, failure, method, design_space, experiment_design, experiment, model, optimization = (items[key] for key, _, _ in UPSTREAM)
    process, process_window = items.get("process_artifact"), items.get("process_window_artifact")
    if process and project and process.get("project_reference") != project.get("project_id"):
        errors.append("process_artifact project link is invalid")
    if process_window and process and process_window.get("process_id") != process.get("process_id"):
        errors.append("process_window_artifact process link is invalid")
    if grease and isinstance(process_window, dict):
        # E5=A / H7 (2026-10-14): a submitted grease-route fixed window must be
        # complete on its own terms, not merely schema-valid. process.schema.json
        # keeps evidence_reference OPTIONAL (the WP-01 baseline shape has none) and
        # only patterns it when present, so this gate is what enforces the
        # PROCESS_WINDOW_DEFINED contract: the window validated, and its evidence
        # reference spelled exactly PROCESS-WINDOW:<window_id> -- the citation a
        # design freeze must consume for MANUFACTURABILITY_ACCEPTABLE. The check is
        # gated on the grease route, so a submitted oil window keeps today's verdict.
        nested_window = process_window.get("process_window") if isinstance(process_window.get("process_window"), dict) else {}
        if nested_window.get("validated") is not True:
            errors.append("process_window_artifact: the submitted fixed window must be validated (process_window.validated is true) on the PRECISION_GREASE_DEV route")
        window_id = nested_window.get("window_id")
        if not isinstance(window_id, str) or not window_id.strip() or nested_window.get("evidence_reference") != f"PROCESS-WINDOW:{window_id}":
            errors.append("process_window_artifact: the submitted fixed window must carry evidence_reference PROCESS-WINDOW:<window_id> on the PRECISION_GREASE_DEV route")
    if grease and isinstance(method, dict):
        # L11 follow-up: the reviewed method's recorded discrimination ruler. Gated on
        # the grease route and inert when the method names no reference set, so every
        # oil request and every reference-free grease request keeps its verdict.
        errors.extend(reference_ruler_errors(method, input_path))
    present = [value for value in (project, challenge, failure, method, design_space, experiment_design, experiment, model, optimization) if value]
    scopes = {value.get("evidence_scope") for value in (method, experiment_design, experiment, model, optimization) if value is not None}
    if scopes - {"SYNTHETIC", "PHYSICAL"} or len(scopes) != 1:
        errors.append("test_method, experiment_design, experiment, model, and optimization evidence_scope values must exist and match")
    if project and project.get("status") != "ACTIVE": errors.append("project_artifact must have status ACTIVE")
    if len(present) == 9 and len({value.get("project_id") for value in present}) != 1: errors.append("all upstream artifact project_id values must match")
    elif no_challenge_shape and len(present) == 8 and len({value.get("project_id") for value in present}) != 1:
        # The grease route's no-challenge shape: the same uniformity rule, over the eight
        # upstreams that do exist. Unreachable on any route that requires a challenge, so
        # the nine-key threshold above stays exactly what it was.
        errors.append("all upstream artifact project_id values must match")
    if failure and challenge and failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if method and failure and (method.get("target_failure_reference") != failure.get("failure_id") or method.get("qualification_status") != "QUALIFIED"): errors.append("test_method_artifact must be linked and qualified")
    if design_space and method and method.get("method_id") not in (design_space.get("qualified_test_method_references") or []): errors.append("design_space_artifact method link is invalid")
    if experiment_design and design_space and experiment_design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    if experiment and experiment_design and experiment.get("experiment_design_reference") != experiment_design.get("experiment_design_id"): errors.append("experiment_artifact design link is invalid")
    if model and experiment and model.get("experiment_reference") != experiment.get("experiment_id"): errors.append("model_artifact experiment link is invalid")
    if optimization and model and optimization.get("model_reference") != model.get("model_id"): errors.append("optimization_artifact model link is invalid")
    # Defect 4 fix: the weakest declared scope across every submitted upstream
    # governs the disposition, so a SYNTHETIC process window cannot inherit
    # PHYSICAL from the optimization artifact.
    scope_values = [value.get("evidence_scope") for value in (method, experiment_design, experiment, model, optimization) if value is not None]
    scope_values += [value.get("evidence_scope") for value in (process, process_window) if value is not None]
    effective_scope = aggregate_scope(scope_values)
    if process is not None and process_window is not None:
        nested = process_window.get("process_window") if isinstance(process_window.get("process_window"), dict) else {}
        if aggregate_scope(scope_values) == "SYNTHETIC" or process_window_synthetic(nested) or process_window_synthetic(process_window):
            errors.append("SYNTHETIC process evidence_scope permits Gate HOLD workflow validation only; a validated window declared SYNTHETIC cannot authorize a state transition")
    request = data.get("gate"); errors.extend(gate_request_errors(request, project.get("project_id", "") if project else "", experiment.get("experiment_id") if experiment else "", effective_scope))
    if not isinstance(request, dict): return errors
    status = request.get("gate_status")
    if effective_scope == "SYNTHETIC" and status != "HOLD": errors.append("SYNTHETIC evidence_scope permits Gate HOLD workflow validation only")
    if status == "GO" and has_gap(request): errors.append("GO cannot use GAP evidence")
    if status in {"PIVOT", "KILL", "FREEZE"} and (not isinstance(request.get("reason"), str) or not request["reason"].strip() or has_gap(request)): errors.append(f"{status} requires explicit reason and evidence without GAP")
    return errors


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python preflight_gate_review.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, path)
    errors.extend(workspace_naming_errors(path))
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: input can form one VERIFIED Gate artifact only")
    charter = read_charter(data.get("project_artifact") if isinstance(data, dict) else None, path)
    if isinstance(data, dict) and CHALLENGE_KEY not in data and isinstance(charter, dict) and charter.get("project_type") == GREASE_PROJECT_TYPE:
        print(challenge_note(charter.get("project_id")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
