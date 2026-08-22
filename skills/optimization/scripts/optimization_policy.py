"""Deterministic wording for a Phase 4 optimization handoff."""

from __future__ import annotations


def has_gap(value: dict) -> bool:
    return any(isinstance(item, dict) and item.get("status") == "GAP" for item in value.get("evidence", []))


def expected_decision_fields(value: dict) -> dict[str, str]:
    optimization_id = value.get("optimization_id", "")
    methods = ", ".join(value.get("methods", []))
    return {
        "decision_question": f"Can supplied optimization request {optimization_id} be handed to the Phase 4 deterministic engine?",
        "hypothesis": f"{optimization_id} records supplied objectives and methods without calculating an optimum.",
        "uncertainty": "No candidate, Pareto front, desirability, non-inferiority result, constraint evaluation, trade-off, formulation recommendation, performance conclusion, or verification result is established by this Phase 3 artifact.",
        "decision_rule": "Hand off only a linked MODEL_BUILT request with supplied objectives, supported Phase 3 methods, and evidence without GAP.",
        "result": f"{optimization_id} records supplied methods {methods}; no optimization calculation or recommendation has been produced.",
        "decision": "GO",
        "next_action": f"Hand {optimization_id} to the Phase 4 deterministic engine without adding candidates or recommendations.",
    }
