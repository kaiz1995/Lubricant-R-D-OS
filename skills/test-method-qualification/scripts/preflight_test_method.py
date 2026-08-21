"""Reject incomplete test-method qualification input before an artifact is built."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from qualification_policy import METRICS, QUALIFICATION_STATUSES, ROLES, role_metric_errors


SKILL_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    names = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json")
    return canonical if all((canonical / name).is_file() for name in names) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def schema_artifact(path: Path, name: str, label: str) -> tuple[list[str], dict | None]:
    try:
        schemas = schema_dir()
        names = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json")
        loaded = {item: json.loads((schemas / item).read_text(encoding="utf-8")) for item in names}
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def measurement_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [label]
    errors = []
    for field in MEASUREMENT_FIELDS:
        item = value.get(field)
        if field == "value":
            if not isinstance(item, (int, float)) or isinstance(item, bool):
                errors.append(f"{label}.value")
        elif not has_text(item):
            errors.append(f"{label}.{field}")
    return errors


def evidence_errors(value: object) -> tuple[list[str], dict[str, dict]]:
    if not isinstance(value, list) or not value:
        return ["evidence"], {}
    errors, indexed = [], {}
    for index, item in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
        elif has_text(item.get("evidence_id")):
            indexed[item["evidence_id"]] = item
    return errors, indexed


def observed_id_errors(value: object, label: str, evidence: dict[str, dict]) -> list[str]:
    if not isinstance(value, list) or not value or not all(has_text(item) for item in value):
        return [label]
    return [f"{label}: {item} must reference OBSERVED evidence" for item in value if item not in evidence or evidence[item].get("status") != "OBSERVED"]


def method_errors(value: object, challenge: dict | None, failure: dict | None, evidence: dict[str, dict]) -> list[str]:
    if not isinstance(value, dict):
        return ["test_method"]
    errors = []
    for field in ("method_id", "name", "standard", "challenge_reference", "target_failure_reference"):
        if not has_text(value.get(field)):
            errors.append(f"test_method.{field}")
    if challenge and value.get("challenge_reference") != challenge.get("challenge_id"):
        errors.append("test_method.challenge_reference must equal challenge_artifact.challenge_id")
    if failure and value.get("target_failure_reference") != failure.get("failure_id"):
        errors.append("test_method.target_failure_reference must equal failure_ctq_artifact.failure_id")
    if failure and value.get("challenge_reference") != failure.get("challenge_reference"):
        errors.append("test_method.challenge_reference must equal failure_ctq_artifact.challenge_reference")
    roles = value.get("role")
    if not isinstance(roles, list) or not roles or len(roles) != len(set(roles)) or any(role not in ROLES for role in roles):
        errors.append("test_method.role")
    metrics = value.get("qualification_metrics")
    if not isinstance(metrics, list) or not metrics:
        errors.append("test_method.qualification_metrics")
    else:
        names = set()
        for index, item in enumerate(metrics):
            label = f"test_method.qualification_metrics[{index}]"
            if not isinstance(item, dict) or item.get("metric") not in METRICS:
                errors.append(f"{label}.metric")
                continue
            if item["metric"] in names:
                errors.append(f"{label}.metric is duplicated")
            names.add(item["metric"])
            errors.extend(measurement_errors(item.get("measurement"), f"{label}.measurement"))
    basis = value.get("qualification_basis")
    if not isinstance(basis, list) or not basis or not all(has_text(item) for item in basis):
        errors.append("test_method.qualification_basis")
    if value.get("qualification_status") not in QUALIFICATION_STATUSES:
        errors.append("test_method.qualification_status")
    source_id = value.get("method_source_evidence_id")
    if not has_text(source_id) or source_id not in evidence or evidence[source_id].get("status") != "OBSERVED":
        errors.append("test_method.method_source_evidence_id must reference OBSERVED evidence")
    errors.extend(observed_id_errors(value.get("qualification_evidence_ids"), "test_method.qualification_evidence_ids", evidence))
    errors.extend(role_metric_errors(value))
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    for key, schema, stage in (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED")):
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
    project, challenge, failure = artifacts["project_artifact"], artifacts["challenge_artifact"], artifacts["failure_ctq_artifact"]
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    if project and challenge and failure and len({project.get("project_id"), challenge.get("project_id"), failure.get("project_id")}) != 1:
        errors.append("project, challenge, and failure_ctq project_id values must match")
    evidence_problems, evidence = evidence_errors(data.get("evidence"))
    errors.extend(evidence_problems)
    errors.extend(method_errors(data.get("test_method"), challenge, failure, evidence))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_test_method.py <input.json>")
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
    print("READY: input can form one TEST_METHODS_QUALIFIED record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
