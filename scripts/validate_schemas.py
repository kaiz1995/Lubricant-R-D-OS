"""Validate the V0 domain contracts and their positive/negative fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "fixtures"
EXPECTED_ERRORS = {
    "project--missing-formula-version.json": "'formula_version' is a required property",
    "challenge--missing-schema-version.json": "'schema_version' is a required property",
    "failure_ctq--missing-unit.json": "'unit' is a required property",
    "test_method--missing-source.json": "'source' is a required property",
    "design_space--missing-method-version.json": "'method_version' is a required property",
    "experiment--designed-stage.json": "'EXPERIMENT_RUNNING' was expected",
    "experiment--missing-material-batch.json": "'material_batch' is a required property",
    "experiment_design--missing-point-generation.json": "'point_generation' is a required property",
    "experiment_design--missing-mixture-total.json": "'mixture_total' is a required property",
    "gate--illegal-status.json": "'APPROVED' is not one of",
}


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validator_for(kind: str, registry: Registry) -> Draft202012Validator:
    return Draft202012Validator(read_json(SCHEMAS / f"{kind}.schema.json"), registry=registry)


def errors_for(validator: Draft202012Validator, instance: dict) -> list[str]:
    return [error.message for error in validator.iter_errors(instance)]


def main() -> int:
    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = read_json(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))

    failures: list[str] = []
    valid_count = invalid_count = 0

    for path in sorted((FIXTURES / "valid").glob("*.json")):
        errors = errors_for(validator_for(path.stem, registry), read_json(path))
        valid_count += 1
        if errors:
            failures.append(f"valid {path.name}: {errors[0]}")

    for path in sorted((FIXTURES / "invalid").glob("*.json")):
        kind = path.name.split("--", 1)[0]
        errors = errors_for(validator_for(kind, registry), read_json(path))
        invalid_count += 1
        expected = EXPECTED_ERRORS[path.name]
        if not errors:
            failures.append(f"invalid {path.name}: unexpectedly accepted")
        elif not any(expected in error for error in errors):
            failures.append(f"invalid {path.name}: expected {expected!r}, got {errors[0]!r}")

    print(f"valid={valid_count} invalid={invalid_count} failures={len(failures)}")
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
