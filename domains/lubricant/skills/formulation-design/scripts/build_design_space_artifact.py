"""Build the only permitted Stage 4 artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from design_space_policy import expected_decision_fields
from preflight_formulation_design import (
    errors_for,
    grease_without_challenge,
    resolved_path,
    unrouted_evidence,
)


DESIGN_SPACE_FIELDS = ("design_space_id", "scope", "variables", "ctq_references", "qualified_test_method_references", "constraints")
# Copied through only when supplied, so an oil-route artifact keeps exactly the
# field set it had before.
OPTIONAL_DESIGN_SPACE_FIELDS = ("process_reference", "baseline_process_reference", "feasibility_regions")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_design_space_artifact.py <input.json> <temporary-file>")
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
    project = json.loads(resolved_path(data["project_artifact"], input_path).read_text(encoding="utf-8"))
    design_space = data["design_space"]
    # The grease route carries no CHALLENGES_DEFINED step, so when no challenge artifact
    # travels with the request the recorded Challenge Map link is written as the ASSUMED
    # route-property evidence item. Every other shape - every oil route, and a grease
    # request that supplied a challenge - writes exactly the evidence it wrote before.
    evidence = list(design_space["evidence"])
    if grease_without_challenge(data, project):
        evidence.append(unrouted_evidence(project["project_id"]))
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "design_space", "project_id": project["project_id"], "stage": "DESIGN_SPACE_DEFINED",
        **expected_decision_fields(design_space, project.get("project_type")), "evidence": evidence,
        **{field: design_space[field] for field in DESIGN_SPACE_FIELDS},
    }
    for field in OPTIONAL_DESIGN_SPACE_FIELDS:
        if field in design_space:
            artifact[field] = design_space[field]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
