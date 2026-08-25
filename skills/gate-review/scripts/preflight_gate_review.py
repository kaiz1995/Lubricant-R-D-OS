"""Reject incomplete Gate-review requests before a VERIFIED artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from gate_review_policy import has_gap


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json", "gate.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"), ("experiment_artifact", "experiment.schema.json", "EXPERIMENT_RUNNING"), ("model_artifact", "model.schema.json", "MODEL_BUILT"), ("optimization_artifact", "optimization.schema.json", "OPTIMIZED"))
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"gate"}
REQUEST_FIELDS = {"gate_id", "scope", "gate_status", "satisfied_conditions", "unsatisfied_conditions", "evidence_gaps", "risks", "reason", "evidence"}


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


def gate_request_errors(request: object, project_id: str, experiment_id: str, evidence_scope: str | None = None) -> list[str]:
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS: return ["gate must contain only the required review fields"]
    candidate = {"schema_version": "0.1.0", "artifact_type": "gate", "project_id": project_id or "input-project", "stage": "VERIFIED", "evidence_scope": evidence_scope, "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": request.get("gate_status"), "next_action": "input", "experiment_reference": experiment_id or "input-experiment", **{key: value for key, value in request.items() if key != "reason"}}
    loaded, registry = schemas()
    return [f"gate: {error.message}" for error in Draft202012Validator(loaded["gate.schema.json"], registry=registry).iter_errors(candidate)]


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict): return ["input must be a JSON object"]
    errors, items = [], {}
    if set(data) != INPUT_FIELDS: errors.append("input must contain only required upstream artifact paths and gate")
    for key, schema, stage in UPSTREAM:
        item_errors, value = artifact(data.get(key), input_path, schema, key); errors.extend(item_errors); items[key] = value
        if value and value.get("stage") != stage: errors.append(f"{key} must be stage {stage}")
        if value and value.get("decision") != "GO": errors.append(f"{key} must have decision GO")
    project, challenge, failure, method, design_space, experiment_design, experiment, model, optimization = (items[key] for key, _, _ in UPSTREAM)
    present = [value for value in (project, challenge, failure, method, design_space, experiment_design, experiment, model, optimization) if value]
    scopes = {value.get("evidence_scope") for value in (method, experiment_design, experiment, model, optimization) if value is not None}
    if scopes - {"SYNTHETIC", "PHYSICAL"} or len(scopes) != 1:
        errors.append("test_method, experiment_design, experiment, model, and optimization evidence_scope values must exist and match")
    if project and project.get("status") != "ACTIVE": errors.append("project_artifact must have status ACTIVE")
    if len(present) == 9 and len({value.get("project_id") for value in present}) != 1: errors.append("all upstream artifact project_id values must match")
    if failure and challenge and failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if method and failure and (method.get("target_failure_reference") != failure.get("failure_id") or method.get("qualification_status") != "QUALIFIED"): errors.append("test_method_artifact must be linked and qualified")
    if design_space and method and design_space.get("qualified_test_method_references") != [method.get("method_id")]: errors.append("design_space_artifact method link is invalid")
    if experiment_design and design_space and experiment_design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    if experiment and experiment_design and experiment.get("experiment_design_reference") != experiment_design.get("experiment_design_id"): errors.append("experiment_artifact design link is invalid")
    if model and experiment and model.get("experiment_reference") != experiment.get("experiment_id"): errors.append("model_artifact experiment link is invalid")
    if optimization and model and optimization.get("model_reference") != model.get("model_id"): errors.append("optimization_artifact model link is invalid")
    request = data.get("gate"); errors.extend(gate_request_errors(request, project.get("project_id", "") if project else "", experiment.get("experiment_id", "") if experiment else "", optimization.get("evidence_scope") if optimization else None))
    if not isinstance(request, dict): return errors
    status = request.get("gate_status")
    if scopes == {"SYNTHETIC"} and status != "HOLD": errors.append("SYNTHETIC evidence_scope permits Gate HOLD workflow validation only")
    if status == "GO" and has_gap(request): errors.append("GO cannot use GAP evidence")
    if status in {"PIVOT", "KILL", "FREEZE"} and (not isinstance(request.get("reason"), str) or not request["reason"].strip() or has_gap(request)): errors.append(f"{status} requires explicit reason and evidence without GAP")
    return errors


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python preflight_gate_review.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: input can form one VERIFIED Gate artifact only"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
