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


# Defect 4 (2026-10-03): process / process-window artifacts were structurally
# unreachable from this gate, and evidence_scope came from the optimization
# artifact alone. A purely synthetic process window therefore never reached the
# SYNTHETIC -> HOLD branch. Two fixes:
#   1. aggregate_scope() takes the weakest scope across every submitted upstream
#      so a SYNTHETIC process window forces HOLD;
#   2. process_window_synthetic() additionally treats a validated=true window
#      declared SYNTHETIC as blocking, because "format valid" != "evidence
#      sufficient" for the downstream design_freeze MANUFACTURABILITY_ACCEPTABLE
#      citation.
SCOPE_RANK = {"SYNTHETIC": 0, "PHYSICAL": 1}


def aggregate_scope(scopes: "list[str | None]") -> str | None:
    """Return the weakest declared scope; None when no scope was supplied."""
    present = [value for value in scopes if isinstance(value, str) and value in SCOPE_RANK]
    if not present: return None
    return min(present, key=lambda value: SCOPE_RANK[value])


def process_window_synthetic(process_window: object) -> bool:
    """True when a process window is validated yet only SYNTHETIC-scoped."""
    if not isinstance(process_window, dict): return False
    if process_window.get("validated") is not True: return False
    scope = process_window.get("evidence_scope")
    if not isinstance(scope, str): return False
    return scope == "SYNTHETIC"


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
