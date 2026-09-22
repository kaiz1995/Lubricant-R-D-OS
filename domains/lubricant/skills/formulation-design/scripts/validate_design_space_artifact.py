"""Validate one deterministic design-space artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from design_space_policy import expected_decision_fields
from preflight_formulation_design import design_space_errors, schema_dir


SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json")


def semantic_errors(artifact: dict) -> list[str]:
    design_space = {field: artifact.get(field) for field in ("design_space_id", "scope", "variables", "ctq_references", "qualified_test_method_references", "constraints", "evidence")}
    errors = design_space_errors(design_space, None, None)
    for field, value in expected_decision_fields(design_space).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic design-space policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_design_space_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        schemas = schema_dir()
        loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(loaded["design_space.schema.json"], registry=registry).iter_errors(artifact)]
    if artifact.get("stage") != "DESIGN_SPACE_DEFINED":
        errors.append("stage must be DESIGN_SPACE_DEFINED")
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic design-space artifact conforms to the Stage 4 contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
