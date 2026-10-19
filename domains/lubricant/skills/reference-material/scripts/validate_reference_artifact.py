"""Validate one deterministic reference artifact against the contract and the policy.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/reference.schema.json`` with the
   common contract in the registry. That schema already carries the two ``if/then``
   rules tying a RESOLVED Known Bad to ``DISCRIMINATION_EVIDENCE_COMPLETE`` and
   ``tier: UNRESOLVED`` to ``DISCRIMINATION_EVIDENCE_INCOMPLETE``; schema errors are
   reported with their instance path so the citation is traceable.
2. Semantic: the artifact equals what ``reference_material_policy`` deterministically
   derives from its own dossiers - the resolution downgrade rule, the ladder tier, the
   downstream flag, the release rule, and the canonical decision block. This catches a
   hand-edited artifact that is schema-legal but not policy-legal (for example a RESOLVED
   Known Bad with no mechanism-bound failure, or a COMPLETE flag justified by nothing).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from reference_material_policy import (
    dossier_evidence_errors,
    downstream_errors,
    expected_decision_fields,
    identity_errors,
    tier_errors,
)
from preflight_reference_material import SCHEMA_NAMES, schema_dir


def schema_errors(artifact: object) -> list[str]:
    schemas = schema_dir()
    loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(loaded["reference.schema.json"], registry=registry)
    return [
        f"reference.schema.json: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in validator.iter_errors(artifact)
    ]


def semantic_errors(artifact: dict) -> list[str]:
    known_good = artifact.get("known_good")
    known_bad = artifact.get("known_bad")
    errors: list[str] = []
    errors.extend(identity_errors(known_good, known_bad))
    errors.extend(dossier_evidence_errors(known_good, known_bad))
    errors.extend(tier_errors(artifact.get("tier"), known_good, known_bad))
    errors.extend(downstream_errors(artifact.get("tier"), artifact.get("downstream_flag"), known_bad))
    policy = expected_decision_fields(
        artifact.get("reference_id"),
        artifact.get("evidence_scope"),
        known_good,
        known_bad,
        artifact.get("tier"),
        artifact.get("downstream_flag"),
        artifact.get("evidence"),
    )
    for field, value in policy.items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic reference-material policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_reference_artifact.py <artifact.json>")
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
    print("PASS: deterministic reference-material artifact conforms to the reference contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
