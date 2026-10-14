"""Build the only permitted Phase 3 statistical-model request artifact.

E-2 boundary (still deliberately NOT wired): the grease route's canonical decision block
(``statistical_analysis_policy.expected_decision_fields(request, grease=True)``) is NOT
dispatched from this builder. The blocker is narrower than it was -- P-2 (2026-10-14) added
the ``applicability_boundary`` slot to ``schemas/model.schema.json``, so the region survives
-- but the grease branch also reads ``variance_reference`` / ``variance_verdict``, and the
contract still has no slot for those, so a validator re-deriving the block from the artifact
would recompute a different ``result``/``next_action`` and FAIL every build. Both call sites
therefore keep the default ``grease=False`` until the model contract carries a variance
reference too. Recorded here (and in ``validate_model_artifact.py``) so the next reader does
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
    # P-2 (2026-10-14): the model is fitted from the round it was fitted on, and that round
    # is named by whichever carrier the route has -- an experiment record on the oil routes
    # (and on a grease round that imported one), or the campaign ledger on the grease route,
    # which carries no experiment stage. schemas/model.schema.json's anyOf accepts either
    # citation; this builder writes the one the request supplies.
    experiment = load("experiment_artifact") if "experiment_artifact" in data else None
    campaign = load("campaign_artifact") if "campaign_artifact" in data else None
    if experiment is None and campaign is None:
        print(
            "HOLD: neither experiment_artifact nor campaign_artifact travels with this request, so the round the "
            "model was fitted on cannot be named; no artifact generated")
        return 1
    request = data["analysis"]
    # The grease route carries no CHALLENGES_DEFINED step, so when no challenge artifact
    # travels with the request the recorded Challenge Map link is written as the ASSUMED
    # route-property evidence item. Every other shape - every oil route, and a grease
    # request that supplied a challenge - writes exactly the evidence it wrote before.
    evidence = list(request["evidence"])
    if grease_without_challenge(data, project):
        evidence.append(unrouted_evidence(project["project_id"]))
    artifact = {"schema_version": "0.1.0", "artifact_type": "model", "project_id": project["project_id"], "stage": "MODEL_BUILT", "evidence_scope": (experiment or campaign)["evidence_scope"], **expected_decision_fields(request), "evidence": evidence, "design_space_reference": design_space["design_space_id"], "test_method_references": [method["method_id"]], "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **{key: request[key] for key in ("model_id", "requested_analyses", "response_references")}}
    if experiment is not None:
        artifact["experiment_reference"] = experiment["experiment_id"]
    if campaign is not None:
        # The round the ledger STANDS AT is the newest recorded entry (W1 has already moved
        # the counter to k+1, and the entry that opened it is round k) -- the same round the
        # preflight's entry-level binding asserts the variance record against.
        rounds = campaign.get("iterations") if isinstance(campaign.get("iterations"), list) else []
        newest = rounds[-1] if rounds and isinstance(rounds[-1], dict) else {}
        artifact["campaign_reference"] = campaign["campaign_id"]
        artifact["iteration"] = newest.get("iteration", campaign.get("current_iteration"))
    # P-2: the applicability boundary is persisted HERE, at the moment the modelling step
    # judges it, so step 16 reads the recorded region instead of asking for it again.
    boundary = request.get("applicability_boundary")
    if boundary is not None:
        artifact["applicability_boundary"] = boundary
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
