"""Build the only permitted SCREENING_PASSED artifact from preflight-valid input.

Deterministic assembly only. Every judgement - the aggregate verdict computed from the
per-test verdicts, the bench gate derived from that verdict, the release rule, and the
canonical decision block - lives in ``grease_screening_policy`` so this builder and the
validator cannot disagree.

The builder never invents a screened index, a limit, or a measurement. An index the caller
did not measure stays absent (reported as a NOTE by the preflight); an index the caller
could not determine is recorded INCONCLUSIVE with its reason, which is a record, not a
guess.

The input-only per-test ``note`` field has no slot in the frozen screening contract
(``additionalProperties: false``), so it is consumed by the policy and stripped here. The
reason for an INCONCLUSIVE index is therefore carried in the artifact's own ``result`` line
and in the run's NOTE output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from grease_screening_policy import (
    SCREENING_ARTIFACT_FIELDS,
    TEST_ARTIFACT_FIELDS,
    derived_overall_verdict,
    derived_screening,
    expected_decision_fields,
)
from preflight_grease_screening import errors_for, resolved_path, schema_artifact


def recorded_screening(screening: dict) -> dict:
    """Project the screening input into its artifact form, deriving the two derived fields."""
    recorded = {field: screening.get(field) for field in SCREENING_ARTIFACT_FIELDS}
    tests = screening.get("tests")
    if isinstance(tests, list):
        recorded["tests"] = [
            {field: test.get(field) for field in TEST_ARTIFACT_FIELDS}
            if isinstance(test, dict)
            else test
            for test in tests
        ]
    recorded.update(derived_screening(recorded.get("tests")))
    return recorded


def build_screening_artifact(data: dict, project: dict) -> dict:
    """Assemble the screening artifact. Pure function of validated input + charter."""
    screening = recorded_screening(data["screening"])
    evidence_scope = data["evidence_scope"]
    return {
        "schema_version": "0.1.0",
        "artifact_type": "screening",
        "project_id": project["project_id"],
        "stage": "SCREENING_PASSED",
        "evidence_scope": evidence_scope,
        **expected_decision_fields(screening, evidence_scope),
        "evidence": data["evidence"],
        **screening,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_screening_artifact.py <input.json> <temporary-file>")
        return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    _, project = schema_artifact(
        resolved_path(data["project_artifact"], input_path), "project.schema.json", "project_artifact"
    )
    artifact = build_screening_artifact(data, project)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"BUILT: {output_path} stage={artifact['stage']} "
        f"overall_verdict={artifact['overall_verdict']} gate_to_bench={artifact['gate_to_bench']} "
        f"decision={artifact['decision']}"
    )
    print(f"DERIVED: worst per-test verdict={derived_overall_verdict(artifact['tests'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
