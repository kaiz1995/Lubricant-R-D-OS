"""Validate one BENCH_TESTED observation against the contract and the censoring discipline.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/bench_test.schema.json`` with the
   common contract in the registry, so the schema's two ``if/then`` rules are enforced
   (a RIGHT-censored run forces ``event_occurred: false`` and ``event_time: null``; a
   censoring type other than NONE forces a non-empty ``stop_reason``). Schema errors are
   reported with their instance path so the citation is traceable.
2. Semantic: the artifact is re-judged by ``bench_test_policy`` on its own fields - the
   identity requirement, the censoring discipline (which is stricter than the schema: an
   event-free run must also declare why it stopped), and the canonical decision block.
   This catches a hand-edited artifact that is schema-legal but not policy-legal: a
   censoring time rewritten into ``event_time``, an unexplained stop, or a decision block
   that claims an outcome the recorded observation does not support.

The censoring citation is the schema's own: a right-censored observation must never be
recorded or used as an end-point value, because once a censoring time is mixed in as an
end-point the variance estimate is wrong and every downstream conclusion is void.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from bench_test_policy import (
    BENCH_TEST_ARTIFACT_TYPE,
    BENCH_TEST_STAGE,
    EVIDENCE_SCOPES,
    expected_decision_fields,
    has_text,
    recorded_record,
    record_field_errors,
)
from preflight_experiment_import import BENCH_SCHEMA_NAMES, bench_schema_dir


def schema_errors(artifact: object) -> list[str]:
    directory = bench_schema_dir()
    loaded = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in BENCH_SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(loaded["bench_test.schema.json"], registry=registry)
    return [
        f"bench_test.schema.json: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in validator.iter_errors(artifact)
    ]


def semantic_errors(artifact: object) -> list[str]:
    """Bench-side policy checks: identity, censoring discipline, decision block."""
    if not isinstance(artifact, dict):
        return ["artifact must be a JSON object"]
    errors: list[str] = []
    if artifact.get("artifact_type") != BENCH_TEST_ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {BENCH_TEST_ARTIFACT_TYPE}")
    if artifact.get("stage") != BENCH_TEST_STAGE:
        errors.append(f"stage must be {BENCH_TEST_STAGE}")
    if artifact.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    if not has_text(artifact.get("project_id")):
        errors.append("project_id")
    errors.extend(record_field_errors(recorded_record(artifact)))
    for field, value in expected_decision_fields(recorded_record(artifact), artifact.get("evidence_scope")).items():
        if artifact.get(field) != value:
            errors.append(
                f"{field} must equal the deterministic bench-test policy: the observation is recorded "
                "exactly as it happened, and a single run is a record rather than a verdict"
            )
    return errors

def main() -> int:
    if len(sys.argv) != 2: print("Usage: python validate_bench_test_artifact.py <artifact.json>"); return 1
    try: artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"FAIL: cannot read artifact or schemas: {error}"); return 1
    try: errors = schema_errors(artifact)
    except (OSError, json.JSONDecodeError) as error: print(f"FAIL: cannot read artifact or schemas: {error}"); return 1
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors: print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic bench_test artifact conforms to the BENCH_TESTED contract and the censoring discipline")
    return 0


if __name__ == "__main__": raise SystemExit(main())
