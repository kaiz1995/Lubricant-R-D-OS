"""Validate one deterministic merged bench artifact, including every derived value.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/bench.schema.json`` with
   the shared ``common.schema.json`` in the registry -- the constant
   ``artifact_type`` / ``stage``, the 17 required fields, the iteration entry
   shape and ``unevaluatedProperties: false``.
2. Semantic: the artifact equals what ``bench_policy`` deterministically derives
   from its own fields -- the derived slot count, the cross-field ledger rules
   JSON Schema cannot express (``current_iteration`` within ``max_iterations`` and
   at the round the ledger stands at, W0/W1/W2), the "only CONTINUE authorizes
   another round" and exit-round-only (E2=B) rules, the contract-default
   provenance marker (its presence must be true, i.e. the cap must be the
   contract's published figure), and the canonical merged decision block.

This catches a hand-edited artifact that is schema-legal but not policy-legal --
for example a record whose ``decision`` was softened from HOLD to GO while its
evidence still carries a GAP, a plan whose ``current_iteration`` was bumped past
the rounds it actually recorded, or one whose cap was edited without touching the
provenance item that claims it came from the contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from bench_policy import BENCH_FIELD_FIELDS, BENCH_STAGE, policy_errors
from preflight_bench_registration import SCHEMA_NAMES, bench_field_errors, schema_dir


def semantic_errors(artifact: object) -> list[str]:
    """The bench-block field rules plus everything bench_policy re-derives.

    The bench block's evidence is not checked here: the artifact-level evidence
    array is the two blocks' evidence merged (bench first), so it is checked as a
    whole by ``bench_policy.evidence_errors`` inside ``policy_errors``.
    """
    if not isinstance(artifact, dict):
        return ["artifact must be a JSON object"]
    bench_fields = {field: artifact.get(field) for field in BENCH_FIELD_FIELDS}
    errors = bench_field_errors(bench_fields)
    errors.extend(policy_errors(artifact))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_bench_artifact.py <artifact.json>")
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
        f"bench.schema.json: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in Draft202012Validator(loaded["bench.schema.json"], registry=registry).iter_errors(artifact)
    ]
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(
        "PASS: deterministic merged bench artifact conforms to the bench contract "
        f"(stage={BENCH_STAGE} bench_id={artifact.get('bench_id')} campaign_id={artifact.get('campaign_id')} "
        f"decision={artifact.get('decision')} iterations={len(artifact.get('iterations') or [])}"
        f"/{artifact.get('max_iterations')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
