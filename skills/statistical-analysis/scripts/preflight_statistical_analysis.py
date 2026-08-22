"""Reject incomplete statistical-analysis requests before a MODEL_BUILT artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from statistical_analysis_policy import has_gap


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"), ("experiment_artifact", "experiment.schema.json", "EXPERIMENT_RUNNING"))
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"analysis"}
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


def request_errors(request: object, project_id: str) -> list[str]:
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        return ["analysis must contain only model_id, requested_analyses, response_references, and evidence"]
    candidate = {"schema_version": "0.1.0", "artifact_type": "model", "project_id": project_id or "input-project", "stage": "MODEL_BUILT", "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": "GO", "next_action": "input", "experiment_reference": "input-experiment", "design_space_reference": "input-design-space", "test_method_references": ["input-method"], "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **request}
    schemas, registry = loaded_schemas()
    return [f"analysis: {error.message}" for error in Draft202012Validator(schemas["model.schema.json"], registry=registry).iter_errors(candidate)]


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    if set(data) != INPUT_FIELDS:
        errors.append("input must contain only required upstream artifact paths and analysis")
    for key, schema, stage in UPSTREAM:
        item_errors, artifact = load_artifact(read_path(data.get(key), input_path), schema, key)
        errors.extend(item_errors)
        artifacts[key] = artifact
        if artifact and artifact.get("stage") != stage:
            errors.append(f"{key} must be stage {stage}")
        if artifact and artifact.get("decision") != "GO":
            errors.append(f"{key} must have decision GO")
    project, challenge, failure, method, design_space, experiment_design, experiment = (artifacts[key] for key, _, _ in UPSTREAM)
    available = [item for item in (project, challenge, failure, method, design_space, experiment_design, experiment) if item]
    if project and project.get("status") != "ACTIVE": errors.append("project_artifact must have status ACTIVE")
    if len(available) == 7 and len({item.get("project_id") for item in available}) != 1: errors.append("all upstream artifact project_id values must match")
    if challenge and failure and failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if failure and method and method.get("target_failure_reference") != failure.get("failure_id"): errors.append("test_method_artifact failure link is invalid")
    if method and (method.get("qualification_status") != "QUALIFIED" or not ({"D", "P"} & set(method.get("role", [])))): errors.append("test_method_artifact must be qualified D or P")
    if design_space and method and design_space.get("qualified_test_method_references") != [method.get("method_id")]: errors.append("design_space_artifact method link is invalid")
    if experiment_design and design_space and experiment_design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    if experiment_design and method and experiment_design.get("test_method_references") != [method.get("method_id")]: errors.append("experiment_design_artifact method link is invalid")
    if experiment and experiment_design and experiment.get("experiment_design_reference") != experiment_design.get("experiment_design_id"): errors.append("experiment_artifact design link is invalid")
    if experiment and design_space and experiment.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_artifact design-space link is invalid")
    if experiment and method and experiment.get("test_method_references") != [method.get("method_id")]: errors.append("experiment_artifact method link is invalid")
    request = data.get("analysis")
    errors.extend(request_errors(request, project.get("project_id", "") if project else ""))
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
