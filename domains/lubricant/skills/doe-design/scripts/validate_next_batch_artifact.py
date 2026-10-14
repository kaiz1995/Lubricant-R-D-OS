"""Validate one deterministic NEXT_BATCH_DECIDED artifact against the contract and the policy.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/next_batch.schema.json`` with the
   common contract in the registry. That schema carries the stage constant, the six stop
   values, the "a stop needs its reason" if/then rule and the required sample fields;
   schema errors are reported with their instance path so the citation is traceable.
2. Semantic: the artifact equals what ``next_batch_policy`` deterministically derives from
   its own fields - the canonical decision block (only CONTINUE is a GO) and the other
   direction of the stop-reason rule (``stop_rationale`` is recorded only for a stop, which
   the schema does not forbid). This catches a hand-edited artifact that is schema-legal
   but not policy-legal: a decision block that claims another round while stop_state says
   the loop has stopped, or a reason attached to a round that continues.

The cross-artifact checks (the campaign carrier - the merged bench artifact
``bench.json`` - the round's design and the round's variance record must agree with this
record) live in the preflight and the builder, which are the only steps that see the
upstream artifacts; this validator re-derives everything that the record itself carries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from next_batch_policy import expected_decision_fields, stop_rationale_errors
from preflight_next_batch import NEXT_BATCH_STAGE, SCHEMA_NAMES, schema_dir


def schema_errors(artifact: object) -> list[str]:
    schemas = schema_dir()
    loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(loaded["next_batch.schema.json"], registry=registry)
    return [
        f"next_batch.schema.json: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in validator.iter_errors(artifact)
    ]


def semantic_errors(artifact: object) -> list[str]:
    if not isinstance(artifact, dict):
        return ["artifact must be a JSON object"]
    errors = list(stop_rationale_errors(artifact, "next_batch artifact"))
    for field, value in expected_decision_fields(artifact, artifact.get("campaign_reference")).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic next-batch policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_next_batch_artifact.py <artifact.json>")
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
    if isinstance(artifact, dict) and artifact.get("stage") != NEXT_BATCH_STAGE:
        errors.append(f"stage must be {NEXT_BATCH_STAGE}")
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(
        "PASS: deterministic next-batch artifact conforms to the step-13b contract "
        f"(stop_state={artifact['stop_state']} decision={artifact['decision']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
