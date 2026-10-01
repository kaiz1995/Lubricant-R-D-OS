"""Validate one deterministic process artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from preflight_process_definition import PROCESS_FIELDS, process_errors, schema_dir
from process_policy import expected_decision_fields


def semantic_errors(artifact: dict) -> list[str]:
    process = {field: artifact.get(field) for field in PROCESS_FIELDS}
    errors = process_errors(process, None)
    for field, value in expected_decision_fields(process).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic process policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_process_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        schemas = schema_dir()
        loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in ("common.schema.json", "process.schema.json")}
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(loaded["process.schema.json"], registry=registry).iter_errors(artifact)]
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic process artifact conforms to the process contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
