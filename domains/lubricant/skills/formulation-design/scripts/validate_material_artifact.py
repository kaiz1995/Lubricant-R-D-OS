"""Validate one deterministic material artifact.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/material.schema.json`` with the
   common contract in the registry, so the record cannot drift from the material
   contract. That schema is deployed beside this skill (it is on the formulation-design
   deployment list in ``scripts/install_domain_skill.py``), which is what makes loading
   it here legal for a deployed bundle.
2. Semantic: the artifact equals what ``material_policy`` deterministically derives from
   its own material block - the shape rules and the canonical decision block. This
   catches a hand-edited artifact that is schema-legal but policy-legal in name only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from material_policy import expected_decision_fields, material_shape_errors
from preflight_material import SCHEMA_NAMES, schema_dir


MATERIAL_SCHEMA = "material.schema.json"


def schema_errors(artifact: object) -> list[str]:
    schemas = schema_dir()
    names = (*SCHEMA_NAMES, MATERIAL_SCHEMA)
    loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in names}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(loaded[MATERIAL_SCHEMA], registry=registry)
    return [
        f"{MATERIAL_SCHEMA}: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in validator.iter_errors(artifact)
    ]


def semantic_errors(artifact: dict) -> list[str]:
    material = {field: artifact.get(field) for field in ("material_id", "category", "identity", "chemistry", "properties", "cost")}
    errors = list(material_shape_errors(material))
    if artifact.get("stage") != "DESIGN_SPACE_DEFINED":
        errors.append("stage must be DESIGN_SPACE_DEFINED")
    for field, value in expected_decision_fields(material, artifact.get("evidence_scope")).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic material policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_material_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    try:
        errors = schema_errors(artifact)
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    if not isinstance(artifact, dict):
        errors.append("artifact must be a JSON object")
    else:
        errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic material artifact conforms to the material contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
