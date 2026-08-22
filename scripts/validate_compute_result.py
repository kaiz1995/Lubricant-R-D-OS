"""Validate a compute result artifact against domains/lubricant/schemas."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "domains" / "lubricant" / "schemas"

def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python validate_compute_result.py <schema_name> <artifact.json>")
        return 1
    schema_name = sys.argv[1]
    artifact_path = Path(sys.argv[2])
    try:
        schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        schemas = {}
        for p in SCHEMA_DIR.glob("*.json"):
            schemas[p.name] = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read artifact or schemas: {e}")
        return 1
    registry = Registry()
    for s in schemas.values():
        if "$id" in s:
            registry = registry.with_resource(s["$id"], Resource.from_contents(s))
    validator = Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    if errors:
        for e in errors:
            loc = "/".join(str(x) for x in e.path) if e.path else "(root)"
            print(f"FAIL: {loc}: {e.message}")
        return 1
    print("PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
