"""Build the only permitted Stage 3 artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_test_method import errors_for, grease_without_challenge, resolved_path, unrouted_evidence
from qualification_policy import expected_decision_fields


METHOD_FIELDS = ("method_id", "name", "standard", "target_failure_reference", "role", "qualification_metrics", "qualification_basis", "qualification_status")
# Grease-route additions. Copied through only when supplied, so an oil-route
# artifact keeps exactly the field set it had before.
OPTIONAL_METHOD_FIELDS = ("qualification_pipeline", "reference_material_reference")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_test_method_artifact.py <input.json> <temporary-file>")
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
    project_path = resolved_path(data["project_artifact"], input_path)
    project = json.loads(project_path.read_text(encoding="utf-8"))
    method = {**data["test_method"], "evidence": data["evidence"], "evidence_scope": data["evidence_scope"]}
    # The grease route carries no CHALLENGES_DEFINED step, so when no challenge artifact
    # travels with the request the recorded Challenge Map link is written as the ASSUMED
    # route-property evidence item. Every other shape - every oil route, and a grease
    # request that supplied a challenge - writes exactly the evidence it wrote before.
    evidence = list(data["evidence"])
    if grease_without_challenge(data, project):
        evidence.append(unrouted_evidence(project["project_id"]))
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "test_method", "project_id": project["project_id"], "stage": "TEST_METHODS_QUALIFIED", "evidence_scope": data["evidence_scope"],
        **expected_decision_fields(method, project.get("project_type")), "evidence": evidence,
        **{field: method[field] for field in METHOD_FIELDS},
    }
    for field in OPTIONAL_METHOD_FIELDS:
        if field in method:
            artifact[field] = method[field]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
