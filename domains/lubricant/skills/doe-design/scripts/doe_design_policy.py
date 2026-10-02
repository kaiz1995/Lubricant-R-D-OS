"""Deterministic decision wording for a supplied Phase 4 DOE-engine request."""

from __future__ import annotations


# WP-04a narrows the family vocabulary to the channels the Phase 4 DOE engine can
# actually solve. Mixture families route MIXTURE_CLOSED variables into the
# engine's ``components``; factor families route INDEPENDENT variables into
# ``factors``; MIXTURE_PROCESS accepts both. TAGUCHI_ROBUST and the pre-WP-04a
# screening/RSM families are not solvable and are deliberately not offered here.
MIXTURE_FAMILIES = ("MIXTURE", "CONSTRAINED_MIXTURE")
FACTOR_FAMILIES = ("FULL_FACTORIAL", "FRACTIONAL_FACTORIAL", "SPLIT_PLOT")
COMBINED_FAMILIES = ("MIXTURE_PROCESS",)
SUPPORTED_FAMILIES = MIXTURE_FAMILIES + FACTOR_FAMILIES + COMBINED_FAMILIES


def has_gap(request: dict) -> bool:
    return any(isinstance(item, dict) and item.get("status") == "GAP" for item in request.get("evidence", []))


def expected_decision_fields(request: dict) -> dict[str, str]:
    design_id = request.get("experiment_design_id", "")
    design = request.get("design") if isinstance(request.get("design"), dict) else {}
    run_plan = request.get("run_plan") if isinstance(request.get("run_plan"), dict) else {}
    family = design.get("family", "")
    target_count = run_plan.get("target_count", "")
    ready = family in SUPPORTED_FAMILIES and not has_gap(request)
    supported = "/".join(SUPPORTED_FAMILIES)
    return {
        "decision_question": f"Can supplied {family} request {design_id} be handed to the Phase 4 deterministic engine?",
        "hypothesis": f"{design_id} records supplied {family} planning inputs for later deterministic point generation.",
        "uncertainty": "Supplied design family, factors, target count, replicates, center points, randomization, response roles, guardrails, total, and information-value statements are not independently verified; statistical sufficiency is not verified and no DOE point, formula, measurement, result, cost, performance, optimization, or downstream conclusion is established.",
        "decision_rule": f"Hand off only a supplied {supported} request with linked qualified D/P method, feasible same-unit bounds, complete responses and guardrails, role-consistent design-space variables, and evidence without GAP.",
        "result": f"{design_id} is {'eligible' if ready else 'not eligible'} for Phase 4 deterministic point generation; family {family} and target count {target_count} are supplied planning inputs, not generated DOE points or a statistical-sufficiency conclusion.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Hand {design_id} to the Phase 4 deterministic engine without adding DOE points." if ready else "Retain supplied evidence and resolve the recorded design-request gap before any Phase 4 handoff.",
    }
