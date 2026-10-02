"""Deterministic application-definition policy: the fail-closed verdict rules.

`result` is a controlled verdict (PASS / FAIL / INCONCLUSIVE / GAP). A PASS can
only be produced when every acceptance criterion carries a determined, OBSERVED
threshold, the life-claim boundary is non-empty and OBSERVED, and no
counterexample was observed. An acceptance criterion with no determined
threshold MUST be recorded with status GAP (never silently omitted); an empty
criteria list forces `result = "GAP"`. This policy is shared by preflight,
builder and validator.

Interface for WP-06 (Stage 13 APPLIED evidence aggregation): the fields
`application_id`, `project_reference`, `formula_reference`,
`process_window_reference`, `bench_references`, `acceptance_criteria`,
`result`, `counterexamples` and `life_claim_boundary` are the stable contract.
"""

from __future__ import annotations

import math

INPUT_FIELDS = {
    "application_id", "project_reference", "formula_reference", "process_window_reference",
    "bench_references", "acceptance_criteria", "result", "counterexamples",
    "life_claim_boundary", "source", "evidence_id", "evidence_scope", "evidence",
}
ARTIFACT_FIELDS = (
    "application_id", "project_reference", "formula_reference", "process_window_reference",
    "bench_references", "acceptance_criteria", "result", "counterexamples", "life_claim_boundary",
)
RESULTS = ("PASS", "FAIL", "INCONCLUSIVE", "GAP")
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}
OPERATORS = {"<", "<=", "==", ">=", ">"}
CRITERION_FIELDS = {"criterion_id", "statement", "threshold", "operator", "unit", "source", "evidence_id", "status"}
COUNTEREXAMPLE_FIELDS = {"counterexample_id", "statement", "observation", "evidence_reference"}
BOUNDARY_FIELDS = {"claim_scope", "status", "validated_conditions", "extrapolation_basis", "evidence_reference"}
CONDITION_FIELDS = {"condition_id", "parameter", "lower_bound", "upper_bound", "unit"}


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def has_gap(application: dict) -> bool:
    evidence = application.get("evidence")
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def boundary_is_empty(value: object) -> bool:
    """True when the life-claim boundary carries no validated condition or is GAP."""
    if not isinstance(value, dict):
        return True
    conditions = value.get("validated_conditions")
    return value.get("status") != "OBSERVED" or not isinstance(conditions, list) or not conditions


def pass_blockers(application: dict) -> list[str]:
    """Every reason a PASS verdict is not yet justified. Empty list = PASS allowed."""
    reasons: list[str] = []
    criteria = application.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        reasons.append("acceptance_criteria must be a non-empty array to claim PASS")
    else:
        for index, criterion in enumerate(criteria):
            label = f"acceptance_criteria[{index}]"
            if not isinstance(criterion, dict):
                reasons.append(f"{label} is not an object")
                continue
            if criterion.get("status") != "OBSERVED":
                reasons.append(f"{label}.status must be OBSERVED to claim PASS (criteria with GAP block PASS)")
            if "threshold" not in criterion or not is_finite_number(criterion.get("threshold")):
                reasons.append(f"{label}.threshold must be a determined number to claim PASS")
    boundary = application.get("life_claim_boundary")
    if boundary_is_empty(boundary):
        reasons.append("life_claim_boundary must be OBSERVED with at least one validated condition to claim PASS")
    counterexamples = application.get("counterexamples")
    if isinstance(counterexamples, list) and counterexamples:
        reasons.append("counterexamples must be empty to claim PASS")
    return reasons


def expected_decision_fields(application: dict) -> dict[str, str]:
    application_id = application.get("application_id", "")
    passed = application.get("result") == "PASS"
    return {
        "decision_question": f"Does the supplied application evidence justify application {application_id}?",
        "hypothesis": f"{application_id} records acceptance criteria, counterexamples and the life-claim boundary for the applied formula+process.",
        "uncertainty": "Supplied criteria, observations and conditions are not independently verified; recorded ASSUMED evidence remains assumed and this record does not by itself establish a field, life, or release conclusion.",
        "decision_rule": "Record the supplied verdict as-is; a PASS is only admissible with determined OBSERVED criteria, a non-empty OBSERVED life-claim boundary, and no counterexamples.",
        "result": application.get("result"),
        "decision": "GO" if passed else "HOLD",
        "next_action": f"Retain {application_id} as an application record with verdict {application.get('result')}.",
    }
