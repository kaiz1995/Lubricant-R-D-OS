"""Build the only permitted FAILURE_CTQ_DEFINED record from preflight-valid input.

The builder is deterministic assembly. For the grease route the CTQ set it records must
carry a declared criteria layer (SCREENING / BENCH / MACHINE) on every CTQ, the failure
mode must be harmonic-drive specific, and the record must hold the full Failure Diagnosis
-> Root-Cause Hypothesis -> Lubricant Contribution chain; those checks live in
``failure_ctq_policy.py`` and run in the preflight before this script may write anything.
Oil routes are assembled exactly as before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from failure_ctq_policy import (
    is_precision_grease,
    policy_errors,
    resolved_project_type,
    unrouted_reference,
    unrouted_statement,
)
from preflight_failure_ctq import (
    CTQ_ITEM_FIELDS,
    errors_for,
    resolved_path,
    schema_errors,
)

# Provenance of the recorded CHALLENGES_DEFINED gap: the route contract is what says
# the stage is on no type_route, so it is what the recorded evidence cites.
ROUTE_CONTRACT_SOURCE = "contracts/state-machine.json"
UNROUTED_EVIDENCE_PREFIX = "EV-UNROUTED-"


def unrouted_evidence(project_id: object) -> dict:
    """The ASSUMED evidence item that records the missing challenge as a gap.

    Never GAP: several preflights refuse a GAP-status item outright, and this is not
    an unresolved gap in the record - it is a recorded property of the route.
    """
    return {
        "evidence_id": f"{UNROUTED_EVIDENCE_PREFIX}{project_id}",
        "statement": unrouted_statement(project_id),
        "source": ROUTE_CONTRACT_SOURCE,
        "status": "ASSUMED",
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_failure_ctq_artifact.py <input.json> <temporary-file>")
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
    _, project = schema_errors(
        resolved_path(data["project_artifact"], input_path), "project.schema.json", "project_artifact"
    )
    failure_ctq = data["failure_ctq"]
    route_type = resolved_project_type(project, failure_ctq)
    # Construction-boundary re-check: the builder must not assemble a grease record around a
    # CTQ set its own route forbids, even when a caller reaches this script directly.
    policy = policy_errors(failure_ctq, route_type)
    if policy:
        print(f"HOLD: missing or invalid: {', '.join(policy)}; no artifact generated")
        return 1
    # The grease route carries no CHALLENGES_DEFINED step, so when no challenge artifact
    # travels with the request the Challenge Map link is RECOMPUTED from the charter's own
    # project_id rather than copied through: the marker is a property of the route, and
    # recomputing it here is what makes it agree with what the preflight enforced and what
    # test_method's existing comparison reads back. When a challenge artifact IS supplied,
    # the supplied id is copied through exactly as before, on every route.
    grease_without_challenge = is_precision_grease(route_type) and resolved_path(data.get("challenge_artifact"), input_path) is None
    challenge_reference = (
        unrouted_reference(project["project_id"]) if grease_without_challenge else failure_ctq.get("challenge_reference")
    )

    # Deterministic projection of each CTQ onto the contract's own field order; unknown
    # keys are dropped rather than copied, so the artifact cannot carry an unpublished field.
    ctqs = [
        {key: ctq[key] for key in CTQ_ITEM_FIELDS if key in ctq}
        for ctq in failure_ctq["ctqs"]
    ]
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "failure_ctq", "project_id": project["project_id"],
        "stage": "FAILURE_CTQ_DEFINED",
        "decision_question": f"What CTQ and test chain address failure {failure_ctq.get('failure_id')}?",
        "hypothesis": (
            f"Failure mode {failure_ctq.get('failure_mode')} is recorded as a diagnostic hypothesis "
            "requiring a testable CTQ chain."
        ),
        "uncertainty": (
            "Diagnosis, hypotheses and lubricant contribution remain unverified; this record does not "
            "qualify a test method and does not make a performance conclusion."
        ),
        "evidence": [
            {
                "evidence_id": item.get("evidence_id"), "statement": item.get("statement"),
                "source": item.get("source"), "status": item.get("status"),
            }
            for item in data["evidence"]
        ]
        + ([unrouted_evidence(project["project_id"])] if grease_without_challenge else []),
        "decision_rule": "Do not act on formulation until diagnosis, hypothesis and lubricant contribution are recorded.",
        "result": "A testable CTQ chain is defined; no performance conclusion is made.",
        "decision": "GO", "next_action": "Qualify the proposed test method.",
        "challenge_reference": challenge_reference,
        "failure_id": failure_ctq.get("failure_id"),
        "failure_mode": failure_ctq.get("failure_mode"),
        "mechanism": failure_ctq.get("mechanism"),
        "failure_diagnosis": failure_ctq.get("failure_diagnosis"),
        "root_cause_hypotheses": failure_ctq.get("root_cause_hypotheses"),
        "lubricant_contribution": failure_ctq.get("lubricant_contribution"),
        "ctqs": ctqs,
        "test_chain": failure_ctq.get("test_chain"),
    }
    if isinstance(failure_ctq.get("interface_failure_modes"), list):
        artifact["interface_failure_modes"] = failure_ctq["interface_failure_modes"]
    if is_precision_grease(route_type):
        artifact["uncertainty"] = (
            "Precision-gear grease route: every CTQ declares one layer of the three-layer criteria "
            "chain, the failure mode is harmonic-drive specific, and the record holds Failure "
            f"Diagnosis -> Root-Cause Hypothesis -> Lubricant Contribution. {artifact['uncertainty']}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
