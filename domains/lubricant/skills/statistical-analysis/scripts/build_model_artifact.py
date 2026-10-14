"""Build the only permitted Phase 3 statistical-model request artifact.

E-2 boundary (deliberately NOT wired): the grease route's canonical decision block
(``statistical_analysis_policy.expected_decision_fields(request, grease=True)``) is NOT
dispatched from this builder. The builder would compute it from the REQUEST while
``validate_model_artifact.py`` re-derives it from the ARTIFACT, and the two materials do
not agree: the grease branch's wording reads ``variance_reference`` / ``variance_verdict``
and the applicability boundary off the request, and the closed ``schemas/model.schema.json``
(``unevaluatedProperties: false``) gives the artifact no slot for any of them -- the
validator would recompute a different ``result``/``next_action`` and FAIL every build.
Both call sites therefore keep the default ``grease=False`` and the policy's grease branch
stays un-dispatched until the model contract itself carries the boundary and the variance
reference. Recorded here (and in ``validate_model_artifact.py``) so the next reader does
not wire it by mistake.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_statistical_analysis import errors_for, grease_without_challenge, unrouted_evidence
from statistical_analysis_policy import expected_decision_fields


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_model_artifact.py <input.json> <temporary-file>"); return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try: data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    def load(key: str) -> dict: return json.loads((input_path.parent / data[key]).read_text(encoding="utf-8"))
    project, method, design_space = (load(key) for key in ("project_artifact", "test_method_artifact", "design_space_artifact"))
    # The grease route may reach this gate without an experiment artifact (that stage is not
    # on its route, and the preflight admits that shape). schemas/model.schema.json still
    # REQUIRES ``experiment_reference`` -- a constraint two scripts record as not ours to
    # change -- so no legal record can be built from such a request. Refuse readably instead
    # of raising KeyError: the gap belongs to the model contract, and it stays visible until
    # that call is made.
    if "experiment_artifact" not in data:
        print(
            "HOLD: experiment_artifact is not on the PRECISION_GREASE_DEV route and "
            "schemas/model.schema.json still requires experiment_reference, so no legal model "
            "record can be built from this request; no artifact generated")
        return 1
    experiment = load("experiment_artifact")
    request = data["analysis"]
    # The grease route carries no CHALLENGES_DEFINED step, so when no challenge artifact
    # travels with the request the recorded Challenge Map link is written as the ASSUMED
    # route-property evidence item. Every other shape - every oil route, and a grease
    # request that supplied a challenge - writes exactly the evidence it wrote before.
    evidence = list(request["evidence"])
    if grease_without_challenge(data, project):
        evidence.append(unrouted_evidence(project["project_id"]))
    artifact = {"schema_version": "0.1.0", "artifact_type": "model", "project_id": project["project_id"], "stage": "MODEL_BUILT", "evidence_scope": experiment["evidence_scope"], **expected_decision_fields(request), "evidence": evidence, "experiment_reference": experiment["experiment_id"], "design_space_reference": design_space["design_space_id"], "test_method_references": [method["method_id"]], "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **{key: request[key] for key in ("model_id", "requested_analyses", "response_references")}}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
