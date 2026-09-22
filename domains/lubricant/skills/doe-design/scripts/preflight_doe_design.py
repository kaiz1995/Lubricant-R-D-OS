"""Reject incomplete DOE-design requests before any EXPERIMENT_DESIGNED artifact is built."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from doe_design_policy import has_gap


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json")
INPUT_FIELDS = {"project_artifact", "challenge_artifact", "failure_ctq_artifact", "test_method_artifact", "design_space_artifact", "experiment_design"}
REQUEST_FIELDS = {"experiment_design_id", "factor_references", "design", "run_plan", "responses", "guardrails", "expected_information_value", "mixture_total", "evidence"}
MEASUREMENT_FIELDS = {"value", "unit", "source", "method_version", "material_batch", "formula_version"}


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def load_schemas() -> tuple[dict[str, dict], Registry]:
    schemas = schema_dir()
    loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return loaded, registry


def schema_artifact(path: Path, name: str, label: str) -> tuple[list[str], dict | None]:
    try:
        loaded, registry = load_schemas()
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def measurement_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != MEASUREMENT_FIELDS:
        return [label]
    errors = []
    number = value.get("value")
    if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
        errors.append(f"{label}.value")
    for field in MEASUREMENT_FIELDS - {"value"}:
        if not has_text(value.get(field)):
            errors.append(f"{label}.{field}")
    return errors


def request_schema_errors(request: object, project_id: str, evidence_scope: str | None = None) -> list[str]:
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        return ["experiment_design must contain only the required request fields"]
    candidate = {
        "schema_version": "0.1.0", "artifact_type": "experiment_design", "project_id": project_id or "input-project", "stage": "EXPERIMENT_DESIGNED", "evidence_scope": evidence_scope,
        "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": "GO", "next_action": "input",
        "design_space_reference": "input-design-space", "test_method_references": ["input-method"], **request,
    }
    try:
        loaded, registry = load_schemas()
    except (OSError, json.JSONDecodeError) as error:
        return [f"experiment_design schemas cannot be read: {error}"]
    return [f"experiment_design: {error.message}" for error in Draft202012Validator(loaded["experiment_design.schema.json"], registry=registry).iter_errors(candidate)]


def request_errors(request: object, design_space: dict | None, failure: dict | None, method: dict | None, project_id: str) -> list[str]:
    errors = request_schema_errors(request, project_id, method.get("evidence_scope") if method else None)
    if not isinstance(request, dict):
        return errors
    design = request.get("design") if isinstance(request.get("design"), dict) else {}
    if design.get("family") != "CONSTRAINED_MIXTURE":
        errors.append("experiment_design.design.family is not supported for GO; only CONSTRAINED_MIXTURE is available")
    if has_gap(request):
        errors.append("experiment_design.evidence contains GAP; current input is insufficient")
    factors = request.get("factor_references")
    variables = {item.get("variable_id"): item for item in design_space.get("variables", []) if isinstance(item, dict)} if design_space else {}
    if isinstance(factors, list):
        if len(factors) < 2:
            errors.append("experiment_design.factor_references requires at least two factors")
        for factor in factors:
            variable = variables.get(factor) if isinstance(factor, str) else None
            if variable is None:
                errors.append(f"experiment_design.factor_references: {factor} does not exist in design_space_artifact")
                continue
            if variable.get("variable_type") != "FORMULATION_VARIABLE":
                errors.append(f"experiment_design.factor_references: {factor} must be FORMULATION_VARIABLE")
    selected = [variables.get(factor) if isinstance(factor, str) else None for factor in factors] if isinstance(factors, list) else []
    units, lower_sum, upper_sum = set(), 0.0, 0.0
    for factor, variable in zip(factors if isinstance(factors, list) else [], selected):
        if not isinstance(variable, dict):
            continue
        label = f"design_space_artifact.variables[{factor}]"
        lower, upper = variable.get("lower_bound"), variable.get("upper_bound")
        errors.extend(measurement_errors(lower, f"{label}.lower_bound"))
        errors.extend(measurement_errors(upper, f"{label}.upper_bound"))
        if not measurement_errors(lower, "") and not measurement_errors(upper, ""):
            if lower["value"] > upper["value"]:
                errors.append(f"{label}.lower_bound.value must be <= upper_bound.value")
            units.update((lower["unit"], upper["unit"]))
            lower_sum += lower["value"]
            upper_sum += upper["value"]
    if len(units) > 1:
        errors.append("selected factor bounds must use the same unit")
    total = request.get("mixture_total")
    errors.extend(measurement_errors(total, "experiment_design.mixture_total"))
    if not measurement_errors(total, ""):
        if total["value"] <= 0:
            errors.append("experiment_design.mixture_total.value must be > 0")
        if units and total["unit"] not in units:
            errors.append("experiment_design.mixture_total.unit must equal selected factor bounds")
        if len(selected) == len(factors or []) and not (lower_sum <= total["value"] <= upper_sum):
            errors.append("experiment_design.mixture_total must be within the sum of selected factor bounds")
    ctqs = {item.get("ctq_id"): item for item in failure.get("ctqs", []) if isinstance(item, dict)} if failure else {}
    allowed_ctqs = set(design_space.get("ctq_references", [])) if design_space else set()
    method_id = method.get("method_id") if method else None
    for response in request.get("responses", []) if isinstance(request.get("responses"), list) else []:
        if not isinstance(response, dict):
            continue
        ctq = response.get("ctq_reference")
        if ctq not in ctqs or ctq not in allowed_ctqs:
            errors.append(f"experiment_design.responses: {ctq} must exist in failure_ctq and design_space")
        if response.get("test_method_reference") != method_id:
            errors.append("experiment_design.responses.test_method_reference must equal the supplied qualified method_id")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    if set(data) != INPUT_FIELDS:
        errors.append("input must contain only required upstream artifact paths and experiment_design")
    requirements = (
        ("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"),
        ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"),
        ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"),
    )
    for key, schema, stage in requirements:
        path = resolved_path(data.get(key), input_path)
        if path is None:
            errors.append(key)
            artifacts[key] = None
            continue
        item_errors, artifact = schema_artifact(path, schema, key)
        errors.extend(item_errors)
        artifacts[key] = artifact
        if artifact is not None and artifact.get("stage") != stage:
            errors.append(f"{key} must be stage {stage}")
        if artifact is not None and artifact.get("decision") != "GO":
            errors.append(f"{key} must have decision GO")
    project, challenge, failure, method, design_space = (artifacts[key] for key, _, _ in requirements)
    present = [item for item in (project, challenge, failure, method, design_space) if item is not None]
    if method is not None and method.get("evidence_scope") not in {"SYNTHETIC", "PHYSICAL"}:
        errors.append("test_method_artifact must declare evidence_scope")
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    if len(present) == 5 and len({item.get("project_id") for item in present}) != 1:
        errors.append("all upstream artifact project_id values must match")
    if challenge is not None and failure is not None and failure.get("challenge_reference") != challenge.get("challenge_id"):
        errors.append("failure_ctq_artifact.challenge_reference must equal challenge_artifact.challenge_id")
    if failure is not None and method is not None and method.get("target_failure_reference") != failure.get("failure_id"):
        errors.append("test_method_artifact.target_failure_reference must equal failure_ctq_artifact.failure_id")
    if method is not None and method.get("qualification_status") != "QUALIFIED":
        errors.append("test_method_artifact must have qualification_status QUALIFIED")
    if method is not None and not ({"D", "P"} & set(method.get("role", []))):
        errors.append("test_method_artifact must have role D or P")
    if design_space is not None and method is not None:
        if design_space.get("qualified_test_method_references") != [method.get("method_id")]:
            errors.append("design_space_artifact qualified method references must equal the supplied method_id")
        ctqs = {item.get("ctq_id"): item for item in failure.get("ctqs", []) if isinstance(item, dict)} if failure else {}
        for ctq_id in design_space.get("ctq_references", []):
            ctq = ctqs.get(ctq_id)
            if ctq is None:
                errors.append(f"design_space_artifact.ctq_references: {ctq_id} does not exist in failure_ctq_artifact")
            elif method["method_id"] not in ctq.get("test_references", []) and method["method_id"] not in failure.get("test_chain", []):
                errors.append(f"design_space_artifact.ctq_references: {ctq_id} is not linked to the supplied qualified method")
    errors.extend(request_errors(data.get("experiment_design"), design_space, failure, method, project.get("project_id", "") if project else ""))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_doe_design.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    print("READY: input can form one EXPERIMENT_DESIGNED request only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
