"""Build the only permitted Phase 3 experiment-design request artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from doe_design_policy import GREASE_PROJECT_TYPE, expected_decision_fields
from preflight_doe_design import errors_for, grease_without_challenge, resolved_path, unrouted_evidence


REQUEST_FIELDS = ("experiment_design_id", "factor_references", "design", "run_plan", "responses", "guardrails", "expected_information_value", "mixture_total", "resource_envelope")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_experiment_design_artifact.py <input.json> <temporary-file>")
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
    method = json.loads(resolved_path(data["test_method_artifact"], input_path).read_text(encoding="utf-8"))
    design_space = json.loads(resolved_path(data["design_space_artifact"], input_path).read_text(encoding="utf-8"))
    request = data["experiment_design"]
    # The grease route carries no CHALLENGES_DEFINED step, so when no challenge artifact
    # travels with the request the recorded Challenge Map link is written as the ASSUMED
    # route-property evidence item. Every other shape - every oil route, and a grease
    # request that supplied a challenge - writes exactly the evidence it wrote before.
    evidence = list(request["evidence"])
    if grease_without_challenge(data, project):
        evidence.append(unrouted_evidence(project["project_id"]))
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "experiment_design", "project_id": project["project_id"], "stage": "EXPERIMENT_DESIGNED", "evidence_scope": method["evidence_scope"],
        **expected_decision_fields(request, project.get("project_type")), "evidence": evidence, "design_space_reference": design_space["design_space_id"], "test_method_references": [method["method_id"]],
        **{field: request[field] for field in REQUEST_FIELDS if field in request},
    }
    # Grease step 8: record which bench schedule bounded this round, when one was
    # supplied. Additive and optional, so a pre-existing input (no bench artifact)
    # builds exactly the artifact it built before.
    if project.get("project_type") == GREASE_PROJECT_TYPE:
        # The route marker is recorded only on the grease route, so every
        # pre-existing oil-route artifact is byte-identical to what it was.
        artifact["project_type"] = project["project_type"]
    if data.get("bench_artifact") is not None:
        bench_path = resolved_path(data["bench_artifact"], input_path)
        bench = json.loads(bench_path.read_text(encoding="utf-8"))
        artifact["bench_reference"] = bench["bench_id"]
        artifact["available_bench_slots"] = bench["available_bench_slots"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
