"""Validate one deterministic bench artifact, including the derived slot count."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from bench_policy import INPUT_FIELDS, available_bench_slots, expected_decision_fields
from preflight_bench_registration import bench_errors, schema_dir


def semantic_errors(artifact: dict) -> list[str]:
    bench = {field: artifact.get(field) for field in INPUT_FIELDS}
    errors = bench_errors(bench)
    try:
        slots = available_bench_slots(bench)
    except ValueError as error:
        errors.append(str(error))
        return errors
    if artifact.get("available_bench_slots") != slots:
        errors.append(f"available_bench_slots must equal the derived {slots}")
    for field, value in expected_decision_fields(bench, slots).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic bench policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_bench_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        schemas = schema_dir()
        loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in ("common.schema.json", "bench.schema.json")}
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(loaded["bench.schema.json"], registry=registry).iter_errors(artifact)]
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic bench artifact conforms to the bench contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
