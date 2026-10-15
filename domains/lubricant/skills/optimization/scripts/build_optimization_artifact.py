"""Build the only permitted Phase 3 optimization request artifact.

ADDITIVE (precision-grease step 14): on that route the artifact lands at
``NON_INFERIORITY_PASSED`` instead of ``OPTIMIZED``, records the objective type the
policy layer resolved (CONSTRAINT_SATISFACTION when the caller supplied none, because
cost is a constraint and never an objective weighed against performance), cites the
variance assessment that admitted the round, and carries the model's applicability
boundary as ``trust_region`` so the engine can enforce it. The six oil routes keep
their original stage, wording, and field set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from optimization_policy import (
    MODEL_TRUST_REGION_INPUT_FIELD,
    TRUST_REGION_FIELD,
    expected_decision_fields,
    grease_route,
    resolve_objective_type,
    stage_for,
    trust_region_from_boundary,
)
from preflight_optimization import errors_for, grease_without_challenge, unrouted_evidence


def _evidence(project: dict, request: dict, data: dict) -> list:
    """The request's evidence, plus the grease route's recorded Challenge Map gap.

    The grease route carries no CHALLENGES_DEFINED step, so when no challenge artifact
    travels with the request the recorded link is written as the ASSUMED route-property
    evidence item. Every other shape - every oil route, and a grease request that supplied
    a challenge - writes exactly the evidence it wrote before.
    """
    evidence = list(request["evidence"])
    if grease_without_challenge(data, project):
        evidence.append(unrouted_evidence(project["project_id"]))
    return evidence


def build_artifact(project: dict, model: dict, request: dict, variance: dict | None, boundary: object, data: dict) -> dict:
    """Assemble the optimization artifact. Pure function of validated input + upstreams.

    ``data`` is the validated request object itself: ``grease_without_challenge`` reads
    the presence of the challenge key off it, which is the route's own input shape.
    """
    grease = grease_route(project)
    trust_region = trust_region_from_boundary(boundary) if grease else None
    variance_id = variance["variance_id"] if isinstance(variance, dict) else None
    # The decision block is computed from the RESOLVED request, so a grease request that
    # omitted objective_type states the default it actually received.
    resolved = {**request, "objective_type": resolve_objective_type(request, grease)}
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "optimization",
        "project_id": project["project_id"],
        "stage": stage_for(grease),
        "evidence_scope": model["evidence_scope"],
        **expected_decision_fields(resolved, grease, trust_region, variance_id if grease else None),
        "evidence": _evidence(project, request, data),
        "model_reference": model["model_id"],
        "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE",
        "optimization_id": request["optimization_id"],
        "objective_type": resolve_objective_type(request, grease),
        "objectives": request["objectives"],
        "methods": request["methods"],
    }
    if grease:
        artifact["variance_reference"] = variance_id
        artifact[TRUST_REGION_FIELD] = trust_region
    return artifact


def main() -> int:
    if len(sys.argv) != 3: print("Usage: python build_optimization_artifact.py <input.json> <temporary-file>"); return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try: data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, input_path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    def load(key: str) -> dict: return json.loads((input_path.parent / data[key]).read_text(encoding="utf-8"))
    project = load("project_artifact"); model = load("model_artifact"); request = data["optimization"]
    variance = load("variance_artifact") if "variance_artifact" in data else None
    artifact = build_artifact(project, model, request, variance, data.get(MODEL_TRUST_REGION_INPUT_FIELD), data)
    output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path} stage={artifact['stage']} objective_type={artifact['objective_type']}"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
