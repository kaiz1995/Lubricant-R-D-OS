"""Reject incomplete duty-definition input before an artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SKILL_ROOT = Path(__file__).resolve().parents[1]
DUTY_FIELDS = ("equipment", "operating_conditions", "maintenance", "temperature", "load", "contamination", "life")


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def has_value(value: object) -> bool:
    return has_text(value) or isinstance(value, (int, float)) and not isinstance(value, bool)


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    names = ("common.schema.json", "project.schema.json", "duty.schema.json")
    return canonical if all((canonical / name).is_file() for name in names) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def project_errors(path: Path) -> tuple[list[str], dict | None]:
    try:
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        project = json.loads((schemas / "project.schema.json").read_text(encoding="utf-8"))
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"project_artifact cannot be read: {error}"], None
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(project["$id"], Resource.from_contents(project))
    errors = [f"project_artifact: {error.message}" for error in Draft202012Validator(project, registry=registry).iter_errors(artifact)]
    if not errors and (artifact.get("stage") != "PROJECT_DEFINED" or artifact.get("status") != "ACTIVE" or artifact.get("decision") != "GO"):
        errors.append("project_artifact must be PROJECT_DEFINED, ACTIVE, and GO")
    return errors, artifact if not errors else None


def duty_errors(duty: object) -> list[str]:
    if not isinstance(duty, dict):
        return ["duty"]
    errors: list[str] = []
    for name in DUTY_FIELDS:
        item = duty.get(name)
        label = f"duty.{name}"
        if not isinstance(item, dict):
            errors.append(label)
            continue
        if not has_value(item.get("value")):
            errors.append(f"{label}.value")
        for field in ("source", "evidence_id", "statement"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") == "GAP":
            errors.append(f"{label}.status GAP requires resolution")
        elif item.get("status") not in {"OBSERVED", "ASSUMED"}:
            errors.append(f"{label}.status must be OBSERVED or ASSUMED")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors: list[str] = []
    project_path = resolved_path(data.get("project_artifact"), input_path)
    if project_path is None:
        errors.append("project_artifact")
    else:
        project_errors_found, _ = project_errors(project_path)
        errors.extend(project_errors_found)
    if not has_text(data.get("duty_id")):
        errors.append("duty_id")
    errors.extend(duty_errors(data.get("duty")))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_duty_definition.py <input.json>")
        return 1
    input_path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    print("READY: input can form one DUTY_DEFINED artifact only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
