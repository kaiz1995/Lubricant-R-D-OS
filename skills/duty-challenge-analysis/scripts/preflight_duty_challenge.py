"""Reject incomplete duty/challenge inputs before a Challenge Map member is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SKILL_ROOT = Path(__file__).resolve().parents[1]
DUTY_FIELDS = (
    "equipment", "operating_conditions", "maintenance", "temperature",
    "load", "contamination", "life",
)
CHALLENGE_FIELDS = (
    "duty_reference", "challenge_id", "category", "description", "severity",
    "exposure", "lubricant_sensitivity", "evidence_gap", "priority",
)
CHALLENGE_CATEGORIES = {
    "MECHANICAL_LOAD", "CONTACT", "HIGH_TEMPERATURE", "LOW_TEMPERATURE", "OXIDATION",
    "WATER_CONTAMINATION", "AIR_FOAM", "PARTICLE_CONTAMINATION", "MATERIAL_COMPATIBILITY",
    "LONG_TERM_STABILITY", "MIXING", "RAW_MATERIAL_VARIATION",
}
LEVELS = {"LOW", "MEDIUM", "HIGH"}


def has_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    if all((canonical / name).is_file() for name in ("common.schema.json", "project.schema.json")):
        return canonical
    return SKILL_ROOT / "references"


def project_errors(path: Path) -> list[str]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        project = json.loads((schemas / "project.schema.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"project_artifact cannot be read: {error}"]
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(project["$id"], Resource.from_contents(project))
    errors = [f"project_artifact: {error.message}" for error in Draft202012Validator(project, registry=registry).iter_errors(artifact)]
    if not errors and (artifact.get("stage") != "PROJECT_DEFINED" or artifact.get("status") != "ACTIVE"):
        errors.append("project_artifact must be stage PROJECT_DEFINED and status ACTIVE")
    return errors


def evidence_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [label]
    errors = []
    if not has_value(value.get("value")):
        errors.append(f"{label}.value")
    for field in ("source", "evidence_id", "statement"):
        if not has_text(value.get(field)):
            errors.append(f"{label}.{field}")
    if value.get("status") != "OBSERVED":
        errors.append(f"{label}.status must be OBSERVED")
    return errors


def evidence_list_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [label]
    errors = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}]")
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}[{index}].{field}")
        if item.get("status") != "OBSERVED":
            errors.append(f"{label}[{index}].status must be OBSERVED")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors: list[str] = []
    project_path = data.get("project_artifact")
    if not has_text(project_path):
        errors.append("project_artifact")
    else:
        resolved = Path(project_path)
        if not resolved.is_absolute():
            resolved = input_path.parent / resolved
        errors.extend(project_errors(resolved))

    duty = data.get("duty")
    if not isinstance(duty, dict):
        errors.append("duty")
    else:
        for field in DUTY_FIELDS:
            errors.extend(evidence_errors(duty.get(field), f"duty.{field}"))

    challenge = data.get("challenge")
    if not isinstance(challenge, dict):
        errors.append("challenge")
    else:
        for field in CHALLENGE_FIELDS:
            if not has_text(challenge.get(field)):
                errors.append(f"challenge.{field}")
        if challenge.get("category") not in CHALLENGE_CATEGORIES:
            errors.append("challenge.category is invalid")
        for field in ("severity", "exposure", "lubricant_sensitivity", "priority"):
            if challenge.get(field) not in LEVELS:
                errors.append(f"challenge.{field} is invalid")
    errors.extend(evidence_list_errors(data.get("challenge_evidence"), "challenge_evidence"))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_duty_challenge.py <input.json>")
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
    print("READY: input can form one CHALLENGES_DEFINED member only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
