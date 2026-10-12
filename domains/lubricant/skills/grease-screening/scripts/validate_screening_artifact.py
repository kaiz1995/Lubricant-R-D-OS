"""Validate one deterministic screening artifact against the contract and the policy.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/screening.schema.json`` with the
   common contract in the registry. That schema carries the ``if/then`` rule
   ``overall_verdict: FAIL -> gate_to_bench: BLOCKED``; schema errors are reported with
   their instance path so the citation is traceable.
2. Semantic: the artifact equals what ``grease_screening_policy`` deterministically derives
   from its own tests - the aggregate verdict (the worst per-test verdict), the bench gate
   derived from it, and the canonical decision block. This catches a hand-edited artifact
   that is schema-legal but not policy-legal: a summary verdict more favourable than the
   recorded tests, a gate flipped to RELEASED over a failure, or a decision block that
   claims a clearance the tests do not support.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from grease_screening_policy import (
    artifact_screening_errors,
    expected_decision_fields,
    recorded_screening,
)
from preflight_grease_screening import SCHEMA_NAMES, schema_dir


def schema_errors(artifact: object) -> list[str]:
    schemas = schema_dir()
    loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(loaded["screening.schema.json"], registry=registry)
    return [
        f"screening.schema.json: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in validator.iter_errors(artifact)
    ]


def semantic_errors(artifact: object) -> list[str]:
    """Screening-side policy checks: shape, derived verdict, derived gate, decision block."""
    if not isinstance(artifact, dict):
        return []
    screening = recorded_screening(artifact)
    errors = artifact_screening_errors(screening)
    for field, value in expected_decision_fields(screening, artifact.get("evidence_scope")).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic grease-screening policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_screening_artifact.py <artifact.json>")
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
    print("PASS: deterministic screening artifact conforms to the screening contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
