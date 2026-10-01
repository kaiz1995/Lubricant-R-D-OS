"""Deterministic process-window scale-up decision policy shared by builder and validator."""

from __future__ import annotations


# LAB -> PILOT -> PRODUCTION: a scale-up step must move strictly forward.
SCALE_ORDER = {"LAB": 0, "PILOT": 1, "PRODUCTION": 2}


def window_evidence_reference(window_id: str) -> str:
    """The reference a design_freeze MANUFACTURABILITY_ACCEPTABLE condition must cite."""
    return f"PROCESS-WINDOW:{window_id}"


def has_gap(container: dict) -> bool:
    evidence = container.get("evidence")
    return isinstance(evidence, list) and any(isinstance(item, dict) and item.get("status") == "GAP" for item in evidence)


def expected_decision_fields(process_id: str, window_id: str, ready: bool) -> dict[str, str]:
    return {
        "decision_question": f"Is process {process_id} window {window_id} fixed from the OPTIMIZED conclusion?",
        "hypothesis": f"{window_id} fixes the manufacturing window of {process_id} at the amplified batch scale, carrying the OPTIMIZED conclusion into a validated process window.",
        "uncertainty": "The fixed window rests on the supplied scale-up evidence only; it does not by itself establish capability, release approval, or product performance.",
        "decision_rule": "Fix the process window only when the DESIGN_SPACE_DEFINED process record and the OPTIMIZED conclusion share a project, the scale step advances to a later scale class, and evidence without GAP is supplied.",
        "result": f"{window_id} is {'fixed' if ready else 'not fixed'} for {process_id} from supplied input only.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Retain {window_id} as the fixed process window and cite it from the design freeze." if ready else "Retain the supplied evidence and resolve the recorded GAP before fixing a process window.",
    }
