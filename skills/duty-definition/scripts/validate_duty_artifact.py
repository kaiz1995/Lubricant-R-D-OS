"""Validate one duty artifact against canonical or deployed schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SKILL_ROOT = Path(__file__).resolve().parents[1]


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    names = ("common.schema.json", "duty.schema.json")
    return canonical if all((canonical / name).is_file() for name in names) else SKILL_ROOT / "references"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_duty_artifact.py <artifact.json>")
        return 1
    try:
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        duty = json.loads((schemas / "duty.schema.json").read_text(encoding="utf-8"))
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(duty["$id"], Resource.from_contents(duty))
    errors = sorted(Draft202012Validator(duty, registry=registry).iter_errors(artifact), key=lambda error: list(error.path))
    if errors:
        for error in errors:
            location = "/".join(map(str, error.path)) or "<root>"
            print(f"FAIL: {location}: {error.message}")
        return 1
    print("PASS: duty artifact conforms to the Duty Definition schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
