"""Validate one deterministic Phase 3 optimization request artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from optimization_policy import expected_decision_fields
from preflight_optimization import SCHEMAS, schema_dir


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python validate_optimization_artifact.py <artifact.json>"); return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")); directory = schema_dir(); schemas = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMAS}
    except (OSError, json.JSONDecodeError) as error: print(f"FAIL: cannot read artifact or schemas: {error}"); return 1
    registry = Registry()
    for schema in schemas.values(): registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(schemas["optimization.schema.json"], registry=registry).iter_errors(artifact)]
    for field, value in expected_decision_fields(artifact).items():
        if artifact.get(field) != value: errors.append(f"{field} must equal the deterministic optimization policy")
    if errors:
        for error in errors: print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic optimization request conforms to the Phase 3 contract"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
