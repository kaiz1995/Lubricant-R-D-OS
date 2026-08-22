"""Deterministic wording for a Phase 4 statistical-analysis handoff."""

from __future__ import annotations


def has_gap(value: dict) -> bool:
    return any(isinstance(item, dict) and item.get("status") == "GAP" for item in value.get("evidence", []))


def expected_decision_fields(value: dict) -> dict[str, str]:
    model_id = value.get("model_id", "")
    analyses = ", ".join(value.get("requested_analyses", []))
    return {
        "decision_question": f"Can supplied analysis request {model_id} be handed to the Phase 4 deterministic engine?",
        "hypothesis": f"{model_id} records supplied analysis requests without calculating a statistical model.",
        "uncertainty": "No coefficients, fit statistics, residual diagnosis, lack-of-fit result, interval, sensitivity result, adequacy conclusion, formulation, performance conclusion, or optimization is established by this Phase 3 artifact.",
        "decision_rule": "Hand off only linked observed-experiment response CTQs with a qualified method and evidence without GAP.",
        "result": f"{model_id} records supplied requests for {analyses}; no statistical calculation or model conclusion has been produced.",
        "decision": "GO",
        "next_action": f"Hand {model_id} to the Phase 4 deterministic engine without adding model results.",
    }
