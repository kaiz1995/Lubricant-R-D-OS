"""Deterministic decision wording for a supplied Phase 4 DOE-engine request."""

from __future__ import annotations


def has_gap(request: dict) -> bool:
    return any(isinstance(item, dict) and item.get("status") == "GAP" for item in request.get("evidence", []))


def expected_decision_fields(request: dict) -> dict[str, str]:
    design_id = request.get("experiment_design_id", "")
    design = request.get("design") if isinstance(request.get("design"), dict) else {}
    run_plan = request.get("run_plan") if isinstance(request.get("run_plan"), dict) else {}
    family = design.get("family", "")
    target_count = run_plan.get("target_count", "")
    ready = family == "CONSTRAINED_MIXTURE" and not has_gap(request)
    return {
        "decision_question": f"Can supplied {family} request {design_id} be handed to the Phase 4 deterministic engine?",
        "hypothesis": f"{design_id} records supplied constrained-mixture planning inputs for later deterministic point generation.",
        "uncertainty": "Supplied design family, factors, target count, replicates, center points, randomization, response roles, guardrails, total, and information-value statements are not independently verified; statistical sufficiency is not verified and no DOE point, formula, measurement, result, cost, performance, optimization, or downstream conclusion is established.",
        "decision_rule": "Hand off only a supplied CONSTRAINED_MIXTURE request with linked qualified D/P method, feasible same-unit formulation bounds and total, complete responses and guardrails, and evidence without GAP.",
        "result": f"{design_id} is {'eligible' if ready else 'not eligible'} for Phase 4 deterministic point generation; family {family} and target count {target_count} are supplied planning inputs, not generated DOE points or a statistical-sufficiency conclusion.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Hand {design_id} to the Phase 4 deterministic engine without adding DOE points." if ready else "Retain supplied evidence and resolve the recorded design-request gap before any Phase 4 handoff.",
    }
