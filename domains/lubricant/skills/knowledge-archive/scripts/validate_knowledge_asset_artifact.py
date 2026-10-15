"""Validate one deterministic KNOWLEDGE_ARCHIVED knowledge_asset artifact.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/knowledge_asset.schema.json`` with
   the common contract in the registry. That schema already carries the two if/then rules
   (CLOSED requires all six present and a QUALIFIED evidence package; SYNTHETIC caps at
   DRAFT with the demo marker). Schema errors are reported with their instance path.
2. Semantic: the artifact equals what ``knowledge_archive_policy`` derives from its own
   fields - the downgrade-only status rule, the synthetic cap, and the canonical decision
   block. This catches a hand-edited artifact that is schema-legal but not policy-legal
   (for example five assets plus a promise, or a cost identity masquerading as a CTQ).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from knowledge_archive_policy import (
    ASSET_KEYS,
    cost_criterion_errors,
    derived_status,
    expected_decision_fields,
    has_text,
    missing_keys,
)
from preflight_knowledge_archive import SCHEMA_NAMES, schema_dir


def schema_errors(artifact: object) -> list[str]:
    schemas = {name: json.loads((schema_dir() / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(schemas["knowledge_asset.schema.json"], registry=registry)
    return [
        f"knowledge_asset.schema.json: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in validator.iter_errors(artifact)
    ]


def semantic_errors(artifact: dict) -> list[str]:
    errors: list[str] = []
    knowledge_assets = artifact.get("knowledge_assets")
    evidence_scope = artifact.get("evidence_scope")
    asset_status = artifact.get("asset_status")
    if asset_status not in ("DRAFT_KNOWLEDGE", "CLOSED_KNOWLEDGE"):
        return [f"asset_status must be DRAFT_KNOWLEDGE or CLOSED_KNOWLEDGE (got {asset_status!r})"]
    derived = derived_status(knowledge_assets, evidence_scope)
    # Downgrade-only: CLOSED must be justified by the artifact's own assets; a DRAFT
    # record is always legal (draft is the safe direction).
    if asset_status == "CLOSED_KNOWLEDGE" and derived != "CLOSED_KNOWLEDGE":
        missing = missing_keys(knowledge_assets)
        errors.append(
            "asset_status CLOSED_KNOWLEDGE is not justified by the artifact's own assets"
            + (f" (missing: {', '.join(missing)})" if missing else "")
            + "; the highest legal status here is DRAFT_KNOWLEDGE"
        )
    if evidence_scope == "SYNTHETIC":
        if artifact.get("synthetic_marker") != "SYNTHETIC_DEMO_ONLY":
            errors.append("a SYNTHETIC record must be force-marked synthetic_marker=SYNTHETIC_DEMO_ONLY")
        if asset_status != "DRAFT_KNOWLEDGE":
            errors.append("a SYNTHETIC project can never reach CLOSED_KNOWLEDGE (NO Synthetic Closure)")
    elif artifact.get("synthetic_marker") is not None:
        errors.append("synthetic_marker is only legal on a SYNTHETIC record")
    if isinstance(knowledge_assets, dict):
        references = [
            entry.get("artifact_reference")
            for key, entry in knowledge_assets.items()
            if key in ASSET_KEYS and isinstance(entry, dict)
        ]
        errors.extend(cost_criterion_errors(references))
    for field, value in expected_decision_fields(
        knowledge_assets, evidence_scope, asset_status, artifact.get("evidence")
    ).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic knowledge-archive policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_knowledge_asset_artifact.py <artifact.json>")
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
    print("PASS: deterministic knowledge_asset artifact conforms to the knowledge-asset contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
