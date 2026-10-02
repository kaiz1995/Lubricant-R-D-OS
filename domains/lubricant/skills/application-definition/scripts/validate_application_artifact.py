"""Validate one deterministic application artifact, including the verdict rules."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from application_policy import ARTIFACT_FIELDS, expected_decision_fields
from preflight_application_definition import application_errors, schema_dir


def semantic_errors(artifact: dict) -> list[str]:
    application = {field: artifact.get(field) for field in ARTIFACT_FIELDS}
    application["source"] = artifact.get("source")
    application["evidence_id"] = artifact.get("evidence_id")
    application["evidence_scope"] = artifact.get("evidence_scope")
    application["evidence"] = artifact.get("evidence")
    errors = application_errors(application)
    for field, value in expected_decision_fields(application).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic application policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_application_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        schemas = schema_dir()
        loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in ("common.schema.json", "application.schema.json")}
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(loaded["application.schema.json"], registry=registry).iter_errors(artifact)]
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic application artifact conforms to the application contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
