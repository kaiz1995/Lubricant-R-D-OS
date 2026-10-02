"""Deterministic disposition wording for a Phase 3 review Gate."""

from __future__ import annotations

# WP-06 separation of concerns: this policy judges exactly one gate — the
# VERIFIED gate (evidence sufficiency for the review). The APPLIED gate
# (application & machine validation verdict) is a separate stage owned by the
# application-validation skill; no wording below decides or hints at an
# APPLIED advancement, and FREEZE is reachable only from APPLIED, never here.
GATED_STAGE = "VERIFIED"

# WP-08 signoff role mapping. The gate artifact can RECORD who technically
# reviewed it and who approved it, plus any recorded dissent. These fields are
# records only: NO code path in this skill (or anywhere in the domain) checks
# authority, identity, or permission — "签批只记录不鉴权" (plan §7 rule 2).
# The FREEZE preconditions (technical_reviewer present, no unresolved dissent)
# are adjudicated solely by scripts/validate_state_machine.py, never here.
SIGNOFF_FIELDS = ("technical_reviewer", "reviewed_at", "approver", "approved_at")
DISSENT_FIELD = "dissent"


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
        "hypothesis": f"{gate_id} records supplied review conditions without creating a Freeze, Close, or application-validation artifact.",
        "uncertainty": "This review records supplied conditions, gaps, risks, and disposition only; it does not create new experiment, model, optimization, application, Freeze, Close, or product-performance evidence.",
        "decision_rule": "GO requires no unsatisfied conditions, no evidence gaps, and no GAP evidence; PIVOT, KILL, and FREEZE require explicit reason and evidence; otherwise retain HOLD. This gate decides the VERIFIED stage only — the APPLIED stage is gated separately by application-validation.",
        "result": f"{gate_id} has deterministic gate disposition {status} from the supplied review conditions and evidence." if value.get("evidence_scope") != "SYNTHETIC" else f"{gate_id} is WORKFLOW_VALIDATED only; SYNTHETIC evidence cannot authorize a state transition.",
        "decision": status,
        "next_action": "Advance only under the state-machine action authorized by this recorded Gate." if status == "GO" else "Retain this WORKFLOW_VALIDATED replay without state transition." if value.get("evidence_scope") == "SYNTHETIC" else "Retain the supplied review record and resolve or execute its stated disposition without creating a Freeze or Close artifact here.",
    }
