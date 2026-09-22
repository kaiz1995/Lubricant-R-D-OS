"""Deterministic disposition wording for a Phase 3 review Gate."""

from __future__ import annotations


def has_gap(value: dict) -> bool:
    return any(isinstance(item, dict) and item.get("status") == "GAP" for item in value.get("evidence", []))


def final_status(value: dict, evidence_scope: str | None = None) -> str:
    if evidence_scope == "SYNTHETIC":
        return "HOLD"
    if value.get("gate_status") == "GO" and (value.get("unsatisfied_conditions") or value.get("evidence_gaps") or has_gap(value)):
        return "HOLD"
    return value.get("gate_status", "HOLD")


def expected_decision_fields(value: dict) -> dict[str, str]:
    gate_id, status = value.get("gate_id", ""), final_status(value, value.get("evidence_scope"))
    return {
        "decision_question": f"Does review Gate {gate_id} have sufficient supplied conditions and evidence?",
        "hypothesis": f"{gate_id} records supplied review conditions without creating a Freeze or Close artifact.",
        "uncertainty": "This review records supplied conditions, gaps, risks, and disposition only; it does not create new experiment, model, optimization, Freeze, Close, or product-performance evidence.",
        "decision_rule": "GO requires no unsatisfied conditions, no evidence gaps, and no GAP evidence; PIVOT, KILL, and FREEZE require explicit reason and evidence; otherwise retain HOLD.",
        "result": f"{gate_id} has deterministic gate disposition {status} from the supplied review conditions and evidence." if value.get("evidence_scope") != "SYNTHETIC" else f"{gate_id} is WORKFLOW_VALIDATED only; SYNTHETIC evidence cannot authorize a state transition.",
        "decision": status,
        "next_action": "Advance only under the state-machine action authorized by this recorded Gate." if status == "GO" else "Retain this WORKFLOW_VALIDATED replay without state transition." if value.get("evidence_scope") == "SYNTHETIC" else "Retain the supplied review record and resolve or execute its stated disposition without creating a Freeze or Close artifact here.",
    }
