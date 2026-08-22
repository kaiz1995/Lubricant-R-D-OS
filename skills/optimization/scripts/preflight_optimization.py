"""Reject incomplete optimization requests before an OPTIMIZED artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from optimization_policy import has_gap


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"), ("experiment_artifact", "experiment.schema.json", "EXPERIMENT_RUNNING"), ("model_artifact", "model.schema.json", "MODEL_BUILT"))
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"optimization"}
REQUEST_FIELDS = {"optimization_id", "objective_type", "objectives", "methods", "evidence"}


def schema_dir() -> Path:
    canonical = ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMAS) else ROOT / "references"


def load_schemas() -> tuple[dict[str, dict], Registry]:
    directory = schema_dir(); schemas = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMAS}; registry = Registry()
    for schema in schemas.values(): registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def read_artifact(value: object, input_path: Path, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    if not isinstance(value, str) or not value.strip(): return [label], None
    try:
        schemas, registry = load_schemas(); artifact = json.loads((input_path.parent / value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(schemas[schema_name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def request_errors(request: object, project_id: str) -> list[str]:
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS: return ["optimization must contain only optimization_id, objective_type, objectives, methods, and evidence"]
    candidate = {"schema_version": "0.1.0", "artifact_type": "optimization", "project_id": project_id or "input-project", "stage": "OPTIMIZED", "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": "GO", "next_action": "input", "model_reference": "input-model", "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **request}
    schemas, registry = load_schemas()
    return [f"optimization: {error.message}" for error in Draft202012Validator(schemas["optimization.schema.json"], registry=registry).iter_errors(candidate)]


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict): return ["input must be a JSON object"]
    errors, artifacts = [], {}
    if set(data) != INPUT_FIELDS: errors.append("input must contain only required upstream artifact paths and optimization")
    for key, schema, stage in UPSTREAM:
        item_errors, artifact = read_artifact(data.get(key), input_path, schema, key); errors.extend(item_errors); artifacts[key] = artifact
        if artifact and artifact.get("stage") != stage: errors.append(f"{key} must be stage {stage}")
        if artifact and artifact.get("decision") != "GO": errors.append(f"{key} must have decision GO")
    project, challenge, failure, method, design_space, experiment_design, experiment, model = (artifacts[key] for key, _, _ in UPSTREAM)
    available = [value for value in (project, challenge, failure, method, design_space, experiment_design, experiment, model) if value]
    if project and project.get("status") != "ACTIVE": errors.append("project_artifact must have status ACTIVE")
    if len(available) == 8 and len({value.get("project_id") for value in available}) != 1: errors.append("all upstream artifact project_id values must match")
    if failure and challenge and failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if method and failure and (method.get("target_failure_reference") != failure.get("failure_id") or method.get("qualification_status") != "QUALIFIED" or not ({"D", "P"} & set(method.get("role", [])))): errors.append("test_method_artifact must be linked qualified D or P")
    if design_space and method and design_space.get("qualified_test_method_references") != [method.get("method_id")]: errors.append("design_space_artifact method link is invalid")
    if experiment_design and design_space and experiment_design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    if experiment and experiment_design and experiment.get("experiment_design_reference") != experiment_design.get("experiment_design_id"): errors.append("experiment_artifact design link is invalid")
    if experiment and design_space and experiment.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_artifact design-space link is invalid")
    if model and experiment and model.get("experiment_reference") != experiment.get("experiment_id"): errors.append("model_artifact experiment link is invalid")
    if model and design_space and model.get("design_space_reference") != design_space.get("design_space_id"): errors.append("model_artifact design-space link is invalid")
    if model and method and model.get("test_method_references") != [method.get("method_id")]: errors.append("model_artifact method link is invalid")
    request = data.get("optimization"); errors.extend(request_errors(request, project.get("project_id", "") if project else ""))
    if not isinstance(request, dict): return errors
    if has_gap(request): errors.append("optimization.evidence contains GAP")
    if "BAYESIAN_OPTIMIZATION" in request.get("methods", []): errors.append("BAYESIAN_OPTIMIZATION is unsupported in Phase 3")
    model_responses = {item.get("ctq_reference") for item in model.get("response_references", []) if isinstance(item, dict)} if model else set()
    for objective in request.get("objectives", []):
        if isinstance(objective, dict) and objective.get("response_reference") not in model_responses: errors.append(f"optimization objective {objective.get('response_reference')} is not present in model_artifact")
    return errors


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python preflight_optimization.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: input can form one OPTIMIZED request only"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
