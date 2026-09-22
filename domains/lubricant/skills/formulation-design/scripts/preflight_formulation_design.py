"""Reject incomplete design-space input before an artifact is built."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from design_space_policy import has_gap


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json")
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")
VARIABLE_FIELDS = {"variable_id", "variable_type", "lower_bound", "upper_bound", "constraint_rationale"}
INPUT_FIELDS = {"project_artifact", "challenge_artifact", "failure_ctq_artifact", "test_method_artifact", "design_space"}
VARIABLE_TYPES = {"MATERIAL_FAMILY", "FORMULATION_VARIABLE", "PROCESS_VARIABLE"}


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


def schema_artifact(path: Path, name: str, label: str) -> tuple[list[str], dict | None]:
    try:
        schemas = schema_dir()
        loaded = {item: json.loads((schemas / item).read_text(encoding="utf-8")) for item in SCHEMA_NAMES}
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def measurement_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != set(MEASUREMENT_FIELDS):
        return [label]
    errors = []
    for field in MEASUREMENT_FIELDS:
        item = value.get(field)
        if field == "value":
            if not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(item):
                errors.append(f"{label}.value")
        elif not has_text(item):
            errors.append(f"{label}.{field}")
    return errors


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["design_space.evidence"]
    errors = []
    for index, item in enumerate(value):
        label = f"design_space.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != {"evidence_id", "statement", "source", "status"}:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
    return errors


def design_space_errors(value: object, failure: dict | None, method: dict | None) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"design_space_id", "scope", "variables", "ctq_references", "qualified_test_method_references", "constraints", "evidence"}:
        return ["design_space must contain only the Stage 4 input fields"]
    errors = []
    for field in ("design_space_id", "scope"):
        if not has_text(value.get(field)):
            errors.append(f"design_space.{field}")
    variables = value.get("variables")
    if not isinstance(variables, list) or not variables:
        errors.append("design_space.variables")
    else:
        variable_ids = set()
        for index, variable in enumerate(variables):
            label = f"design_space.variables[{index}]"
            if not isinstance(variable, dict) or set(variable) != VARIABLE_FIELDS:
                errors.append(label)
                continue
            variable_id = variable.get("variable_id")
            if not has_text(variable_id):
                errors.append(f"{label}.variable_id")
            elif variable_id in variable_ids:
                errors.append(f"{label}.variable_id is duplicated")
            else:
                variable_ids.add(variable_id)
            if variable.get("variable_type") not in VARIABLE_TYPES:
                errors.append(f"{label}.variable_type")
            errors.extend(measurement_errors(variable.get("lower_bound"), f"{label}.lower_bound"))
            errors.extend(measurement_errors(variable.get("upper_bound"), f"{label}.upper_bound"))
            if not has_text(variable.get("constraint_rationale")):
                errors.append(f"{label}.constraint_rationale")
            lower, upper = variable.get("lower_bound"), variable.get("upper_bound")
            if isinstance(lower, dict) and isinstance(upper, dict) and not measurement_errors(lower, "") and not measurement_errors(upper, ""):
                if lower["unit"] != upper["unit"]:
                    errors.append(f"{label} bounds must use the same unit")
                if lower["value"] > upper["value"]:
                    errors.append(f"{label}.lower_bound.value must be <= upper_bound.value")
    ctq_references = value.get("ctq_references")
    if not isinstance(ctq_references, list) or not ctq_references or not all(has_text(item) for item in ctq_references):
        errors.append("design_space.ctq_references")
    elif len(ctq_references) != len(set(ctq_references)):
        errors.append("design_space.ctq_references are duplicated")
    method_references = value.get("qualified_test_method_references")
    if not isinstance(method_references, list) or not method_references or not all(has_text(item) for item in method_references):
        errors.append("design_space.qualified_test_method_references")
    elif method is not None and method_references != [method.get("method_id")]:
        errors.append("design_space.qualified_test_method_references must equal the supplied qualified method_id")
    constraints = value.get("constraints")
    if not isinstance(constraints, list) or not constraints or not all(has_text(item) for item in constraints):
        errors.append("design_space.constraints")
    errors.extend(evidence_errors(value.get("evidence")))
    if not errors and has_gap(value):
        errors.append("design_space.evidence contains GAP; current input is insufficient")
    if failure is not None and method is not None and isinstance(ctq_references, list) and all(has_text(item) for item in ctq_references):
        ctqs = {item.get("ctq_id"): item for item in failure.get("ctqs", []) if isinstance(item, dict)}
        method_id = method.get("method_id")
        for ctq_id in ctq_references:
            ctq = ctqs.get(ctq_id)
            if ctq is None:
                errors.append(f"design_space.ctq_references: {ctq_id} does not exist")
            elif method_id not in ctq.get("test_references", []) and method_id not in failure.get("test_chain", []):
                errors.append(f"design_space.ctq_references: {ctq_id} is not linked to the supplied qualified method")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors = []
    if set(data) != INPUT_FIELDS:
        errors.append("input must contain only required Stage 4 artifact paths and design_space")
    artifacts: dict[str, dict | None] = {}
    requirements = (
        ("project_artifact", "project.schema.json", "PROJECT_DEFINED"),
        ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"),
        ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"),
        ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"),
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
    project = artifacts["project_artifact"]
    challenge = artifacts["challenge_artifact"]
    failure = artifacts["failure_ctq_artifact"]
    method = artifacts["test_method_artifact"]
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    present = [item for item in (project, challenge, failure, method) if item is not None]
    if len(present) == 4 and len({item.get("project_id") for item in present}) != 1:
        errors.append("project, challenge, failure_ctq, and test_method project_id values must match")
    if challenge is not None and failure is not None and failure.get("challenge_reference") != challenge.get("challenge_id"):
        errors.append("failure_ctq_artifact.challenge_reference must equal challenge_artifact.challenge_id")
    if failure is not None and method is not None and method.get("target_failure_reference") != failure.get("failure_id"):
        errors.append("test_method_artifact.target_failure_reference must equal failure_ctq_artifact.failure_id")
    if method is not None and method.get("qualification_status") != "QUALIFIED":
        errors.append("test_method_artifact must have qualification_status QUALIFIED")
    errors.extend(design_space_errors(data.get("design_space"), failure, method))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_formulation_design.py <input.json>")
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
    print("READY: input can form one DESIGN_SPACE_DEFINED record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
