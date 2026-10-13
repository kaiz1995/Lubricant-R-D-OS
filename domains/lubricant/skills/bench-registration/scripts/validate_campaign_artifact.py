"""Validate one deterministic campaign artifact against the contract and the policy.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/campaign.schema.json``
   with the shared ``common.schema.json`` in the registry -- the constant
   ``artifact_type`` / ``stage``, the required inner-loop fields, the iteration
   entry shape and ``unevaluatedProperties: false``.
2. Semantic: the artifact equals what ``campaign_policy`` deterministically
   derives from its own fields. That covers the cross-field rule JSON Schema
   cannot express (``current_iteration`` must not exceed ``max_iterations`` and
   must not sit before the rounds already recorded), the "only CONTINUE
   authorizes another round" rule, the contract-default provenance marker (its
   presence must be true, i.e. the cap must be the contract's published figure),
   and the canonical decision block.

This catches a hand-edited artifact that is schema-legal but not policy-legal --
for example a record whose ``decision`` was softened from HOLD to GO while its
newest round still ended KILL, or one whose cap was edited without touching the
provenance item that claims it came from the contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from campaign_policy import CAMPAIGN_STAGE, policy_errors
from preflight_campaign_registration import SCHEMA_NAMES, schema_dir


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_campaign_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        directory = schema_dir()
        loaded = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [
        f"campaign.schema.json: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in Draft202012Validator(loaded["campaign.schema.json"], registry=registry).iter_errors(artifact)
    ]
    errors.extend(policy_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(
        "PASS: deterministic campaign artifact conforms to the campaign contract "
        f"(stage={CAMPAIGN_STAGE} campaign_id={artifact.get('campaign_id')} "
        f"decision={artifact.get('decision')} iterations={len(artifact.get('iterations') or [])}"
        f"/{artifact.get('max_iterations')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
